"""Idempotent seeder for Module 13 - Compliance & Regulatory Management.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists (Lesson L-12).

Per L-09, all stdout text is plain ASCII (no Unicode arrows / dots / emoji).

Per tenant produces:
    - 4 IncidentType rows (injury / near_miss / environmental / property_damage)
    - 3 IncidentReport rows (one each: low / medium / high severity)
    - 2 RiskAssessment rows (one approved high-risk, one draft medium-risk)
    - 2 SafetyAuditChecklist rows (5S walk + LOTO compliance)
    - 1 SafetyAudit (scheduled tomorrow)
    - 5 ComplianceDocument rows (ISO 9001 SOP, ISO 14001 procedure, WI,
      Form, Policy) - first one effective with a signature.
    - 4 WasteCategory rows (hazardous chemical / e-waste / biohazard / general)
    - 1 WasteManifest (in_transit) with 2 disposal lines
    - 1 ProductRecall (Class III, in_progress) on the first plm.Product
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant
from apps.compliance import models as cm


INCIDENT_TYPES = [
    ('slip_fall', 'Slip / Trip / Fall', 'injury'),
    ('chemical_spill', 'Chemical Spill', 'environmental'),
    ('near_miss', 'Near Miss', 'near_miss'),
    ('equipment_damage', 'Equipment Damage', 'property_damage'),
]

WASTE_CATEGORIES = [
    ('chem_haz', 'Hazardous Chemical Waste', 'hazardous_chemical', 'D001'),
    ('e_waste', 'Electronic Waste', 'e_waste', ''),
    ('biohaz', 'Biohazardous Waste', 'biohazard', ''),
    ('general', 'General Solid Waste', 'general', ''),
]

CHECKLISTS = [
    ('FIVE_S', '5S Workplace Walk', [
        'Sort: are unneeded items visible in the area?',
        'Set in order: are tools and materials in their designated locations?',
        'Shine: is the workspace clean and free of debris?',
        'Standardize: are visual standards posted and current?',
        'Sustain: do operators perform daily 5S checks?',
    ]),
    ('LOTO', 'Lockout/Tagout Compliance', [
        'Are all energy sources isolated before maintenance?',
        'Are personal locks applied (one per worker)?',
        'Are tags filled in with name, date, and reason?',
        'Are stored energy sources released or restrained?',
        'Has a verified test of zero energy been performed?',
    ]),
]


class Command(BaseCommand):
    help = 'Seed Module 13 — Compliance & Regulatory data per tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Tear down compliance data before seeding.')

    def handle(self, *args, **opts):
        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING('No active tenants found.'))
            return

        if opts.get('flush'):
            self._flush(tenants)

        for t in tenants:
            self._seed_tenant(t)

        self.stdout.write(self.style.SUCCESS(
            'Compliance seeding complete. Log in as a tenant admin '
            '(e.g. admin_acme) to see the data; the superuser admin has '
            'tenant=None and will see empty lists.'
        ))

    def _flush(self, tenants):
        for t in tenants:
            cm.RecallNotice.all_objects.filter(tenant=t).delete()
            cm.RecallAffectedLot.all_objects.filter(tenant=t).delete()
            cm.ProductRecall.all_objects.filter(tenant=t).delete()
            cm.WasteDisposalRecord.all_objects.filter(tenant=t).delete()
            cm.WasteManifest.all_objects.filter(tenant=t).delete()
            cm.WasteCategory.all_objects.filter(tenant=t).delete()
            cm.AuditLogArchive.all_objects.filter(tenant=t).delete()
            cm.ElectronicSignature.all_objects.filter(tenant=t).delete()
            cm.DocumentApproval.all_objects.filter(tenant=t).delete()
            cm.ComplianceDocument.all_objects.filter(tenant=t).delete()
            cm.SafetyAuditItem.all_objects.filter(tenant=t).delete()
            cm.SafetyAudit.all_objects.filter(tenant=t).delete()
            cm.SafetyAuditChecklist.all_objects.filter(tenant=t).delete()
            cm.RiskAssessment.all_objects.filter(tenant=t).delete()
            cm.IncidentReport.all_objects.filter(tenant=t).delete()
            cm.IncidentType.all_objects.filter(tenant=t).delete()
        self.stdout.write(self.style.WARNING('Compliance data flushed.'))

    @transaction.atomic
    def _seed_tenant(self, tenant):
        if cm.IncidentReport.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  - {tenant.slug}: data already exists, skipping. (Use --flush to re-seed.)')
            return

        # Pick a tenant admin as the system actor (fallback to None).
        from apps.accounts.models import User
        admin = (
            User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
            or User.objects.filter(tenant=tenant).first()
        )

        # Optional warehouse for incident location (if inventory has data).
        warehouse = None
        try:
            from apps.inventory.models import Warehouse
            warehouse = Warehouse.all_objects.filter(tenant=tenant).first()
        except Exception:
            pass

        # 13.1 Incident Types
        types = {}
        for code, name, cat in INCIDENT_TYPES:
            obj, _ = cm.IncidentType.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={'name': name, 'category': cat, 'is_active': True},
            )
            types[code] = obj

        # 13.1 Incidents
        now = timezone.now()
        cm.IncidentReport.objects.create(
            tenant=tenant, incident_type=types['slip_fall'],
            title='Slip on wet floor near loading dock',
            description='Operator slipped on water spilled from forklift hose. No injury.',
            occurred_at=now - timedelta(days=3),
            location=warehouse, severity='low', status='closed',
            reporter=admin,
            immediate_actions='Cordoned off area; mopped up spill.',
            root_cause='Worn hydraulic hose seal on forklift #3.',
            corrective_actions='Replaced seal; added daily hose inspection to PM.',
            closed_at=now - timedelta(days=1), closed_by=admin,
        )
        cm.IncidentReport.objects.create(
            tenant=tenant, incident_type=types['chemical_spill'],
            title='Coolant spill at CNC station',
            description='Approximately 5L of coolant leaked from CNC-LATHE-02 sump.',
            occurred_at=now - timedelta(days=2),
            location=warehouse, severity='medium', status='investigating',
            reporter=admin,
            immediate_actions='Contained with absorbent; isolated machine.',
        )
        cm.IncidentReport.objects.create(
            tenant=tenant, incident_type=types['near_miss'],
            title='Near miss: pallet fell from racking',
            description='Pallet shifted during forklift extraction; landed in empty aisle.',
            occurred_at=now - timedelta(hours=12),
            location=warehouse, severity='high', status='reported',
            reporter=admin,
        )

        # 13.1 Risk Assessments
        cm.RiskAssessment.objects.create(
            tenant=tenant,
            title='Forklift operations in receiving area',
            hazard='Forklifts crossing pedestrian walkways during shift change.',
            location=warehouse, likelihood=4, severity=4,
            control_measures='Painted floor lanes; mirror at blind corner; high-vis vests required.',
            residual_likelihood=2, residual_severity=4,
            status='approved', approved_by=admin, approved_at=now - timedelta(days=10),
        )
        cm.RiskAssessment.objects.create(
            tenant=tenant,
            title='Manual lifting in finished-goods staging',
            hazard='Repetitive lifting of 15-25kg cartons; risk of MSD.',
            likelihood=3, severity=3,
            control_measures='Lift-assist trolleys provided; rotation policy.',
            status='draft',
        )

        # 13.1 Checklists + Audit
        for code, name, items in CHECKLISTS:
            checklist, created = cm.SafetyAuditChecklist.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={
                    'name': name,
                    'items': [{'order': i + 1, 'question': q} for i, q in enumerate(items)],
                    'is_active': True,
                },
            )
        first_checklist = cm.SafetyAuditChecklist.objects.filter(tenant=tenant).first()
        cm.SafetyAudit.objects.create(
            tenant=tenant, checklist=first_checklist,
            location=warehouse, scheduled_for=date.today() + timedelta(days=1),
            auditor=admin, status='scheduled',
        )

        # 13.2 Documents
        doc1 = cm.ComplianceDocument.objects.create(
            tenant=tenant, doc_type='iso_9001', title='Quality Manual',
            description='Top-level QMS document per ISO 9001:2015 clause 4.4.',
            version='2.1', status='effective',
            effective_from=date.today() - timedelta(days=180),
            owner=admin,
        )
        cm.DocumentApproval.objects.create(
            tenant=tenant, document=doc1, action='publish',
            actor=admin, comment='Annual review approved.',
        )
        if admin is not None:
            cm.ElectronicSignature.objects.create(
                tenant=tenant, document=doc1, signer=admin,
                typed_name=admin.get_full_name() or admin.username,
                role='Quality Manager', reason='approval',
            )
        cm.ComplianceDocument.objects.create(
            tenant=tenant, doc_type='iso_14001', title='Environmental Policy',
            version='1.0', status='effective',
            effective_from=date.today() - timedelta(days=90),
            owner=admin,
        )
        cm.ComplianceDocument.objects.create(
            tenant=tenant, doc_type='sop', title='SOP-001: Receiving Inspection',
            description='Standard procedure for incoming material inspection.',
            version='3.0', status='in_review', owner=admin,
        )
        cm.ComplianceDocument.objects.create(
            tenant=tenant, doc_type='wi', title='WI-014: CNC Lathe Tool Change',
            version='1.2', status='draft', owner=admin,
        )
        cm.ComplianceDocument.objects.create(
            tenant=tenant, doc_type='form', title='Form-007: Calibration Sticker',
            version='1.0', status='effective',
            effective_from=date.today() - timedelta(days=365),
            owner=admin,
        )

        # 13.4 Waste
        wcats = {}
        for code, name, hclass, epa in WASTE_CATEGORIES:
            obj, _ = cm.WasteCategory.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={
                    'name': name, 'hazard_class': hclass,
                    'epa_code': epa, 'is_active': True,
                },
            )
            wcats[code] = obj
        manifest = cm.WasteManifest.objects.create(
            tenant=tenant, category=wcats['chem_haz'],
            generator=tenant.name,
            transporter='EcoLogistics Inc.', disposal_facility='Acme Hazardous Disposal',
            epa_id='STATE-12345',
            manifest_date=date.today() - timedelta(days=2),
            pickup_at=now - timedelta(days=1),
            status='in_transit',
        )
        cm.WasteDisposalRecord.objects.create(
            manifest=manifest, line_number=1,
            description='Spent coolant - mineral-oil based',
            quantity_kg=Decimal('110.0000'),
            container_type='drum_55gal', container_count=2,
            disposal_method='recycling',
        )
        cm.WasteDisposalRecord.objects.create(
            manifest=manifest, line_number=2,
            description='Used cleaning solvents',
            quantity_kg=Decimal('40.0000'),
            container_type='drum_55gal', container_count=1,
            disposal_method='incineration',
        )
        # Recompute denorm to match the lines.
        from django.db.models import Sum
        manifest.total_quantity_kg = (
            manifest.disposal_records.aggregate(t=Sum('quantity_kg')).get('t')
            or Decimal('0')
        )
        manifest.save(update_fields=['total_quantity_kg', 'updated_at'])

        # 13.5 Recall (only if a plm.Product exists for this tenant)
        try:
            from apps.plm.models import Product
            product = Product.all_objects.filter(tenant=tenant).first()
        except Exception:
            product = None
        if product is not None:
            recall = cm.ProductRecall.objects.create(
                tenant=tenant, product=product,
                title=f'Voluntary recall: {product.sku} packaging defect',
                severity='class_iii',
                root_cause='Out-of-spec carton material risks shipping damage.',
                corrective_action='Switch to upgraded carton supplier; recall existing stock.',
                status='in_progress', initiated_by=admin,
            )
            # If we can find lots, link the first one as a demonstration.
            try:
                from apps.inventory.models import Lot
                lot = Lot.all_objects.filter(tenant=tenant, product=product).first()
                if lot is not None:
                    cm.RecallAffectedLot.objects.create(
                        tenant=tenant, recall=recall, lot=lot,
                        affected_quantity=Decimal('500.0000'),
                        recovered_quantity=Decimal('120.0000'),
                    )
                    recall.affected_quantity = Decimal('500.0000')
                    recall.recovered_quantity = Decimal('120.0000')
                    recall.save(update_fields=[
                        'affected_quantity', 'recovered_quantity', 'updated_at',
                    ])
            except Exception:
                pass
            cm.RecallNotice.objects.create(
                tenant=tenant, recall=recall, channel='email',
                audience='Distribution partners (tier-1)',
                subject=f'Voluntary recall notice — {product.sku}',
                body='Please segregate any affected stock and contact us for return logistics.',
                status='draft',
            )

        self.stdout.write(self.style.SUCCESS(f'  - {tenant.slug}: compliance seeded.'))
