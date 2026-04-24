"""Dynamic UI builder for the Tag Relay processor.

Each mapping with ``ui.enabled = true`` contributes a variable (and optionally
a form-control) to the processor's UI. Elements bind to *mirror* tags written
onto the Tag Relay's own app_key during each relay — the destination is
authoritative, but the mirror gives the UI a stable local reference.
"""

from __future__ import annotations

from pydoover import ui
from pydoover.ui.declarative import UITagBinding

from .names import mirror_key_for, variable_name_for, writeback_name_for
from .validation import partition_mappings


def _tag_type_for_variable(variable_type: str) -> str:
    if variable_type == "boolean":
        return "boolean"
    if variable_type == "text":
        return "string"
    return "number"


class TagRelayUI(ui.UI):
    async def setup(self):
        # Skip invalid mappings silently — Application.setup logs the reject.
        valid, _ = partition_mappings(self.config.mappings.elements)
        for mapping in valid:
            ui_cfg = mapping.ui
            if not ui_cfg.enabled.value:
                continue

            dest_app = mapping.dest_app_key.value
            dest_tag = mapping.dest_tag_name.value

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

            control = self._build_form_control(
                ui_cfg.form_control.value,
                display_name,
                dest_app,
                dest_tag,
            )
            if control is not None:
                self.add_element(control)

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
        return ui.NumericVariable(display_name, **kwargs)

    def _build_form_control(self, form_control, display_name, dest_app, dest_tag):
        if not form_control or form_control == "none":
            return None

        name = writeback_name_for(dest_app, dest_tag)
        label = f"Set {display_name}"

        if form_control == "float_input":
            return ui.FloatInput(label, name=name)
        if form_control == "text_input":
            return ui.TextInput(label, name=name)
        if form_control == "boolean":
            return ui.BooleanParameter(name=name, display_name=label)
        return None


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
