"""Shared fixtures for the Module 16 BI test suite."""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.bi import models as B
from apps.core.models import Tenant, set_current_tenant


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme BI', slug='acme-bi-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex BI', slug='globex-bi-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_bi', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_bi', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_bi', password='pw', tenant=globex,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def admin_client(client, acme_admin):
    client.force_login(acme_admin)
    return client


@pytest.fixture
def staff_client(client, acme_staff):
    client.force_login(acme_staff)
    return client


@pytest.fixture
def globex_client(client, globex_admin):
    client.force_login(globex_admin)
    return client


@pytest.fixture
def oee_kpi(db, acme):
    return B.KPIDefinition.objects.create(
        tenant=acme, code='oee', name='OEE', unit='%',
        direction='higher_is_better',
        target_value=Decimal('85'),
        warning_threshold=Decimal('70'),
        critical_threshold=Decimal('60'),
    )


@pytest.fixture
def throughput_kpi(db, acme):
    return B.KPIDefinition.objects.create(
        tenant=acme, code='throughput', name='Throughput', unit='units',
        direction='higher_is_better',
    )


@pytest.fixture
def dashboard(db, acme):
    return B.KPIDashboard.objects.create(
        tenant=acme, name='Ops Daily', slug='ops-daily',
        is_shared=True, default_period='last_30d',
    )


@pytest.fixture
def report_data_source(db, acme):
    return B.ReportDataSource.objects.create(
        tenant=acme, code='production_reports', name='Production Reports',
        model_label='mes.ProductionReport',
        allowed_fields=['id', 'reported_at', 'good_qty', 'scrap_qty'],
    )


@pytest.fixture
def report(db, acme, report_data_source):
    return B.ReportDefinition.objects.create(
        tenant=acme, data_source=report_data_source,
        name='Test Report', row_limit=10,
    )


@pytest.fixture
def predictive_model(db, acme):
    return B.PredictiveModel.objects.create(
        tenant=acme, code='demand_forecast', name='Test forecaster',
        lookback_days=30, forecast_horizon_days=7, is_active=True,
    )


@pytest.fixture
def data_mart(db, acme):
    return B.DataMart.objects.create(
        tenant=acme, code='test_mart', name='Test Mart',
        source_definition={'model_label': 'mes.ProductionReport', 'group_by': [], 'measures': {}},
    )


@pytest.fixture
def schedule(db, acme, report):
    return B.ReportSchedule.objects.create(
        tenant=acme, name='Weekly summary', report=report,
        frequency='weekly', next_run_at=timezone.now() + timedelta(days=1),
        format='csv', status='active',
    )
