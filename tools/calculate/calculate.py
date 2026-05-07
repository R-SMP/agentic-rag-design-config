"""Arithmetic calculation tool."""

from typing import Annotated

from langchain_core.tools import tool


@tool
def calculate(
    expressions: Annotated[
        list[str],
        "List of arithmetic / boolean expressions to evaluate in a SINGLE "
        "batched call.  Always group every expression you currently need "
        "into one call instead of invoking this tool repeatedly. "
        "EXPRESSION SYNTAX IS PYTHON.  Use Python operators only: "
        "arithmetic '+', '-', '*', '/', '//', '%', '**'; comparison "
        "'==', '!=', '<', '<=', '>', '>='; boolean 'and', 'or', 'not' "
        "(NOT '&&', '||', '!' — those are JavaScript / C and will fail "
        "with a syntax error).  Parentheses are supported.  Bound "
        "callables: abs(), round(), min(), max() — no other functions, "
        "no name lookups, no imports.  "
        "Examples (all valid Python): "
        "['25.4 * 3 + 10', '2 * 3.14159 * 75', '20 / 75', '30 > 25', "
        "'8.0 >= 3 and 8.0 <= 11', 'abs(-7) + min(2, 5)'].",
    ],
) -> str:
    """Evaluate one or more Python expressions in a single call.

    The expression language is Python (the implementation calls
    ``eval`` with a restricted namespace).  Returns one line per
    expression in the form ``<expression> = <result>``, or
    ``<expression> -> error: <message>`` when an expression fails.
    The order of the output lines matches the order of the input list.
    """
    allowed_names = {"abs": abs, "round": round, "min": min, "max": max}

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
