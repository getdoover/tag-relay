"""CEL transform compilation and evaluation.

Each mapping may carry an optional CEL expression that runs against the source
value. The input tag value is bound as ``x``; the expression result becomes the
value written to the destination.

CEL is strict about mixing ``int`` and ``double`` in arithmetic. To smooth
over the most common footgun — ``x * 0.5 + 10`` with an integer source —
we detect expressions that contain any float literal and normalise them:
bare integer literals are rewritten as floats, and an integer ``x`` is cast
to float at evaluation time. Expressions that use only integer literals are
left alone, so pure-int arithmetic like ``x * 1000`` keeps its integer
semantics.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import cel

log = logging.getLogger(__name__)


class TransformError(Exception):
    """Raised when a CEL expression fails to compile or evaluate."""


# Matches `1.2`, `1e10`, `1.5E-3` — any numeric literal with a decimal point
# or exponent. Presence of one of these means the expression is doing float
# math.
_FLOAT_LITERAL_RE = re.compile(r"\b\d+\.\d+|\b\d+[eE][-+]?\d+")

# Matches bare integer literals that aren't already part of a float or
# identifier. Left lookbehind rejects `.`, digits, and word chars; right
# lookahead rejects `.`, digits, word chars, `e`/`E`.
_INT_LITERAL_RE = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def _normalise_for_double(expression: str) -> tuple[str, bool]:
    """Promote bare int literals to floats when the expression mixes float math.

    Returns ``(normalised_expression, in_double_mode)``. ``in_double_mode`` is
    True iff the expression contains at least one float literal — meaning any
    integer ``x`` should also be cast to double before evaluation. Note we
    can't use object-identity on the returned string to detect "we touched
    it"; if the expression already only contains float literals, ``re.sub``
    returns the same string, but we still need to cast ``x``.
    """
    if not _FLOAT_LITERAL_RE.search(expression):
        return expression, False
    return _INT_LITERAL_RE.sub(r"\1.0", expression), True


class TransformCache:
    def __init__(self):
        self._programs: dict[str, Any] = {}

    def evaluate(self, expression: str | None, x: Any) -> Any:
        if not expression:
            return x

        normalised, in_double_mode = _normalise_for_double(expression)
        program = self._programs.get(normalised)
        if program is None:
            try:
                program = cel.compile(normalised)
            except Exception as e:
                raise TransformError(
                    f"Failed to compile CEL expression {expression!r}: {e}"
                ) from e
            self._programs[normalised] = program

        # Cast int -> float only when the expression mixes float math
        # (otherwise pure-int expressions stay in int space). Keep booleans
        # as bool (bool is a subclass of int in Python — type() check is
        # strict and excludes it).
        if in_double_mode and type(x) is int:
            x = float(x)

        try:
            return program.execute({"x": x})
        except Exception as e:
            raise TransformError(
                f"Failed to evaluate CEL expression {expression!r} with x={x!r}: {e}"
            ) from e
