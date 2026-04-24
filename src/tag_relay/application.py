import logging
import re

from pydoover import ui
from pydoover.models import AggregateUpdateEvent, MessageCreateEvent, ScheduleEvent
from pydoover.processor import Application

from .app_config import TagRelayConfig
from .app_ui import TagRelayUI
from .names import mirror_key_for, writeback_name_for
from .transforms import TransformCache, TransformError
from .validation import (
    describe_cycle,
    describe_mapping,
    endpoints,
    find_cycles,
    partition_mappings,
)

log = logging.getLogger(__name__)


_WRITEBACK_RE = re.compile(r"wb_[a-f0-9]+")


class TagRelayApplication(Application):
    config_cls = TagRelayConfig
    ui_cls = TagRelayUI

    config: TagRelayConfig

    async def setup(self):
        self._transforms = TransformCache()
        self._valid_mappings = self._validate_mappings()

    def _validate_mappings(self):
        valid, rejected = partition_mappings(self.config.mappings.elements)
        for mapping in rejected:
            src, dst = endpoints(mapping)
            if src == dst:
                log.error(
                    "Rejecting identity-loop mapping %s — would infinite-loop if relayed.",
                    describe_mapping(mapping),
                )
            else:
                log.error(
                    "Rejecting mapping with missing source/destination fields: %s",
                    describe_mapping(mapping),
                )

        for cycle in find_cycles(valid):
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
            return event.channel.name in ("ui_cmds", "dv-rpc")
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

    @ui.handler(_WRITEBACK_RE)
    async def on_writeback(self, ctx, value):
        if value is None:
            return
        mapping = self._mapping_for_writeback(ctx.method)
        if mapping is None:
            log.warning("Writeback %s has no matching mapping — stale cmd?", ctx.method)
            return

        dest_app = mapping.dest_app_key.value
        dest_tag = mapping.dest_tag_name.value
        log.info("Writeback %s -> %s.%s = %r", ctx.method, dest_app, dest_tag, value)
        await self.tag_manager.set_tag(dest_tag, value, app_key=dest_app)
        # Mirror locally so the UI reflects the new value before the next
        # source-driven relay overwrites it.
        await self.tag_manager.set_tag(mirror_key_for(dest_app, dest_tag), value)

    def _mapping_for_writeback(self, method: str):
        for mapping in self._valid_mappings:
            if writeback_name_for(
                mapping.dest_app_key.value, mapping.dest_tag_name.value
            ) == method:
                return mapping
        return None

    async def _relay(self, mapping):
        source = self.tag_manager.get_tag(
            mapping.source_tag_name.value,
            app_key=mapping.source_app_key.value,
        )
        if source is None:
            log.debug(
                "Source %s.%s has no value; skipping",
                mapping.source_app_key.value,
                mapping.source_tag_name.value,
            )
            return

        try:
            value = self._transforms.evaluate(mapping.transform_cel.value, source)
        except TransformError as e:
            log.error("Skipping mapping due to transform error: %s", e)
            return

        dest_app = mapping.dest_app_key.value
        dest_tag = mapping.dest_tag_name.value
        log.info(
            "Relay %s.%s -> %s.%s : %r -> %r",
            mapping.source_app_key.value,
            mapping.source_tag_name.value,
            dest_app,
            dest_tag,
            source,
            value,
        )
        await self.tag_manager.set_tag(dest_tag, value, app_key=dest_app)
        # Mirror to self for the Tag Relay UI. Cheap — same aggregate flush.
        await self.tag_manager.set_tag(mirror_key_for(dest_app, dest_tag), value)


def _tag_in_diff(diff: dict, app_key: str, tag_name: str) -> bool:
    if not app_key or not tag_name:
        return False
    app_bucket = diff.get(app_key)
    if not isinstance(app_bucket, dict):
        return False
    return tag_name in app_bucket
