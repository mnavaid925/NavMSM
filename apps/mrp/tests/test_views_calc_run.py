"""MRP Calculation list/detail and Run lifecycle (start → complete → apply).

Converts manual plan §4.4 (calc list), §4.5 (calc detail + run detail),
§4.11.2 RUN-01..RUN-07, and §4.13 NEG-07 / NEG-12.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.mrp.models import (
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun, MRPRunResult,
    NetRequirement,
)


@pytest.mark.django_db
class TestCalculationListDetail:
    def test_list_renders_seeded_calc(self, admin_client, calc):
        r = admin_client.get(reverse('mrp:calculation_list'))
        assert r.status_code == 200
        assert calc.mrp_number.encode() in r.content

    def test_detail_lists_nets_prs_excs(self, admin_client, acme, calc, raw_product):
        # Add a net req, a PR, and an exception so the detail page exercises all 3 sub-tables.
        NetRequirement.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            period_start=date.today(), period_end=date.today() + timedelta(days=6),
            bom_level=0, gross_requirement=Decimal('5'),
            scheduled_receipts_qty=Decimal('0'),
            projected_on_hand=Decimal('0'), net_requirement=Decimal('5'),
            planned_order_qty=Decimal('5'),
            planned_release_date=date.today(),
            lot_size_method='l4l',
        )
        MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-DET', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('5'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='draft', priority='normal',
        )
        MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='past due',
        )
        r = admin_client.get(reverse('mrp:calculation_detail', args=[calc.pk]))
        assert r.status_code == 200
        assert b'MPR-DET' in r.content


@pytest.mark.django_db
class TestRunCreate:
    def test_create_run_pair_atomic(self, admin_client, acme):
        today = date.today()
        r = admin_client.post(reverse('mrp:run_create'), {
            # MRPRunForm
            'name': 'Manual run #1',
            'run_type': 'regenerative',
            'commit_notes': '',
            # MRPCalculationForm (same POST, separate fields)
            'horizon_start': today.isoformat(),
            'horizon_end': (today + timedelta(days=28)).isoformat(),
            'time_bucket': 'week',
            'description': 'Auto-test',
        })
        assert r.status_code == 302
        run = MRPRun.objects.filter(tenant=acme).order_by('-created_at').first()
        assert run is not None
        assert run.status == 'queued'
        assert run.mrp_calculation is not None
        assert run.mrp_calculation.status == 'draft'

    def test_horizon_end_le_start_blocks_pair(self, admin_client, acme):
        today = date.today()
        r = admin_client.post(reverse('mrp:run_create'), {
            'name': 'Bad', 'run_type': 'regenerative', 'commit_notes': '',
            'horizon_start': today.isoformat(),
            'horizon_end': today.isoformat(),
            'time_bucket': 'week', 'description': '',
        })
        assert r.status_code == 200
        # Calc form rejects → no calc + no run created.
        assert not MRPRun.objects.filter(tenant=acme, name='Bad').exists()


@pytest.mark.django_db
class TestRunStart:
    def _queued_run(self, acme, calc):
        return MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-START',
            name='start-test', run_type='regenerative',
            status='queued', mrp_calculation=calc,
        )

    def test_start_completes_run(
        self, admin_client, acme, calc, fg_product, raw_product,
        released_bom, snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        run = self._queued_run(acme, calc)
        r = admin_client.post(reverse('mrp:run_start', args=[run.pk]))
        assert r.status_code == 302
        run.refresh_from_db()
        calc.refresh_from_db()
        assert run.status == 'completed'
        assert calc.status == 'completed'
        # Result row created
        assert MRPRunResult.objects.filter(run=run).exists()

    def test_start_when_not_queued_warns(self, admin_client, acme, calc):
        run = MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-DONE', name='x',
            run_type='regenerative', status='completed',
            mrp_calculation=calc,
        )
        r = admin_client.post(reverse('mrp:run_start', args=[run.pk]))
        assert r.status_code == 302
        run.refresh_from_db()
        assert run.status == 'completed'  # unchanged

    def test_start_engine_failure_marks_failed(
        self, admin_client, acme, calc, monkeypatch,
    ):
        run = self._queued_run(acme, calc)

        def boom(*a, **kw):
            raise RuntimeError('engine boom')
        from apps.mrp.services import mrp_engine
        monkeypatch.setattr(mrp_engine, 'run_mrp', boom)

        r = admin_client.post(reverse('mrp:run_start', args=[run.pk]))
        assert r.status_code == 302
        run.refresh_from_db()
        calc.refresh_from_db()
        assert run.status == 'failed'
        assert calc.status == 'failed'
        assert 'engine boom' in run.error_message


@pytest.mark.django_db
class TestRunNonIntPk:
    def test_non_numeric_pk_404(self, admin_client):
        # int converter rejects non-int — Django returns 404 (URL resolver).
        r = admin_client.get('/mrp/runs/abc/')
        assert r.status_code == 404


@pytest.mark.django_db
class TestRunFullLifecycle:
    """End-to-end: create run via form -> start -> apply (admin) -> verify
    everything ends with calc 'committed' and run 'applied'."""
    def test_create_start_apply(
        self, admin_client, acme, fg_product, raw_product,
        released_bom, snapshot_fg, snapshot_rm, completed_forecast_run,
    ):
        today = date.today()
        admin_client.post(reverse('mrp:run_create'), {
            'name': 'lifecycle', 'run_type': 'regenerative', 'commit_notes': '',
            'horizon_start': today.isoformat(),
            'horizon_end': (today + timedelta(days=28)).isoformat(),
            'time_bucket': 'week', 'description': '',
        })
        run = MRPRun.objects.filter(tenant=acme, name='lifecycle').get()
        admin_client.post(reverse('mrp:run_start', args=[run.pk]))
        run.refresh_from_db()
        assert run.status == 'completed'
        admin_client.post(reverse('mrp:run_apply', args=[run.pk]))
        run.refresh_from_db()
        run.mrp_calculation.refresh_from_db()
        assert run.status == 'applied'
        assert run.mrp_calculation.status == 'committed'
