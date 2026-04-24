"""Smoke tests for the tag-relay processor."""

import pytest

from tag_relay import handler
from tag_relay.app_config import TagRelayConfig, MappingObject, UIConfig
from tag_relay.application import TagRelayApplication, _tag_in_diff
from tag_relay.names import (
    mirror_key_for,
    variable_name_for,
    writeback_name_for,
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
    writeback = writeback_name_for(dest_app, dest_tag)
    variable = variable_name_for(dest_app, dest_tag)
    # Same hash slug across all three helpers for a given destination.
    assert mirror.split("_", 1)[1] == writeback.split("_", 1)[1]
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


def test_transform_type_mismatch_surfaces_as_transform_error():
    # CEL is strict about int * float — one of the documented gotchas.
    cache = TransformCache()
    with pytest.raises(TransformError):
        cache.evaluate("x * 1.8", 25)
    # Using double(x) resolves it.
    assert cache.evaluate("double(x) * 1.8", 25) == pytest.approx(45.0)
