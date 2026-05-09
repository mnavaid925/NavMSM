"""Sub-module 14.1 - meter consumption services.

Pure-ish writers; consumption math is performed in the model's save().
"""
import csv
from decimal import Decimal
from io import TextIOWrapper

from django.db import transaction
from django.utils import timezone

from apps.utility import models


@transaction.atomic
def post_consumption(meter, *, period_start, period_end, start_reading,
                     end_reading, unit_cost=None, source='manual',
                     source_meter_reading=None, recorded_by=None, notes=''):
    """Atomic ledger writer for a UtilityConsumption row.

    Idempotent when ``source_meter_reading`` is provided — partial unique
    constraint prevents duplicates from the EAM auto-feed signal.
    """
    if source_meter_reading is not None:
        existing = models.UtilityConsumption.all_objects.filter(
            source_meter_reading=source_meter_reading,
        ).first()
        if existing is not None:
            return existing
    if unit_cost is None:
        unit_cost = _resolve_unit_cost(meter, period_start)
    return models.UtilityConsumption.all_objects.create(
        tenant=meter.tenant,
        meter=meter,
        period_start=period_start,
        period_end=period_end,
        start_reading=Decimal(start_reading),
        end_reading=Decimal(end_reading),
        unit_cost=Decimal(unit_cost or 0),
        source=source,
        source_meter_reading=source_meter_reading,
        recorded_by=recorded_by,
        notes=notes,
        recorded_at=timezone.now(),
    )


def _resolve_unit_cost(meter, when):
    """Snapshot the active tariff's flat_rate for the given moment."""
    qs = (
        models.UtilityTariff.all_objects
        .filter(
            tenant=meter.tenant, utility_type=meter.utility_type,
            is_active=True, effective_from__lte=when.date() if hasattr(when, 'date') else when,
        )
        .order_by('-effective_from')
    )
    tariff = qs.first()
    if tariff is None:
        return Decimal('0')
    return tariff.flat_rate or Decimal('0')


@transaction.atomic
def bulk_import_billing(meter, csv_file, recorded_by=None):
    """Idempotent CSV bulk-import of consumption rows for a single meter.

    CSV columns (header row required):
        period_start,period_end,start_reading,end_reading,unit_cost
    """
    fp = TextIOWrapper(csv_file, encoding='utf-8') if hasattr(csv_file, 'read') else csv_file
    reader = csv.DictReader(fp)
    created, skipped = 0, 0
    for row in reader:
        ps = row['period_start']
        pe = row['period_end']
        existing = models.UtilityConsumption.all_objects.filter(
            tenant=meter.tenant, meter=meter,
            period_start=ps, period_end=pe,
        ).first()
        if existing is not None:
            skipped += 1
            continue
        post_consumption(
            meter,
            period_start=ps, period_end=pe,
            start_reading=row['start_reading'],
            end_reading=row['end_reading'],
            unit_cost=row.get('unit_cost') or None,
            source='billing_import',
            recorded_by=recorded_by,
        )
        created += 1
    return {'created': created, 'skipped': skipped}
