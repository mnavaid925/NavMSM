"""Pure-function service correctness."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.procurement import models as procm
from apps.procurement.services.blanket import consume_release, reverse_release
from apps.procurement.services.po_revision import next_revision_number, snapshot_po
from apps.procurement.services.scorecard import compute_scorecard


class _FakeEvent:
    """Lightweight stand-in for SupplierMetricEvent for pure-function tests."""

    def __init__(self, event_type, value=Decimal('0')):
        self.event_type = event_type
        self.value = value


class TestComputeScorecard:
    def test_all_on_time(self):
        events = [_FakeEvent('po_received_on_time')] * 5
        r = compute_scorecard(events)
        assert r.otd_pct == Decimal('100.00')

    def test_quality_mix(self):
        events = (
            [_FakeEvent('quality_pass')] * 9 + [_FakeEvent('quality_fail')]
        )
        r = compute_scorecard(events)
        assert r.quality_rating == Decimal('90.00')
        assert r.defect_rate_pct == Decimal('10.00')

    def test_overall_score_weighted(self):
        events = (
            [_FakeEvent('po_received_on_time')] * 4
            + [_FakeEvent('po_received_late', Decimal('3'))]
            + [_FakeEvent('quality_pass')] * 8
            + [_FakeEvent('quality_fail')] * 2
            + [_FakeEvent('response_received')] * 5
            + [_FakeEvent('price_variance', Decimal('5'))]
        )
        r = compute_scorecard(events)
        # 80% OTD * 0.40 + 80% Q * 0.40 + 100% Resp * 0.10 + 95 price_score * 0.10
        # = 32 + 32 + 10 + 9.5 = 83.5
        assert r.overall_score == Decimal('83.50')

    def test_no_events_zeros(self):
        r = compute_scorecard([])
        assert r.otd_pct == Decimal('0')
        assert r.overall_score == Decimal('0')


@pytest.mark.django_db
class TestSnapshotPO:
    def test_snapshot_round_trip(self, po):
        snap = snapshot_po(po)
        assert snap['po_number'] == po.po_number
        assert len(snap['lines']) == 1
        assert snap['lines'][0]['quantity'] == str(po.lines.first().quantity)

    def test_next_revision_number(self, acme, po, acme_admin):
        assert next_revision_number(po) == 1
        procm.PurchaseOrderRevision.objects.create(
            tenant=acme, po=po, revision_number=1,
            change_summary='first', changed_by=acme_admin,
            snapshot_json=snapshot_po(po),
        )
        assert next_revision_number(po) == 2


@pytest.mark.django_db
class TestConsumeRelease:
    def test_consume_updates_denorms(self, acme, supplier, cmp_product):
        today = timezone.now().date()
        bpo = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=60),
            total_committed_value=Decimal('1000'),
        )
        bol = procm.BlanketOrderLine.objects.create(
            tenant=acme, blanket_order=bpo, product=cmp_product,
            total_quantity=Decimal('100'),
            unit_of_measure='EA', unit_price=Decimal('5'),
        )
        rel = procm.ScheduleRelease.objects.create(
            tenant=acme, blanket_order=bpo, release_date=today, status='released',
        )
        procm.ScheduleReleaseLine.objects.create(
            tenant=acme, release=rel, blanket_order_line=bol,
            quantity=Decimal('10'),
        )
        consume_release(rel)
        bol.refresh_from_db()
        bpo.refresh_from_db()
        assert bol.consumed_quantity == Decimal('10')
        assert bpo.consumed_value == Decimal('50.00')

    def test_consume_blocks_overdraw(self, acme, supplier, cmp_product):
        today = timezone.now().date()
        bpo = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=60),
            total_committed_value=Decimal('1000'),
        )
        bol = procm.BlanketOrderLine.objects.create(
            tenant=acme, blanket_order=bpo, product=cmp_product,
            total_quantity=Decimal('5'), unit_of_measure='EA', unit_price=Decimal('5'),
        )
        rel = procm.ScheduleRelease.objects.create(
            tenant=acme, blanket_order=bpo, release_date=today, status='released',
        )
        procm.ScheduleReleaseLine.objects.create(
            tenant=acme, release=rel, blanket_order_line=bol,
            quantity=Decimal('50'),  # exceeds commitment
        )
        with pytest.raises(ValueError):
            consume_release(rel)

    def test_reverse_release_deducts(self, acme, supplier, cmp_product):
        today = timezone.now().date()
        bpo = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=60),
            total_committed_value=Decimal('1000'),
        )
        bol = procm.BlanketOrderLine.objects.create(
            tenant=acme, blanket_order=bpo, product=cmp_product,
            total_quantity=Decimal('100'),
            unit_of_measure='EA', unit_price=Decimal('5'),
        )
        rel = procm.ScheduleRelease.objects.create(
            tenant=acme, blanket_order=bpo, release_date=today, status='released',
        )
        procm.ScheduleReleaseLine.objects.create(
            tenant=acme, release=rel, blanket_order_line=bol,
            quantity=Decimal('10'),
        )
        consume_release(rel)
        reverse_release(rel)
        bol.refresh_from_db()
        bpo.refresh_from_db()
        assert bol.consumed_quantity == Decimal('0')
        assert bpo.consumed_value == Decimal('0')
