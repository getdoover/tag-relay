"""CEL transform compilation and evaluation.

Each mapping may carry an optional CEL expression that runs against the source
value. The input tag value is bound as ``x``; the expression result becomes the
value written to the destination.
"""

from __future__ import annotations

import logging
from typing import Any

import cel

log = logging.getLogger(__name__)


class TransformError(Exception):
    """Raised when a CEL expression fails to compile or evaluate."""


class TransformCache:
    def __init__(self):
        self._programs: dict[str, Any] = {}

    def evaluate(self, expression: str | None, x: Any) -> Any:
        if not expression:
            return x

        program = self._programs.get(expression)
        if program is None:
            try:
                program = cel.compile(expression)
            except Exception as e:
                raise TransformError(
                    f"Failed to compile CEL expression {expression!r}: {e}"
                ) from e
            self._programs[expression] = program

        try:
            return program.execute({"x": x})
        except Exception as e:
            raise TransformError(
                f"Failed to evaluate CEL expression {expression!r} with x={x!r}: {e}"
            ) from e
