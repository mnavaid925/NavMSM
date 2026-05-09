"""Form layer tests — L-01 unique guards, L-14 required reasons, file validators."""
from datetime import date
from io import BytesIO

import pytest

from apps.compliance import forms, models as cm


pytestmark = pytest.mark.django_db


# ---------- L-01 tenant-hidden unique guards ----------

def test_incident_type_form_blocks_duplicate_code(acme, incident_type_injury):
    f = forms.IncidentTypeForm(
        data={'code': 'injury', 'name': 'Dup', 'category': 'injury', 'is_active': True},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'code' in f.errors


def test_incident_type_form_excludes_self_on_edit(acme, incident_type_injury):
    f = forms.IncidentTypeForm(
        data={'code': 'injury', 'name': 'Edited', 'category': 'injury', 'is_active': True},
        instance=incident_type_injury, tenant=acme,
    )
    assert f.is_valid(), f.errors


def test_waste_category_form_blocks_duplicate(acme, waste_category):
    f = forms.WasteCategoryForm(
        data={'code': 'chem', 'name': 'Dup', 'hazard_class': 'hazardous_chemical',
              'epa_code': '', 'is_active': True},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'code' in f.errors


def test_safety_checklist_form_blocks_duplicate(acme, checklist):
    f = forms.SafetyChecklistForm(
        data={'code': '5S', 'name': 'Dup', 'is_active': True},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'code' in f.errors


# ---------- L-14 reason-required workflow forms ----------

def test_incident_investigation_requires_root_cause():
    f = forms.IncidentInvestigationForm(data={'root_cause': '   '})
    assert not f.is_valid()


def test_incident_action_requires_corrective_actions():
    f = forms.IncidentActionForm(data={'corrective_actions': ''})
    assert not f.is_valid()


def test_incident_cancel_requires_reason():
    f = forms.IncidentCancelForm(data={'cancellation_reason': ''})
    assert not f.is_valid()


def test_recall_cancel_requires_reason():
    f = forms.RecallCancelForm(data={'cancellation_reason': ''})
    assert not f.is_valid()


def test_doc_approval_requires_comment():
    f = forms.DocumentApprovalCommentForm(data={'comment': '  '})
    assert not f.is_valid()


def test_signature_requires_typed_name_min_len():
    f = forms.ElectronicSignatureForm(data={'typed_name': 'AB', 'reason': 'approval', 'password': 'x'})
    assert not f.is_valid()
    assert 'typed_name' in f.errors


# ---------- Cross-field validation ----------

def test_risk_form_residual_pair_or_neither(acme):
    f = forms.RiskAssessmentForm(
        data={
            'title': 't', 'hazard': 'h', 'likelihood': 3, 'severity': 4,
            'residual_likelihood': 2,  # severity missing
            'control_measures': '', 'notes': '',
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'residual_severity' in f.errors


def test_archive_generate_form_period_order():
    f = forms.ArchiveGenerateForm(data={
        'period_start': '2026-05-10',
        'period_end': '2026-05-01',
    })
    assert not f.is_valid()
    assert 'period_end' in f.errors


def test_waste_manifest_delivery_after_pickup(acme, waste_category):
    f = forms.WasteManifestForm(
        data={
            'category': waste_category.pk, 'generator': 'G',
            'manifest_date': '2026-05-10',
            'pickup_at': '2026-05-10T10:00',
            'delivered_at': '2026-05-09T10:00',
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'delivered_at' in f.errors


# ---------- File-upload safety on ComplianceDocumentForm (L-22) ----------

def _file(content, name='doc.pdf', ctype='application/pdf'):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content, content_type=ctype)


def test_doc_form_rejects_oversize_attachment(acme):
    big = _file(b'x' * (26 * 1024 * 1024))  # 26 MiB > 25 MiB cap
    f = forms.ComplianceDocumentForm(
        data={'doc_type': 'sop', 'title': 't', 'version': '1.0', 'effective_to': ''},
        files={'attachment': big}, tenant=acme,
    )
    assert not f.is_valid()
    assert 'attachment' in f.errors


def test_doc_form_rejects_bad_content_type(acme):
    f = forms.ComplianceDocumentForm(
        data={'doc_type': 'sop', 'title': 't', 'version': '1.0', 'effective_to': ''},
        files={'attachment': _file(b'PDF', name='doc.pdf', ctype='application/x-msdownload')},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'attachment' in f.errors


def test_doc_form_accepts_pdf(acme):
    f = forms.ComplianceDocumentForm(
        data={'doc_type': 'sop', 'title': 'Quality Manual', 'version': '1.0', 'effective_to': ''},
        files={'attachment': _file(b'%PDF-1.4 ...', name='qm.pdf', ctype='application/pdf')},
        tenant=acme,
    )
    assert f.is_valid(), f.errors
