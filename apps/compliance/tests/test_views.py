"""View / URL smoke + workflow happy paths for Module 13."""
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance import models as cm


pytestmark = pytest.mark.django_db


# ---------- List + create smoke ----------

LIST_URLS = [
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


@pytest.mark.parametrize('name', LIST_URLS)
def test_list_pages_render_for_admin(admin_client, name):
    r = admin_client.get(reverse(name))
    assert r.status_code == 200, f'{name} -> {r.status_code}'


def test_incident_create_post(admin_client, acme, incident_type_injury):
    r = admin_client.post(reverse('compliance:incident_create'), data={
        'incident_type': incident_type_injury.pk,
        'title': 'Test', 'description': 'desc',
        'occurred_at': '2026-05-10T10:00',
        'severity': 'medium',
    })
    assert r.status_code in (200, 302)
    assert cm.IncidentReport.objects.filter(tenant=acme, title='Test').exists()


def test_risk_create_post(admin_client, acme):
    r = admin_client.post(reverse('compliance:risk_create'), data={
        'title': 'R1', 'hazard': 'h', 'likelihood': 3, 'severity': 4,
        'control_measures': '', 'notes': '',
    })
    assert r.status_code in (200, 302)
    assert cm.RiskAssessment.objects.filter(tenant=acme, title='R1').exists()


def test_waste_category_create_post(admin_client, acme):
    r = admin_client.post(reverse('compliance:waste_category_create'), data={
        'code': 'wc1', 'name': 'WC1', 'hazard_class': 'general',
        'epa_code': '', 'is_active': 'on',
    })
    assert r.status_code in (200, 302)
    assert cm.WasteCategory.objects.filter(tenant=acme, code='wc1').exists()


# ---------- Workflow happy paths ----------

def test_incident_full_lifecycle(admin_client, acme, incident_type_injury, acme_admin):
    e = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='Lifecycle', description='d', occurred_at=timezone.now(),
        severity='low', reporter=acme_admin,
    )
    # reported -> investigating
    r = admin_client.post(
        reverse('compliance:incident_investigate', args=[e.pk]),
        data={'root_cause': 'RCA filled in'},
    )
    assert r.status_code == 302
    e.refresh_from_db(); assert e.status == 'investigating'
    # investigating -> corrective_action
    r = admin_client.post(
        reverse('compliance:incident_action', args=[e.pk]),
        data={'corrective_actions': 'CA filled in'},
    )
    e.refresh_from_db(); assert e.status == 'corrective_action'
    # corrective_action -> closed
    r = admin_client.post(reverse('compliance:incident_close', args=[e.pk]))
    e.refresh_from_db(); assert e.status == 'closed'


def test_incident_cancel_requires_reason(admin_client, incident):
    r = admin_client.post(
        reverse('compliance:incident_cancel', args=[incident.pk]),
        data={'cancellation_reason': '   '},
    )
    assert r.status_code == 302
    incident.refresh_from_db(); assert incident.status == 'reported'


def test_incident_cancel_with_reason(admin_client, incident):
    r = admin_client.post(
        reverse('compliance:incident_cancel', args=[incident.pk]),
        data={'cancellation_reason': 'duplicate report'},
    )
    incident.refresh_from_db()
    assert incident.status == 'cancelled'
    assert incident.cancellation_reason == 'duplicate report'


def test_risk_workflow(admin_client, risk_assessment):
    admin_client.post(reverse('compliance:risk_submit', args=[risk_assessment.pk]))
    risk_assessment.refresh_from_db(); assert risk_assessment.status == 'in_review'
    admin_client.post(reverse('compliance:risk_approve', args=[risk_assessment.pk]))
    risk_assessment.refresh_from_db(); assert risk_assessment.status == 'approved'
    admin_client.post(reverse('compliance:risk_archive', args=[risk_assessment.pk]))
    risk_assessment.refresh_from_db(); assert risk_assessment.status == 'archived'


def test_safety_audit_workflow_and_record(admin_client, safety_audit):
    admin_client.post(reverse('compliance:audit_start', args=[safety_audit.pk]))
    safety_audit.refresh_from_db(); assert safety_audit.status == 'in_progress'
    admin_client.post(reverse('compliance:audit_record', args=[safety_audit.pk]),
                      data={'item_order': 1, 'question': 'Q1', 'result': 'pass', 'finding': ''})
    safety_audit.refresh_from_db(); assert safety_audit.pass_count == 1
    admin_client.post(reverse('compliance:audit_record', args=[safety_audit.pk]),
                      data={'item_order': 2, 'question': 'Q2', 'result': 'fail', 'finding': 'Mess'})
    safety_audit.refresh_from_db(); assert safety_audit.fail_count == 1
    admin_client.post(reverse('compliance:audit_complete', args=[safety_audit.pk]))
    safety_audit.refresh_from_db(); assert safety_audit.status == 'completed'


def test_document_lifecycle(admin_client, document):
    admin_client.post(reverse('compliance:document_submit', args=[document.pk]))
    document.refresh_from_db(); assert document.status == 'in_review'
    admin_client.post(reverse('compliance:document_approve', args=[document.pk]),
                      data={'comment': 'approved'})
    document.refresh_from_db(); assert document.status == 'approved'
    admin_client.post(reverse('compliance:document_publish', args=[document.pk]))
    document.refresh_from_db()
    assert document.status == 'effective'
    assert document.effective_from is not None


def test_document_reject_returns_to_draft(admin_client, document):
    admin_client.post(reverse('compliance:document_submit', args=[document.pk]))
    admin_client.post(reverse('compliance:document_reject', args=[document.pk]),
                      data={'comment': 'needs work'})
    document.refresh_from_db()
    assert document.status == 'draft'


def test_document_supersede(admin_client, document):
    document.status = 'effective'
    document.effective_from = date.today()
    document.save(update_fields=['status', 'effective_from'])
    admin_client.post(reverse('compliance:document_supersede', args=[document.pk]))
    document.refresh_from_db()
    assert document.status == 'superseded'
    assert document.effective_to is not None


def test_document_sign_requires_password(admin_client, document, acme_admin):
    r = admin_client.post(reverse('compliance:document_sign', args=[document.pk]), data={
        'typed_name': acme_admin.username, 'role': 'QA',
        'reason': 'approval', 'password': 'wrong-password',
    })
    assert r.status_code == 302
    assert not cm.ElectronicSignature.objects.filter(document=document).exists()


def test_document_sign_succeeds_with_correct_password(admin_client, document, acme_admin):
    r = admin_client.post(reverse('compliance:document_sign', args=[document.pk]), data={
        'typed_name': acme_admin.username, 'role': 'QA',
        'reason': 'approval', 'password': 'pw',
    })
    assert r.status_code == 302
    assert cm.ElectronicSignature.objects.filter(document=document, signer=acme_admin).count() == 1


def test_manifest_dispatch_dispose_reconcile(admin_client, manifest):
    admin_client.post(reverse('compliance:manifest_dispatch', args=[manifest.pk]))
    manifest.refresh_from_db(); assert manifest.status == 'in_transit'
    admin_client.post(reverse('compliance:manifest_dispose', args=[manifest.pk]))
    manifest.refresh_from_db(); assert manifest.status == 'disposed'
    admin_client.post(reverse('compliance:manifest_reconcile', args=[manifest.pk]))
    manifest.refresh_from_db(); assert manifest.status == 'reconciled'


def test_recall_workflow(admin_client, recall):
    admin_client.post(reverse('compliance:recall_progress', args=[recall.pk]))
    recall.refresh_from_db(); assert recall.status == 'in_progress'
    admin_client.post(reverse('compliance:recall_complete', args=[recall.pk]))
    recall.refresh_from_db(); assert recall.status == 'completed'
    admin_client.post(reverse('compliance:recall_close', args=[recall.pk]))
    recall.refresh_from_db()
    assert recall.status == 'closed'
    assert recall.closed_at is not None


# ---------- Archive generation + verification ----------

def test_archive_generate_creates_row(admin_client, acme):
    today = date.today()
    r = admin_client.post(reverse('compliance:archive_generate'), data={
        'period_start': today.isoformat(),
        'period_end': today.isoformat(),
    })
    assert r.status_code == 302
    assert cm.AuditLogArchive.objects.filter(tenant=acme).count() == 1


def test_archive_generate_idempotent_per_period(admin_client, acme):
    today = date.today()
    admin_client.post(reverse('compliance:archive_generate'), data={
        'period_start': today.isoformat(), 'period_end': today.isoformat(),
    })
    admin_client.post(reverse('compliance:archive_generate'), data={
        'period_start': today.isoformat(), 'period_end': today.isoformat(),
    })
    assert cm.AuditLogArchive.objects.filter(tenant=acme).count() == 1
