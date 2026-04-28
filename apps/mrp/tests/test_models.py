"""Model invariants, helper methods, and __str__ coverage."""
from decimal import Decimal

import pytest

from apps.mrp.models import (
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun,
)


@pytest.mark.django_db
class TestMRPCalculationHelpers:
    def test_is_editable_only_in_draft(self, calc):
        assert calc.is_editable() is True
        calc.status = 'running'
        assert calc.is_editable() is False
        calc.status = 'completed'
        assert calc.is_editable() is False

    def test_can_commit_only_when_completed(self, calc):
        for status in ('draft', 'running', 'failed', 'committed', 'discarded'):
            calc.status = status
            assert calc.can_commit() is False
        calc.status = 'completed'
        assert calc.can_commit() is True


@pytest.mark.django_db
class TestMRPRunHelpers:
    def _make_run(self, acme, calc, status='queued', run_type='regenerative'):
        return MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-T1', name='Test',
            run_type=run_type, status=status,
            mrp_calculation=calc,
        )

    def test_can_start_only_in_queued(self, acme, calc):
        run = self._make_run(acme, calc, status='queued')
        assert run.can_start() is True
        run.status = 'running'
        assert run.can_start() is False

    def test_can_apply_blocks_simulation(self, acme, calc):
        run = self._make_run(acme, calc, status='completed', run_type='simulation')
        assert run.can_apply() is False

    def test_can_apply_allows_completed_regenerative(self, acme, calc):
        run = self._make_run(acme, calc, status='completed', run_type='regenerative')
        assert run.can_apply() is True

    def test_can_discard_completed_or_failed(self, acme, calc):
        run = self._make_run(acme, calc, status='completed')
        assert run.can_discard() is True
        run.status = 'failed'
        assert run.can_discard() is True
        run.status = 'queued'
        assert run.can_discard() is False


@pytest.mark.django_db
class TestPRHelpers:
    def test_status_helpers(self, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='draft')
        assert pr.is_editable() is True
        assert pr.can_approve() is True
        assert pr.can_cancel() is True

        pr.status = 'approved'
        assert pr.is_editable() is False
        assert pr.can_approve() is False
        assert pr.can_cancel() is True

        pr.status = 'converted'
        assert pr.can_cancel() is False


@pytest.mark.django_db
class TestStrRepr:
    def test_calc_str(self, calc):
        assert calc.mrp_number in str(calc)
        assert calc.name in str(calc)

    def test_pr_str(self, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product)
        assert raw_product.sku in str(pr)

    def test_exception_str(self, acme, calc, raw_product):
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high',
            message='past due',
        )
        s = str(exc)
        assert 'Late Order' in s
        assert raw_product.sku in s
