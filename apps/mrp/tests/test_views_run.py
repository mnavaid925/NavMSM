"""MRP Run lifecycle tests — RBAC + atomic apply + delete protection."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.mrp.models import MRPCalculation, MRPRun


def _make_run(acme, calc, *, status='completed', run_type='regenerative', run_number='MRPRUN-T1'):
    return MRPRun.objects.create(
        tenant=acme, run_number=run_number, name='Test',
        run_type=run_type, status=status,
        mrp_calculation=calc,
    )


@pytest.mark.django_db
class TestRunApply:
    def test_admin_can_apply_completed_regenerative(self, admin_client, acme, calc):
        # Calc must be completed for run.can_apply()
        MRPCalculation.objects.filter(pk=calc.pk).update(status='completed')
        run = _make_run(acme, calc, status='completed', run_type='regenerative')
        r = admin_client.post(reverse('mrp:run_apply', args=[run.pk]))
        assert r.status_code == 302
        run.refresh_from_db()
        calc.refresh_from_db()
        assert run.status == 'applied'
        assert calc.status == 'committed'
        assert calc.committed_at is not None

    def test_apply_simulation_blocked(self, admin_client, acme, calc):
        run = _make_run(acme, calc, status='completed', run_type='simulation')
        admin_client.post(reverse('mrp:run_apply', args=[run.pk]))
        run.refresh_from_db()
        assert run.status == 'completed'

    def test_staff_cannot_apply_d01(self, staff_client, acme, calc):
        MRPCalculation.objects.filter(pk=calc.pk).update(status='completed')
        run = _make_run(acme, calc, status='completed', run_type='regenerative')
        r = staff_client.post(reverse('mrp:run_apply', args=[run.pk]))
        assert r.status_code == 302
        run.refresh_from_db()
        assert run.status == 'completed'  # NOT applied

    def test_concurrent_apply_idempotent(self, admin_client, acme, calc):
        """Second Apply request must be a no-op once the first has flipped the row."""
        MRPCalculation.objects.filter(pk=calc.pk).update(status='completed')
        run = _make_run(acme, calc, status='completed', run_type='regenerative')
        admin_client.post(reverse('mrp:run_apply', args=[run.pk]))
        # Second Apply
        r2 = admin_client.post(reverse('mrp:run_apply', args=[run.pk]))
        assert r2.status_code == 302
        run.refresh_from_db()
        assert run.status == 'applied'


@pytest.mark.django_db
class TestRunDiscard:
    def test_admin_can_discard_completed(self, admin_client, acme, calc):
        run = _make_run(acme, calc, status='completed', run_type='regenerative')
        admin_client.post(reverse('mrp:run_discard', args=[run.pk]))
        run.refresh_from_db()
        calc.refresh_from_db()
        assert run.status == 'discarded'
        assert calc.status == 'discarded'

    def test_staff_cannot_discard_d01(self, staff_client, acme, calc):
        run = _make_run(acme, calc, status='completed')
        staff_client.post(reverse('mrp:run_discard', args=[run.pk]))
        run.refresh_from_db()
        assert run.status == 'completed'


@pytest.mark.django_db
class TestRunDelete:
    def test_applied_run_undeletable(self, admin_client, acme, calc):
        run = _make_run(acme, calc, status='applied')
        admin_client.post(reverse('mrp:run_delete', args=[run.pk]))
        assert MRPRun.objects.filter(pk=run.pk).exists()


@pytest.mark.django_db
class TestCalculationDelete:
    def test_calc_delete_blocked_when_runs_exist_d05(self, admin_client, acme, calc):
        """F-05 / D-05: deleting a calc with runs must surface a friendly error
        rather than silently cascading run history away."""
        _make_run(acme, calc, status='completed')
        r = admin_client.post(reverse('mrp:calculation_delete', args=[calc.pk]))
        assert r.status_code == 302
        # ProtectedError caught by view; calc still exists
        assert MRPCalculation.objects.filter(pk=calc.pk).exists()

    def test_calc_delete_allowed_when_no_runs(self, admin_client, acme, calc):
        admin_client.post(reverse('mrp:calculation_delete', args=[calc.pk]))
        assert not MRPCalculation.objects.filter(pk=calc.pk).exists()

    def test_committed_calc_undeletable(self, admin_client, acme, calc):
        MRPCalculation.objects.filter(pk=calc.pk).update(status='committed')
        admin_client.post(reverse('mrp:calculation_delete', args=[calc.pk]))
        assert MRPCalculation.objects.filter(pk=calc.pk).exists()

    def test_staff_cannot_delete_calc_d01(self, staff_client, acme, calc):
        staff_client.post(reverse('mrp:calculation_delete', args=[calc.pk]))
        assert MRPCalculation.objects.filter(pk=calc.pk).exists()
