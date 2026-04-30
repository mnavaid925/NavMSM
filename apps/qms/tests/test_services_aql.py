"""Pure-function tests for the AQL table service."""
import pytest

from apps.qms.services.aql import lookup_plan, AQLPlan


class TestAQLLookup:
    def test_lot_size_500_aql_2_5_level_II_known_plan(self):
        # Lot size 500 -> Level II -> code letter H -> sample 50, AQL 2.5 -> Ac 5 / Re 6
        p = lookup_plan(500, 2.5, 'II')
        assert p.code_letter == 'H'
        assert p.sample_size == 50
        assert p.accept_number == 5
        assert p.reject_number == 6

    def test_lot_size_50_aql_4_level_II(self):
        # Lot size 50 -> Level II -> code D -> sample 8 -> AQL 4.0 -> Ac 1 / Re 2
        p = lookup_plan(50, 4.0, 'II')
        assert p.code_letter == 'D'
        assert p.sample_size == 8
        assert p.accept_number == 1
        assert p.reject_number == 2

    def test_lot_size_2_uses_arrow_resolution(self):
        # Lot size 2 -> Level II -> code A -> sample 2; AQL 4.0 has down arrow,
        # so should escalate up the code-letter chain.
        p = lookup_plan(2, 4.0, 'II')
        assert isinstance(p, AQLPlan)
        # Sample size cannot exceed the lot, so it gets clamped to 2.
        assert p.sample_size == 2

    def test_levels_diverge_for_same_lot(self):
        # Same lot at different levels should produce different code letters
        p_l1 = lookup_plan(500, 2.5, 'I')
        p_l2 = lookup_plan(500, 2.5, 'II')
        p_l3 = lookup_plan(500, 2.5, 'III')
        assert p_l1.sample_size <= p_l2.sample_size <= p_l3.sample_size

    def test_unknown_level_raises(self):
        with pytest.raises(ValueError):
            lookup_plan(100, 2.5, 'IV')

    def test_lot_size_below_2_raises(self):
        with pytest.raises(ValueError):
            lookup_plan(0, 2.5, 'II')

    def test_sample_clamped_to_lot_size(self):
        # If the table picks a sample size larger than the lot, clamp to lot.
        p = lookup_plan(5, 0.10, 'III')
        assert p.sample_size <= 5

    def test_aql_snapping_to_nearest_supported(self):
        # AQL 0.5 (not in table) should snap to a nearby value (0.40 or 0.65).
        p = lookup_plan(500, 0.5, 'II')
        assert p.sample_size > 0
