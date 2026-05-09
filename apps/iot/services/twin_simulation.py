"""Module 15 - Digital Twin simulator.

Pure function. Evaluates the scenario's input_payload against the twin's
attributes (state + derived) and returns a result_payload dict. NEVER mutates
the twin's persisted state - the caller may persist the scenario's result_payload.
"""
from __future__ import annotations

from decimal import Decimal

from .twin import FormulaError, evaluate_formula


def run_simulation(scenario) -> dict:
    """Execute the simulation. Returns the result payload.

    scenario.input_payload contract:
        { "<attribute_name>": <number>, ... }  - overrides for state values

    Result payload:
        {
            "computed": { name: value, ... },     # all attributes after eval
            "matched_expected": bool,             # input == expected_output
            "errors": [str, ...]                  # per-attribute formula errors
        }
    """
    twin = scenario.twin
    attrs = list(twin.attributes.all())
    inputs = dict(scenario.input_payload or {})
    expected = dict(scenario.expected_output or {})
    state = {}
    errors = []

    # Pass 1: state/measurement values from inputs (override) or default 0.
    for attr in attrs:
        if attr.attribute_type in ('state', 'measurement'):
            state[attr.name] = Decimal(str(inputs.get(attr.name, 0)))

    # Pass 2: derived formulas.
    for attr in attrs:
        if attr.attribute_type == 'derived':
            ctx = {k: v for k, v in state.items()}
            try:
                state[attr.name] = evaluate_formula(attr.formula, ctx)
            except FormulaError as exc:
                errors.append(f'{attr.name}: {exc}')
                state[attr.name] = None

    matched = True
    for k, v in expected.items():
        actual = state.get(k)
        try:
            if actual is None or Decimal(str(actual)) != Decimal(str(v)):
                matched = False
                break
        except Exception:  # noqa: BLE001
            matched = False
            break

    return {
        'computed': {k: (str(v) if v is not None else None) for k, v in state.items()},
        'matched_expected': matched,
        'errors': errors,
    }
