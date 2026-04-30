"""ANSI/ASQ Z1.4 single-sampling AQL table.

Pure functions, no ORM imports. Returns ``(sample_size, accept_number,
reject_number)`` for a given ``(lot_size, aql, level)`` tuple.

Coverage in v1:
    - General inspection levels I, II, III
    - Lot-size brackets 2-2 through 500001-and-above
    - AQL values: 0.10, 0.15, 0.25, 0.40, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0

Reference:
    ANSI/ASQ Z1.4-2003 Table I (Sample size code letters) +
    Table II-A (Single sampling plans for normal inspection).

Note:
    This is the canonical / textbook table. Where the standard
    arrows up / down to a different sample-size code (e.g. when a sample
    size exceeds the lot), this implementation uses the destination cell
    rather than the arrow indirection - keeps the function deterministic
    and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass


# Lot-size brackets -> sample-size code letter for each general level.
# Indexed by (level, bracket_index). Bracket order matches LOT_SIZE_BRACKETS.
LOT_SIZE_BRACKETS = [
    (2, 8),
    (9, 15),
    (16, 25),
    (26, 50),
    (51, 90),
    (91, 150),
    (151, 280),
    (281, 500),
    (501, 1200),
    (1201, 3200),
    (3201, 10000),
    (10001, 35000),
    (35001, 150000),
    (150001, 500000),
    (500001, 10**12),
]

# Code letter per (level, bracket_index)
CODE_LETTER = {
    'I': ['A', 'A', 'B', 'C', 'C', 'D', 'E', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M'],
    'II': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q'],
    'III': ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R'],
}

# Sample size for each code letter.
SAMPLE_SIZE = {
    'A': 2, 'B': 3, 'C': 5, 'D': 8, 'E': 13, 'F': 20, 'G': 32, 'H': 50,
    'J': 80, 'K': 125, 'L': 200, 'M': 315, 'N': 500, 'P': 800, 'Q': 1250, 'R': 2000,
}

# Single-sampling normal inspection plans:
# (Ac, Re) per (code_letter, aql_string).
# 'arrow' means 'use the next code letter's plan' - resolved at lookup time.
ACCEPT_REJECT_TABLE = {
    'A': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓', '0.65': '↓',
          '1.0': '↓', '1.5': '↓', '2.5': '↓', '4.0': '↓', '6.5': (0, 1),
          '10.0': (0, 1)},
    'B': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓', '0.65': '↓',
          '1.0': '↓', '1.5': '↓', '2.5': '↓', '4.0': (0, 1), '6.5': (0, 1),
          '10.0': (1, 2)},
    'C': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓', '0.65': '↓',
          '1.0': '↓', '1.5': '↓', '2.5': (0, 1), '4.0': (0, 1), '6.5': (1, 2),
          '10.0': (2, 3)},
    'D': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓', '0.65': '↓',
          '1.0': '↓', '1.5': (0, 1), '2.5': (0, 1), '4.0': (1, 2), '6.5': (2, 3),
          '10.0': (3, 4)},
    'E': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓', '0.65': '↓',
          '1.0': (0, 1), '1.5': (0, 1), '2.5': (1, 2), '4.0': (2, 3),
          '6.5': (3, 4), '10.0': (5, 6)},
    'F': {'0.10': '↓', '0.15': '↓', '0.25': '↓', '0.40': '↓',
          '0.65': (0, 1), '1.0': (0, 1), '1.5': (1, 2), '2.5': (2, 3),
          '4.0': (3, 4), '6.5': (5, 6), '10.0': (7, 8)},
    'G': {'0.10': '↓', '0.15': '↓', '0.25': '↓',
          '0.40': (0, 1), '0.65': (0, 1), '1.0': (1, 2), '1.5': (2, 3),
          '2.5': (3, 4), '4.0': (5, 6), '6.5': (7, 8), '10.0': (10, 11)},
    'H': {'0.10': '↓', '0.15': '↓',
          '0.25': (0, 1), '0.40': (0, 1), '0.65': (1, 2), '1.0': (2, 3),
          '1.5': (3, 4), '2.5': (5, 6), '4.0': (7, 8), '6.5': (10, 11),
          '10.0': (14, 15)},
    'J': {'0.10': '↓',
          '0.15': (0, 1), '0.25': (0, 1), '0.40': (1, 2), '0.65': (2, 3),
          '1.0': (3, 4), '1.5': (5, 6), '2.5': (7, 8), '4.0': (10, 11),
          '6.5': (14, 15), '10.0': (21, 22)},
    'K': {'0.10': (0, 1), '0.15': (0, 1), '0.25': (1, 2), '0.40': (2, 3),
          '0.65': (3, 4), '1.0': (5, 6), '1.5': (7, 8), '2.5': (10, 11),
          '4.0': (14, 15), '6.5': (21, 22), '10.0': (21, 22)},
    'L': {'0.10': (0, 1), '0.15': (1, 2), '0.25': (2, 3), '0.40': (3, 4),
          '0.65': (5, 6), '1.0': (7, 8), '1.5': (10, 11), '2.5': (14, 15),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
    'M': {'0.10': (1, 2), '0.15': (2, 3), '0.25': (3, 4), '0.40': (5, 6),
          '0.65': (7, 8), '1.0': (10, 11), '1.5': (14, 15), '2.5': (21, 22),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
    'N': {'0.10': (2, 3), '0.15': (3, 4), '0.25': (5, 6), '0.40': (7, 8),
          '0.65': (10, 11), '1.0': (14, 15), '1.5': (21, 22), '2.5': (21, 22),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
    'P': {'0.10': (3, 4), '0.15': (5, 6), '0.25': (7, 8), '0.40': (10, 11),
          '0.65': (14, 15), '1.0': (21, 22), '1.5': (21, 22), '2.5': (21, 22),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
    'Q': {'0.10': (5, 6), '0.15': (7, 8), '0.25': (10, 11), '0.40': (14, 15),
          '0.65': (21, 22), '1.0': (21, 22), '1.5': (21, 22), '2.5': (21, 22),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
    'R': {'0.10': (7, 8), '0.15': (10, 11), '0.25': (14, 15), '0.40': (21, 22),
          '0.65': (21, 22), '1.0': (21, 22), '1.5': (21, 22), '2.5': (21, 22),
          '4.0': (21, 22), '6.5': (21, 22), '10.0': (21, 22)},
}

# Order of code letters (ascending sample size) for arrow resolution.
CODE_LETTERS_ASCENDING = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H',
                          'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R']

# AQL strings supported (ordered).
AQL_STRINGS = ['0.10', '0.15', '0.25', '0.40', '0.65',
               '1.0', '1.5', '2.5', '4.0', '6.5', '10.0']


@dataclass(frozen=True)
class AQLPlan:
    code_letter: str
    sample_size: int
    accept_number: int
    reject_number: int


def _bracket_index(lot_size: int) -> int:
    if lot_size < 2:
        raise ValueError('Lot size must be at least 2.')
    for idx, (lo, hi) in enumerate(LOT_SIZE_BRACKETS):
        if lo <= lot_size <= hi:
            return idx
    return len(LOT_SIZE_BRACKETS) - 1


def _normalize_aql(aql) -> str:
    """Snap a numeric AQL to the nearest supported AQL string."""
    aql_f = float(aql)
    table = [(float(s), s) for s in AQL_STRINGS]
    # Pick the closest supported AQL value, preferring the lower (stricter) one
    # on a tie so we never accept loose plans the user did not ask for.
    best = min(table, key=lambda t: (abs(t[0] - aql_f), t[0]))
    return best[1]


def lookup_plan(lot_size: int, aql, level: str = 'II') -> AQLPlan:
    """Return the single-sampling plan for normal inspection.

    Args:
        lot_size: number of items in the lot (>= 2).
        aql: AQL value (will be snapped to the nearest supported AQL string).
        level: 'I', 'II', or 'III'. Default is 'II'.
    """
    level = (level or 'II').upper()
    if level not in CODE_LETTER:
        raise ValueError(f'Unknown inspection level: {level}')
    aql_str = _normalize_aql(aql)
    bracket = _bracket_index(int(lot_size))
    code = CODE_LETTER[level][bracket]
    plan = ACCEPT_REJECT_TABLE[code].get(aql_str)
    # Resolve a down-arrow by stepping one code letter at a time.
    while plan == '↓':
        idx = CODE_LETTERS_ASCENDING.index(code)
        if idx + 1 >= len(CODE_LETTERS_ASCENDING):
            raise ValueError(
                f'No plan exists for code {code} at AQL {aql_str}.'
            )
        code = CODE_LETTERS_ASCENDING[idx + 1]
        plan = ACCEPT_REJECT_TABLE[code].get(aql_str)
    if plan is None:
        raise ValueError(
            f'AQL {aql_str} not in table for code {code}.'
        )
    accept, reject = plan
    sample = SAMPLE_SIZE[code]
    # Standard rule: if sample size >= lot size, inspect 100% (Ac/Re still apply).
    if sample > lot_size:
        sample = int(lot_size)
    return AQLPlan(
        code_letter=code,
        sample_size=sample,
        accept_number=accept,
        reject_number=reject,
    )
