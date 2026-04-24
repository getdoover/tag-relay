# Tag Relay

A Doover **cloud processor** (`type: PRO`) that relays tag values between apps
on a single agent. Each mapping reads a source tag, optionally applies a CEL
transform, and writes the result to a destination tag. Optional per-mapping
UI surfaces the relayed value on the Tag Relay's own app card.

Cross-agent relay is on the roadmap but not yet implemented — v1 is
same-agent only.

## Commands

```bash
uv run pytest tests -v       # Run smoke tests
uv run export-config         # Rewrite config_schema in doover_config.json
```

There is no `export-ui` — the UI is built dynamically from config at runtime.

## Project structure

```
src/tag_relay/
  __init__.py       # Lambda handler entry (src.tag_relay.handler)
  app_config.py     # TagRelayConfig + MappingObject + UIConfig + RangeObject
  application.py    # TagRelayApplication — filters, on_aggregate_update, on_schedule, writeback handler
  app_ui.py         # TagRelayUI — dynamic UI builder (overrides UI.setup)
  names.py          # Deterministic mirror/writeback/variable name helpers
  transforms.py     # TransformCache — compile-once CEL evaluation
tests/
```

No Dockerfile: processors are Lambda-zipped, not containerised.

## pydoover 1.0 processor patterns

- `pydoover.processor.Application` (via `pydoover.processor.run_app`) — not
  `pydoover.docker.Application`. The Lambda handler calls `run_app(app, event,
  context)`.
- Class-level declarative config: subclass `config.Schema`, and for nested
  objects subclass `config.Object` (e.g. `MappingObject`, `UIConfig`).
- Dynamic UI: override `ui.UI.setup` and call `self.add_element(...)`. This
  sets `is_static = False`, which makes the processor republish the UI
  schema on every invocation.
- Cross-app tag access: `self.tag_manager.get_tag(tag_name, app_key=...)` and
  `self.tag_manager.set_tag(tag_name, value, app_key=...)`.
- Loop guard: the processor base rejects `tag_values` events whose diff
  contains the processor's own `app_key`, so mirror writes on self don't
  re-trigger the relay.

## UI surface model (why mirror tags exist)

Tags live on the `tag_values` channel aggregate, keyed by `app_key`:
`{app_key: {tag_name: value}}`. UI `currentValue` expressions use
`$tag.app().<name>` — which resolves against the publishing app's own subtree.
There's no supported expression syntax for `$tag.app(<other_key>).<name>`.

So Tag Relay writes *two* tag values per relay:
1. **Authoritative** — to the destination app_key (this is the actual relay).
2. **Mirror** — to the Tag Relay's own app_key under a deterministic
   `mirror_<slug>` key, used solely as the UI binding target.

`names.py` is the single source of truth for how slugs are derived
(`sha1(f"{dest_app}/{dest_tag}")[:8]`). Mirror tag keys and UI variable
names share that slug.

## Filters

- `pre_hook_filter` — rejects events that aren't `tag_values` aggregate
  updates, `ui_cmds`/`dv-rpc` message creates, or schedule/manual events.
- `post_setup_filter` — for `tag_values` events, additionally requires that at
  least one event-mode mapping's source tag appears in the diff. This avoids
  running the body when the event is unrelated to any configured mapping.

## Gotchas

- **CEL int/float strictness**: `x * 1.8` fails when `x` is int. Use
  `double(x) * 1.8`. Transform errors surface as `TransformError` and are
  logged; the mapping is skipped, others continue.
- Top-level `dv_proc_schedules` is the only schedule the platform honours —
  there is no per-mapping cron. Mappings mark themselves `trigger=schedule`
  to opt in to the shared schedule; otherwise they fire on event.
