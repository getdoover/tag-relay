from pathlib import Path

from pydoover import config
from pydoover.processor import ManySubscriptionConfig, ScheduleConfig


class RangeObject(config.Object):
    label = config.String("Label")
    min = config.Number("Min")
    max = config.Number("Max")
    colour = config.Enum(
        "Colour",
        choices=["red", "yellow", "green", "blue", "grey", "black"],
        default="grey",
    )


class UIConfig(config.Object):
    enabled = config.Boolean(
        "Show on Tag Relay UI",
        description="If on, surface the relayed value as a variable on the Tag Relay app's UI.",
        default=False,
    )
    display_name = config.String(
        "Display Name",
        description="Label shown on the UI.",
        default=None,
    )
    variable_type = config.Enum(
        "Variable Type",
        choices=["numeric", "boolean", "text"],
        default="numeric",
    )
    units = config.String(
        "Units",
        description="Units suffix (numeric only).",
        default=None,
    )
    precision = config.Integer(
        "Decimal Precision",
        description="Number of decimal places to show (numeric only).",
        default=None,
        minimum=0,
    )
    ranges = config.Array(
        "Ranges",
        element=RangeObject("Range"),
        description="Optional coloured ranges (numeric only).",
    )
    form_control = config.Enum(
        "Form Control",
        choices=["none", "float_input", "text_input", "boolean"],
        description=(
            "Optional write-back control. When set, user input is written "
            "directly to the destination tag (bypassing the CEL transform)."
        ),
        default="none",
    )


class MappingObject(config.Object):
    source_app_key = config.ApplicationInstall(
        "Source App",
        description="App on this agent whose tag is being relayed.",
    )
    source_tag_name = config.String(
        "Source Tag",
        description="Name of the tag on the source app.",
    )
    dest_app_key = config.ApplicationInstall(
        "Destination App",
        description="App on this agent to write the relayed value into.",
    )
    dest_tag_name = config.String(
        "Destination Tag",
        description="Name of the tag to write on the destination app.",
    )
    transform_cel = config.String(
        "Transform (CEL)",
        description=(
            "Optional Common Expression Language expression applied to the "
            "source value. The input is bound as `x`. Examples: "
            "`x * 1.8 + 32`, `double(x) / 1000.0`, `x > 10`."
        ),
        default=None,
    )
    trigger_mode = config.Enum(
        "Trigger",
        description=(
            "`event` (default): relay whenever the source tag changes. "
            "`schedule`: relay only on the processor's scheduled runs — "
            "requires the top-level schedule to be configured."
        ),
        choices=["event", "schedule"],
        default="event",
    )
    ui = UIConfig("UI")


class TagRelayConfig(config.Schema):
    subscriptions = ManySubscriptionConfig(default=["tag_values", "ui_cmds"])
    schedule = ScheduleConfig(
        description=(
            "Optional cron/rate schedule. Only needed if at least one mapping "
            "uses trigger=schedule. Leave disabled otherwise."
        ),
        default=None,
    )
    mappings = config.Array(
        "Mappings",
        element=MappingObject("Mapping"),
        description="One entry per source-to-destination tag relay.",
        default=[],
    )


def export():
    TagRelayConfig.export(
        Path(__file__).parents[2] / "doover_config.json", "tag_relay"
    )


if __name__ == "__main__":
    export()
