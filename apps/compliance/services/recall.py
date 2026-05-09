"""Sub-module 13.5 services - recall lifecycle + traceability rollups."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.compliance import models


def recompute_affected_quantity(recall):
    """Sum across affected lots; persist on the parent ProductRecall."""
    total = (
        models.RecallAffectedLot.all_objects
        .filter(recall=recall)
        .aggregate(t=Sum('affected_quantity'))
        .get('t') or Decimal('0')
    )
    recovered = (
        models.RecallAffectedLot.all_objects
        .filter(recall=recall)
        .aggregate(t=Sum('recovered_quantity'))
        .get('t') or Decimal('0')
    )
    if recall.affected_quantity != total or recall.recovered_quantity != recovered:
        recall.affected_quantity = total
        recall.recovered_quantity = recovered
        recall.save(update_fields=[
            'affected_quantity', 'recovered_quantity', 'updated_at',
        ])
    return recall


@transaction.atomic
def add_affected_lot(recall, *, lot, affected_quantity):
    obj, created = models.RecallAffectedLot.objects.get_or_create(
        tenant=recall.tenant, recall=recall, lot=lot,
        defaults={'affected_quantity': Decimal(affected_quantity)},
    )
    if not created:
        obj.affected_quantity = Decimal(affected_quantity)
        obj.save(update_fields=['affected_quantity', 'updated_at'])
    recompute_affected_quantity(recall)
    return obj


@transaction.atomic
def remove_affected_lot(link):
    recall = link.recall
    link.delete()
    recompute_affected_quantity(recall)


@transaction.atomic
def progress_recall(recall, *, by=None):
    if not recall.is_progressable():
        return recall
    recall.status = 'in_progress'
    recall.save(update_fields=['status', 'updated_at'])
    return recall


@transaction.atomic
def complete_recall(recall, *, by=None):
    if not recall.is_completable():
        return recall
    recall.status = 'completed'
    recall.save(update_fields=['status', 'updated_at'])
    return recall


@transaction.atomic
def close_recall(recall, *, by=None):
    if not recall.is_closeable():
        return recall
    recall.status = 'closed'
    recall.closed_at = timezone.now()
    recall.save(update_fields=['status', 'closed_at', 'updated_at'])
    return recall


@transaction.atomic
def cancel_recall(recall, *, reason, by=None):
    if not recall.is_cancellable():
        return recall
    recall.status = 'cancelled'
    recall.cancellation_reason = reason
    recall.save(
        update_fields=['status', 'cancellation_reason', 'updated_at'],
    )
    return recall


@transaction.atomic
def send_notice(notice, *, by=None):
    if not notice.is_sendable():
        return notice
    notice.status = 'sent'
    notice.sent_at = timezone.now()
    notice.save(update_fields=['status', 'sent_at', 'updated_at'])
    return notice


@transaction.atomic
def acknowledge_notice(notice, *, by=None):
    if not notice.is_acknowledgable():
        return notice
    notice.status = 'acknowledged'
    notice.acknowledged_at = timezone.now()
    notice.save(update_fields=['status', 'acknowledged_at', 'updated_at'])
    return notice
