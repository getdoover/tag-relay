"""Mapping validation: identity-loop rejection and cycle detection.

Run at the start of each processor invocation. Identity loops (source==dest)
are silently filtered here; callers are expected to log them exactly once.
Chain cycles (A.x -> B.y -> A.x, or longer) are only warned about — they
still run, because the user may have knowingly set up feedback.
"""

from __future__ import annotations

import logging
from typing import Iterable

log = logging.getLogger(__name__)


TagRef = tuple[str, str]  # (app_key, tag_name)


def endpoints(mapping) -> tuple[TagRef, TagRef]:
    src = (mapping.source_app_key.value, mapping.source_tag_name.value)
    dst = (mapping.dest_app_key.value, mapping.dest_tag_name.value)
    return src, dst


def partition_mappings(mappings: Iterable) -> tuple[list, list]:
    """Split mappings into (valid, rejected) lists.

    A mapping is rejected if any endpoint field is empty, or if source == dest
    (identity loop — guaranteed to infinite-loop if relayed).
    """
    valid: list = []
    rejected: list = []
    for m in mappings:
        src, dst = endpoints(m)
        if not all(src) or not all(dst) or src == dst:
            rejected.append(m)
            continue
        valid.append(m)
    return valid, rejected


def find_cycles(mappings: Iterable) -> list[list[TagRef]]:
    """Return all simple cycles in the mapping graph.

    Nodes are ``(app_key, tag_name)`` tuples; edges are mappings from source
    to destination. Each returned cycle is a list of nodes, with the first
    node repeated at the end (i.e. ``[A, B, A]`` for a two-edge cycle).
    """
    graph: dict[TagRef, list[TagRef]] = {}
    for m in mappings:
        src, dst = endpoints(m)
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


def describe_mapping(mapping) -> str:
    src, dst = endpoints(mapping)
    return f"{describe_endpoint(src)} -> {describe_endpoint(dst)}"
