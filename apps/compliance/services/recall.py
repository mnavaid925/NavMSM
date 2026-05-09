"""Sub-module 13.5 services - recall lifecycle + traceability rollups + leak sweep."""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.compliance import models


_OUTBOUND_MOVEMENT_TYPES = ('issue', 'transfer', 'production_out', 'scrap')
_log = logging.getLogger(__name__)


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
    """C.5 — Flip notice status -> 'sent' AND deliver the actual message.

    For `channel='email'`: sends via Django `send_mail()` using the project
    email backend (console in DEBUG, SMTP in production). Failure to deliver
    is logged at WARNING and DOES NOT roll the status flip back — operators
    can re-attempt delivery via the email log / outbox if needed.

    Idempotent: `is_sendable()` ensures only `draft` notices are processed,
    so a double-click on the Send button never re-fires the email.
    """
    if not notice.is_sendable():
        return notice
    notice.status = 'sent'
    notice.sent_at = timezone.now()
    notice.save(update_fields=['status', 'sent_at', 'updated_at'])
    if notice.channel == 'email' and notice.recipient_email:
        _deliver_recall_notice_email(notice)
    return notice


def _deliver_recall_notice_email(notice) -> None:
    """Send the recall notice via Django `send_mail`.

    Wraps in try/except so transient SMTP failures cannot roll back the
    status transition; operators can resend manually from a future "Resend"
    UI if needed.
    """
    from django.conf import settings
    from django.core.mail import send_mail

    body_with_meta = (
        f'{notice.body}\n\n'
        f'-- This notice is part of recall {notice.recall.recall_number} --\n'
        f'Audience: {notice.audience}\n'
        f'Notice ID: {notice.notice_number}\n'
    )
    try:
        send_mail(
            subject=notice.subject,
            message=body_with_meta,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[notice.recipient_email],
            fail_silently=False,
        )
    except Exception as exc:
        _log.warning(
            'compliance.recall: send_mail failed for notice=%s recall=%s '
            'recipient=%s err=%s',
            notice.notice_number, notice.recall.recall_number,
            notice.recipient_email, exc, exc_info=True,
        )


@transaction.atomic
def acknowledge_notice(notice, *, by=None):
    if not notice.is_acknowledgable():
        return notice
    notice.status = 'acknowledged'
    notice.acknowledged_at = timezone.now()
    notice.save(update_fields=['status', 'acknowledged_at', 'updated_at'])
    return notice


# ----------------------------------------------------------------------------
# C.7  Recall leak sweep — detect outbound movements on recalled lots
# ----------------------------------------------------------------------------

def sweep_lot_for_leaks(affected_lot) -> int:
    """Recompute leak denorms on a single RecallAffectedLot.

    Counts every outbound StockMovement (`issue` / `transfer` / `production_out`
    / `scrap`) on `affected_lot.lot` posted strictly AFTER the parent recall
    was filed. Updates `post_recall_movement_count` + `last_leak_at` in a
    single UPDATE so the call is race-safe under concurrent writers.

    Returns the count of leaks detected (after recall filing).
    """
    from apps.inventory.models import StockMovement

    recall = affected_lot.recall
    if recall is None or recall.created_at is None:
        return 0
    leaks = StockMovement.all_objects.filter(
        tenant_id=affected_lot.tenant_id,
        lot=affected_lot.lot,
        movement_type__in=_OUTBOUND_MOVEMENT_TYPES,
        posted_at__gt=recall.created_at,
    ).order_by('-posted_at')
    count = leaks.count()
    last = leaks.first()
    last_at = last.posted_at if last else None
    models.RecallAffectedLot.objects.filter(pk=affected_lot.pk).update(
        post_recall_movement_count=count,
        last_leak_at=last_at,
        updated_at=timezone.now(),
    )
    return count


def on_outbound_movement(stock_movement) -> None:
    """Hook invoked from `inventory.StockMovement.post_save`.

    For every active recall whose `affected_lots` matches the movement's lot,
    bump the leak denorms by one and stamp the timestamp. Closed/cancelled
    recalls are excluded so historical recalls do not re-trigger leaks on
    routine post-closure inventory cleanup.
    """
    if stock_movement.lot_id is None:
        return
    if stock_movement.movement_type not in _OUTBOUND_MOVEMENT_TYPES:
        return
    if stock_movement.tenant_id is None:
        return
    affected = models.RecallAffectedLot.all_objects.filter(
        tenant_id=stock_movement.tenant_id,
        lot_id=stock_movement.lot_id,
        recall__status__in=('draft', 'in_progress', 'completed'),
    )
    if not affected.exists():
        return
    try:
        with transaction.atomic():
            for link in affected:
                # Sweep the actual count from the ledger so concurrent
                # writers cannot drift the denorm.
                sweep_lot_for_leaks(link)
                _log.warning(
                    'compliance.recall: leak detected on recall=%s lot=%s '
                    'movement=%s qty=%s posted_at=%s',
                    link.recall.recall_number, stock_movement.lot,
                    stock_movement.get_movement_type_display(),
                    stock_movement.qty, stock_movement.posted_at,
                )
    except Exception as exc:
        _log.warning(
            'compliance.recall: leak sweep failed on movement_pk=%s err=%s',
            stock_movement.pk, exc, exc_info=True,
        )
