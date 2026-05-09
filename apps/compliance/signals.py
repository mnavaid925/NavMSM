"""Module 13 - Compliance & Regulatory Management signals.

Wires:
    * Status-transition audit logging (mirrors apps.utility.signals factory
      pattern with weak=False per L-18). Action prefixes are
      ``compliance.<resource>.<status>``.
    * Cross-module hook: mes.AndonAlert(type='safety').post_save ->
      compliance.IncidentReport (idempotent on source_andon FK).

Audit emission writes ``meta=<payload>`` to ``tenants.TenantAuditLog`` —
NOT ``payload=`` (that's a different model's field). Audit failure is
logged at WARNING and never breaks a write path (mirrors L-19 pattern).
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.utils import timezone

from . import models as cm


_pre_status_snapshots: dict = {}
_log = logging.getLogger(__name__)


def _audit(action: str, instance, extra: dict | None = None):
    try:
        from apps.tenants.models import TenantAuditLog
    except ImportError:
        return
    if getattr(instance, 'tenant_id', None) is None:
        return
    payload = {'pk': instance.pk}
    if extra:
        payload.update(extra)
    try:
        TenantAuditLog.objects.create(
            tenant_id=instance.tenant_id,
            action=action,
            target_type=instance.__class__.__name__,
            target_id=str(instance.pk),
            meta=payload,
        )
    except Exception as exc:
        _log.warning(
            'compliance audit emit failed: action=%s target=%s pk=%s err=%s',
            action, instance.__class__.__name__, instance.pk, exc,
            exc_info=True,
        )


def _mk_status_signals(model_cls, action_prefix: str):
    """L-18: weak=False on every closure receiver."""

    def _pre(sender, instance, **kwargs):
        if not instance.pk:
            return
        try:
            prev = sender.all_objects.only('status').get(pk=instance.pk).status
        except sender.DoesNotExist:
            return
        _pre_status_snapshots[(sender, instance.pk)] = prev

    def _post(sender, instance, created, **kwargs):
        prev = _pre_status_snapshots.pop((sender, instance.pk), None)
        if created:
            _audit(
                f'compliance.{action_prefix}.created', instance,
                {'status': getattr(instance, 'status', None)},
            )
            return
        if prev is not None and prev != getattr(instance, 'status', None):
            _audit(
                f'compliance.{action_prefix}.{instance.status}',
                instance,
                {'previous_status': prev, 'status': instance.status},
            )

    pre_save.connect(
        _pre, sender=model_cls, weak=False,
        dispatch_uid=f'compliance.{action_prefix}.pre_save',
    )
    post_save.connect(
        _post, sender=model_cls, weak=False,
        dispatch_uid=f'compliance.{action_prefix}.post_save',
    )


# Audit registrations: every status-bearing model.
_mk_status_signals(cm.IncidentReport, 'incident')
_mk_status_signals(cm.RiskAssessment, 'risk_assessment')
_mk_status_signals(cm.SafetyAudit, 'safety_audit')
_mk_status_signals(cm.ComplianceDocument, 'document')
_mk_status_signals(cm.WasteManifest, 'waste_manifest')
_mk_status_signals(cm.ProductRecall, 'recall')
_mk_status_signals(cm.RecallNotice, 'recall_notice')


# ----------------------------------------------------------------------------
# Electronic signature audit (immutable post_save snapshot)
# ----------------------------------------------------------------------------

def _on_signature_save(sender, instance, created, **kwargs):
    if created:
        _audit(
            'compliance.signature.created', instance,
            {
                'document': instance.document.doc_number,
                'reason': instance.reason,
                'signer': str(instance.signer) if instance.signer else None,
            },
        )


post_save.connect(
    _on_signature_save, sender=cm.ElectronicSignature, weak=False,
    dispatch_uid='compliance.signature.post_save',
)


# ----------------------------------------------------------------------------
# Cross-module hook 1 — mes.AndonAlert(type='safety') -> IncidentReport
# ----------------------------------------------------------------------------

def _on_safety_andon(sender, instance, created, **kwargs):
    """Auto-create an IncidentReport when a safety AndonAlert fires.

    Idempotent on the partial unique constraint
    ``compliance_incident_unique_andon`` on ``IncidentReport.source_andon``.
    Silently skips when no ``incident_type`` with category='security' or
    'injury' is configured for the tenant — operators must seed at least
    one incident type before this hook can fire.
    """
    if not created:
        return
    if (instance.alert_type or '').lower() != 'safety':
        return
    if instance.tenant_id is None:
        return
    # Idempotency guard.
    if cm.IncidentReport.all_objects.filter(source_andon=instance).exists():
        return
    incident_type = cm.IncidentType.all_objects.filter(
        tenant_id=instance.tenant_id, is_active=True,
    ).order_by('code').first()
    if incident_type is None:
        return
    severity_map = {
        'low': 'low', 'medium': 'medium',
        'high': 'high', 'critical': 'critical',
    }
    sev = severity_map.get((instance.severity or '').lower(), 'medium')
    try:
        with transaction.atomic():
            description = (
                getattr(instance, 'message', '')
                or getattr(instance, 'title', '')
                or 'Auto-created from MES safety andon.'
            )
            title_prefix = (
                getattr(instance, 'alert_number', None)
                or getattr(instance, 'title', None)
                or instance.pk
            )
            cm.IncidentReport.all_objects.create(
                tenant_id=instance.tenant_id,
                incident_type=incident_type,
                title=f'Safety Andon: {title_prefix}',
                description=description,
                occurred_at=getattr(instance, 'raised_at', None) or timezone.now(),
                severity=sev,
                status='reported',
                source_andon=instance,
            )
    except Exception as exc:
        _log.warning(
            'compliance: safety andon -> incident auto-create failed: %s',
            exc, exc_info=True,
        )


def _connect_mes_hooks():
    try:
        from apps.mes.models import AndonAlert
    except ImportError:
        return
    post_save.connect(
        _on_safety_andon, sender=AndonAlert, weak=False,
        dispatch_uid='compliance.mes_andon_to_incident',
    )


_connect_mes_hooks()


# ----------------------------------------------------------------------------
# Cross-module hook 2 — qms.NCR(severity='critical') -> IncidentReport (C.6)
# ----------------------------------------------------------------------------

def _on_critical_ncr(sender, instance, created, **kwargs):
    """Auto-create an IncidentReport when a critical NCR is filed.

    QMS severity values are typically 'minor' / 'major' / 'critical'. We treat
    'critical' as warranting an EHS incident report because a critical
    quality nonconformance often correlates with a safety event (recalled
    lot in production, contaminated material released, etc.).

    Idempotent on the partial unique constraint
    ``compliance_incident_unique_ncr`` on ``IncidentReport.source_ncr``.
    Fires on creation AND on transition to 'critical' (in case severity is
    upgraded during investigation). Silently skips when no IncidentType is
    configured for the tenant.
    """
    if instance.tenant_id is None:
        return
    if (getattr(instance, 'severity', '') or '').lower() != 'critical':
        return
    # Idempotency guard.
    if cm.IncidentReport.all_objects.filter(source_ncr=instance).exists():
        return
    incident_type = cm.IncidentType.all_objects.filter(
        tenant_id=instance.tenant_id, is_active=True,
    ).order_by('code').first()
    if incident_type is None:
        return
    try:
        with transaction.atomic():
            ncr_number = getattr(instance, 'ncr_number', None) or instance.pk
            ncr_title = getattr(instance, 'title', '') or 'Critical NCR'
            ncr_description = getattr(instance, 'description', '') or (
                'Auto-created from critical QMS Non-Conformance Report.'
            )
            occurred = (
                getattr(instance, 'reported_at', None)
                or getattr(instance, 'created_at', None)
                or timezone.now()
            )
            cm.IncidentReport.all_objects.create(
                tenant_id=instance.tenant_id,
                incident_type=incident_type,
                title=f'Critical NCR: {ncr_number}',
                description=f'{ncr_title}\n\n{ncr_description}',
                occurred_at=occurred,
                severity='critical',
                status='reported',
                source_ncr=instance,
            )
    except Exception as exc:
        _log.warning(
            'compliance: critical NCR -> incident auto-create failed: %s',
            exc, exc_info=True,
        )


def _connect_qms_hooks():
    try:
        from apps.qms.models import NonConformanceReport
    except ImportError:
        return
    post_save.connect(
        _on_critical_ncr, sender=NonConformanceReport, weak=False,
        dispatch_uid='compliance.qms_ncr_to_incident',
    )


_connect_qms_hooks()


# ----------------------------------------------------------------------------
# Cross-module hook 3 — inventory.StockMovement on recalled lot -> leak (C.7)
# ----------------------------------------------------------------------------

def _on_stock_movement(sender, instance, created, **kwargs):
    """Detect outbound movements on a lot that is part of an active recall.

    Bumps `RecallAffectedLot.post_recall_movement_count` and stamps
    `last_leak_at` so the recall detail page can warn an operator. Service
    helper is in [apps/compliance/services/recall.py](services/recall.py)
    so the same logic can be invoked from a management command for backfill.
    """
    if not created:
        return
    from apps.compliance.services.recall import on_outbound_movement
    on_outbound_movement(instance)


def _connect_inventory_hooks():
    try:
        from apps.inventory.models import StockMovement
    except ImportError:
        return
    post_save.connect(
        _on_stock_movement, sender=StockMovement, weak=False,
        dispatch_uid='compliance.inventory_movement_recall_leak',
    )


_connect_inventory_hooks()
