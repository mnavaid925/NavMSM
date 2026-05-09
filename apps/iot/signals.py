"""Module 15 - IoT signal handlers.

Hooks (all idempotent; pre_delete reversal counterparts paired):

    1. iot.IoTReading.post_save     -> iot.StreamMetric (denorm refresh)
    2. iot.IoTReading.post_save     -> eam.ConditionReading (when tag has
                                       condition_point set)
    3. iot.IoTReading.post_save     -> iot.AnomalyDetection (rule eval)
    4. iot.AnomalyDetection.post_save -> iot.AlertNotification (per channel)
    5. iot.AnomalyDetection.post_save -> mes.AndonAlert (when severity>=high
                                          and rule has 'mes_andon' channel)
    6. iot.AnomalyDetection.post_save -> eam.FailurePrediction (severity=critical
                                          and tag.condition_point set)
    7. mes.ProductionReport.post_save -> iot.OEEPeriod denorm refresh
    8. eam.DowntimeEvent.post_save  -> iot.MachineStateLog (idempotent)

Also wires an audit factory for the 8 status-tracked models. Per Lesson L-18
the factory uses ``post_save.connect(..., weak=False)`` so the closures are
not garbage-collected after ``apps.ready()`` finishes.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from . import models


# ============================================================================
# Hook 1: IoTReading.post_save -> StreamMetric refresh
# ============================================================================

@receiver(post_save, sender=models.IoTReading, dispatch_uid='iot_reading_stream_metric')
def _iot_reading_to_stream_metric(sender, instance, created, **kwargs):
    if not instance.tenant_id or not instance.device_tag_id:
        return
    tag = instance.device_tag
    metric, _ = models.StreamMetric.objects.get_or_create(
        tenant=instance.tenant, device_tag=tag,
    )
    cutoff = timezone.now() - timedelta(hours=24)
    qs = models.IoTReading.objects.filter(
        tenant=instance.tenant, device_tag=tag, timestamp__gte=cutoff,
        value_numeric__isnull=False,
    )
    values = [r.value_numeric for r in qs.only('value_numeric')]
    metric.latest_value = instance.value_numeric
    metric.latest_timestamp = instance.timestamp
    metric.count_24h = len(values)
    if values:
        metric.last_24h_min = min(values)
        metric.last_24h_max = max(values)
        metric.last_24h_avg = (sum(values) / Decimal(len(values))).quantize(Decimal('0.0001'))
    metric.save()


# ============================================================================
# Hook 2: IoTReading.post_save -> eam.ConditionReading
# ============================================================================

@receiver(post_save, sender=models.IoTReading, dispatch_uid='iot_reading_to_condition_reading')
def _iot_reading_to_condition(sender, instance, created, **kwargs):
    if not created or not instance.tenant_id:
        return
    tag = instance.device_tag
    if tag is None or tag.condition_point_id is None:
        return
    if instance.value_numeric is None:
        return
    try:
        from apps.eam import models as eam_models
    except Exception:  # noqa: BLE001
        return
    if not hasattr(eam_models.ConditionReading, 'source_iot_reading'):
        return
    if eam_models.ConditionReading.objects.filter(
        tenant=instance.tenant, source_iot_reading=instance,
    ).exists():
        return
    with transaction.atomic():
        eam_models.ConditionReading.objects.create(
            tenant=instance.tenant,
            point=tag.condition_point,
            reading_value=instance.value_numeric,
            recorded_at=instance.timestamp,
            source_iot_reading=instance,
        )


@receiver(pre_delete, sender=models.IoTReading, dispatch_uid='iot_reading_to_condition_reverse')
def _iot_reading_condition_reverse(sender, instance, **kwargs):
    try:
        from apps.eam import models as eam_models
    except Exception:  # noqa: BLE001
        return
    if not hasattr(eam_models.ConditionReading, 'source_iot_reading'):
        return
    eam_models.ConditionReading.objects.filter(
        tenant=instance.tenant, source_iot_reading=instance,
    ).delete()


# ============================================================================
# Hook 3: IoTReading.post_save -> AnomalyDetection
# ============================================================================

def _rule_scope_filter(tag):
    """Build the Q filter that matches rules whose scope covers ``tag``."""
    from django.db.models import Q
    q = Q(device_tag=tag)
    if tag.device_id:
        q |= Q(scope_device=tag.device)
    if tag.device and tag.device.asset_id:
        q |= Q(scope_asset=tag.device.asset)
    return q


@receiver(post_save, sender=models.IoTReading, dispatch_uid='iot_reading_anomaly_eval')
def _iot_reading_anomaly_eval(sender, instance, created, **kwargs):
    if not created or not instance.tenant_id:
        return
    if instance.value_numeric is None:
        return
    from .services import anomaly as anomaly_svc
    tag = instance.device_tag
    rules = list(
        models.AlertRule.objects.filter(tenant=instance.tenant, is_active=True)
        .filter(_rule_scope_filter(tag))
    )
    if not rules:
        return
    cutoff = instance.timestamp - timedelta(seconds=3600)
    history = list(
        models.IoTReading.objects.filter(
            tenant=instance.tenant, device_tag=tag,
            timestamp__lt=instance.timestamp, timestamp__gte=cutoff,
            value_numeric__isnull=False,
        ).order_by('timestamp').values_list('value_numeric', flat=True)
    )
    for rule in rules:
        cool_cutoff = instance.timestamp - timedelta(seconds=rule.cooldown_seconds or 0)
        if models.AnomalyDetection.objects.filter(
            tenant=instance.tenant, rule=rule, detected_at__gte=cool_cutoff,
        ).exists():
            continue
        matched, baseline, deviation = anomaly_svc.evaluate_rule(rule, instance, history)
        if not matched:
            continue
        if models.AnomalyDetection.objects.filter(
            tenant=instance.tenant, rule=rule, source_reading=instance,
        ).exists():
            continue
        models.AnomalyDetection.objects.create(
            tenant=instance.tenant,
            rule=rule,
            source_reading=instance,
            detected_at=instance.timestamp,
            value=instance.value_numeric,
            baseline_value=baseline,
            deviation=deviation,
            severity=rule.severity,
            status='new',
        )


# ============================================================================
# Hook 4-6: AnomalyDetection.post_save fanouts
# ============================================================================

@receiver(post_save, sender=models.AnomalyDetection, dispatch_uid='iot_detection_fanout')
def _detection_fanout(sender, instance, created, **kwargs):
    if not created or not instance.tenant_id:
        return
    rule = instance.rule
    channels = rule.channel_list()
    for ch in channels:
        if models.AlertNotification.objects.filter(
            tenant=instance.tenant, detection=instance, channel=ch,
        ).exists():
            continue
        models.AlertNotification.objects.create(
            tenant=instance.tenant, detection=instance, channel=ch,
            status='queued', sent_at=None,
        )

    if 'mes_andon' in channels and instance.severity in ('high', 'critical'):
        try:
            from apps.mes import models as mes_models
        except Exception:  # noqa: BLE001
            mes_models = None
        if mes_models and hasattr(mes_models.AndonAlert, 'source_anomaly'):
            if not mes_models.AndonAlert.objects.filter(
                tenant=instance.tenant, source_anomaly=instance,
            ).exists():
                # AndonAlert.work_center is PROTECT/non-null. For IoT-spawned
                # alerts we pick the first work center for the tenant; if none
                # exists we silently skip (no point creating an alert that
                # can't be saved).
                from apps.pps.models import WorkCenter
                wc = WorkCenter.objects.filter(tenant=instance.tenant).first()
                if wc is not None:
                    with transaction.atomic():
                        # Compute next AND- sequence (mirrors apps/mes/views.py).
                        last_num = (
                            mes_models.AndonAlert.objects
                            .filter(tenant=instance.tenant, alert_number__startswith='AND-')
                            .order_by('-alert_number').values_list('alert_number', flat=True)
                            .first()
                        )
                        next_n = 1
                        if last_num:
                            try:
                                next_n = int(last_num.split('-')[-1]) + 1
                            except (ValueError, IndexError):
                                next_n = 1
                        mes_models.AndonAlert.objects.create(
                            tenant=instance.tenant,
                            alert_number=f'AND-{next_n:05d}',
                            alert_type='equipment',
                            severity=instance.severity,
                            title=f'IoT anomaly: {rule.name}',
                            message=f'Detection {instance.detection_number}: '
                                    f'value={instance.value} baseline={instance.baseline_value}.',
                            work_center=wc,
                            raised_at=instance.detected_at,
                            status='open',
                            source_anomaly=instance,
                        )

    if instance.severity == 'critical':
        tag = instance.source_reading.device_tag if instance.source_reading_id else None
        if tag is not None and tag.condition_point_id is not None:
            try:
                from apps.eam import models as eam_models
            except Exception:  # noqa: BLE001
                eam_models = None
            if eam_models and hasattr(eam_models.FailurePrediction, 'source_anomaly'):
                if not eam_models.FailurePrediction.objects.filter(
                    tenant=instance.tenant, source_anomaly=instance,
                ).exists():
                    asset = getattr(tag.condition_point, 'asset', None)
                    if asset is not None:
                        with transaction.atomic():
                            from decimal import Decimal as _D
                            eam_models.FailurePrediction.objects.create(
                                tenant=instance.tenant,
                                asset=asset,
                                summary=f'IoT anomaly {instance.detection_number}: {rule.name}',
                                recommended_action='Investigate the source IoT reading and inspect the asset.',
                                confidence_pct=_D('70'),
                                status='open',
                                source_anomaly=instance,
                            )


@receiver(pre_delete, sender=models.AnomalyDetection, dispatch_uid='iot_detection_reverse')
def _detection_reverse(sender, instance, **kwargs):
    try:
        from apps.mes import models as mes_models
        if hasattr(mes_models.AndonAlert, 'source_anomaly'):
            mes_models.AndonAlert.objects.filter(
                tenant=instance.tenant, source_anomaly=instance,
            ).delete()
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.eam import models as eam_models
        if hasattr(eam_models.FailurePrediction, 'source_anomaly'):
            eam_models.FailurePrediction.objects.filter(
                tenant=instance.tenant, source_anomaly=instance,
            ).delete()
    except Exception:  # noqa: BLE001
        pass


# ============================================================================
# Hook 7: mes.ProductionReport.post_save -> OEEPeriod refresh
# ============================================================================

def _connect_mes_production_report():
    try:
        from apps.mes.models import ProductionReport
    except Exception:  # noqa: BLE001
        return

    def _on_production_report_saved(sender, instance, created, **kwargs):
        if not created or not getattr(instance, 'tenant_id', None):
            return
        op = getattr(instance, 'operation', None)
        if op is None:
            return
        wo = getattr(op, 'work_order', None)
        po = getattr(wo, 'production_order', None) if wo is not None else None
        asset = None
        if po is not None and hasattr(po, 'product') and po.product is not None:
            try:
                from apps.eam import models as eam_models
                cc = getattr(po.product, 'cost_center', None)
                if cc is not None:
                    asset = eam_models.Asset.objects.filter(
                        tenant=instance.tenant, cost_center=cc,
                    ).first()
            except Exception:  # noqa: BLE001
                asset = None
        if asset is None:
            return
        from .services import oee as oee_svc
        period_date = (instance.reported_at or timezone.now()).date()
        with transaction.atomic():
            period, _ = models.OEEPeriod.objects.get_or_create(
                tenant=instance.tenant, asset=asset, shift=None,
                period_date=period_date,
            )
            try:
                oee_svc.recompute_period(period)
            except Exception:  # noqa: BLE001
                pass

    post_save.connect(
        _on_production_report_saved, sender=ProductionReport,
        weak=False, dispatch_uid='iot_oee_from_mes_production_report',
    )


_connect_mes_production_report()


# ============================================================================
# Hook 8: eam.DowntimeEvent.post_save -> MachineStateLog
# ============================================================================

def _connect_eam_downtime_event():
    try:
        from apps.eam.models import DowntimeEvent
    except Exception:  # noqa: BLE001
        return

    def _on_downtime_saved(sender, instance, created, **kwargs):
        if not created or not getattr(instance, 'tenant_id', None):
            return
        if not getattr(instance, 'asset_id', None):
            return
        if models.MachineStateLog.objects.filter(
            tenant=instance.tenant, source_downtime=instance,
        ).exists():
            return
        with transaction.atomic():
            models.MachineStateLog.objects.create(
                tenant=instance.tenant,
                asset=instance.asset,
                state='down',
                started_at=instance.start_at,
                ended_at=instance.end_at,
                source='eam_downtime',
                source_downtime=instance,
            )

    def _on_downtime_pre_delete(sender, instance, **kwargs):
        models.MachineStateLog.objects.filter(
            tenant=instance.tenant, source_downtime=instance,
        ).delete()

    post_save.connect(
        _on_downtime_saved, sender=DowntimeEvent,
        weak=False, dispatch_uid='iot_state_from_eam_downtime',
    )
    pre_delete.connect(
        _on_downtime_pre_delete, sender=DowntimeEvent,
        weak=False, dispatch_uid='iot_state_from_eam_downtime_reverse',
    )


_connect_eam_downtime_event()


# ============================================================================
# Audit factory (Lesson L-18: weak=False or hoist to module scope).
# ============================================================================

AUDITED_MODELS = (
    models.Device,
    models.DeviceBroker,
    models.DeviceTag,
    models.DigitalTwin,
    models.TwinSimulationScenario,
    models.OEEPeriod,
    models.AlertRule,
    models.AnomalyDetection,
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
                metadata={'pk': instance.pk, 'model': sender.__name__},
            )
        except Exception:  # noqa: BLE001
            return
    return _handler


for _model in AUDITED_MODELS:
    _audit_handler = _make_audit_handler(_model, f'iot.{_model.__name__}')
    post_save.connect(
        _audit_handler, sender=_model,
        weak=False, dispatch_uid=f'iot_audit_{_model.__name__}',
    )
