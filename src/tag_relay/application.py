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
        # Cross-app destination writes are buffered here and flushed in
        # close(). We can't use tag_manager.set_tag(app_key=…) because its
        # commit_tags path doesn't pass `allow_invoking_channel=True`, which
        # pydoover's anti-recursion guard requires for tag_values publishes
        # spanning multiple app subtrees during a tag_values-triggered run.
        self._pending_external_updates: dict[str, dict[str, Any]] = {}

    async def close(self):
        if not self._pending_external_updates:
            return
        await self.api.update_channel_aggregate(
            "tag_values",
            self._pending_external_updates,
            allow_invoking_channel=True,
        )
        # Audit log — mirrors what tag_manager.commit_tags does for self-writes.
        await self.api.create_message(
            "tag_values",
            self._pending_external_updates,
            allow_invoking_channel=True,
        )
        self._pending_external_updates = {}

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
        if isinstance(event, AggregateUpdateEvent):
            return event.channel.name == "tag_values"
        if isinstance(event, MessageCreateEvent):
            # No UI write-back in tag-relay — every message-create is noise.
            return False
        # schedule events, manual invokes — always pass
        return True

    async def post_setup_filter(self, event):
        if isinstance(event, AggregateUpdateEvent) and event.channel.name == "tag_values":
            diff = event.request_data.data or {}
            for mapping in self._valid_mappings:
                if mapping.trigger_mode.value != "event":
                    continue
                if _tag_in_diff(diff, mapping.source_app_key.value, mapping.source_tag_name.value):
                    return True
            return False
        return True

    async def on_aggregate_update(self, event: AggregateUpdateEvent):
        diff = event.request_data.data or {}
        for mapping in self._valid_mappings:
            if mapping.trigger_mode.value != "event":
                continue
            if not _tag_in_diff(diff, mapping.source_app_key.value, mapping.source_tag_name.value):
                continue
            await self._relay(mapping)

    async def on_schedule(self, event: ScheduleEvent):
        for mapping in self._valid_mappings:
            if mapping.trigger_mode.value == "schedule":
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
        if dest_app == self.app_key:
            # Writing into our own subtree — the tag_manager's normal flush
            # doesn't trip the anti-recursion guard in this case.
            await self.tag_manager.set_tag(dest_tag, value)
        else:
            self._pending_external_updates.setdefault(dest_app, {})[dest_tag] = value
        # Mirror to self for the Tag Relay UI. Cheap — same aggregate flush.
        await self.tag_manager.set_tag(mirror_key_for(dest_app, dest_tag), value)


def _tag_in_diff(diff: dict, app_key: str, tag_name: str) -> bool:
    if not app_key or not tag_name:
        return False
    app_bucket = diff.get(app_key)
    if not isinstance(app_bucket, dict):
        return False
    return tag_name in app_bucket
