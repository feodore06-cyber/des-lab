"""Recompute derived variables from their formula, without running arbitrary code."""

import ast
import operator

_ALLOWED = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
            ast.UAdd: operator.pos, ast.Mod: operator.mod}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(formula: str, row: dict) -> float | None:
    """Evaluate an arithmetic formula over a row's values; None when it cannot be computed."""
    text = str(formula or "").strip()
    if not text or len(text) > 300:
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            value = _number(row.get(node.id))
            if value is None:
                raise ValueError(node.id)
            return value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
                raise ZeroDivisionError
            return _ALLOWED[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](walk(node.operand))
        raise ValueError("unsupported")

    try:
        return walk(tree)
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        return None


def recompute(row: dict, items: list) -> dict:
    """Fill every derived variable that has a formula and whose inputs are present."""
    out = dict(row)
    for item in items:
        if item.get("role") != "derived" or not item.get("formula"):
            continue
        value = evaluate(item["formula"], out)
        if value is not None:
            out[item["name"]] = value
    return out
