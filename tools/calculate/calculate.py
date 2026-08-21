"""Arithmetic calculation tool."""

import math
from typing import Annotated

from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool


def _cot(x: float) -> float:
    """Cotangent.  cos/sin rather than 1/tan so the value is exact at the
    quarter-turns where tan blows up; sin(x) == 0 raises, and the caller
    sees it as that expression's own error line."""
    return math.cos(x) / math.sin(x)


def _acot(x: float) -> float:
    """Inverse cotangent, range (0, pi) — continuous through x == 0,
    unlike atan(1/x), which jumps and divides by zero there."""
    return math.pi / 2 - math.atan(x)


def _in_degrees(fn):
    """Wrap a radians-IN function so it takes degrees."""
    return lambda x: fn(math.radians(x))


def _out_degrees(fn):
    """Wrap a radians-OUT inverse so it returns degrees."""
    return lambda x: math.degrees(fn(x))


# RADIAN-based (standard Python) trig, and a DEGREE-based twin of each,
# suffixed ``d``.  Both exist on purpose: every angle in this design
# configurator is in DEGREES, but a model reaching for ``sin`` expects
# Python's radians.  Shipping only one of the two makes the other spelling
# SILENTLY wrong -- sin(20) for a 20-degree angle returns 0.913, not 0.342,
# and nothing raises.  With both, sind(20) and sin(radians(20)) agree.
_TRIG = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "cot": _cot,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "acot": _acot,
}

_ALLOWED_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "pi": math.pi,
    "radians": math.radians, "degrees": math.degrees,
    # atan2 recovers the angle from two lengths and keeps the quadrant,
    # which atan(y / x) cannot.
    "atan2": math.atan2,
    "atan2d": lambda y, x: math.degrees(math.atan2(y, x)),
    **_TRIG,
    **{f"{name}d": (_out_degrees(fn) if name.startswith("a")
                    else _in_degrees(fn))
       for name, fn in _TRIG.items()},
}


@tool
@generic_tool("Calculate")
def calculate(
    expressions: Annotated[
        list[str],
        "List of arithmetic / boolean expressions to evaluate in a SINGLE "
        "batched call.  BATCH INTO ONE CALL; a second call only when a "
        "later expression needs an earlier result. "
        "EXPRESSION SYNTAX IS PYTHON.  Use Python operators only: "
        "arithmetic '+', '-', '*', '/', '//', '%', '**'; comparison "
        "'==', '!=', '<', '<=', '>', '>='; boolean 'and', 'or', 'not' "
        "(NOT '&&', '||', '!' — those are JavaScript / C and will fail "
        "with a syntax error).  Parentheses are supported.  Bound "
        "callables: abs(), round(), min(), max(); the constant pi; and "
        "TRIGONOMETRY — sin, cos, tan, cot and the inverses asin, acos, "
        "atan, acot, atan2 all work in RADIANS (standard Python), while "
        "the d-suffixed twins sind, cosd, tand, cotd, asind, acosd, "
        "atand, acotd, atan2d work in DEGREES.  Every angle parameter in "
        "this configurator (innerAngle / middleAngle / outerAngle) is in "
        "DEGREES, so use the d-forms on them: sind(20) is 0.342, whereas "
        "sin(20) reads 20 as radians and returns 0.913.  radians() and "
        "degrees() convert explicitly.  No other functions, no name "
        "lookups, no imports.  "
        "Examples (all valid Python): "
        "['25.4 * 3 + 10', '2 * 3.14159 * 75', '20 / 75', '30 > 25', "
        "'8.0 >= 3 and 8.0 <= 11', 'abs(-7) + min(2, 5)', "
        "'sind(20) * 15.0', 'atan2d(3, 4)', 'degrees(asin(0.342))'].",
    ],
) -> str:
    """Evaluate one or more Python expressions in a single call.

    The expression language is Python (the implementation calls
    ``eval`` with a restricted namespace).  Returns one line per
    expression in the form ``<expression> = <result>``, or
    ``<expression> -> error: <message>`` when an expression fails.
    The order of the output lines matches the order of the input list.
    """
    allowed_names = _ALLOWED_NAMES

    if not expressions:
        return "Calculation error: no expressions provided"

    lines = []
    for expr in expressions:
        try:
            result = eval(expr, {"__builtins__": {}}, allowed_names)  # noqa: S307
            lines.append(f"{expr} = {result}")
        except Exception as exc:
            lines.append(f"{expr} -> error: {exc}")
    return "\n".join(lines)
