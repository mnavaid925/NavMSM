"""Pure-function tests for SPC service - X-bar/R limits + Western Electric."""
from decimal import Decimal

import pytest

from apps.qms.services.spc import (
    check_western_electric, compute_xbar_r, is_out_of_control,
)


class TestComputeXbarR:
    def test_textbook_example(self):
        # Textbook: 5 subgroups of size 5, all centered around 100 with low variation.
        subgroups = [
            [99.8, 100.0, 100.2, 99.9, 100.1],
            [100.1, 99.9, 100.0, 100.2, 99.8],
            [100.0, 100.1, 99.9, 100.0, 100.0],
            [99.9, 100.0, 100.1, 99.9, 100.1],
            [100.2, 100.0, 99.8, 100.0, 100.0],
        ]
        r = compute_xbar_r(subgroups)
        # CL should be approximately 100.
        assert abs(float(r.cl) - 100.0) < 0.01
        # UCL > CL > LCL
        assert r.ucl > r.cl > r.lcl
        # Range chart limits
        assert r.cl_r > 0
        assert r.ucl_r > r.cl_r >= r.lcl_r
        assert r.sample_size_used == 5

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_xbar_r([])

    def test_inconsistent_subgroup_size_raises(self):
        with pytest.raises(ValueError):
            compute_xbar_r([[1, 2, 3], [1, 2]])

    def test_unsupported_subgroup_size_raises(self):
        with pytest.raises(ValueError):
            compute_xbar_r([[1] * 11])  # n=11 not in table

    def test_subgroup_size_2_uses_constants(self):
        # Subgroup size 2 - smallest allowed. A2 = 1.880.
        r = compute_xbar_r([[10, 12], [11, 13], [12, 10]])
        assert r.cl > 0
        assert r.ucl > r.cl


class TestWesternElectricRules:
    def test_rule_1_outlier_detected(self):
        cl = Decimal('10')
        ucl = Decimal('13')
        lcl = Decimal('7')
        violations = check_western_electric(
            [10, 11, 9, 10, 11, 15, 10, 9, 11], cl=cl, ucl=ucl, lcl=lcl,
        )
        # Index 5 is value 15 > UCL 13 -> R1
        assert 'R1' in violations[5]
        # Surrounding points should be clean
        assert violations[0] == [] or 'R1' not in violations[0]

    def test_rule_4_eight_consecutive_above_cl(self):
        cl = Decimal('10')
        ucl = Decimal('14')
        lcl = Decimal('6')
        # 8 consecutive points above CL but inside limits
        v = check_western_electric(
            [11, 12, 11, 12, 11, 12, 11, 12], cl=cl, ucl=ucl, lcl=lcl,
        )
        assert 'R4' in v[7]  # index 7 has 8 consecutive above

    def test_clean_run_no_violations(self):
        cl = Decimal('10')
        ucl = Decimal('13')
        lcl = Decimal('7')
        v = check_western_electric([9, 11, 10, 11, 9, 10], cl=cl, ucl=ucl, lcl=lcl)
        # All within limits, alternating sides - no R1 / R4
        for entry in v:
            assert 'R1' not in entry
            assert 'R4' not in entry

    def test_is_out_of_control_helper(self):
        assert is_out_of_control(['R1'])
        assert is_out_of_control(['R1', 'R2'])
        # R2 / R3 / R4 alone do NOT make a point OOC under our convention - only R1 does.
        assert not is_out_of_control(['R2'])
        assert not is_out_of_control([])
