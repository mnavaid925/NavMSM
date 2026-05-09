"""Shared fixtures for the Compliance & Regulatory Management test suite."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.compliance import models as cm


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Comp', slug='acme-comp-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Comp', slug='globex-comp-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_comp', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_comp', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_comp', password='pw', tenant=globex,
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


# ---------- Compliance fixtures ----------

@pytest.fixture
def incident_type_injury(db, acme):
    return cm.IncidentType.objects.create(
        tenant=acme, code='injury', name='Injury', category='injury',
    )


@pytest.fixture
def incident(db, acme, incident_type_injury, acme_admin):
    from django.utils import timezone
    return cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='Test slip', description='Slipped on wet floor.',
        occurred_at=timezone.now(), severity='medium',
        reporter=acme_admin,
    )


@pytest.fixture
def risk_assessment(db, acme):
    return cm.RiskAssessment.objects.create(
        tenant=acme, title='Test risk', hazard='Test hazard',
        likelihood=3, severity=4,
    )


@pytest.fixture
def checklist(db, acme):
    return cm.SafetyAuditChecklist.objects.create(
        tenant=acme, code='5S', name='5S walk',
        items=[{'order': 1, 'question': 'Is the area tidy?'}],
    )


@pytest.fixture
def safety_audit(db, acme, checklist, acme_admin):
    return cm.SafetyAudit.objects.create(
        tenant=acme, checklist=checklist,
        scheduled_for=date.today() + timedelta(days=1),
        auditor=acme_admin, status='scheduled',
    )


@pytest.fixture
def document(db, acme, acme_admin):
    return cm.ComplianceDocument.objects.create(
        tenant=acme, doc_type='sop', title='SOP-001 Receiving',
        version='1.0', status='draft', owner=acme_admin,
    )


@pytest.fixture
def waste_category(db, acme):
    return cm.WasteCategory.objects.create(
        tenant=acme, code='chem', name='Chemical', hazard_class='hazardous_chemical',
    )


@pytest.fixture
def manifest(db, acme, waste_category):
    return cm.WasteManifest.objects.create(
        tenant=acme, category=waste_category,
        generator='Acme Plant', manifest_date=date.today(),
    )


@pytest.fixture
def plm_product(db, acme):
    """Build a minimal plm.Product for recall tests."""
    from apps.plm.models import Product
    return Product.objects.create(
        tenant=acme, sku='WIDGET-001', name='Test Widget',
    )


@pytest.fixture
def recall(db, acme, plm_product, acme_admin):
    return cm.ProductRecall.objects.create(
        tenant=acme, product=plm_product, title='Test recall',
        severity='class_iii', initiated_by=acme_admin,
    )
