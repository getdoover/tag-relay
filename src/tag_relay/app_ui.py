"""Dynamic UI builder for the Tag Relay processor.

Each mapping with ``ui.enabled = true`` contributes a variable (and optionally
a form-control) to the processor's UI. Elements bind to *mirror* tags written
onto the Tag Relay's own app_key during each relay — the destination is
authoritative, but the mirror gives the UI a stable local reference.
"""

from __future__ import annotations

from pydoover import ui
from pydoover.ui.declarative import UITagBinding

from .names import mirror_key_for, variable_name_for
from .validation import endpoints, partition_mappings


_GAUGE_WIDGET = {
    "linear": ui.Widget.linear,
    "radial": ui.Widget.radial,
}


def _tag_type_for_variable(variable_type: str) -> str:
    if variable_type == "boolean":
        return "boolean"
    if variable_type == "text":
        return "string"
    return "number"


class TagRelayUI(ui.UI):
    async def setup(self):
        # Skip invalid mappings silently — Application.setup logs the reject.
        valid, _ = partition_mappings(self.config.mappings.elements, self.app_key)
        for mapping in valid:
            ui_cfg = mapping.ui
            if not ui_cfg.enabled.value:
                continue

            _src, (dest_app, dest_tag) = endpoints(mapping, self.app_key)

            variable_type = ui_cfg.variable_type.value or "numeric"
            display_name = ui_cfg.display_name.value or f"{dest_app}.{dest_tag}"
            var_name = variable_name_for(dest_app, dest_tag)

            binding = UITagBinding(
                tag_name=mirror_key_for(dest_app, dest_tag),
                tag_type=_tag_type_for_variable(variable_type),
                app_nested=True,
            )

            element = self._build_variable(
                variable_type, display_name, var_name, binding, ui_cfg
            )
            if element is not None:
                self.add_element(element)

    def _build_variable(self, variable_type, display_name, name, binding, ui_cfg):
        if variable_type == "boolean":
            return ui.BooleanVariable(
                display_name,
                value=binding,
                name=name,
            )
        if variable_type == "text":
            return ui.TextVariable(
                display_name,
                value=binding,
                name=name,
            )
        # numeric (default)
        kwargs = {"name": name, "value": binding}
        if ui_cfg.precision.value is not None:
            kwargs["precision"] = ui_cfg.precision.value
        ranges = _build_ranges(ui_cfg.ranges)
        if ranges:
            kwargs["ranges"] = ranges
        gauge = _GAUGE_WIDGET.get(ui_cfg.gauge_type.value)
        if gauge is not None:
            kwargs["form"] = gauge
        return ui.NumericVariable(display_name, **kwargs)


def _build_ranges(ranges_array):
    result = []
    for row in ranges_array.elements:
        label = row.label.value
        min_v = row.min.value
        max_v = row.max.value
        colour = row.colour.value or "grey"
        if min_v is None or max_v is None:
            continue
        result.append(ui.Range(label=label, min_val=min_v, max_val=max_v, colour=colour))
    return result
