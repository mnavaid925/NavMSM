"""Model invariants, auto-numbering, denorm computations."""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bi import models as B


@pytest.mark.django_db
class TestAutoNumbering:
    def test_report_definition_auto_number(self, acme, report_data_source):
        r1 = B.ReportDefinition.objects.create(tenant=acme, data_source=report_data_source, name='R1')
        r2 = B.ReportDefinition.objects.create(tenant=acme, data_source=report_data_source, name='R2')
        assert r1.report_number == 'RPT-00001'
        assert r2.report_number == 'RPT-00002'

    def test_report_run_auto_number(self, acme, report):
        run = B.ReportRun.objects.create(tenant=acme, report=report)
        assert run.run_number.startswith('RR-')

    def test_prediction_run_auto_number(self, acme, predictive_model):
        run = B.PredictionRun.objects.create(tenant=acme, predictive_model=predictive_model)
        assert run.run_number.startswith('PR-')

    def test_trend_auto_number(self, acme):
        t = B.TrendAnalysis.objects.create(tenant=acme, name='Test trend')
        assert t.trend_number.startswith('TA-')

    def test_data_mart_auto_number(self, acme):
        m = B.DataMart.objects.create(tenant=acme, code='dm1', name='DM 1')
        assert m.mart_number.startswith('DM-')

    def test_report_schedule_auto_number(self, acme, report):
        s = B.ReportSchedule.objects.create(tenant=acme, name='Test', report=report, frequency='daily')
        assert s.schedule_number.startswith('SCH-')

    def test_export_auto_number(self, acme):
        e = B.ReportExport.objects.create(tenant=acme, format='csv')
        assert e.export_number.startswith('EXP-')

    def test_delivery_auto_number(self, acme, schedule):
        rec = B.ReportRecipient.objects.create(tenant=acme, schedule=schedule, email='x@x.com')
        d = B.ReportDelivery.objects.create(tenant=acme, schedule=schedule, recipient=rec)
        assert d.delivery_number.startswith('DLV-')


@pytest.mark.django_db
class TestKPISnapshot:
    def test_delta_vs_prior_with_value(self, acme, oee_kpi):
        snap = B.KPISnapshot.objects.create(
            tenant=acme, kpi_definition=oee_kpi,
            period_start='2026-01-01', period_end='2026-01-31',
            value=Decimal('80'), prior_period_value=Decimal('70'),
        )
        assert snap.delta_vs_prior == Decimal('10')
        assert snap.delta_pct_vs_prior > Decimal('14')

    def test_delta_vs_prior_no_prior(self, acme, oee_kpi):
        snap = B.KPISnapshot.objects.create(
            tenant=acme, kpi_definition=oee_kpi,
            period_start='2026-01-01', period_end='2026-01-31',
            value=Decimal('80'),
        )
        assert snap.delta_vs_prior is None
        assert snap.delta_pct_vs_prior is None


@pytest.mark.django_db
class TestUniqueConstraints:
    def test_kpi_definition_unique_per_tenant_code(self, acme, oee_kpi):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            B.KPIDefinition.objects.create(tenant=acme, code='oee', name='dup')

    def test_dashboard_unique_per_tenant_slug(self, acme, dashboard):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            B.KPIDashboard.objects.create(tenant=acme, name='dup', slug=dashboard.slug)

    def test_dashboard_slug_can_repeat_across_tenants(self, acme, globex, dashboard):
        d2 = B.KPIDashboard.objects.create(tenant=globex, name='Other', slug=dashboard.slug)
        assert d2.pk != dashboard.pk


@pytest.mark.django_db
class TestPredictiveModel:
    def test_run_is_cancelable_states(self, acme, predictive_model):
        run = B.PredictionRun.objects.create(tenant=acme, predictive_model=predictive_model, status='queued')
        assert run.is_cancelable() is True
        run.status = 'completed'
        assert run.is_cancelable() is False


@pytest.mark.django_db
class TestReportSchedule:
    def test_pausable_resumable(self, acme, schedule):
        assert schedule.is_pausable() is True
        assert schedule.is_resumable() is False
        schedule.status = 'paused'
        assert schedule.is_pausable() is False
        assert schedule.is_resumable() is True
