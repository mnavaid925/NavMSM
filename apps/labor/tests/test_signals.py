"""Audit + cross-module signal tests, including the L-18 dispatch_uid presence guard."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db.models.signals import post_save, pre_save


REQUIRED_DISPATCH_UIDS = [
    # Audit factories
    'labor.labor.employee.pre_save',
    'labor.labor.employee.post_save',
    'labor.labor.leave.pre_save',
    'labor.labor.leave.post_save',
    'labor.labor.incentive_run.pre_save',
    'labor.labor.incentive_run.post_save',
    'labor.labor.period.pre_save',
    'labor.labor.period.post_save',
    'labor.labor.assessment.pre_save',
    'labor.labor.assessment.post_save',
    'labor.labor.training_plan.pre_save',
    'labor.labor.training_plan.post_save',
    'labor.labor.cert.pre_save',
    'labor.labor.cert.post_save',
    # Cross-module hooks
    'labor.timelog_to_attendance',
    'labor.timelog_to_booking',
    'labor.mwo_to_booking',
    'labor.report_to_incentive',
]


class TestL18DispatchUIDPresence:
    """Lesson L-18 - factory-built signal handlers must remain registered after
    apps.ready(). A weak=False bug would cause the closure to be GC'd and the
    handler silently dropped. This test runs after Django app loading so the
    receivers list is the production state.
    """
    def test_required_dispatch_uids_attached(self):
        # Django signal lookup_key is (dispatch_uid_str, sender_id_int) when
        # dispatch_uid was provided to connect(). The first element is the
        # dispatch_uid string we want to assert against.
        all_uids = set()
        for receiver_meta in pre_save.receivers + post_save.receivers:
            lookup_key = receiver_meta[0]
            if isinstance(lookup_key, tuple) and lookup_key:
                first = lookup_key[0]
                if isinstance(first, str):
                    all_uids.add(first)
        missing = [u for u in REQUIRED_DISPATCH_UIDS if u not in all_uids]
        assert not missing, f'Missing dispatch_uids: {missing}'


@pytest.mark.django_db
class TestCrossModuleHooks:
    def test_mwo_labor_creates_booking(self, acme, acme_admin, employee, cost_center):
        """eam.MWOLaborLog post_save -> indirect LaborBooking."""
        from apps.eam.models import Asset, MaintenanceWorkOrder, MWOLaborLog
        from django.utils import timezone
        # Link the user to the employee so the signal can resolve.
        employee.user = acme_admin
        employee.save()
        asset = Asset.objects.create(
            tenant=acme, name='X', cost_center=cost_center,
            criticality='medium', status='operational', is_active=True,
        )
        mwo = MaintenanceWorkOrder.objects.create(
            tenant=acme, asset=asset, wo_type='corrective', priority='medium',
            title='T', status='draft',
            reported_by=acme_admin, reported_at=timezone.now(),
        )
        # Provide a labor rate so the snapshot is non-zero.
        from apps.labor import models as L
        L.LaborRate.objects.create(
            tenant=acme, employee=employee, hourly_rate=Decimal('30'),
            overtime_multiplier=Decimal('1.50'),
            effective_from=date.today() - timedelta(days=30),
        )
        labor = MWOLaborLog.objects.create(
            tenant=acme, mwo=mwo, technician=acme_admin,
            started_at=timezone.now() - timedelta(hours=1),
            ended_at=timezone.now(), minutes=60,
            hourly_rate=Decimal('30'),
        )
        # Signal should have fired - one indirect booking now exists.
        bookings = L.LaborBooking.objects.filter(
            tenant=acme, source_mwo_labor=labor, kind='indirect',
        )
        assert bookings.count() == 1
        assert bookings.first().cost_center_id == cost_center.id

    def test_mwo_labor_idempotent(self, acme, acme_admin, employee, cost_center):
        """Re-saving an MWO labor log does NOT create a second booking."""
        from apps.eam.models import Asset, MaintenanceWorkOrder, MWOLaborLog
        from django.utils import timezone
        employee.user = acme_admin
        employee.save()
        asset = Asset.objects.create(
            tenant=acme, name='X', cost_center=cost_center,
            criticality='medium', status='operational', is_active=True,
        )
        mwo = MaintenanceWorkOrder.objects.create(
            tenant=acme, asset=asset, wo_type='corrective', priority='medium',
            title='T', status='draft',
            reported_by=acme_admin, reported_at=timezone.now(),
        )
        from apps.labor import models as L
        L.LaborRate.objects.create(
            tenant=acme, employee=employee, hourly_rate=Decimal('30'),
            overtime_multiplier=Decimal('1.50'),
            effective_from=date.today() - timedelta(days=30),
        )
        labor = MWOLaborLog.objects.create(
            tenant=acme, mwo=mwo, technician=acme_admin,
            started_at=timezone.now() - timedelta(hours=1),
            ended_at=timezone.now(), minutes=60,
            hourly_rate=Decimal('30'),
        )
        labor.save()  # second save - should not create a duplicate.
        assert L.LaborBooking.objects.filter(
            tenant=acme, source_mwo_labor=labor,
        ).count() == 1
