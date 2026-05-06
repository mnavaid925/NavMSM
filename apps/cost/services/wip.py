"""WIP ledger services.

Atomic ledger writer + denorm bumps + close-job invariant. Mirrors the
``inventory.services.movements.post_movement`` shape so users get a
consistent feel between modules.
"""
from decimal import Decimal

from django.db import transaction


# Mapping: entry_type -> (denorm field name on JobCost, sign multiplier)
# Convention: amount stored signed; denorm holds the *positive* aggregate per
# bucket and ``recompute_balance`` does the netting.
_TYPE_TO_DENORM = {
    'material_issued': 'total_material',
    'labor_applied': 'total_labor',
    'overhead_applied': 'total_overhead',
    'completion': 'total_completion_credit',
    'variance': 'total_overhead',  # treat variances as overhead bucket in v1
    'adjustment': 'total_overhead',
}


def _bump(job, entry_type, delta):
    field = _TYPE_TO_DENORM.get(entry_type)
    if field is None:
        return
    current = getattr(job, field) or Decimal('0')
    setattr(job, field, current + delta)


def post_wip_entry(*, tenant, job, entry_type, amount, **kwargs):
    """Atomic ledger write + JobCost denorm bump.

    Required: tenant, job, entry_type, amount.
    Optional: quantity, unit_of_measure, cost_center, routing_operation,
    source_movement, source_labor_booking, source_production_report,
    source_overhead_allocation, posted_by, notes, is_reversal.
    """
    from .. import models as cm

    if entry_type not in dict(cm.WIPEntry.ENTRY_TYPE_CHOICES):
        raise ValueError(f'invalid entry_type: {entry_type}')
    amount = Decimal(amount)

    with transaction.atomic():
        # Refresh job for consistent denorm bump.
        job = cm.JobCost.all_objects.select_for_update().get(pk=job.pk)
        entry = cm.WIPEntry.all_objects.create(
            tenant=tenant,
            job=job,
            entry_type=entry_type,
            amount=amount,
            **kwargs,
        )
        _bump(job, entry_type, amount)
        job.recompute_balance()
        job.save(update_fields=[
            'total_material', 'total_labor', 'total_overhead',
            'total_completion_credit', 'wip_balance', 'updated_at',
        ])
    return entry


def reverse_wip_entry(entry, *, posted_by=None, reason=''):
    """Emit an offsetting reversal entry against the same job.

    Idempotent guard: refuses if a reversal already exists.
    """
    from .. import models as cm

    if entry.is_reversal:
        raise ValueError('cannot reverse a reversal entry')
    existing = cm.WIPEntry.all_objects.filter(
        tenant_id=entry.tenant_id, is_reversal=True,
        notes__startswith=f'reversal-of:{entry.entry_number}',
    ).first()
    if existing is not None:
        return existing
    return post_wip_entry(
        tenant=entry.tenant, job=entry.job,
        entry_type=entry.entry_type,
        amount=-(entry.amount or Decimal('0')),
        is_reversal=True,
        posted_by=posted_by,
        notes=f'reversal-of:{entry.entry_number} {reason}'.strip(),
    )


def close_job(job, *, closed_by=None, force=False):
    """Flip the job to closed. Refuses non-zero balance unless ``force=True``.

    Returns ``(ok: bool, message: str)``.
    """
    from django.utils import timezone
    from .. import models as cm

    job = cm.JobCost.all_objects.get(pk=job.pk)
    if job.status == 'closed':
        return (True, 'Job already closed.')
    bal = job.wip_balance or Decimal('0')
    if abs(bal) > Decimal('0.01') and not force:
        return (False, f'WIP balance is {bal} - post an adjustment entry first or use force.')
    with transaction.atomic():
        cm.JobCost.all_objects.filter(pk=job.pk, status='open').update(
            status='closed', closed_at=timezone.now(),
            closed_by=closed_by,
        )
    return (True, 'Job closed.')


def compute_operation_rollup(job):
    """Group WIPEntry rows by routing_operation for the operation-wise report."""
    from .. import models as cm
    from collections import defaultdict

    rollup = defaultdict(lambda: {
        'op': None, 'material': Decimal('0'), 'labor': Decimal('0'),
        'overhead': Decimal('0'), 'completion': Decimal('0'),
    })
    qs = cm.WIPEntry.all_objects.filter(job=job).select_related('routing_operation')
    for e in qs:
        key = e.routing_operation_id or 0
        bucket = rollup[key]
        bucket['op'] = e.routing_operation
        amount = e.amount or Decimal('0')
        if e.entry_type == 'material_issued':
            bucket['material'] += amount
        elif e.entry_type == 'labor_applied':
            bucket['labor'] += amount
        elif e.entry_type == 'overhead_applied':
            bucket['overhead'] += amount
        elif e.entry_type == 'completion':
            bucket['completion'] += amount
    return [
        {
            'operation': v['op'],
            'material': v['material'],
            'labor': v['labor'],
            'overhead': v['overhead'],
            'completion': v['completion'],
            'net': v['material'] + v['labor'] + v['overhead'] - v['completion'],
        }
        for v in rollup.values()
    ]
