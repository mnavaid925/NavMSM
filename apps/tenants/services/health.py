"""Tenant health / monitoring helpers."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant

from ..models import TenantHealthSnapshot, UsageMeter


def capture_snapshot(tenant: Tenant) -> TenantHealthSnapshot:
    """Capture an instantaneous health snapshot for a tenant."""
    active_users = User.objects.filter(tenant=tenant, is_active=True).count()
    storage = UsageMeter.all_objects.filter(
        tenant=tenant, metric='storage_mb',
    ).aggregate(q=Sum('quantity'))['q'] or Decimal('0')
    api_calls = UsageMeter.all_objects.filter(
        tenant=tenant, metric='api_calls',
    ).aggregate(q=Sum('quantity'))['q'] or Decimal('0')

    # Simple score: 100 - penalty terms (stubbed until real telemetry is wired).
    score = Decimal('100.00')

    return TenantHealthSnapshot.objects.create(
        tenant=tenant,
        captured_at=timezone.now(),
        active_users=active_users,
        storage_mb=int(storage),
        api_calls_24h=int(api_calls),
        error_rate=Decimal('0.00'),
        avg_response_ms=0,
        health_score=score,
    )
