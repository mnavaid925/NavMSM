"""Pure-function service tests for pm_scheduler, prediction, downtime, tool_life."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.eam.services.downtime import compute_downtime, refresh_mwo_downtime
from apps.eam.services.pm_scheduler import generate_upcoming_pm
from apps.eam.services.prediction import classify_reading, check_reading
from apps.eam.services.tool_life import bump_tool_life, consume_usage_log


# ---------- pm_scheduler ----------

def _plan(**overrides):
    base = dict(
        is_active=True,
        trigger_type='calendar',
        frequency_days=30,
        frequency_meter=None,
        last_done_at=None,
        last_done_meter=None,
        next_due_at=None,
        next_due_meter=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestGenerateUpcomingPM:
    def test_calendar_emits_horizon_dates(self):
        today = date(2026, 1, 1)
        plan = _plan(frequency_days=30, next_due_at=date(2026, 1, 15))
        out = generate_upcoming_pm(plan, horizon_days=120, today=today, max_count=10)
        dates = [d for d, _ in out]
        # Expect Jan15, Feb14, Mar16, Apr15 inside the 120-day window.
        assert len(dates) == 4
        assert dates[0] == date(2026, 1, 15)
        assert dates[1] == date(2026, 2, 14)

    def test_max_count_caps_output(self):
        today = date(2026, 1, 1)
        plan = _plan(frequency_days=10, next_due_at=date(2026, 1, 5))
        out = generate_upcoming_pm(plan, horizon_days=365, today=today, max_count=3)
        assert len(out) == 3

    def test_inactive_plan_returns_empty(self):
        plan = _plan(is_active=False)
        assert generate_upcoming_pm(plan) == []

    def test_meter_only_emits_single_threshold(self):
        plan = _plan(
            trigger_type='meter', frequency_days=None,
            frequency_meter=Decimal('500'), last_done_meter=Decimal('1000'),
        )
        out = generate_upcoming_pm(plan)
        assert len(out) == 1
        d, m = out[0]
        assert d is None
        assert m == Decimal('1500')

    def test_past_anchor_pulled_to_today(self):
        today = date(2026, 5, 1)
        plan = _plan(frequency_days=30, next_due_at=date(2026, 1, 1))
        out = generate_upcoming_pm(plan, horizon_days=60, today=today, max_count=5)
        # First emitted date must be >= today.
        assert all(d >= today for d, _ in out if d is not None)


# ---------- prediction ----------

class TestClassifyReading:
    def test_inside_band_normal(self):
        cr = classify_reading(Decimal('3'), Decimal('1'), Decimal('5'))
        assert cr.status == 'normal'
        assert cr.breached is False

    def test_marginal_breach_warning(self):
        # 5% over the high alarm with band of 4 -> margin=0.05 (under 20% -> warning).
        cr = classify_reading(Decimal('5.2'), Decimal('1'), Decimal('5'))
        assert cr.status == 'warning'

    def test_severe_breach_critical(self):
        # 100% over the high alarm of 5 -> critical.
        cr = classify_reading(Decimal('10'), Decimal('1'), Decimal('5'))
        assert cr.status == 'critical'

    def test_no_alarm_band_normal(self):
        cr = classify_reading(Decimal('99'), None, None)
        assert cr.status == 'normal'

    def test_value_none_normal(self):
        cr = classify_reading(None, Decimal('1'), Decimal('5'))
        assert cr.status == 'normal'

    def test_low_breach(self):
        cr = classify_reading(Decimal('0'), Decimal('1'), Decimal('5'))
        assert cr.breached is True


# ---------- downtime ----------

class TestComputeDowntime:
    def test_sums_minutes_by_bucket(self):
        events = [
            SimpleNamespace(minutes=Decimal('30'), downtime_type='unplanned'),
            SimpleNamespace(minutes=Decimal('15'), downtime_type='planned'),
            SimpleNamespace(minutes=Decimal('45'), downtime_type='unplanned'),
        ]
        s = compute_downtime(events)
        assert s.total_minutes == Decimal('90.00')
        assert s.unplanned_minutes == Decimal('75.00')
        assert s.planned_minutes == Decimal('15.00')
        assert s.event_count == 3
        assert s.unplanned_pct == Decimal('83.33')

    def test_empty_events(self):
        s = compute_downtime([])
        assert s.total_minutes == Decimal('0')
        assert s.unplanned_pct == Decimal('0')


@pytest.mark.django_db
class TestRefreshMwoDowntime:
    def test_persists_total(self, acme, asset, mwo):
        from apps.eam.models import DowntimeEvent
        from django.utils import timezone
        now = timezone.now()
        DowntimeEvent.objects.create(
            tenant=acme, asset=asset, mwo=mwo,
            started_at=now, ended_at=now + timedelta(minutes=30),
            downtime_type='unplanned',
        )
        DowntimeEvent.objects.create(
            tenant=acme, asset=asset, mwo=mwo,
            started_at=now, ended_at=now + timedelta(minutes=20),
            downtime_type='planned',
        )
        refresh_mwo_downtime(mwo)
        mwo.refresh_from_db()
        assert mwo.downtime_minutes == Decimal('50.00')


# ---------- prediction: check_reading persists status ----------

@pytest.mark.django_db
class TestCheckReadingPersists:
    def test_critical_reading_status_updated(self, acme, monitoring_point):
        from apps.eam.models import ConditionReading
        # high_alarm=5.0; reading=10 -> critical.
        r = ConditionReading.objects.create(
            tenant=acme, point=monitoring_point,
            reading_value=Decimal('10'),
        )
        # Force status back to normal then call check_reading.
        ConditionReading.all_objects.filter(pk=r.pk).update(status='normal')
        result = check_reading(r)
        r.refresh_from_db()
        assert result.status == 'critical'
        assert r.status == 'critical'


# ---------- tool_life ----------

@pytest.mark.django_db
class TestBumpToolLife:
    def test_atomic_increment(self, acme, tool):
        from apps.eam.models import Tool
        bump_tool_life(tool, cycles_added=100, hours_added=Decimal('5'))
        bump_tool_life(tool, cycles_added=50, hours_added=Decimal('2.5'))
        tool.refresh_from_db()
        assert tool.current_cycles == 150
        assert tool.current_hours == Decimal('7.5')


@pytest.mark.django_db
class TestConsumeUsageLog:
    def test_emits_log_and_bumps_denorm(self, acme, tool, acme_admin):
        from apps.eam.models import ToolUsageLog
        log = consume_usage_log(
            tool, cycles_added=200, hours_added=Decimal('3'),
            operator=acme_admin, notes='Test',
        )
        assert isinstance(log, ToolUsageLog)
        tool.refresh_from_db()
        assert tool.current_cycles == 200
        assert tool.current_hours == Decimal('3')
