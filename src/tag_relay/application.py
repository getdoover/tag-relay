import logging
from typing import Any

from pydoover.models import AggregateUpdateEvent, MessageCreateEvent, ScheduleEvent
from pydoover.processor import Application

from .app_config import TagRelayConfig
from .app_ui import TagRelayUI
from .names import mirror_key_for
from .transforms import TransformCache, TransformError
from .validation import (
    describe_cycle,
    describe_mapping,
    endpoints,
    find_cycles,
    partition_mappings,
)

log = logging.getLogger(__name__)


class TagRelayApplication(Application):
    config_cls = TagRelayConfig
    ui_cls = TagRelayUI

    config: TagRelayConfig

    async def setup(self):
        self._transforms = TransformCache()
        self._valid_mappings = self._validate_mappings()
        # All relay writes go here, buffered until close(). Structure:
        # {app_key: {tag_name: value}}. We don't use tag_manager.set_tag
        # because:
        #   1. Its commit_tags doesn't pass allow_invoking_channel=True,
        #      tripping pydoover's anti-recursion guard on cross-app writes.
        #   2. It always wants to do BOTH aggregate update + log message,
        #      with no per-call control. We need to mirror the trigger
        #      event type (aggregate-only vs message-only) exactly.
        self._pending_updates: dict[str, dict[str, Any]] = {}
        # Set by each entry handler. One of: "aggregate", "message", "both".
        # close() decides what to publish based on this.
        self._publish_mode: str = "aggregate"

    async def close(self):
        if not self._pending_updates:
            return
        # The anti-recursion guard only fires when the publish channel
        # equals the invoking channel; for schedule triggers there is no
        # invoking channel, and even on tag_values triggers the guard
        # passes when data is scoped to self. Pass the override only when
        # the buffer actually spans other apps' subtrees, to avoid the
        # guard's warning log on every same-app relay.
        spans_other_apps = any(k != self.app_key for k in self._pending_updates)

        if self._publish_mode in ("aggregate", "both"):
            await self.api.update_channel_aggregate(
                "tag_values",
                self._pending_updates,
                allow_invoking_channel=spans_other_apps,
            )
        if self._publish_mode in ("message", "both"):
            await self.api.create_message(
                "tag_values",
                self._pending_updates,
                allow_invoking_channel=spans_other_apps,
            )
        self._pending_updates = {}

    def _validate_mappings(self):
        valid, rejected = partition_mappings(
            self.config.mappings.elements, self.app_key
        )
        for mapping in rejected:
            src, dst = endpoints(mapping, self.app_key)
            if src == dst:
                log.error(
                    "Rejecting identity-loop mapping %s — would infinite-loop if relayed.",
                    describe_mapping(mapping, self.app_key),
                )
            else:
                log.error(
                    "Rejecting mapping with missing source/destination fields: %s",
                    describe_mapping(mapping, self.app_key),
                )

        for cycle in find_cycles(valid, self.app_key):
            log.warning(
                "Tag-relay mapping cycle detected (will still run — may cause "
                "repeated writes): %s",
                describe_cycle(cycle),
            )

        return valid

    async def pre_hook_filter(self, event):
        # tag_values aggregate updates and message creates both trigger us;
        # we mirror the trigger type into the publish path. Anything else
        # (ui_cmds, dv-rpc, channels we don't care about) is noise.
        if isinstance(event, AggregateUpdateEvent):
            return event.channel.name == "tag_values"
        if isinstance(event, MessageCreateEvent):
            return event.channel.name == "tag_values"
        # schedule events, manual invokes — always pass
        return True

    async def post_setup_filter(self, event):
        diff = _diff_from_event(event)
        if diff is None:
            # Schedule / manual invoke — always pass; no source diff to filter on.
            return True
        for mapping in self._valid_mappings:
            if mapping.trigger_mode.value != "event":
                continue
            if _tag_in_diff(diff, mapping.source_app_key.value, mapping.source_tag_name.value):
                return True
        return False

    async def on_aggregate_update(self, event: AggregateUpdateEvent):
        self._publish_mode = "aggregate"
        await self._run_event_mappings(event.request_data.data or {})

    async def on_message_create(self, event: MessageCreateEvent):
        self._publish_mode = "message"
        await self._run_event_mappings(event.message.data or {})

    async def on_schedule(self, event: ScheduleEvent):
        # Scheduled relays publish both an aggregate update and a log
        # message — they're the canonical "snapshot the world right now"
        # path, so we want the dest's current state to update AND a log
        # entry for the graph.
        self._publish_mode = "both"
        for mapping in self._valid_mappings:
            if mapping.trigger_mode.value == "schedule":
                await self._relay(mapping)

    async def _run_event_mappings(self, diff: dict):
        for mapping in self._valid_mappings:
            if mapping.trigger_mode.value != "event":
                continue
            if not _tag_in_diff(diff, mapping.source_app_key.value, mapping.source_tag_name.value):
                continue
            await self._relay(mapping)

    async def _relay(self, mapping):
        (src_app, src_tag), (dest_app, dest_tag) = endpoints(mapping, self.app_key)
        source = self.tag_manager.get_tag(src_tag, app_key=src_app)
        if source is None:
            log.debug("Source %s.%s has no value; skipping", src_app, src_tag)
            return

        try:
            value = self._transforms.evaluate(mapping.transform_cel.value, source)
        except TransformError as e:
            log.error("Skipping mapping due to transform error: %s", e)
            return

        log.info(
            "Relay %s.%s -> %s.%s : %r -> %r",
            src_app, src_tag, dest_app, dest_tag, source, value,
        )
        # Always buffer the destination write.
        self._pending_updates.setdefault(dest_app, {})[dest_tag] = value
        # Mirror onto self only when both:
        #   * destination is on another app (UI can't bind across apps), AND
        #   * this mapping's UI is enabled (otherwise nothing reads the mirror).
        if dest_app != self.app_key and mapping.ui.enabled.value:
            self._pending_updates.setdefault(self.app_key, {})[
                mirror_key_for(dest_app, dest_tag)
            ] = value


def _tag_in_diff(diff: dict, app_key: str, tag_name: str) -> bool:
    if not app_key or not tag_name:
        return False
    app_bucket = diff.get(app_key)
    if not isinstance(app_bucket, dict):
        return False
    return tag_name in app_bucket


def _diff_from_event(event) -> dict | None:
    """Return the source-side diff dict from a tag_values event, or None
    if the event is not a tag_values trigger (e.g. a schedule fire).
    """
    if isinstance(event, AggregateUpdateEvent) and event.channel.name == "tag_values":
        return event.request_data.data or {}
    if isinstance(event, MessageCreateEvent) and event.channel.name == "tag_values":
        return event.message.data or {}
    return None
