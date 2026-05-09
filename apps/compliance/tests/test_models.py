"""Model layer tests for Module 13 — auto-numbering, computed fields, immutability."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.compliance import models as cm


pytestmark = pytest.mark.django_db


# ---------- Auto-numbering ----------

def test_incident_auto_number(acme, incident_type_injury):
    e1 = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='a', description='a', occurred_at=timezone.now(),
    )
    e2 = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='b', description='b', occurred_at=timezone.now(),
    )
    assert e1.incident_number == 'INC-00001'
    assert e2.incident_number == 'INC-00002'


def test_risk_auto_number(acme):
    r = cm.RiskAssessment.objects.create(
        tenant=acme, title='x', hazard='y', likelihood=2, severity=3,
    )
    assert r.assessment_number == 'RA-00001'


def test_audit_auto_number(acme, checklist, acme_admin):
    a = cm.SafetyAudit.objects.create(
        tenant=acme, checklist=checklist,
        scheduled_for=date.today(), auditor=acme_admin,
    )
    assert a.audit_number == 'AUD-00001'


def test_document_auto_number(acme):
    d = cm.ComplianceDocument.objects.create(
        tenant=acme, title='Doc 1', version='1.0',
    )
    assert d.doc_number == 'DOC-00001'


def test_waste_manifest_auto_number(acme, waste_category):
    m = cm.WasteManifest.objects.create(
        tenant=acme, category=waste_category, generator='G', manifest_date=date.today(),
    )
    assert m.manifest_number == 'WM-00001'


def test_recall_auto_number(acme, plm_product):
    r = cm.ProductRecall.objects.create(
        tenant=acme, product=plm_product, title='R',
    )
    assert r.recall_number == 'RCL-00001'


def test_archive_auto_number(acme):
    a = cm.AuditLogArchive.objects.create(
        tenant=acme, period_start=date.today(), period_end=date.today(),
    )
    assert a.archive_number == 'ALA-00001'


# ---------- Computed / denorm fields ----------

def test_risk_score_computed_in_save(acme):
    r = cm.RiskAssessment.objects.create(
        tenant=acme, title='x', hazard='y', likelihood=4, severity=5,
    )
    assert r.risk_score == 20
    r.likelihood = 2
    r.severity = 3
    r.save()
    assert r.risk_score == 6


def test_risk_band_property(acme):
    # Bands per model: <4 low; 4-8 medium; 9-15 high; >=16 critical.
    cases = [(1, 1, 'low'), (1, 3, 'low'), (2, 2, 'medium'),
             (4, 3, 'high'), (5, 5, 'critical')]
    for L, S, expected in cases:
        r = cm.RiskAssessment(
            tenant=acme, title='t', hazard='h', likelihood=L, severity=S,
        )
        r.save()
        assert r.risk_band == expected, f'L={L} S={S} score={r.risk_score} -> {r.risk_band}, expected {expected}'


def test_residual_score_computed(acme):
    r = cm.RiskAssessment.objects.create(
        tenant=acme, title='x', hazard='y', likelihood=4, severity=4,
        residual_likelihood=2, residual_severity=3,
    )
    assert r.residual_score == 6


def test_residual_score_null_when_only_one_set(acme):
    r = cm.RiskAssessment.objects.create(
        tenant=acme, title='x', hazard='y', likelihood=4, severity=4,
        residual_likelihood=2,  # severity not set
    )
    assert r.residual_score is None


# ---------- Unique constraints ----------

def test_incident_type_unique_per_tenant(acme):
    cm.IncidentType.objects.create(tenant=acme, code='dup', name='A')
    with pytest.raises(IntegrityError):
        cm.IncidentType.objects.create(tenant=acme, code='dup', name='B')


def test_safety_audit_item_unique_per_audit(safety_audit, acme):
    cm.SafetyAuditItem.objects.create(
        tenant=acme, audit=safety_audit, item_order=1,
        question='Q1', result='pass',
    )
    with pytest.raises(IntegrityError):
        cm.SafetyAuditItem.objects.create(
            tenant=acme, audit=safety_audit, item_order=1,
            question='Q1 dup', result='fail',
        )


def test_recall_affected_lot_unique(acme, recall):
    """Ensure a single (recall, lot) pair only links once."""
    from apps.inventory.models import Lot
    lot = Lot.objects.create(
        tenant=acme, lot_number='L-1', product=recall.product,
    )
    cm.RecallAffectedLot.objects.create(
        tenant=acme, recall=recall, lot=lot,
        affected_quantity=Decimal('10'),
    )
    with pytest.raises(IntegrityError):
        cm.RecallAffectedLot.objects.create(
            tenant=acme, recall=recall, lot=lot,
            affected_quantity=Decimal('5'),
        )


# ---------- Immutability ----------

def test_electronic_signature_is_immutable(acme, document, acme_admin):
    sig = cm.ElectronicSignature.objects.create(
        tenant=acme, document=document, signer=acme_admin,
        typed_name='Acme Admin', role='QA', reason='approval',
    )
    sig.typed_name = 'Forged Name'
    with pytest.raises(ValidationError):
        sig.save()


# ---------- Workflow helpers ----------

def test_incident_workflow_helpers_match_status(acme, incident_type_injury):
    e = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='t', description='d', occurred_at=timezone.now(),
    )
    assert e.is_investigatable() and not e.is_actionable()
    e.status = 'investigating'
    assert e.is_actionable() and not e.is_closeable()
    e.status = 'corrective_action'
    assert e.is_closeable()
    e.status = 'closed'
    assert not e.is_editable()


def test_recovery_pct(acme, plm_product):
    r = cm.ProductRecall.objects.create(
        tenant=acme, product=plm_product, title='R',
        affected_quantity=Decimal('100'),
        recovered_quantity=Decimal('30'),
    )
    assert r.recovery_pct == Decimal('30.00')


def test_recovery_pct_when_zero_affected(acme, plm_product):
    r = cm.ProductRecall.objects.create(
        tenant=acme, product=plm_product, title='R',
    )
    assert r.recovery_pct == Decimal('0')


# ---------- L-02 validators ----------

def test_risk_likelihood_outside_range(acme):
    r = cm.RiskAssessment(
        tenant=acme, title='x', hazard='y', likelihood=6, severity=3,
    )
    with pytest.raises(ValidationError):
        r.full_clean()


def test_recall_affected_qty_non_negative(acme, recall):
    from apps.inventory.models import Lot
    lot = Lot.objects.create(
        tenant=acme, lot_number='L-2', product=recall.product,
    )
    link = cm.RecallAffectedLot(
        tenant=acme, recall=recall, lot=lot,
        affected_quantity=Decimal('-5'),
    )
    with pytest.raises(ValidationError):
        link.full_clean()
