# Tag Relay

<img src="https://doover.com/wp-content/uploads/Doover-Logo-Landscape-Navy-padded-small.png" alt="App Icon" style="max-width: 300px;">

**A Doover processor that relays tag values between apps on a device — with
optional CEL transforms and per-mapping UI.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

[Overview](#overview) · [Configuration](#configuration) · [UI](#ui) ·
[Triggers](#triggers) · [Transforms](#transforms) · [Developer](DEVELOPMENT.md)

<br/>

## Overview

Tag Relay is a cloud processor (`type: PRO`). One instance, configured with a
list of *mappings*. Each mapping describes one flow:

```
<source_app>.<source_tag>  ──[optional CEL transform]──▶  <dest_app>.<dest_tag>
```

Everything is scoped to a single agent: the processor reads tags from one app
on the agent and writes them to another app on the same agent. (Cross-agent
relay is on the roadmap — v1 is same-agent only.)

By default, every mapping fires on source tag change. Mappings can opt into
scheduled relays instead (via the top-level schedule and `trigger=schedule`).

<br/>

## Configuration

| Field | Purpose |
|-------|---------|
| **Subscriptions** | Pre-set to `tag_values` and `ui_cmds`. Don't usually change. |
| **Schedule** | Cron/rate schedule. Only needed if any mapping uses `trigger=schedule`. |
| **Mappings** | Array — one entry per relay. |

Each **Mapping**:

| Field | Purpose |
|-------|---------|
| **Source App** | Installed app whose tag is being relayed. |
| **Source Tag** | Tag name on the source app. |
| **Destination App** | Installed app to write into. Leave blank to write into the Tag Relay app itself. |
| **Destination Tag** | Tag name to write on the destination. |
| **Transform (CEL)** | Optional. Expression applied to the source value (bound as `x`). |
| **Trigger** | `event` (default) or `schedule`. |
| **UI** | Optional — surface the relayed value as a variable on the Tag Relay UI. |

<br/>

## Transforms

Transforms are [CEL (Common Expression Language)](https://github.com/google/cel-spec)
expressions. The source value is bound as `x`; the expression result is written
to the destination.

Examples:

```
x                          # identity (equivalent to leaving transform empty)
x * 0.5 + 10               # linear transform (y = m*x + b) — scale by 0.5, offset +10
x * 1000                   # unit scale — stays in int space
x * 1.8 + 32               # Celsius → Fahrenheit
x > 10                     # threshold to boolean
int(x / 100)               # truncating division
```

**Int/float coercion.** CEL itself rejects mixed int/double arithmetic
(`Int(25) * Float(1.8)` is an error). The relay smooths this over: if the
expression contains **any** numeric literal with a decimal point (e.g.
`0.5`, `1.8`, `0.002442`), every integer literal in the expression and the
input `x` are auto-promoted to double before evaluation. Expressions with
no decimal literals — `x * 1000`, `x + 1` — stay in integer space and
preserve int semantics. You shouldn't need `double(x)` in typical linear
transforms.

**Gotcha:** CEL is strict about mixed int/float arithmetic. If `x` arrives as
an int and the expression has a float literal, cast with `double(x)` first.
Transform errors are logged and the mapping is skipped — other mappings in the
same run continue.

<br/>

## Triggers

- **`event`** (default) — the processor subscribes to the `tag_values` channel.
  When the source tag changes, the mapping runs immediately.
- **`schedule`** — the mapping is skipped on change events and runs only when
  the top-level **Schedule** fires. Useful for throttling noisy sources or
  periodic snapshot relays.

<br/>

## UI

Each mapping can opt in to a read-only variable on the Tag Relay app card:

- Numeric, boolean, or text variable types
- Numeric variables support decimal precision, units, coloured ranges, and an
  optional `linear` or `radial` gauge rendering

The UI is rendered on the Tag Relay's own app card, not injected into the
destination app's card. It references a mirror tag that the processor writes
to its own app subtree on each relay.

<br/>

## Commands

```bash
uv run pytest tests -v       # Run tests
uv run export-config         # Rewrite config_schema in doover_config.json
doover app publish --profile dv2   # Publish after schema changes
```

<br/>

## Need Help?

- Email: support@doover.com
- [Doover Documentation](https://docs.doover.com)
- [Developer Documentation](DEVELOPMENT.md)

<br/>

## License

Apache License 2.0 — see [LICENSE](LICENSE).
