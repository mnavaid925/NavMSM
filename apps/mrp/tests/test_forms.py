"""Form validation tests — every clean() branch covered.

Includes regression coverage for:
    - L-01 (tenant duplicate guard)
    - F-12 / D-06 (resolution_notes required on resolve flow)
    - F-13 / D-14 (weekly seasonality index > 52)
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.mrp.forms import (
    ForecastModelForm, InventorySnapshotForm, MRPCalculationForm,
    MRPExceptionResolveForm, MRPPurchaseRequisitionForm,
    SeasonalityProfileForm,
)
from apps.mrp.models import ForecastModel, InventorySnapshot, SeasonalityProfile


# ---------------- ForecastModelForm ----------------

@pytest.mark.django_db
class TestForecastModelForm:
    def test_create_happy_path(self, acme):
        form = ForecastModelForm(
            data={
                'name': 'New SMA', 'description': '',
                'method': 'moving_avg', 'params': '{}',
                'period_type': 'week', 'horizon_periods': 12,
                'is_active': True,
            },
            tenant=acme,
        )
        assert form.is_valid(), form.errors

    def test_duplicate_name_blocked_l01(self, acme, forecast_model):
        form = ForecastModelForm(
            data={
                'name': forecast_model.name, 'description': '',
                'method': 'moving_avg', 'params': '{}',
                'period_type': 'week', 'horizon_periods': 12,
                'is_active': True,
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'name' in form.errors


# ---------------- SeasonalityProfileForm ----------------

@pytest.mark.django_db
class TestSeasonalityForm:
    def test_monthly_index_over_12_blocked(self, acme, fg_product):
        form = SeasonalityProfileForm(
            data={
                'product': fg_product.pk,
                'period_type': 'month', 'period_index': 13,
                'seasonal_index': '1.0', 'notes': '',
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'period_index' in form.errors

    def test_weekly_index_over_52_blocked_d14(self, acme, fg_product):
        """F-13 / D-14 fix: weekly index > 52 must surface as a friendly form error."""
        form = SeasonalityProfileForm(
            data={
                'product': fg_product.pk,
                'period_type': 'week', 'period_index': 53,
                'seasonal_index': '1.0', 'notes': '',
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'period_index' in form.errors

    def test_duplicate_blocked_l01(self, acme, fg_product):
        SeasonalityProfile.objects.create(
            tenant=acme, product=fg_product,
            period_type='month', period_index=1,
            seasonal_index=Decimal('1.0'),
        )
        form = SeasonalityProfileForm(
            data={
                'product': fg_product.pk,
                'period_type': 'month', 'period_index': 1,
                'seasonal_index': '1.0', 'notes': '',
            },
            tenant=acme,
        )
        assert not form.is_valid()


# ---------------- InventorySnapshotForm ----------------

@pytest.mark.django_db
class TestInventoryForm:
    def _payload(self, product, **overrides):
        base = {
            'product': product.pk,
            'on_hand_qty': '5', 'safety_stock': '2', 'reorder_point': '10',
            'lead_time_days': 7, 'lot_size_method': 'l4l',
            'lot_size_value': '0', 'lot_size_max': '0',
            'as_of_date': date.today().isoformat(), 'notes': '',
        }
        base.update(overrides)
        return base

    def test_foq_zero_value_rejected(self, acme, fg_product):
        form = InventorySnapshotForm(
            data=self._payload(fg_product, lot_size_method='foq', lot_size_value='0'),
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'lot_size_value' in form.errors

    def test_min_max_max_le_min_rejected(self, acme, fg_product):
        form = InventorySnapshotForm(
            data=self._payload(
                fg_product, lot_size_method='min_max',
                lot_size_value='50', lot_size_max='50',
            ),
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'lot_size_max' in form.errors

    def test_duplicate_product_blocked_l01(self, acme, fg_product, snapshot_fg):
        form = InventorySnapshotForm(
            data=self._payload(fg_product),
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'product' in form.errors


# ---------------- MRPCalculationForm ----------------

@pytest.mark.django_db
class TestCalculationForm:
    def test_horizon_end_must_be_after_start(self, acme):
        today = date.today()
        form = MRPCalculationForm(
            data={
                'name': 'X', 'horizon_start': today.isoformat(),
                'horizon_end': today.isoformat(),
                'time_bucket': 'week', 'description': '',
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'horizon_end' in form.errors


# ---------------- MRPPurchaseRequisitionForm ----------------

@pytest.mark.django_db
class TestPRForm:
    def test_release_after_required_rejected(self, acme, raw_product):
        form = MRPPurchaseRequisitionForm(
            data={
                'product': raw_product.pk, 'quantity': '5',
                'required_by_date': date.today().isoformat(),
                'suggested_release_date': (date.today() + timedelta(days=3)).isoformat(),
                'priority': 'normal', 'notes': '',
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'suggested_release_date' in form.errors


# ---------------- MRPExceptionResolveForm ----------------

@pytest.mark.django_db
class TestResolveForm:
    def test_empty_notes_blocked_d06(self, acme, calc, raw_product):
        """F-12 / D-06: resolve flow now requires a non-empty resolution note."""
        from apps.mrp.models import MRPException
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='m',
        )
        form = MRPExceptionResolveForm(data={'resolution_notes': '   '}, instance=exc)
        assert not form.is_valid()
        assert 'resolution_notes' in form.errors

    def test_non_empty_notes_accepted(self, acme, calc, raw_product):
        from apps.mrp.models import MRPException
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='m',
        )
        form = MRPExceptionResolveForm(
            data={'resolution_notes': 'Resolved manually.'}, instance=exc,
        )
        assert form.is_valid(), form.errors


# ---------------- D-19 — obsolete product / MPS no longer locks edits ----------------

@pytest.mark.django_db
class TestObsoleteRefEditableD19:
    """Found while walking the manual test plan: any form that filtered
    `Product.objects.exclude(status='obsolete')` (or `MasterProductionSchedule`)
    locked editing of records whose referenced row went obsolete after creation.
    The `_scoped_choices` helper now pins the existing instance value into the
    queryset on edit while still hiding obsolete rows on create."""

    def _payload_snapshot(self, product):
        return {
            'product': product.pk,
            'on_hand_qty': '5', 'safety_stock': '1', 'reorder_point': '2',
            'lead_time_days': 7, 'lot_size_method': 'l4l',
            'lot_size_value': '0', 'lot_size_max': '0',
            'as_of_date': date.today().isoformat(), 'notes': '',
        }

    def test_inventory_edit_works_when_product_obsolete(
        self, acme, fg_product, snapshot_fg,
    ):
        # Make the referenced product obsolete after the snapshot exists.
        fg_product.status = 'obsolete'
        fg_product.save()
        form = InventorySnapshotForm(
            data=self._payload_snapshot(fg_product),
            instance=snapshot_fg, tenant=acme,
        )
        assert form.is_valid(), form.errors

    def test_inventory_create_still_excludes_obsolete(self, acme, fg_product):
        fg_product.status = 'obsolete'
        fg_product.save()
        form = InventorySnapshotForm(
            data=self._payload_snapshot(fg_product),
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'product' in form.errors

    def test_seasonality_edit_works_when_product_obsolete(
        self, acme, fg_product,
    ):
        sp = SeasonalityProfile.objects.create(
            tenant=acme, product=fg_product,
            period_type='month', period_index=3,
            seasonal_index=Decimal('1.05'),
        )
        fg_product.status = 'obsolete'
        fg_product.save()
        form = SeasonalityProfileForm(
            data={
                'product': fg_product.pk,
                'period_type': 'month', 'period_index': 3,
                'seasonal_index': '1.05', 'notes': '',
            },
            instance=sp, tenant=acme,
        )
        assert form.is_valid(), form.errors

    def test_pr_edit_works_when_product_obsolete(
        self, acme, calc, raw_product, make_pr,
    ):
        from datetime import timedelta
        pr = make_pr(acme, calc, raw_product)
        raw_product.status = 'obsolete'
        raw_product.save()
        form = MRPPurchaseRequisitionForm(
            data={
                'product': raw_product.pk, 'quantity': '10',
                'required_by_date': (date.today() + timedelta(days=14)).isoformat(),
                'suggested_release_date': (date.today() + timedelta(days=7)).isoformat(),
                'priority': 'normal', 'notes': '',
            },
            instance=pr, tenant=acme,
        )
        assert form.is_valid(), form.errors
