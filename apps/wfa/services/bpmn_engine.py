"""Module 20.1 - BPMN runtime engine.

Pure-function helpers that advance a ProcessInstance from node to node
following the persisted graph. The transition-condition evaluator below
is SECURITY-CRITICAL: NEVER call eval() or exec() on a stored
condition_expr - the parser in ``_safe_eval`` mirrors the whitelist used
by ``apps/iot/services/twin.py`` and rejects anything that is not an
explicit token.

Allowed tokens:
    * numeric and string constants
    * variable identifiers (a-zA-Z0-9_) resolved against ProcessVariable
      rows + the optional context dict passed by the caller
    * binary operators: + - * /
    * boolean / comparison operators: and or not == != < <= > >=
    * function calls: min(...), max(...), abs(...)
    * parentheses

The advance helpers themselves are pure with respect to the database -
they read the persisted graph + the runtime variables, decide what to
do, and return a description of the next state. The caller (view or
management command) is responsible for writing the new ProcessInstance
row + the matching ProcessActivity log entry inside its own
transaction.atomic block.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from typing import Any


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub, ast.Not)
_ALLOWED_BOOLOPS = (ast.And, ast.Or)
_ALLOWED_CMPOPS = (
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)
_ALLOWED_FUNCS = {
    'min': min,
    'max': max,
    'abs': abs,
}


class FormulaError(Exception):
    """Raised when a transition expression contains disallowed syntax."""


def _coerce(v):
    if v is None:
        return None
    if isinstance(v, (bool, int, float, Decimal, str)):
        return v
    return str(v)


def _safe_eval(node, ctx):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise FormulaError('Only literal constants allowed.')
    if isinstance(node, ast.Num):  # py<3.8 compat
        return node.n
    if isinstance(node, ast.Name):
        if node.id in ctx:
            return _coerce(ctx[node.id])
        if node.id in ('True', 'true'):
            return True
        if node.id in ('False', 'false'):
            return False
        raise FormulaError(f"Undefined variable: {node.id}")
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise FormulaError(
                f"Operator {type(node.op).__name__} not allowed.",
            )
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
                return 0
            return left / right
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise FormulaError(
                f"Unary {type(node.op).__name__} not allowed.",
            )
        v = _safe_eval(node.operand, ctx)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.Not):
            return not v
        return v
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _ALLOWED_BOOLOPS):
            raise FormulaError('Boolean op not allowed.')
        vals = [_safe_eval(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            result = True
            for v in vals:
                result = result and v
            return result
        result = False
        for v in vals:
            result = result or v
        return result
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaError('Chained comparisons not allowed.')
        op = node.ops[0]
        if not isinstance(op, _ALLOWED_CMPOPS):
            raise FormulaError(f"Comparison {type(op).__name__} not allowed.")
        left = _safe_eval(node.left, ctx)
        right = _safe_eval(node.comparators[0], ctx)
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
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


def evaluate_condition(expr: str, ctx: dict) -> bool:
    """Evaluate a transition condition. Empty expressions are TRUE."""
    if not expr or not expr.strip():
        return True
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f"Syntax error: {exc}") from exc
    return bool(_safe_eval(tree, ctx))


def gather_instance_context(instance) -> dict:
    """Build the {var_name: value} context for an instance.

    Reads ProcessVariable rows + the instance's context_json field.
    Returns Decimal / int / bool / str values (no model objects).
    """
    ctx: dict[str, Any] = {}
    base = instance.context_json or {}
    if isinstance(base, dict):
        for k, v in base.items():
            ctx[str(k)] = v
    for var in instance.variables.all():
        raw = var.value_text
        if var.value_type == 'int':
            try:
                ctx[var.name] = int(raw)
            except (TypeError, ValueError):
                ctx[var.name] = 0
        elif var.value_type == 'decimal':
            try:
                ctx[var.name] = Decimal(raw)
            except Exception:
                ctx[var.name] = Decimal('0')
        elif var.value_type == 'bool':
            ctx[var.name] = str(raw).strip().lower() in ('1', 'true', 'yes', 'y')
        else:
            ctx[var.name] = raw
    return ctx


def next_node(instance):
    """Return the next ProcessNode for ``instance`` following the first
    transition whose condition evaluates to True, or None if no outgoing
    transition matches (terminal node).
    """
    cur = instance.current_node
    if cur is None:
        return None
    ctx = gather_instance_context(instance)
    transitions = list(cur.outgoing.select_related('to_node').order_by('id'))
    for t in transitions:
        try:
            if evaluate_condition(t.condition_expr or '', ctx):
                return t.to_node
        except FormulaError:
            continue
    return None
