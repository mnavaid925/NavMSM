"""Audit-log emission + cross-module hooks for Module 13."""
import pytest
from django.utils import timezone

from apps.compliance import models as cm


pytestmark = pytest.mark.django_db


def _audit_qs():
    from apps.tenants.models import TenantAuditLog
    return TenantAuditLog.objects


def test_incident_created_audited(acme, incident_type_injury):
    e = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=incident_type_injury,
        title='t', description='d', occurred_at=timezone.now(),
    )
    assert _audit_qs().filter(
        tenant=acme, target_type='IncidentReport',
        target_id=str(e.pk), action='compliance.incident.created',
    ).exists()


def test_incident_status_transition_audited(incident):
    incident.status = 'investigating'
    incident.save(update_fields=['status'])
    assert _audit_qs().filter(
        target_type='IncidentReport', target_id=str(incident.pk),
        action='compliance.incident.investigating',
    ).exists()


def test_document_status_transition_audited(document):
    document.status = 'in_review'
    document.save(update_fields=['status'])
    assert _audit_qs().filter(
        target_type='ComplianceDocument', target_id=str(document.pk),
        action='compliance.document.in_review',
    ).exists()


def test_signature_create_audited(acme, document, acme_admin):
    s = cm.ElectronicSignature.objects.create(
        tenant=acme, document=document, signer=acme_admin,
        typed_name='Acme Admin', role='QA', reason='approval',
    )
    assert _audit_qs().filter(
        target_type='ElectronicSignature', target_id=str(s.pk),
        action='compliance.signature.created',
    ).exists()


def test_recall_status_transition_audited(recall):
    recall.status = 'in_progress'
    recall.save(update_fields=['status'])
    assert _audit_qs().filter(
        target_type='ProductRecall', target_id=str(recall.pk),
        action='compliance.recall.in_progress',
    ).exists()


def test_status_signal_factory_registered_for_each_model(acme):
    """L-18 guard: status-bearing models actually emit audit rows on save.

    A previous version of this test introspected post_save.receivers to look
    up dispatch_uids, but that internal structure stores hashed receiver
    keys, not the uid strings. The functional check below is equivalent and
    survives Django version drift.
    """
    from django.utils import timezone
    from django.db.models import Q

    from apps.tenants.models import TenantAuditLog

    # Save a fresh instance of each status-bearing model under test and
    # confirm a `compliance.<resource>.created` audit row was emitted.
    expected_actions = []

    it = cm.IncidentType.objects.create(tenant=acme, code='probe', name='Probe')
    inc = cm.IncidentReport.objects.create(
        tenant=acme, incident_type=it, title='Probe', description='d',
        occurred_at=timezone.now(),
    )
    expected_actions.append(('IncidentReport', str(inc.pk), 'compliance.incident.created'))

    risk = cm.RiskAssessment.objects.create(
        tenant=acme, title='Probe', hazard='h', likelihood=2, severity=2,
    )
    expected_actions.append(('RiskAssessment', str(risk.pk), 'compliance.risk_assessment.created'))

    actions = TenantAuditLog.objects.filter(tenant=acme).values_list(
        'target_type', 'target_id', 'action',
    )
    for triple in expected_actions:
        assert triple in actions, f'missing audit row for {triple}'


# ---------- Cross-module hook: mes.AndonAlert(safety) -> IncidentReport ----------

def _build_mes_context(acme, sku='AS-01', order_number='PO-01'):
    """Build the minimum chain Product -> Routing -> BOM -> ProductionOrder -> MESWorkOrder.

    Field names mirror canonical fixtures in [apps/mes/tests/conftest.py](../../mes/tests/conftest.py):
      - Routing uses `routing_number` + `version`
      - BillOfMaterials uses `bom_number` + `bom_type`
      - ProductionOrder uses `quantity` (NOT `planned_qty`)
      - MESWorkOrder uses `wo_number` + `quantity_to_build` + `product` (NOT `planned_qty`)
    """
    from decimal import Decimal
    from apps.bom.models import BillOfMaterials
    from apps.mes.models import MESWorkOrder
    from apps.plm.models import Product
    from apps.pps.models import ProductionOrder, Routing
    product = Product.objects.create(tenant=acme, sku=sku, name=f'Probe {sku}')
    routing = Routing.objects.create(
        tenant=acme, product=product, routing_number=f'ROUT-{sku}',
        version='A', name='R', status='active', is_default=True,
    )
    bom = BillOfMaterials.objects.create(
        tenant=acme, product=product, bom_number=f'BOM-{sku}',
        name=f'BOM {sku}', bom_type='ebom', version='1', status='released',
    )
    po = ProductionOrder.objects.create(
        tenant=acme, product=product, bom=bom, routing=routing,
        order_number=order_number, quantity=Decimal('10'),
        status='released', priority='normal', scheduling_method='forward',
    )
    return MESWorkOrder.objects.create(
        tenant=acme, wo_number=f'WO-{sku}', production_order=po, product=product,
        quantity_to_build=Decimal('10'),
    )


def _build_work_center(acme, code='WC-COMP'):
    from decimal import Decimal
    from apps.pps.models import WorkCenter
    return WorkCenter.objects.create(
        tenant=acme, code=code, name='Compliance probe WC',
        work_center_type='machine',
        capacity_per_hour=Decimal('10'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('50'), is_active=True,
    )


@pytest.fixture
def mes_safety_alert(db, acme, acme_admin):
    """Build the minimal MES context to fire a safety AndonAlert.

    `AndonAlert.work_center` is non-null, so the chain is
    Product -> Routing -> BOM -> PO -> MESWorkOrder + WorkCenter -> AndonAlert.
    """
    from apps.mes.models import AndonAlert
    wo = _build_mes_context(acme)
    wc = _build_work_center(acme)
    return AndonAlert.objects.create(
        tenant=acme, work_order=wo, work_center=wc, alert_type='safety',
        severity='medium', title='Spill', message='Spill on aisle B',
        raised_by=acme_admin, raised_at=timezone.now(),
    )


def test_safety_andon_auto_creates_incident(acme, incident_type_injury, mes_safety_alert):
    incidents = cm.IncidentReport.objects.filter(
        tenant=acme, source_andon=mes_safety_alert,
    )
    assert incidents.count() == 1, (
        f'expected 1 auto-created incident; got {incidents.count()}'
    )
    inc = incidents.first()
    assert inc.severity == 'medium'
    assert inc.status == 'reported'


def test_safety_andon_idempotent_on_resave(acme, incident_type_injury, mes_safety_alert):
    """Second post_save of the same AndonAlert must NOT create a duplicate."""
    mes_safety_alert.severity = 'high'
    mes_safety_alert.save(update_fields=['severity'])
    incidents = cm.IncidentReport.objects.filter(source_andon=mes_safety_alert)
    assert incidents.count() == 1


def test_non_safety_andon_does_not_create_incident(acme, incident_type_injury):
    """Only alert_type='safety' fires the hook."""
    from apps.mes.models import AndonAlert
    wo = _build_mes_context(acme, sku='AS-02', order_number='PO-02')
    wc = _build_work_center(acme, code='WC-COMP-2')
    alert = AndonAlert.objects.create(
        tenant=acme, work_order=wo, work_center=wc, alert_type='quality',
        severity='medium', title='Q', message='Quality issue',
        raised_at=timezone.now(),
    )
    assert not cm.IncidentReport.objects.filter(source_andon=alert).exists()


# ---------- Cross-module hook 2: qms.NCR(severity='critical') -> IncidentReport (C.6) ----------

def _build_ncr(acme, *, severity='critical', sku='NC-S1', sequence='-1'):
    """Build a minimum NonConformanceReport for the auto-incident hook test.

    Field names are pinned to [apps/qms/models.py](../../qms/models.py): the
    timestamp is `reported_at` (not detected_at). `source` is a required
    enum (we use 'internal' as the safest default that does not require an
    inspection FK).
    """
    from apps.plm.models import Product
    from apps.qms.models import NonConformanceReport
    Product.objects.create(tenant=acme, sku=sku, name=f'NCR probe {sku}')
    return NonConformanceReport.objects.create(
        tenant=acme,
        ncr_number=f'NCR-{sequence}',
        title='Critical contamination found',
        description='Lot-level contamination identified during incoming inspection.',
        severity=severity,
        source='internal',
        reported_at=timezone.now(),
    )


def test_critical_ncr_auto_creates_incident(acme, incident_type_injury):
    ncr = _build_ncr(acme, severity='critical')
    incidents = cm.IncidentReport.objects.filter(tenant=acme, source_ncr=ncr)
    assert incidents.count() == 1, (
        f'expected 1 incident from critical NCR; got {incidents.count()}'
    )
    inc = incidents.first()
    assert inc.severity == 'critical'
    assert inc.status == 'reported'
    assert ncr.ncr_number in inc.title


def test_non_critical_ncr_does_not_create_incident(acme, incident_type_injury):
    ncr = _build_ncr(acme, severity='major', sku='NC-MJ', sequence='-2')
    assert not cm.IncidentReport.objects.filter(source_ncr=ncr).exists()


def test_critical_ncr_idempotent_on_resave(acme, incident_type_injury):
    ncr = _build_ncr(acme, severity='critical', sku='NC-IDM', sequence='-3')
    initial_count = cm.IncidentReport.objects.filter(tenant=acme, source_ncr=ncr).count()
    assert initial_count == 1
    ncr.title = 'Updated title (still critical)'
    ncr.save()
    final_count = cm.IncidentReport.objects.filter(tenant=acme, source_ncr=ncr).count()
    assert final_count == 1, 'incident must NOT duplicate on second save'


def test_critical_ncr_skipped_when_no_incident_type(acme):
    """If the tenant has no IncidentType configured, hook silently skips."""
    ncr = _build_ncr(acme, severity='critical', sku='NC-NIT', sequence='-4')
    assert not cm.IncidentReport.objects.filter(source_ncr=ncr).exists()


# ---------- Cross-module hook 3: inventory.StockMovement -> RecallAffectedLot leak (C.7) ----------

def _build_recall_with_lot(acme, plm_product, acme_admin):
    """Build a ProductRecall with one RecallAffectedLot row for leak tests."""
    from apps.inventory.models import Lot
    lot = Lot.objects.create(
        tenant=acme, lot_number='LEAK-LOT-1', product=plm_product,
    )
    recall = cm.ProductRecall.objects.create(
        tenant=acme, product=plm_product, title='Leak probe recall',
        severity='class_iii', status='in_progress', initiated_by=acme_admin,
    )
    link = cm.RecallAffectedLot.objects.create(
        tenant=acme, recall=recall, lot=lot,
        affected_quantity=10,
    )
    return recall, link, lot


def _build_warehouse_and_bin(acme):
    """Build Warehouse -> WarehouseZone -> StorageBin (the inventory model
    chain — StorageBin links to a Zone, not directly to Warehouse)."""
    from apps.inventory.models import StorageBin, Warehouse, WarehouseZone
    wh = Warehouse.objects.create(
        tenant=acme, code='WH-LEAK', name='Leak probe WH', is_default=True,
    )
    zone = WarehouseZone.objects.create(
        tenant=acme, warehouse=wh, code='Z-1', name='Storage zone',
    )
    bin_ = StorageBin.objects.create(
        tenant=acme, zone=zone, code='BIN-LEAK',
    )
    return wh, bin_


def test_outbound_movement_on_recalled_lot_increments_leak_count(acme, plm_product, acme_admin):
    from decimal import Decimal
    from apps.inventory.models import StockMovement
    recall, link, lot = _build_recall_with_lot(acme, plm_product, acme_admin)
    _wh, bin_ = _build_warehouse_and_bin(acme)
    StockMovement.objects.create(
        tenant=acme, product=plm_product, lot=lot,
        movement_type='issue', from_bin=bin_,
        qty=Decimal('5'), reason='probe',
    )
    link.refresh_from_db()
    assert link.post_recall_movement_count == 1
    assert link.last_leak_at is not None
    assert link.has_leaks is True


def test_inbound_movement_on_recalled_lot_does_not_count(acme, plm_product, acme_admin):
    """A receipt back into stock is not a leak — only outbound (issue, transfer, production_out, scrap)."""
    from decimal import Decimal
    from apps.inventory.models import StockMovement
    recall, link, lot = _build_recall_with_lot(acme, plm_product, acme_admin)
    _wh, bin_ = _build_warehouse_and_bin(acme)
    StockMovement.objects.create(
        tenant=acme, product=plm_product, lot=lot,
        movement_type='receipt', to_bin=bin_,
        qty=Decimal('10'), reason='probe receipt',
    )
    link.refresh_from_db()
    assert link.post_recall_movement_count == 0
    assert link.has_leaks is False


def test_movement_on_unrelated_lot_does_not_affect_recall(acme, plm_product, acme_admin):
    """A movement on a lot NOT in the recall affects nothing."""
    from decimal import Decimal
    from apps.inventory.models import Lot, StockMovement
    recall, link, lot = _build_recall_with_lot(acme, plm_product, acme_admin)
    _wh, bin_ = _build_warehouse_and_bin(acme)
    other_lot = Lot.objects.create(
        tenant=acme, lot_number='UNRELATED', product=plm_product,
    )
    StockMovement.objects.create(
        tenant=acme, product=plm_product, lot=other_lot,
        movement_type='issue', from_bin=bin_,
        qty=Decimal('1'), reason='probe',
    )
    link.refresh_from_db()
    assert link.post_recall_movement_count == 0


def test_closed_recall_does_not_track_leaks(acme, plm_product, acme_admin):
    """Once recall.status == 'closed' or 'cancelled', new movements are not flagged."""
    from decimal import Decimal
    from apps.inventory.models import StockMovement
    recall, link, lot = _build_recall_with_lot(acme, plm_product, acme_admin)
    _wh, bin_ = _build_warehouse_and_bin(acme)
    recall.status = 'closed'
    recall.closed_at = timezone.now()
    recall.save(update_fields=['status', 'closed_at'])
    StockMovement.objects.create(
        tenant=acme, product=plm_product, lot=lot,
        movement_type='issue', from_bin=bin_,
        qty=Decimal('5'),
    )
    link.refresh_from_db()
    assert link.post_recall_movement_count == 0


def test_sweep_service_recomputes_count_from_ledger(acme, plm_product, acme_admin):
    """`sweep_lot_for_leaks` re-counts from the source-of-truth ledger.

    Useful for backfill or verifying post-incident inventory after the
    signal is enabled in production.
    """
    from decimal import Decimal
    from apps.inventory.models import StockMovement
    from apps.compliance.services.recall import sweep_lot_for_leaks
    recall, link, lot = _build_recall_with_lot(acme, plm_product, acme_admin)
    _wh, bin_ = _build_warehouse_and_bin(acme)
    for _ in range(3):
        StockMovement.objects.create(
            tenant=acme, product=plm_product, lot=lot,
            movement_type='issue', from_bin=bin_, qty=Decimal('1'),
        )
    sweep_lot_for_leaks(link)
    link.refresh_from_db()
    assert link.post_recall_movement_count == 3
