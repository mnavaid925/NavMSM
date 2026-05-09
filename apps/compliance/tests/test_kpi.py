"""C.4 — EHS KPI service: TRIR, LTIR, near-miss ratio."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.compliance import models as cm
from apps.compliance.services.kpi import compute_ehs_kpis


def _make_incident(*, tenant, incident_type, severity='medium', when=None,
                   sequence='1'):
    return cm.IncidentReport.objects.create(
        tenant=tenant, incident_type=incident_type,
        title=f'Probe-{sequence}', description='probe',
        occurred_at=when or timezone.now(),
        severity=severity, status='reported',
    )


@pytest.mark.django_db
class TestEHSKPIs:

    def test_zero_incidents_returns_zero_rates(self, acme):
        kpis = compute_ehs_kpis(acme, period_days=90)
        assert kpis['recordable_count'] == 0
        assert kpis['lost_time_count'] == 0
        assert kpis['near_miss_count'] == 0
        assert kpis['trir'] == Decimal('0.00')
        assert kpis['ltir'] == Decimal('0.00')
        assert kpis['near_miss_ratio'] == Decimal('0.00')

    def test_recordable_severity_counts(self, acme, incident_type_injury):
        # 2 medium + 1 high + 1 critical = 4 recordable, 2 lost-time
        for i, sev in enumerate(['low', 'medium', 'medium', 'high', 'critical']):
            _make_incident(tenant=acme, incident_type=incident_type_injury,
                           severity=sev, sequence=str(i))
        kpis = compute_ehs_kpis(acme, period_days=90)
        assert kpis['recordable_count'] == 4  # excludes 'low' = first aid only
        assert kpis['lost_time_count'] == 2  # high + critical

    def test_trir_formula(self, acme, incident_type_injury):
        """TRIR = (recordable * 200_000) / hours_worked.

        With 4 recordable + the fallback hours (24,000), TRIR =
        4 * 200000 / 24000 = 33.33.
        """
        for i, sev in enumerate(['medium', 'medium', 'high', 'critical']):
            _make_incident(tenant=acme, incident_type=incident_type_injury,
                           severity=sev, sequence=str(i))
        kpis = compute_ehs_kpis(acme, period_days=90)
        # Either AttendanceRecord exists (real hours) or fallback 24_000
        if kpis['fallback_hours_used']:
            assert kpis['trir'] == Decimal('33.33')

    def test_near_miss_ratio_uses_near_miss_category(self, acme):
        nm = cm.IncidentType.objects.create(
            tenant=acme, code='nm', name='Near miss', category='near_miss',
        )
        injury = cm.IncidentType.objects.create(
            tenant=acme, code='inj', name='Injury', category='injury',
        )
        # 1 recordable injury, 5 near-misses -> ratio = 5
        _make_incident(tenant=acme, incident_type=injury, severity='medium')
        for i in range(5):
            _make_incident(tenant=acme, incident_type=nm, severity='low',
                           sequence=f'nm-{i}')
        kpis = compute_ehs_kpis(acme, period_days=90)
        assert kpis['recordable_count'] == 1
        assert kpis['near_miss_count'] == 5
        assert kpis['near_miss_ratio'] == Decimal('5.00')

    def test_period_window_excludes_old_incidents(self, acme, incident_type_injury):
        old = timezone.now() - timedelta(days=200)
        recent = timezone.now() - timedelta(days=5)
        _make_incident(tenant=acme, incident_type=incident_type_injury,
                       severity='high', when=old, sequence='old')
        _make_incident(tenant=acme, incident_type=incident_type_injury,
                       severity='high', when=recent, sequence='recent')
        kpis = compute_ehs_kpis(acme, period_days=90)
        # Only the recent incident is counted
        assert kpis['recordable_count'] == 1
        assert kpis['lost_time_count'] == 1

    def test_cancelled_incidents_excluded(self, acme, incident_type_injury):
        inc = _make_incident(tenant=acme, incident_type=incident_type_injury,
                             severity='high')
        inc.status = 'cancelled'
        inc.save(update_fields=['status'])
        kpis = compute_ehs_kpis(acme, period_days=90)
        assert kpis['recordable_count'] == 0


@pytest.mark.django_db
class TestDashboardKPIRender:

    def test_dashboard_includes_ehs_panel(self, admin_client, acme, incident_type_injury):
        _make_incident(tenant=acme, incident_type=incident_type_injury, severity='high')
        from django.urls import reverse
        r = admin_client.get(reverse('compliance:index'))
        assert r.status_code == 200
        assert b'EHS Leading' in r.content
        assert b'TRIR' in r.content
        assert b'LTIR' in r.content
