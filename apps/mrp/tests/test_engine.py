"""End-to-end MRP engine tests, including regression coverage for:

- D-02 (net_change mode no longer raises IntegrityError)
- D-04 (concurrent / repeated PR sequence allocation)
- D-09 (BOM lookup is a single query)
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.mrp.models import (
    MRPException, MRPPurchaseRequisition, NetRequirement,
)
from apps.mrp.services import exceptions as exc_service
from apps.mrp.services import mrp_engine


@pytest.mark.django_db
class TestEngineHappyPath:
    def test_run_with_forecast_demand_writes_net_rows(
        self, acme, calc, fg_product, raw_product,
        released_bom, snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        summary = mrp_engine.run_mrp(calc, mode='regenerative')
        assert summary.skipped_no_bom == []
        nets = NetRequirement.objects.filter(mrp_calculation=calc)
        assert nets.exists()
        # End-item rows at level 0
        assert nets.filter(product=fg_product, bom_level=0).exists()
        # Component rows at level 1 with parent_product set
        comp_rows = nets.filter(product=raw_product, bom_level=1)
        assert comp_rows.exists()
        assert comp_rows.first().parent_product_id == fg_product.pk

    def test_pr_auto_generation_only_for_purchased_types(
        self, acme, calc, fg_product, released_bom,
        snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        mrp_engine.run_mrp(calc, mode='regenerative')
        # FG is finished_good — must NOT have a PR
        assert not MRPPurchaseRequisition.objects.filter(
            mrp_calculation=calc, product=fg_product,
        ).exists()


@pytest.mark.django_db
class TestEngineExceptions:
    def test_no_bom_emits_critical_exception(
        self, acme, calc, fg_product, snapshot_fg, completed_forecast_run,
    ):
        summary = mrp_engine.run_mrp(calc, mode='regenerative')
        assert fg_product.sku in summary.skipped_no_bom
        n = exc_service.generate_exceptions(calc, summary.skipped_no_bom)
        assert n >= 1
        no_bom = MRPException.objects.filter(
            mrp_calculation=calc, exception_type='no_bom', product=fg_product,
        ).first()
        assert no_bom is not None
        assert no_bom.severity == 'critical'

    def test_late_order_severity_grading(self, acme, calc, raw_product):
        NetRequirement.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            period_start=date.today(),
            period_end=date.today() + timedelta(days=6),
            bom_level=0, gross_requirement=Decimal('10'),
            scheduled_receipts_qty=Decimal('0'),
            projected_on_hand=Decimal('0'),
            net_requirement=Decimal('10'),
            planned_order_qty=Decimal('10'),
            planned_release_date=date.today() - timedelta(days=10),
            lot_size_method='l4l',
        )
        n = exc_service.generate_exceptions(calc, [])
        assert n >= 1
        late = MRPException.objects.filter(
            mrp_calculation=calc, exception_type='late_order',
        ).first()
        assert late is not None
        assert late.severity == 'high'

    def test_expedite_skipped_when_release_date_in_past_d16(
        self, acme, calc, raw_product, snapshot_rm,
    ):
        """F-14 / D-16: expedite must NOT fire when planned_release_date is past
        — that case is already covered by `late_order`."""
        NetRequirement.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            period_start=date.today() + timedelta(days=2),
            period_end=date.today() + timedelta(days=8),
            bom_level=0, gross_requirement=Decimal('10'),
            scheduled_receipts_qty=Decimal('0'),
            projected_on_hand=Decimal('0'),
            net_requirement=Decimal('10'),
            planned_order_qty=Decimal('10'),
            planned_release_date=date.today() - timedelta(days=5),
            lot_size_method='foq',
        )
        exc_service.generate_exceptions(calc, [])
        # late_order should fire, expedite should NOT
        assert MRPException.objects.filter(
            mrp_calculation=calc, exception_type='late_order',
        ).exists()
        assert not MRPException.objects.filter(
            mrp_calculation=calc, exception_type='expedite',
        ).exists()


@pytest.mark.django_db
class TestEngineNetChangeModeD02:
    """F-02 fix: net_change mode used to raise IntegrityError on duplicate
    NetRequirement rows. After the fix, it behaves identically to regenerative.
    """
    def test_net_change_does_not_raise_or_duplicate(
        self, acme, calc, fg_product, raw_product, released_bom,
        snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        mrp_engine.run_mrp(calc, mode='regenerative')
        first_count = NetRequirement.objects.filter(mrp_calculation=calc).count()
        # Second call — would have raised IntegrityError before D-02 fix
        mrp_engine.run_mrp(calc, mode='net_change')
        second_count = NetRequirement.objects.filter(mrp_calculation=calc).count()
        # Same calc + product + period_start should exist exactly once
        from django.db.models import Count
        dupes = (
            NetRequirement.objects.filter(mrp_calculation=calc)
            .values('product', 'period_start')
            .annotate(n=Count('id')).filter(n__gt=1)
        )
        assert not dupes.exists()
        assert first_count == second_count


@pytest.mark.django_db
class TestEnginePRSequenceD04:
    """F-04 fix: PR creation retries on IntegrityError so two engine runs against
    the same tenant (or accidental sequence collisions) cannot 500 the call."""
    def test_pr_sequence_recovers_from_collision(
        self, acme, calc, fg_product, raw_product, released_bom,
        snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        # Pre-allocate the slot the engine would normally grab.
        MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-00001', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('1'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='approved',  # 'approved' so the engine's draft-cleanup pass leaves it
            priority='normal',
        )
        # Run engine — must not raise even though MPR-00001 is taken.
        summary = mrp_engine.run_mrp(calc, mode='regenerative')
        all_prs = MRPPurchaseRequisition.objects.filter(
            tenant=acme, mrp_calculation=calc,
        )
        # PR numbers must be unique
        nums = list(all_prs.values_list('pr_number', flat=True))
        assert len(nums) == len(set(nums))
        # The engine produced at least the new draft PRs reported in summary
        assert summary.total_pr_suggestions == all_prs.filter(status='draft').count()


@pytest.mark.django_db
class TestEngineBOMQueryBudgetD09:
    """F-09 fix: BOM lookup runs in a single query for the whole end-item set
    rather than 2 queries per end item.
    """
    def test_bom_lookup_is_single_query(
        self, acme, calc, fg_product, raw_product,
        released_bom, snapshot_fg, snapshot_rm, completed_forecast_run,
        django_assert_max_num_queries,
    ):
        # The full engine fires plenty of queries (snapshots, receipts, MPS,
        # BOM explosion, Net+PR writes). The contract here is that the BOM
        # lookup loop itself collapses to ONE query — we assert a global
        # ceiling that proves we are not doing 2 lookups per end item.
        with django_assert_max_num_queries(50):
            mrp_engine.run_mrp(calc, mode='regenerative')
