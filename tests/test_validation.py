"""Tests for mapping validation (identity-loop filtering and cycle detection)."""

from types import SimpleNamespace

from tag_relay.validation import (
    describe_cycle,
    describe_mapping,
    endpoints,
    find_cycles,
    partition_mappings,
)


def _mapping(source_app, source_tag, dest_app, dest_tag):
    """Build a duck-typed mapping matching what pydoover's Object produces.

    Each field exposes a ``.value`` attribute, matching the config element API.
    """
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
    valid, rejected = partition_mappings(mappings)
    assert valid == mappings
    assert rejected == []


def test_partition_rejects_identity_loop():
    same_tag = _mapping("app_a", "x", "app_a", "x")
    other = _mapping("app_a", "x", "app_b", "y")
    valid, rejected = partition_mappings([same_tag, other])
    assert valid == [other]
    assert rejected == [same_tag]


def test_partition_rejects_missing_fields():
    missing_source_app = _mapping("", "x", "app_b", "y")
    missing_source_tag = _mapping("app_a", "", "app_b", "y")
    missing_dest_app = _mapping("app_a", "x", "", "y")
    missing_dest_tag = _mapping("app_a", "x", "app_b", "")
    none_field = _mapping(None, "x", "app_b", "y")
    all_missing = [
        missing_source_app,
        missing_source_tag,
        missing_dest_app,
        missing_dest_tag,
        none_field,
    ]
    good = _mapping("app_a", "x", "app_b", "y")

    valid, rejected = partition_mappings(all_missing + [good])
    assert valid == [good]
    assert rejected == all_missing


def test_identity_loop_allowed_when_app_same_but_tag_differs():
    # Same app, different tag — legitimate, not a loop.
    inside_same_app = _mapping("app_a", "raw", "app_a", "cooked")
    valid, rejected = partition_mappings([inside_same_app])
    assert valid == [inside_same_app]
    assert rejected == []


# --- find_cycles --------------------------------------------------------


def test_no_cycles_in_linear_chain():
    # a.x -> b.y -> c.z
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "c", "z"),
    ]
    assert find_cycles(mappings) == []


def test_detects_two_node_cycle():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "a", "x"),
    ]
    cycles = find_cycles(mappings)
    assert len(cycles) == 1
    # Cycle rendered as A -> B -> A or B -> A -> B depending on DFS entry point
    rendered = describe_cycle(cycles[0])
    assert rendered in ("a.x -> b.y -> a.x", "b.y -> a.x -> b.y")


def test_detects_three_node_cycle():
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "c", "z"),
        _mapping("c", "z", "a", "x"),
    ]
    cycles = find_cycles(mappings)
    assert len(cycles) == 1
    nodes = [node for node in cycles[0][:-1]]  # drop repeated tail node
    assert set(nodes) == {("a", "x"), ("b", "y"), ("c", "z")}


def test_cycle_detection_tolerates_extra_linear_tail():
    # b.y is in a cycle with a.x, and also branches out to an unrelated dest.
    mappings = [
        _mapping("a", "x", "b", "y"),
        _mapping("b", "y", "a", "x"),
        _mapping("b", "y", "c", "z"),  # non-cyclic extra edge
    ]
    cycles = find_cycles(mappings)
    assert len(cycles) == 1


def test_describe_mapping():
    m = _mapping("tracker", "run_hours", "display", "hours")
    assert describe_mapping(m) == "tracker.run_hours -> display.hours"


def test_endpoints_returns_tuples():
    m = _mapping("a", "x", "b", "y")
    src, dst = endpoints(m)
    assert src == ("a", "x")
    assert dst == ("b", "y")
