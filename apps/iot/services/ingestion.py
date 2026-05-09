"""Module 15 - IoT ingestion service.

Pure-function entry points for posting IoTReading rows. The post_save signal
in apps/iot/signals.py handles the cross-module cascades (StreamMetric refresh,
AnomalyDetection eval, eam.ConditionReading mirror) - this service only
constructs and persists the ledger row inside an atomic block.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone


def _coerce_value(tag, raw):
    """Coerce raw payload value to (numeric, text, bool) per tag.data_type."""
    if raw is None or raw == '':
        return None, '', None
    dt = tag.data_type
    if dt == 'float':
        try:
            return Decimal(str(raw)), '', None
        except (InvalidOperation, TypeError, ValueError):
            return None, str(raw), None
    if dt == 'int':
        try:
            return Decimal(int(raw)), '', None
        except (TypeError, ValueError):
            return None, str(raw), None
    if dt == 'bool':
        if isinstance(raw, bool):
            return None, '', raw
        as_str = str(raw).strip().lower()
        return None, '', as_str in ('1', 'true', 'yes', 'on')
    # string
    return None, str(raw), None


def post_iot_reading(*, tenant, device_tag, value, timestamp=None, quality='good',
                     source='manual', batch=None, notes=''):
    """Single-row ingest. Returns the persisted IoTReading instance.

    Caller is responsible for tenant scoping; this function does not infer
    tenant from thread-local.
    """
    from apps.iot import models as iot_models

    if timestamp is None:
        timestamp = timezone.now()
    v_num, v_text, v_bool = _coerce_value(device_tag, value)
    with transaction.atomic():
        reading = iot_models.IoTReading(
            tenant=tenant,
            device_tag=device_tag,
            timestamp=timestamp,
            value_numeric=v_num,
            value_text=v_text,
            value_bool=v_bool,
            quality=quality,
            source=source,
            batch=batch,
            notes=notes,
        )
        reading.save()
    return reading


def bulk_ingest(*, tenant, payload, source_format='json', user=None, notes=''):
    """Atomic bulk ingest. Returns (batch, created_count, errors).

    payload contract:
        - JSON: list of {tag_address: str | tag_id: int, timestamp: ISO8601,
                         value, quality?: str}
        - CSV: header row tag_address,timestamp,value,quality
    """
    from apps.iot import models as iot_models

    rows: list[dict] = []
    if source_format == 'json':
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError as exc:
            return None, 0, [f'JSON parse error: {exc}']
        if not isinstance(data, list):
            return None, 0, ['JSON payload must be a list of objects.']
        rows = list(data)
    elif source_format == 'csv':
        reader = csv.DictReader(io.StringIO(payload))
        rows = list(reader)
    else:
        return None, 0, [f'Unsupported source_format: {source_format}']

    errors: list[str] = []
    with transaction.atomic():
        batch = iot_models.IoTReadingBatch.objects.create(
            tenant=tenant,
            ingested_at=timezone.now(),
            ingested_by=user,
            source_format=source_format,
            row_count=len(rows),
            status='received',
            notes=notes,
        )
        created = 0
        for idx, row in enumerate(rows):
            tag = None
            tag_id = row.get('tag_id')
            tag_address = row.get('tag_address')
            if tag_id:
                tag = iot_models.DeviceTag.objects.filter(
                    tenant=tenant, pk=tag_id, is_active=True,
                ).first()
            elif tag_address:
                tag = iot_models.DeviceTag.objects.filter(
                    tenant=tenant, address=tag_address, is_active=True,
                ).first()
            if tag is None:
                errors.append(f'Row {idx}: tag not found ({tag_id or tag_address}).')
                continue
            ts = row.get('timestamp')
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except ValueError:
                    errors.append(f'Row {idx}: invalid timestamp.')
                    continue
            elif ts is None:
                ts = timezone.now()
            quality = row.get('quality') or 'good'
            value = row.get('value')
            try:
                post_iot_reading(
                    tenant=tenant, device_tag=tag, value=value,
                    timestamp=ts, quality=quality, source='replay', batch=batch,
                )
                created += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f'Row {idx}: {exc}')
        batch.row_count = created
        batch.status = 'processed' if not errors else ('partial' if created else 'failed')
        if errors:
            batch.error_summary = '\n'.join(errors[:50])
        batch.save(update_fields=['row_count', 'status', 'error_summary'])
    return batch, created, errors
