"""Module 15 - Digital Twin services.

Includes a SECURITY-CRITICAL safe-expression evaluator. NEVER call eval() or
exec() on user-supplied formulas - the parser below rejects everything that
isn't an explicit token in the whitelist.

Allowed tokens:
    * decimal numbers (e.g. 3.14, -5)
    * variable identifiers (a-zA-Z0-9_) bound to provided context
    * binary operators: + - * /
    * function calls: min(...), max(...), abs(...)
    * parentheses
"""
from __future__ import annotations

import ast
from decimal import Decimal
from typing import Any


# Safe operator set: subclass of ast operators that we allow.
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)
_ALLOWED_FUNCS = {
    'min': min,
    'max': max,
    'abs': abs,
}


class FormulaError(Exception):
    """Raised when a formula contains disallowed syntax."""


def _safe_eval(node, ctx):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        raise FormulaError('Only numeric constants allowed.')
    if isinstance(node, ast.Num):  # py<3.8 compat
        return Decimal(str(node.n))
    if isinstance(node, ast.Name):
        if node.id in ctx:
            v = ctx[node.id]
            if v is None:
                return Decimal('0')
            return v if isinstance(v, Decimal) else Decimal(str(v))
        raise FormulaError(f"Undefined variable: {node.id}")
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise FormulaError(f"Operator {type(node.op).__name__} not allowed.")
        left = _safe_eval(node.left, ctx)
        right = _safe_eval(node.right, ctx)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                return Decimal('0')
            return left / right
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise FormulaError(f"Unary {type(node.op).__name__} not allowed.")
        v = _safe_eval(node.operand, ctx)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError('Indirect function calls not allowed.')
        fn = _ALLOWED_FUNCS.get(node.func.id)
        if fn is None:
            raise FormulaError(f"Function {node.func.id} not allowed.")
        args = [_safe_eval(a, ctx) for a in node.args]
        if not args:
            raise FormulaError(f"{node.func.id} requires at least one argument.")
        return fn(*args)
    raise FormulaError(f"Unsupported node: {type(node).__name__}")


def evaluate_formula(formula: str, ctx: dict) -> Decimal:
    """Evaluate a whitelisted formula against ``ctx``.

    Raises FormulaError on any unsafe construct.
    """
    if not formula or not formula.strip():
        return Decimal('0')
    try:
        tree = ast.parse(formula, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f"Syntax error: {exc}") from exc
    return _safe_eval(tree, ctx)


def compute_twin_state(twin) -> dict:
    """Recompute every attribute on the twin and return a {name: value} dict.

    For state/measurement attributes, pulls the latest IoTReading on the
    source tag's StreamMetric. For derived attributes, evaluates ``formula``
    in a context built from sibling attributes.

    Returns the dict of computed values; the caller decides whether to
    persist via ``.update()``.
    """
    # Lazy ORM imports to keep this module ORM-free at top.
    attrs = list(twin.attributes.select_related('source_tag', 'source_tag__stream_metric').all())
    state = {}

    # Pass 1: pull state/measurement values directly.
    for attr in attrs:
        if attr.attribute_type in ('state', 'measurement'):
            sm = getattr(attr.source_tag, 'stream_metric', None) if attr.source_tag else None
            state[attr.name] = sm.latest_value if sm and sm.latest_value is not None else None

    # Pass 2: evaluate derived formulas against the passed-1 context.
    for attr in attrs:
        if attr.attribute_type == 'derived':
            ctx = {k: (v if v is not None else Decimal('0')) for k, v in state.items()}
            try:
                state[attr.name] = evaluate_formula(attr.formula, ctx)
            except FormulaError:
                state[attr.name] = None
    return state
