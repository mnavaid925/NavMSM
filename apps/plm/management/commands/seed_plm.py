"""Idempotent seeder for PLM sample data across existing tenants.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Does NOT touch tenants without users (the Django superuser tenant=None
    is intentionally not seeded — its data wouldn't be visible to its login
    anyway)
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import (
    CADDocument, CADDocumentVersion, ComplianceStandard,
    EngineeringChangeOrder, ECOImpactedItem, NPIDeliverable, NPIProject,
    NPIStage, Product, ProductCategory, ProductCompliance, ProductRevision,
    ProductSpecification, ProductVariant,
)


# Global standards catalog — shared across tenants.
STANDARDS = [
    ('ISO_9001', 'ISO 9001 — Quality Management', 'global'),
    ('ISO_14001', 'ISO 14001 — Environmental Management', 'global'),
    ('RoHS', 'RoHS — Restriction of Hazardous Substances', 'eu'),
    ('REACH', 'REACH — Registration, Evaluation, Authorisation of Chemicals', 'eu'),
    ('CE', 'CE Marking — European Conformity', 'eu'),
    ('UL', 'UL — Underwriters Laboratories Safety Certification', 'us'),
    ('FCC', 'FCC — Federal Communications Commission', 'us'),
    ('IPC', 'IPC — Electronic Assembly Standards', 'global'),
]


def _seed_standards(stdout):
    created = 0
    for code, name, region in STANDARDS:
        obj, was_created = ComplianceStandard.objects.get_or_create(
            code=code,
            defaults={'name': name, 'region': region, 'is_active': True},
        )
        if was_created:
            created += 1
    stdout.write(f'  standards: {created} created (catalog total {ComplianceStandard.objects.count()})')


def _seed_categories(tenant):
    """Returns the created/looked-up category dict keyed by code."""
    fixtures = [
        ('RAW', 'Raw Materials', None),
        ('CMP', 'Components', None),
        ('ASM', 'Sub-Assemblies', None),
        ('FIN', 'Finished Goods', None),
        ('METAL', 'Metals', 'RAW'),
        ('PLAS', 'Plastics', 'RAW'),
        ('ELEC', 'Electronics', 'CMP'),
        ('MECH', 'Mechanical', 'CMP'),
    ]
    cats = {}
    for code, name, parent_code in fixtures:
        parent = cats.get(parent_code) if parent_code else None
        obj, _ = ProductCategory.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={'name': name, 'parent': parent, 'is_active': True},
        )
        cats[code] = obj
    return cats


def _seed_products(tenant, cats):
    fixtures = [
        ('SKU-1001', 'Stainless Steel 304 Sheet 2mm', 'METAL', 'raw_material', 'kg'),
        ('SKU-1002', 'ABS Plastic Pellets', 'PLAS', 'raw_material', 'kg'),
        ('SKU-2001', 'M3 Hex Bolt 8mm', 'MECH', 'component', 'ea'),
        ('SKU-2002', 'Heat-Sink 40x40mm', 'MECH', 'component', 'ea'),
        ('SKU-2003', 'PCB Controller v2', 'ELEC', 'component', 'ea'),
        ('SKU-2004', 'LCD Display 16x2', 'ELEC', 'component', 'ea'),
        ('SKU-2005', '24V DC Motor 250W', 'ELEC', 'component', 'ea'),
        ('SKU-3001', 'Power Supply Sub-Assembly', 'ASM', 'sub_assembly', 'ea'),
        ('SKU-3002', 'Cooling Fan Sub-Assembly', 'ASM', 'sub_assembly', 'ea'),
        ('SKU-3003', 'Drive Shaft Module', 'ASM', 'sub_assembly', 'ea'),
        ('SKU-4001', 'Industrial Controller Mk-3', 'FIN', 'finished_good', 'ea'),
        ('SKU-4002', 'Conveyor Drive 1000W', 'FIN', 'finished_good', 'ea'),
        ('SKU-4003', 'Robotic Arm Joint', 'FIN', 'finished_good', 'ea'),
        ('SKU-4004', 'Smart Sensor Pack', 'FIN', 'finished_good', 'set'),
        ('SKU-4005', 'Servo Driver Module', 'FIN', 'finished_good', 'ea'),
        ('SKU-4006', 'PLC Controller Cabinet', 'FIN', 'finished_good', 'ea'),
        ('SKU-4007', 'HMI Touchscreen Panel', 'FIN', 'finished_good', 'ea'),
        ('SKU-4008', 'Linear Actuator 200mm', 'FIN', 'finished_good', 'ea'),
        ('SKU-4009', 'Encoder Module', 'FIN', 'finished_good', 'ea'),
        ('SKU-4010', 'Motor Starter Kit', 'FIN', 'finished_good', 'set'),
    ]
    products = []
    for sku, name, cat_code, ptype, uom in fixtures:
        prod, created = Product.objects.get_or_create(
            tenant=tenant, sku=sku,
            defaults={
                'name': name, 'category': cats[cat_code],
                'product_type': ptype, 'unit_of_measure': uom,
                'description': f'Demo product seeded for {tenant.name}.',
                'status': 'active',
            },
        )
        products.append(prod)

        if created:
            # Two revisions per product
            rev_a = ProductRevision.objects.create(
                tenant=tenant, product=prod, revision_code='A',
                effective_date=date.today() - timedelta(days=180),
                status='superseded', change_notes='Initial release.',
            )
            rev_b = ProductRevision.objects.create(
                tenant=tenant, product=prod, revision_code='B',
                effective_date=date.today() - timedelta(days=30),
                status='active', change_notes='Tolerance tightening + material upgrade.',
            )
            prod.current_revision = rev_b
            prod.save(update_fields=['current_revision'])

            # Specs
            for st, k, v, u in [
                ('physical', 'Weight', f'{random.randint(50, 5000)}', 'g'),
                ('physical', 'Length', f'{random.randint(20, 500)}', 'mm'),
                ('mechanical', 'Tolerance', '±0.05', 'mm'),
            ]:
                ProductSpecification.objects.create(
                    tenant=tenant, product=prod, revision=rev_b,
                    spec_type=st, key=k, value=v, unit=u,
                )

            # 1-2 variants for finished goods
            if ptype == 'finished_good':
                for color in random.sample(['Red', 'Blue', 'Black'], k=2):
                    ProductVariant.objects.create(
                        tenant=tenant, product=prod,
                        variant_sku=f'{sku}-{color[:3].upper()}',
                        name=f'{name} ({color})',
                        attributes={'color': color, 'finish': 'matte'},
                        status='active',
                    )
    return products


def _seed_ecos(tenant, products, admin):
    if EngineeringChangeOrder.objects.filter(tenant=tenant).exists():
        return
    fixtures = [
        ('Material upgrade for SKU-1001', 'material', 'high', 'draft'),
        ('Tolerance tightening for SKU-2001', 'design', 'medium', 'submitted'),
        ('Replacement controller for SKU-2003', 'specification', 'critical', 'approved'),
        ('Process change for SKU-4001 assembly', 'process', 'low', 'implemented'),
        ('Documentation refresh for SKU-3001', 'documentation', 'low', 'draft'),
    ]
    now = timezone.now()
    for i, (title, ctype, prio, status) in enumerate(fixtures, start=1):
        eco = EngineeringChangeOrder(
            tenant=tenant,
            number=f'ECO-{i:05d}',
            title=title, description=f'Demo ECO #{i} for {tenant.name}.',
            change_type=ctype, priority=prio, reason='Continuous improvement.',
            requested_by=admin, status=status,
            target_implementation_date=date.today() + timedelta(days=30),
        )
        if status in ('submitted', 'approved', 'implemented'):
            eco.submitted_at = now - timedelta(days=10)
        if status in ('approved', 'implemented'):
            eco.approved_at = now - timedelta(days=5)
        if status == 'implemented':
            eco.implemented_at = now - timedelta(days=1)
        eco.save()
        # 1-2 impacted items
        for prod in random.sample(products, k=min(2, len(products))):
            ECOImpactedItem.objects.create(
                tenant=tenant, eco=eco, product=prod,
                change_summary=f'Update {prod.sku} per ECO {eco.number}.',
            )


def _seed_cad(tenant, products):
    if CADDocument.objects.filter(tenant=tenant).exists():
        return
    fixtures = [
        ('DRW-001', 'Frame Assembly Drawing', '2d_drawing'),
        ('DRW-002', 'Power Module Schematic', 'schematic'),
        ('DRW-003', 'Controller PCB Layout', 'pcb'),
        ('MDL-001', 'Robotic Arm 3D Model', '3d_model'),
        ('MDL-002', 'Conveyor Drive 3D Model', '3d_model'),
        ('ASM-001', 'Final Assembly View', 'assembly'),
        ('DRW-004', 'Heat-Sink Mechanical Drawing', '2d_drawing'),
        ('DRW-005', 'HMI Front Panel Layout', '2d_drawing'),
    ]
    for i, (num, title, dt) in enumerate(fixtures):
        prod = products[i % len(products)] if products else None
        doc = CADDocument.objects.create(
            tenant=tenant, drawing_number=num, title=title,
            doc_type=dt, product=prod, is_active=True,
            description=f'Seeded {dt} for {tenant.name}.',
        )
        # Note: we cannot seed real binary files — placeholder versions only,
        # without files. Tenant admins should upload real CAD files via the UI.


def _seed_compliance(tenant, products, admin):
    if ProductCompliance.objects.filter(tenant=tenant).exists():
        return
    standards = list(ComplianceStandard.objects.filter(is_active=True))
    if not standards:
        return
    chosen_products = random.sample(products, k=min(8, len(products)))
    for p in chosen_products:
        for std in random.sample(standards, k=min(2, len(standards))):
            status = random.choice(['compliant', 'compliant', 'in_progress', 'pending'])
            issued = date.today() - timedelta(days=random.randint(60, 600))
            expires = issued + timedelta(days=random.choice([365, 730, 1095]))
            ProductCompliance.objects.create(
                tenant=tenant, product=p, standard=std,
                status=status,
                certification_number=f'CRT-{p.sku}-{std.code}-{random.randint(1000, 9999)}',
                issuing_body=random.choice(['TUV', 'SGS', 'BSI', 'UL']),
                issued_date=issued if status == 'compliant' else None,
                expiry_date=expires if status == 'compliant' else None,
                notes='Demo compliance record.',
            )


def _seed_npi(tenant, products, admin):
    if NPIProject.objects.filter(tenant=tenant).exists():
        return
    fixtures = [
        ('Next-gen Controller', 'in_progress', 'design'),
        ('Smart Sensor Pack', 'planning', 'concept'),
        ('Cost-reduced Power Supply', 'in_progress', 'validation'),
    ]
    for i, (name, status, current_stage) in enumerate(fixtures, start=1):
        prod = products[i % len(products)] if products else None
        p = NPIProject.objects.create(
            tenant=tenant,
            code=f'NPI-{i:05d}',
            name=name,
            description=f'Demo NPI initiative #{i} for {tenant.name}.',
            product=prod, project_manager=admin,
            status=status, current_stage=current_stage,
            target_launch_date=date.today() + timedelta(days=90 * i),
        )
        # All 7 stages
        for seq, (stage_code, _label) in enumerate(NPIProject.STAGE_CHOICES, start=1):
            stage_status = 'pending'
            gate = 'pending'
            if seq < list(dict(NPIProject.STAGE_CHOICES)).index(current_stage) + 1:
                stage_status, gate = 'passed', 'go'
            elif stage_code == current_stage:
                stage_status = 'in_progress'
            stage = NPIStage.objects.create(
                tenant=tenant, project=p, stage=stage_code, sequence=seq,
                planned_start=date.today() - timedelta(days=(8 - seq) * 14),
                planned_end=date.today() - timedelta(days=(8 - seq) * 14 - 10),
                status=stage_status, gate_decision=gate,
                gate_notes='Demo gate review.' if gate == 'go' else '',
            )
            # 1-3 deliverables
            for j in range(random.randint(1, 3)):
                NPIDeliverable.objects.create(
                    tenant=tenant, stage=stage,
                    name=f'Deliverable {seq}.{j+1} for {stage.get_stage_display()}',
                    description='Auto-seeded.', owner=admin,
                    due_date=date.today() + timedelta(days=random.randint(-20, 30)),
                    status=random.choice(['pending', 'in_progress', 'done']),
                )


class Command(BaseCommand):
    help = (
        'Seed PLM demo data (categories, products, ECOs, CAD, compliance, '
        'NPI projects) for every tenant. Idempotent — skips per-tenant if '
        'PLM data already exists for that tenant.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe PLM data first.')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write(self.style.WARNING('  Flushing PLM data...'))
            for model in (
                NPIDeliverable, NPIStage, NPIProject,
                ProductCompliance,
                CADDocumentVersion, CADDocument,
                ECOImpactedItem, EngineeringChangeOrder,
                ProductSpecification, ProductVariant,
                ProductRevision, Product, ProductCategory,
            ):
                model.all_objects.all().delete()

        _seed_standards(self.stdout)

        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING(
                'No active tenants found — run seed_tenants first.'
            ))
            return

        for tenant in tenants:
            set_current_tenant(tenant)
            if Product.objects.filter(tenant=tenant).exists():
                self.stdout.write(f'  {tenant.slug}: PLM data exists — skipping (use --flush to re-seed)')
                continue

            admin = User.objects.filter(
                tenant=tenant, is_tenant_admin=True,
            ).first() or User.objects.filter(tenant=tenant).first()

            self.stdout.write(self.style.SUCCESS(f'  {tenant.slug}: seeding PLM...'))
            cats = _seed_categories(tenant)
            products = _seed_products(tenant, cats)
            _seed_ecos(tenant, products, admin)
            _seed_cad(tenant, products)
            _seed_compliance(tenant, products, admin)
            _seed_npi(tenant, products, admin)

        set_current_tenant(None)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('PLM seed complete.'))
        self.stdout.write(self.style.WARNING(
            'NOTE: CAD documents are seeded WITHOUT file binaries. Use the '
            'app to upload real CAD files (allowed: pdf, dwg, dxf, step, stp, '
            'iges, igs, png, jpg, svg, zip; max 25 MB).'
        ))
