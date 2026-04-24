"""Tests for mapping validation (identity-loop filtering and cycle detection)."""

from types import SimpleNamespace

from tag_relay.validation import (
    describe_cycle,
    describe_mapping,
    endpoints,
    find_cycles,
    partition_mappings,
)


SELF_KEY = "tag_relay_self"


def _mapping(source_app, source_tag, dest_app, dest_tag):
    """Duck-typed mapping matching pydoover's Object .value accessor."""
    return SimpleNamespace(
        source_app_key=SimpleNamespace(value=source_app),
        source_tag_name=SimpleNamespace(value=source_tag),
        dest_app_key=SimpleNamespace(value=dest_app),
        dest_tag_name=SimpleNamespace(value=dest_tag),
    )


# --- partition_mappings -------------------------------------------------


def test_partition_passes_through_valid_mappings():
    mappings = [
        _mapping("app_a", "x", "app_b", "y"),
        _mapping("app_b", "y", "app_c", "z"),
    ]
    valid, rejected = partition_mappings(mappings, SELF_KEY)
    assert valid == mappings
    assert rejected == []


def test_partition_rejects_identity_loop():
    same_tag = _mapping("app_a", "x", "app_a", "x")
    other = _mapping("app_a", "x", "app_b", "y")
    valid, rejected = partition_mappings([same_tag, other], SELF_KEY)
    assert valid == [other]
    assert rejected == [same_tag]


def test_partition_rejects_missing_required_fields():
    missing_source_app = _mapping("", "x", "app_b", "y")
    missing_source_tag = _mapping("app_a", "", "app_b", "y")
    missing_dest_tag = _mapping("app_a", "x", "app_b", "")
    none_source_app = _mapping(None, "x", "app_b", "y")
    all_missing = [
        missing_source_app,
        missing_source_tag,
        missing_dest_tag,
        none_source_app,
    ]
    good = _mapping("app_a", "x", "app_b", "y")

    valid, rejected = partition_mappings(all_missing + [good], SELF_KEY)
    assert valid == [good]
    assert rejected == all_missing


def test_blank_dest_app_coalesces_to_self():
    # Blank dest_app means "write to the Tag Relay itself".
    m = _mapping("app_a", "x", "", "y")
    valid, rejected = partition_mappings([m], SELF_KEY)
    assert valid == [m]
    assert rejected == []
    _src, dst = endpoints(m, SELF_KEY)
    assert dst == (SELF_KEY, "y")


def test_blank_dest_app_identity_loop_is_rejected():
    # Source is on the Tag Relay itself; dest_app blank → also the Tag Relay.
    # Same tag name on both sides → identity loop.
    m = _mapping(SELF_KEY, "x", "", "x")
    valid, rejected = partition_mappings([m], SELF_KEY)
    assert valid == []
    assert rejected == [m]


def test_identity_loop_allowed_when_app_same_but_tag_differs():
    # Same app, different tag — legitimate transform-in-place, not a loop.
    inside_same_app = _mapping("app_a", "raw", "app_a", "cooked")
    valid, rejected = partition_mappings([inside_same_app], SELF_KEY)
    assert valid == [inside_same_app]
    assert rejected == []


# --- find_cycles --------------------------------------------------------


def test_no_cycles_in_linear_chain():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "c", "z"),
    ]
    assert find_cycles(mappings, SELF_KEY) == []


def test_detects_two_node_cycle():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "a", "x"),
    ]
    cycles = find_cycles(mappings, SELF_KEY)
    assert len(cycles) == 1
    rendered = describe_cycle(cycles[0])
    assert rendered in ("a.x -> b.y -> a.x", "b.y -> a.x -> b.y")


def test_detects_three_node_cycle():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "c", "z"),
        _mapping("c", "z", "a", "x"),
    ]
    cycles = find_cycles(mappings, SELF_KEY)
    assert len(cycles) == 1
    nodes = cycles[0][:-1]
    assert set(nodes) == {("a", "x"), ("b", "y"), ("c", "z")}


def test_cycle_through_blank_dest_resolves_to_self():
    # a.x -> self.y (blank dest_app) -> a.x
    mappings = [
        _mapping("a", "x", "", "y"),
        _mapping(SELF_KEY, "y", "a", "x"),
    ]
    cycles = find_cycles(mappings, SELF_KEY)
    assert len(cycles) == 1
    nodes = cycles[0][:-1]
    assert set(nodes) == {("a", "x"), (SELF_KEY, "y")}


def test_cycle_detection_tolerates_extra_linear_tail():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "a", "x"),
        _mapping("b", "y", "c", "z"),  # non-cyclic extra edge
    ]
    cycles = find_cycles(mappings, SELF_KEY)
    assert len(cycles) == 1


def test_describe_mapping_includes_resolved_dest():
    m = _mapping("tracker", "run_hours", "", "hours")
    assert describe_mapping(m, SELF_KEY) == f"tracker.run_hours -> {SELF_KEY}.hours"


def test_endpoints_returns_resolved_tuples():
    m = _mapping("a", "x", "b", "y")
    src, dst = endpoints(m, SELF_KEY)
    assert src == ("a", "x")
    assert dst == ("b", "y")
