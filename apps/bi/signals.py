"""Module 16 - BI signals.

Two responsibilities:

    1. Audit factory (Lesson L-18: ``weak=False`` + unique ``dispatch_uid``
       per model) mirroring ``apps/iot/signals.py``.
    2. Internal cross-module hook on ``cost.AccountingPeriod`` going to
       ``status='closed'`` to refresh all active ``KPISnapshot`` rows for
       the period (best-effort, swallows exceptions so closing a period
       never fails because of BI side-effects).
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from . import models


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit factory (L-18 — weak=False + unique dispatch_uid per model).
# ---------------------------------------------------------------------------

AUDITED_MODELS = (
    models.KPIDefinition,
    models.KPIDashboard,
    models.KPIWidget,
    models.ReportDefinition,
    models.ReportRun,
    models.PredictiveModel,
    models.PredictionRun,
    models.DataMart,
    models.ReportSchedule,
    models.ReportDelivery,
)


def _make_audit_handler(model_cls, action_prefix):
    def _handler(sender, instance, created, **kwargs):
        if not getattr(instance, 'tenant_id', None):
            return
        try:
            from apps.tenants.models import TenantAuditLog
        except Exception:  # noqa: BLE001
            return
        action = f'{action_prefix}.{"created" if created else "updated"}'
        try:
            TenantAuditLog.objects.create(
                tenant=instance.tenant,
                action=action,
                meta={'pk': instance.pk, 'model': sender.__name__},
            )
        except Exception:  # noqa: BLE001
            logger.warning('bi audit emit failed for %s pk=%s', sender.__name__, instance.pk)
            return
    return _handler


for _model in AUDITED_MODELS:
    _audit_handler = _make_audit_handler(_model, f'bi.{_model.__name__}')
    post_save.connect(
        _audit_handler, sender=_model,
        weak=False,
        dispatch_uid=f'bi_audit_{_model.__name__}',
    )


# ---------------------------------------------------------------------------
# Internal hook: refresh KPI snapshots when a cost period closes.
# ---------------------------------------------------------------------------

try:
    from apps.cost.models import AccountingPeriod  # noqa: F401
    HAS_COST = True
except Exception:  # noqa: BLE001
    HAS_COST = False


if HAS_COST:
    @receiver(post_save, sender='cost.AccountingPeriod',
              dispatch_uid='bi_refresh_kpis_on_period_close', weak=False)
    def _refresh_kpis_on_period_close(sender, instance, created, **kwargs):
        if created or getattr(instance, 'status', '') != 'closed':
            return
        try:
            from .services.kpi import refresh_snapshot
            tenant = instance.tenant
            qs = models.KPIDefinition.all_objects.filter(tenant=tenant, is_active=True)
            for definition in qs:
                try:
                    refresh_snapshot(
                        definition,
                        period_start=instance.period_start,
                        period_end=instance.period_end,
                        scope_type='tenant',
                        scope_pk=None,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        'bi KPI refresh skipped for %s on tenant %s period %s',
                        definition.code, tenant_id_of(tenant), instance.pk,
                    )
        except Exception:  # noqa: BLE001
            logger.warning('bi period-close refresh handler crashed')


def tenant_id_of(t):
    return getattr(t, 'pk', None)
