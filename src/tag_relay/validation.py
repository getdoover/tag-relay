"""Mapping validation: identity-loop rejection and cycle detection.

Run at the start of each processor invocation. Identity loops (source==dest)
are silently filtered here; callers are expected to log them exactly once.
Chain cycles (A.x -> B.y -> A.x, or longer) are only warned about — they
still run, because the user may have knowingly set up feedback.

Destination app may be left blank by the operator, in which case it
coalesces to the Tag Relay's own app_key. Callers pass that in as
``self_app_key`` so the resolved endpoints are always concrete.
"""

from __future__ import annotations

import logging
from typing import Iterable

log = logging.getLogger(__name__)


TagRef = tuple[str, str]  # (app_key, tag_name)


def endpoints(mapping, self_app_key: str) -> tuple[TagRef, TagRef]:
    """Return (source, dest) tag refs with dest_app coalesced to self_app_key."""
    src_app = mapping.source_app_key.value
    src_tag = mapping.source_tag_name.value
    dst_app = mapping.dest_app_key.value or self_app_key
    dst_tag = mapping.dest_tag_name.value
    return (src_app, src_tag), (dst_app, dst_tag)


def partition_mappings(
    mappings: Iterable, self_app_key: str
) -> tuple[list, list]:
    """Split mappings into (valid, rejected) lists.

    A mapping is rejected if source app/tag or destination tag is missing,
    or if source == dest after coalescing (identity loop — guaranteed to
    infinite-loop if relayed). A blank destination app is **not** rejected;
    it coalesces to ``self_app_key``.
    """
    valid: list = []
    rejected: list = []
    for m in mappings:
        src, dst = endpoints(m, self_app_key)
        if not all(src) or not all(dst) or src == dst:
            rejected.append(m)
            continue
        valid.append(m)
    return valid, rejected


def find_cycles(mappings: Iterable, self_app_key: str) -> list[list[TagRef]]:
    """Return all simple cycles in the mapping graph.

    Nodes are ``(app_key, tag_name)`` tuples (destination coalesced to
    ``self_app_key`` when blank); edges are mappings from source to
    destination. Each returned cycle is a list of nodes, with the first
    node repeated at the end (``[A, B, A]`` for a two-edge cycle).
    """
    graph: dict[TagRef, list[TagRef]] = {}
    for m in mappings:
        src, dst = endpoints(m, self_app_key)
        graph.setdefault(src, []).append(dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[TagRef, int] = {}
    cycles: list[list[TagRef]] = []

    def visit(node: TagRef, path: list[TagRef]) -> None:
        colour[node] = GRAY
        path.append(node)
        for neighbour in graph.get(node, ()):
            state = colour.get(neighbour, WHITE)
            if state == GRAY:
                # back-edge into the current path: extract the cycle
                idx = path.index(neighbour)
                cycles.append(path[idx:] + [neighbour])
            elif state == WHITE:
                visit(neighbour, path)
        path.pop()
        colour[node] = BLACK

    for node in list(graph.keys()):
        if colour.get(node, WHITE) == WHITE:
            visit(node, [])
    return cycles


def describe_endpoint(ref: TagRef) -> str:
    return f"{ref[0]}.{ref[1]}"


def describe_cycle(cycle: list[TagRef]) -> str:
    return " -> ".join(describe_endpoint(n) for n in cycle)


def describe_mapping(mapping, self_app_key: str) -> str:
    src, dst = endpoints(mapping, self_app_key)
    return f"{describe_endpoint(src)} -> {describe_endpoint(dst)}"
