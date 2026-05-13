"""Form validation tests (L-01 unique_together, L-14 required reasons, XOR rules)."""
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bi import forms, models as B


@pytest.mark.django_db
class TestKPIDefinitionForm:
    def test_duplicate_code_rejected(self, acme, oee_kpi):
        f = forms.KPIDefinitionForm(data={
            'code': 'oee', 'name': 'Dup', 'unit': '%', 'direction': 'higher_is_better',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'code' in f.errors

    def test_unique_code_allowed(self, acme):
        f = forms.KPIDefinitionForm(data={
            'code': 'oee', 'name': 'OEE', 'unit': '%', 'direction': 'higher_is_better',
        }, tenant=acme)
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestReportDataSourceForm:
    def test_code_must_be_in_registry(self, acme):
        f = forms.ReportDataSourceForm(data={
            'code': 'something-not-registered', 'name': 'X', 'model_label': 'foo.Bar',
            'allowed_fields': [], 'default_filters': {}, 'is_active': True,
        }, tenant=acme)
        assert not f.is_valid()
        assert 'code' in f.errors

    def test_registered_code_accepted(self, acme):
        f = forms.ReportDataSourceForm(data={
            'code': 'production_reports', 'name': 'X', 'model_label': 'mes.ProductionReport',
            'allowed_fields': [], 'default_filters': {}, 'is_active': True,
        }, tenant=acme)
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestPredictionRunCancelForm:
    def test_empty_reason_rejected(self):
        f = forms.PredictionRunCancelForm(data={'cancellation_reason': '   '})
        assert not f.is_valid()

    def test_non_empty_reason_accepted(self):
        f = forms.PredictionRunCancelForm(data={'cancellation_reason': 'Wrong target'})
        assert f.is_valid()


@pytest.mark.django_db
class TestReportScheduleForm:
    def test_xor_report_or_dashboard(self, acme, report, dashboard):
        f = forms.ReportScheduleForm(data={
            'name': 'S1', 'report': report.pk, 'dashboard': dashboard.pk,
            'frequency': 'daily', 'timezone_name': 'UTC',
            'next_run_at': timezone.now(), 'format': 'csv',
        }, tenant=acme)
        assert not f.is_valid()

    def test_neither_report_nor_dashboard_rejected(self, acme):
        f = forms.ReportScheduleForm(data={
            'name': 'S2', 'frequency': 'daily', 'timezone_name': 'UTC',
            'next_run_at': timezone.now(), 'format': 'csv',
        }, tenant=acme)
        assert not f.is_valid()

    def test_report_only_accepted(self, acme, report):
        f = forms.ReportScheduleForm(data={
            'name': 'S3', 'report': report.pk, 'frequency': 'daily', 'timezone_name': 'UTC',
            'next_run_at': timezone.now().isoformat(), 'format': 'csv',
        }, tenant=acme)
        assert f.is_valid(), f.errors

    def test_custom_frequency_requires_cron(self, acme, report):
        f = forms.ReportScheduleForm(data={
            'name': 'S4', 'report': report.pk, 'frequency': 'custom',
            'cron_expression': '', 'timezone_name': 'UTC',
            'next_run_at': timezone.now().isoformat(), 'format': 'csv',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'cron_expression' in f.errors


@pytest.mark.django_db
class TestDataMartForm:
    def test_source_definition_must_have_model_label(self, acme):
        f = forms.DataMartForm(data={
            'code': 'm1', 'name': 'M', 'source_definition': {},
            'refresh_frequency': 'daily', 'is_active': True,
        }, tenant=acme)
        assert not f.is_valid()
        assert 'source_definition' in f.errors

    def test_duplicate_code_rejected(self, acme, data_mart):
        f = forms.DataMartForm(data={
            'code': data_mart.code, 'name': 'Dup',
            'source_definition': {'model_label': 'foo.Bar'},
            'refresh_frequency': 'daily', 'is_active': True,
        }, tenant=acme)
        assert not f.is_valid()
        assert 'code' in f.errors


@pytest.mark.django_db
class TestReportScheduleDisableForm:
    def test_empty_reason_rejected(self):
        f = forms.ReportScheduleDisableForm(data={'disabled_reason': ' '})
        assert not f.is_valid()

    def test_non_empty_reason_accepted(self):
        f = forms.ReportScheduleDisableForm(data={'disabled_reason': 'Owner left team'})
        assert f.is_valid()
