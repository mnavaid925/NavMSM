"""TenantAuditLog regression: verify the signal factories actually persist rows.

Closes the §1.7 / §6 D-09 gap noted in the SQA report — without these
tests, a regression in `_audit()` would silently drop audit events.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import models as U


pytestmark = [pytest.mark.django_db]


def _audit_qs():
    from apps.tenants.models import TenantAuditLog
    return TenantAuditLog.objects


def test_dr_event_status_transition_audited(acme, utility_type_electricity, acme_admin):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled', created_by=acme_admin,
    )
    e.status = 'active'
    e.save()
    qs = _audit_qs().filter(
        tenant_id=acme.id, target_type='DemandResponseEvent',
        target_id=str(e.pk), action='utility.dre.active',
    )
    assert qs.exists(), 'utility.dre.active audit row missing'


def test_dr_event_creation_audited(acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    qs = _audit_qs().filter(
        tenant_id=acme.id, target_type='DemandResponseEvent',
        target_id=str(e.pk), action='utility.dre.created',
    )
    assert qs.exists(), 'utility.dre.created audit row missing on first save'


def test_allocation_posted_flag_audited(acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter,
        share_pct=Decimal('100'),
    )
    a.is_posted_to_cost = True
    a.posted_at = timezone.now()
    a.save(update_fields=['is_posted_to_cost', 'posted_at'])
    qs = _audit_qs().filter(
        tenant_id=acme.id, target_type='UtilityAllocation',
        target_id=str(a.pk), action='utility.allocation.posted',
    )
    assert qs.exists(), 'utility.allocation.posted audit row missing'


def test_allocation_unposted_audited(acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter,
        share_pct=Decimal('100'), is_posted_to_cost=True,
        posted_at=timezone.now(),
    )
    # Flip false → fires unposted audit.
    a.is_posted_to_cost = False
    a.save(update_fields=['is_posted_to_cost'])
    qs = _audit_qs().filter(
        tenant_id=acme.id, target_type='UtilityAllocation',
        target_id=str(a.pk), action='utility.allocation.unposted',
    )
    assert qs.exists(), 'utility.allocation.unposted audit row missing'


def test_carbon_reversal_flag_audited(acme, acp_open, emission_factor_grid):
    c = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    c.is_reversal = True
    c.save(update_fields=['is_reversal'])
    qs = _audit_qs().filter(
        tenant_id=acme.id, target_type='CarbonEmission',
        target_id=str(c.pk), action='utility.carbon.reversed',
    )
    assert qs.exists(), 'utility.carbon.reversed audit row missing'


def test_audit_emit_failure_logs_warning(acme, utility_type_electricity, caplog):
    """D-09: audit emit failure logs a warning instead of swallowing silently.

    We force a failure by monkey-patching `TenantAuditLog.objects.create` to
    raise; the signal handler must log a warning rather than re-raise.
    """
    import logging

    from apps.tenants.models import TenantAuditLog

    orig_create = TenantAuditLog.objects.create

    def boom(*a, **kw):
        raise RuntimeError('synthetic audit failure')

    TenantAuditLog.objects.create = boom
    try:
        with caplog.at_level(logging.WARNING, logger='apps.utility.signals'):
            now = timezone.now()
            U.DemandResponseEvent.objects.create(
                tenant=acme, utility_type=utility_type_electricity,
                start_at=now, end_at=now + timedelta(hours=1),
                status='scheduled',
            )
        assert any('audit emit failed' in rec.getMessage() for rec in caplog.records), (
            f'expected a warning log; saw {[r.getMessage() for r in caplog.records]}'
        )
    finally:
        TenantAuditLog.objects.create = orig_create
