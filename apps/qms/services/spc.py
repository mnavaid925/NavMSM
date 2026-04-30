"""Statistical Process Control (SPC) math.

Pure functions, no ORM imports.

Coverage in v1:
    - X-bar / R control limits using A2 / D3 / D4 constants
      for subgroup sizes 2..10 (the textbook range).
    - Western Electric runs rules 1..4:
        Rule 1: any single point outside 3-sigma (UCL or LCL).
        Rule 2: 2 of 3 consecutive points beyond 2-sigma on the same side.
        Rule 3: 4 of 5 consecutive points beyond 1-sigma on the same side.
        Rule 4: 8 consecutive points on the same side of the centerline.

Out of scope (deferred):
    - Capability indices (Cp, Cpk, Pp, Ppk).
    - p / np / c / u attribute charts (model fields exist; UCL/LCL math
      will be added in a follow-up).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence


# A2, D3, D4 constants for X-bar/R charts. Index = subgroup size.
_XBAR_R_CONSTANTS = {
    2:  {'A2': Decimal('1.880'), 'D3': Decimal('0'),     'D4': Decimal('3.267')},
    3:  {'A2': Decimal('1.023'), 'D3': Decimal('0'),     'D4': Decimal('2.575')},
    4:  {'A2': Decimal('0.729'), 'D3': Decimal('0'),     'D4': Decimal('2.282')},
    5:  {'A2': Decimal('0.577'), 'D3': Decimal('0'),     'D4': Decimal('2.115')},
    6:  {'A2': Decimal('0.483'), 'D3': Decimal('0'),     'D4': Decimal('2.004')},
    7:  {'A2': Decimal('0.419'), 'D3': Decimal('0.076'), 'D4': Decimal('1.924')},
    8:  {'A2': Decimal('0.373'), 'D3': Decimal('0.136'), 'D4': Decimal('1.864')},
    9:  {'A2': Decimal('0.337'), 'D3': Decimal('0.184'), 'D4': Decimal('1.816')},
    10: {'A2': Decimal('0.308'), 'D3': Decimal('0.223'), 'D4': Decimal('1.777')},
}


@dataclass(frozen=True)
class XBarRLimits:
    cl: Decimal       # X-bar centerline (grand mean)
    ucl: Decimal      # X-bar upper control limit
    lcl: Decimal      # X-bar lower control limit
    cl_r: Decimal     # R-chart centerline (mean of subgroup ranges)
    ucl_r: Decimal
    lcl_r: Decimal
    sample_size_used: int


def _to_decimal(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def compute_xbar_r(subgroups: Sequence[Sequence]) -> XBarRLimits:
    """Compute X-bar and R control limits from a list of subgroups.

    Each subgroup is a sequence of measurements (size 2..10). All subgroups
    must be the same size.
    """
    if not subgroups:
        raise ValueError('At least one subgroup is required to compute SPC limits.')
    sizes = {len(g) for g in subgroups}
    if len(sizes) != 1:
        raise ValueError('All subgroups must have the same size.')
    n = sizes.pop()
    if n not in _XBAR_R_CONSTANTS:
        raise ValueError(f'Subgroup size {n} not supported (must be 2..10).')

    # Convert everything to Decimal for predictable arithmetic.
    means = []
    ranges = []
    for g in subgroups:
        vals = [_to_decimal(v) for v in g]
        m = sum(vals) / Decimal(len(vals))
        means.append(m)
        ranges.append(max(vals) - min(vals))

    grand_mean = sum(means) / Decimal(len(means))
    mean_range = sum(ranges) / Decimal(len(ranges))

    c = _XBAR_R_CONSTANTS[n]
    a2_r = c['A2'] * mean_range
    return XBarRLimits(
        cl=grand_mean,
        ucl=grand_mean + a2_r,
        lcl=grand_mean - a2_r,
        cl_r=mean_range,
        ucl_r=c['D4'] * mean_range,
        lcl_r=c['D3'] * mean_range,
        sample_size_used=len(subgroups),
    )


def _zone(value: Decimal, cl: Decimal, sigma: Decimal) -> str:
    """Return the zone of a point relative to CL: 'A_high', 'A_low', etc.

    Zones (per Shewhart conventions):
        A_high: > CL + 2 sigma
        B_high: > CL + 1 sigma
        C_high: > CL
        C_low:  <= CL
        B_low:  < CL - 1 sigma
        A_low:  < CL - 2 sigma
    """
    if value > cl + 2 * sigma:
        return 'A_high'
    if value > cl + sigma:
        return 'B_high'
    if value > cl:
        return 'C_high'
    if value < cl - 2 * sigma:
        return 'A_low'
    if value < cl - sigma:
        return 'B_low'
    if value < cl:
        return 'C_low'
    return 'C_low'  # exactly on CL counts as low side


def check_western_electric(
    points: Iterable,
    *,
    cl: Decimal,
    ucl: Decimal,
    lcl: Decimal,
) -> list[list[str]]:
    """Return a list of violation codes (1..4) for each point.

    Each list element corresponds to ``points[i]``. An empty list means no
    violations triggered at that index.
    """
    pts = [_to_decimal(p) for p in points]
    cl = _to_decimal(cl)
    ucl = _to_decimal(ucl)
    lcl = _to_decimal(lcl)
    sigma = (ucl - cl) / Decimal('3')  # CL + 3 sigma = UCL

    zones = [_zone(p, cl, sigma) for p in pts]
    high_side = [z.endswith('_high') for z in zones]
    low_side = [z.endswith('_low') for z in zones]
    out: list[list[str]] = [[] for _ in pts]

    for i, (p, z) in enumerate(zip(pts, zones)):
        # Rule 1: any point beyond 3 sigma.
        if p > ucl or p < lcl:
            out[i].append('R1')

        # Rule 2: 2 of 3 consecutive points in zone A or beyond, same side.
        if i >= 2:
            window_high = [zones[j] in ('A_high',) or pts[j] > ucl for j in range(i - 2, i + 1)]
            window_low = [zones[j] in ('A_low',) or pts[j] < lcl for j in range(i - 2, i + 1)]
            if sum(window_high) >= 2 or sum(window_low) >= 2:
                out[i].append('R2')

        # Rule 3: 4 of 5 consecutive points in zone B or beyond, same side.
        if i >= 4:
            window_high = [
                zones[j] in ('B_high', 'A_high') or pts[j] > ucl
                for j in range(i - 4, i + 1)
            ]
            window_low = [
                zones[j] in ('B_low', 'A_low') or pts[j] < lcl
                for j in range(i - 4, i + 1)
            ]
            if sum(window_high) >= 4 or sum(window_low) >= 4:
                out[i].append('R3')

        # Rule 4: 8 consecutive points on the same side of CL.
        if i >= 7:
            if all(high_side[j] for j in range(i - 7, i + 1)):
                out[i].append('R4')
            elif all(low_side[j] for j in range(i - 7, i + 1)):
                out[i].append('R4')

    return out


def is_out_of_control(violations: list[str]) -> bool:
    return any(v == 'R1' for v in violations)
