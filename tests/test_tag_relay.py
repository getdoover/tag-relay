"""Smoke tests for the tag-relay processor."""

import pytest

from tag_relay import handler
from tag_relay.app_config import TagRelayConfig, MappingObject, UIConfig
from tag_relay.application import TagRelayApplication, _tag_in_diff
from tag_relay.names import (
    mirror_key_for,
    variable_name_for,
)
from tag_relay.transforms import TransformCache, TransformError


def test_handler_is_callable():
    assert callable(handler)


def test_config_schema_exports():
    schema = TagRelayConfig.to_schema()
    props = schema["properties"]
    assert "dv_proc_subscriptions" in props
    assert "mappings" in props
    # mapping element carries the fields we expect
    mapping_props = props["mappings"]["items"]["properties"]
    for key in (
        "source_app",
        "source_tag",
        "destination_app",
        "destination_tag",
        "transform_cel",
        "trigger",
        "ui",
    ):
        assert key in mapping_props


def test_application_wires_the_right_cls():
    assert TagRelayApplication.config_cls is TagRelayConfig
    # UI class is dynamic (setup override), so is_static is False
    ui = TagRelayApplication.ui_cls(None, None, None)
    assert not ui.is_static


def test_config_survives_deployment_config_injection():
    """Regression: `_inject_deployment_config` must keep `mappings` as an
    Array so `.elements` is accessible. Previously a `clear_elements()` call
    in the handler wiped the schema's `_element_map`, causing every field
    (including `mappings`) to be replaced with a plain `ConfigElement`.
    """
    cfg = TagRelayConfig()
    cfg._inject_deployment_config(
        {
            "dv_proc_subscriptions": ["tag_values"],
            "dv_proc_schedules": None,
            "mappings": [
                {
                    "source_app": "src_app",
                    "source_tag": "x",
                    "destination_app": "dst_app",
                    "destination_tag": "y",
                    "trigger": "event",
                    "ui": {},
                }
            ],
        }
    )
    assert hasattr(cfg.mappings, "elements"), (
        f"expected Array, got {type(cfg.mappings).__name__}"
    )
    assert len(cfg.mappings.elements) == 1
    mapping = cfg.mappings.elements[0]
    assert mapping.source_app_key.value == "src_app"
    assert mapping.dest_app_key.value == "dst_app"


# --- names --------------------------------------------------------------


def test_names_are_deterministic_and_distinct():
    a = mirror_key_for("app-one", "tag_a")
    b = mirror_key_for("app-one", "tag_a")
    c = mirror_key_for("app-one", "tag_b")
    d = mirror_key_for("app-two", "tag_a")
    assert a == b
    assert a != c
    assert a != d


def test_related_names_share_slug():
    dest_app = "abc-123"
    dest_tag = "my_tag"
    mirror = mirror_key_for(dest_app, dest_tag)
    variable = variable_name_for(dest_app, dest_tag)
    # Same hash slug across helpers for a given destination.
    assert mirror.split("_", 1)[1] == variable.split("_", 1)[1]


# --- diff helper --------------------------------------------------------


def test_tag_in_diff_matches_when_both_present():
    diff = {"source_app_1": {"my_tag": 42}}
    assert _tag_in_diff(diff, "source_app_1", "my_tag") is True


def test_tag_in_diff_rejects_missing_fields():
    diff = {"source_app_1": {"my_tag": 42}}
    assert _tag_in_diff(diff, "other_app", "my_tag") is False
    assert _tag_in_diff(diff, "source_app_1", "other_tag") is False
    assert _tag_in_diff({}, "source_app_1", "my_tag") is False
    assert _tag_in_diff(diff, "", "my_tag") is False


# --- transforms ---------------------------------------------------------


def test_transform_identity_passthrough():
    cache = TransformCache()
    assert cache.evaluate(None, 42) == 42
    assert cache.evaluate("", 42) == 42


def test_transform_basic_arithmetic():
    cache = TransformCache()
    assert cache.evaluate("x + 1", 10) == 11
    assert cache.evaluate("x * 2", 3) == 6


def test_transform_caches_compiled_programs():
    cache = TransformCache()
    cache.evaluate("x + 1", 1)
    cache.evaluate("x + 1", 2)
    assert list(cache._programs.keys()) == ["x + 1"]


def test_transform_compile_error_raises():
    cache = TransformCache()
    with pytest.raises(TransformError):
        cache.evaluate("this is not valid CEL ++", 1)


def test_transform_auto_coerces_int_when_expression_has_float_literal():
    # CEL is strict about int*float; we normalise by promoting bare int
    # literals to floats and casting x to float when the expression mentions
    # a float literal. The user's original "linear transform" case:
    cache = TransformCache()
    assert cache.evaluate("x * 0.002442 + 0", 7740) == pytest.approx(
        7740 * 0.002442
    )
    # Bias literal also promoted to double
    assert cache.evaluate("x * 0.5 + 10", 2) == pytest.approx(11.0)
    # Celsius -> Fahrenheit, int input, mixed literals
    assert cache.evaluate("x * 1.8 + 32", 25) == pytest.approx(77.0)


def test_transform_pure_int_expressions_keep_int_semantics():
    # No float literal -> no coercion. Stays int arithmetic end-to-end.
    cache = TransformCache()
    assert cache.evaluate("x * 1000", 7) == 7000
    result = cache.evaluate("x + 1", 10)
    assert result == 11 and type(result) is int


def test_transform_integer_literals_inside_functions_still_coerced():
    # Bare integer literal inside a float expression -> promoted to double.
    cache = TransformCache()
    assert cache.evaluate("(x + 100) * 0.5", 4) == pytest.approx(52.0)
