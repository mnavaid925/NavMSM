"""Security tests — RBAC matrix (L-10), multi-tenant IDOR, anonymous redirects."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance import models as cm


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------- Anonymous redirect on every list URL ----------

ANON_LIST_URLS = [
    'compliance:index',
    'compliance:incident_type_list',
    'compliance:incident_list',
    'compliance:risk_list',
    'compliance:checklist_list',
    'compliance:audit_list',
    'compliance:document_list',
    'compliance:audit_trail_list',
    'compliance:archive_list',
    'compliance:waste_category_list',
    'compliance:manifest_list',
    'compliance:recall_list',
]


@pytest.mark.parametrize('name', ANON_LIST_URLS)
def test_anonymous_redirected_to_login(client, name):
    r = client.get(reverse(name))
    assert r.status_code in (301, 302)


# ---------- RBAC: admin-only mutate routes block staff ----------

ADMIN_ONLY_GET_URLS = [
    'compliance:incident_type_create',
    'compliance:risk_create',
    'compliance:checklist_create',
    'compliance:audit_create',
    'compliance:document_create',
    'compliance:waste_category_create',
    'compliance:manifest_create',
    'compliance:recall_create',
]


@pytest.mark.parametrize('name', ADMIN_ONLY_GET_URLS)
def test_staff_blocked_from_admin_only_create(staff_client, name):
    r = staff_client.get(reverse(name))
    assert r.status_code in (301, 302, 403)


def test_staff_can_view_lists(staff_client):
    for name in ANON_LIST_URLS:
        r = staff_client.get(reverse(name))
        assert r.status_code != 403, f'staff should be able to read {name}'


def test_staff_can_report_an_incident(staff_client, acme, incident_type_injury):
    """Reporting an incident is open to any logged-in user (not admin-only)."""
    r = staff_client.get(reverse('compliance:incident_create'))
    assert r.status_code == 200


def test_staff_blocked_from_archive_generate(staff_client):
    r = staff_client.post(reverse('compliance:archive_generate'),
                          data={'period_start': '2026-05-01', 'period_end': '2026-05-31'})
    assert r.status_code in (302, 403)
    assert not cm.AuditLogArchive.objects.exists()


def test_staff_blocked_from_document_publish(staff_client, document):
    document.status = 'approved'
    document.save(update_fields=['status'])
    r = staff_client.post(reverse('compliance:document_publish', args=[document.pk]))
    assert r.status_code in (302, 403)
    document.refresh_from_db()
    assert document.status == 'approved'


def test_staff_blocked_from_recall_progress(staff_client, recall):
    r = staff_client.post(reverse('compliance:recall_progress', args=[recall.pk]))
    assert r.status_code in (302, 403)
    recall.refresh_from_db()
    assert recall.status == 'initiated'


# ---------- Multi-tenant IDOR ----------

def test_other_tenant_cannot_view_incident(globex_client, incident):
    r = globex_client.get(reverse('compliance:incident_detail', args=[incident.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_edit_incident(globex_client, incident):
    r = globex_client.get(reverse('compliance:incident_edit', args=[incident.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_close_incident(globex_client, incident):
    r = globex_client.post(reverse('compliance:incident_close', args=[incident.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_risk(globex_client, risk_assessment):
    r = globex_client.get(reverse('compliance:risk_detail', args=[risk_assessment.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_document(globex_client, document):
    r = globex_client.get(reverse('compliance:document_detail', args=[document.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_sign_document(globex_client, document):
    r = globex_client.post(reverse('compliance:document_sign', args=[document.pk]),
                           data={'typed_name': 'Forged', 'reason': 'approval', 'password': 'pw'})
    assert r.status_code == 404
    assert not cm.ElectronicSignature.objects.filter(document=document).exists()


def test_other_tenant_cannot_view_manifest(globex_client, manifest):
    r = globex_client.get(reverse('compliance:manifest_detail', args=[manifest.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_dispatch_manifest(globex_client, manifest):
    r = globex_client.post(reverse('compliance:manifest_dispatch', args=[manifest.pk]))
    assert r.status_code == 404
    manifest.refresh_from_db()
    assert manifest.status == 'draft'


def test_other_tenant_cannot_view_recall(globex_client, recall):
    r = globex_client.get(reverse('compliance:recall_detail', args=[recall.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_progress_recall(globex_client, recall):
    r = globex_client.post(reverse('compliance:recall_progress', args=[recall.pk]))
    assert r.status_code == 404
    recall.refresh_from_db()
    assert recall.status == 'initiated'


# ---------- Workflow gating (L-03) ----------

def test_cannot_close_un_actioned_incident(admin_client, incident):
    """Only corrective_action incidents can be closed."""
    r = admin_client.post(reverse('compliance:incident_close', args=[incident.pk]))
    assert r.status_code == 302
    incident.refresh_from_db()
    assert incident.status == 'reported'


def test_cannot_publish_draft_document(admin_client, document):
    """Only approved documents can be published."""
    r = admin_client.post(reverse('compliance:document_publish', args=[document.pk]))
    assert r.status_code == 302
    document.refresh_from_db()
    assert document.status == 'draft'


def test_cannot_complete_initiated_recall(admin_client, recall):
    """Only in_progress recalls can be completed."""
    r = admin_client.post(reverse('compliance:recall_complete', args=[recall.pk]))
    assert r.status_code == 302
    recall.refresh_from_db()
    assert recall.status == 'initiated'
