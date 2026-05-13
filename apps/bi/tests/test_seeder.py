"""Seeder smoke tests."""
import pytest
from django.core.management import call_command

from apps.bi import models as B


@pytest.mark.django_db
def test_seed_bi_creates_kpis_and_dashboard(acme, acme_admin):
    call_command('seed_bi', tenant=acme.slug)
    assert B.KPIDefinition.all_objects.filter(tenant=acme).count() >= 8
    assert B.KPIDashboard.all_objects.filter(tenant=acme).count() == 1
    assert B.KPIWidget.all_objects.filter(tenant=acme).count() >= 4
    assert B.ReportDataSource.all_objects.filter(tenant=acme).count() >= 4
    assert B.ReportDefinition.all_objects.filter(tenant=acme).count() == 1
    assert B.PredictiveModel.all_objects.filter(tenant=acme).count() >= 2
    assert B.DataMart.all_objects.filter(tenant=acme).count() == 1
    assert B.ReportSchedule.all_objects.filter(tenant=acme).count() == 1
    assert B.ReportRecipient.all_objects.filter(tenant=acme).count() == 1


@pytest.mark.django_db
def test_seed_bi_idempotent(acme, acme_admin):
    """Running seed_bi twice should not double-up the rows."""
    call_command('seed_bi', tenant=acme.slug)
    count1 = B.KPIDefinition.all_objects.filter(tenant=acme).count()
    call_command('seed_bi', tenant=acme.slug)
    count2 = B.KPIDefinition.all_objects.filter(tenant=acme).count()
    assert count1 == count2


@pytest.mark.django_db
def test_seed_bi_flush_clears_then_repopulates(acme, acme_admin):
    call_command('seed_bi', tenant=acme.slug)
    count1 = B.KPIDefinition.all_objects.filter(tenant=acme).count()
    call_command('seed_bi', tenant=acme.slug, flush=True)
    count2 = B.KPIDefinition.all_objects.filter(tenant=acme).count()
    assert count1 == count2
