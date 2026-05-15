"""Idempotent demo seeder for Module 18 - Returns & RMA Management.

Seeds per tenant (all 5 sub-modules):
    18.1  5 RMA reason codes; 5 RMA requests spanning every status
          (draft / submitted / approved / rejected / cancelled) with lines.
    18.2  Return receipts - the approved RMA auto-spawns one via signal;
          the seeder fills it with inspection lines + dispositions, which
          in turn route a repair order + an inventory restock movement.
    18.3  Repair orders - one auto-spawned from a 'repair' disposition,
          filled with a part-usage row and a labor-log row.
    18.4  3 warranty policies; 4 warranty registrations (incl. 1 aged to
          expired); 2 warranty claims (1 approved-replace).
    18.5  4 failure modes; 4 root-cause categories; 2 return analyses;
          1 supplier chargeback.

Best-effort: SO/Customer/Product/Supplier-dependent rows are skipped
silently when those modules have no data for the tenant.

Safe to rerun without `--flush`. Use `--flush` to wipe RMA data for the
chosen tenants before reseeding.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Tenant
from apps.rma.models import (
    FailureMode,
    RMALine,
    RMARequest,
    RMAReason,
    RepairLaborLog,
    RepairOrder,
    RepairPartUsage,
    ReturnAnalysis,
    ReturnReceipt,
    ReturnReceiptLine,
    RootCauseCategory,
    SupplierChargeback,
    WarrantyClaim,
    WarrantyPolicy,
    WarrantyRegistration,
)

REASONS = [
    ('Dead on Arrival', 'quality_defect'),
    ('Damaged in Transit', 'shipping_damage'),
    ('Wrong Item Received', 'wrong_item'),
    ('No Longer Needed', 'customer_change'),
    ('Within Warranty Failure', 'warranty'),
]
FAILURE_MODES = [
    ('Power Supply Failure', 'electrical'),
    ('Bearing Seizure', 'mechanical'),
    ('Firmware Crash', 'software'),
    ('Surface Corrosion', 'material'),
]
ROOT_CAUSES = [
    ('Component Tolerance Drift', 'supplier'),
    ('Assembly Torque Error', 'manufacturing'),
    ('Inadequate Packaging', 'logistics'),
    ('Design Margin Too Low', 'design'),
]
POLICIES = [
    ('Standard 12-Month', 'parts_and_labor', 12),
    ('Extended 24-Month', 'full', 24),
    ('Parts-Only 6-Month', 'parts', 6),
]


class Command(BaseCommand):
    help = 'Idempotent demo seeder for Module 18 - Returns & RMA Management.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug of a single tenant to seed (default: all).')
        parser.add_argument('--flush', action='store_true',
                            help='Delete existing RMA data before seeding.')

    def handle(self, *args, **opts):
        slug = opts.get('tenant')
        tenants = (
            Tenant.objects.filter(slug=slug)
            if slug else Tenant.objects.filter(is_active=True)
        )
        if not tenants.exists():
            self.stderr.write(self.style.WARNING('No matching tenants found.'))
            return

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n== Tenant: {tenant.slug} =='))
            if opts['flush']:
                self._flush(tenant)
            elif RMAReason.all_objects.filter(tenant=tenant).exists():
                self.stdout.write(self.style.WARNING(
                    '  RMA data already exists. Skipping. Use --flush to re-seed.',
                ))
                continue
            self._seed_tenant(tenant)

        self.stdout.write(self.style.SUCCESS(
            '\nDone. Log in as a tenant admin (e.g. admin_<slug>) to see RMA '
            'data; the global "admin" superuser has no tenant and sees empty lists.',
        ))

    def _flush(self, tenant):
        # Child-first deletion order to respect PROTECT FKs.
        SupplierChargeback.all_objects.filter(tenant=tenant).delete()
        ReturnAnalysis.all_objects.filter(tenant=tenant).delete()
        RepairOrder.all_objects.filter(tenant=tenant).delete()  # cascades parts + labor
        ReturnReceiptLine.all_objects.filter(tenant=tenant).delete()
        ReturnReceipt.all_objects.filter(tenant=tenant).delete()
        WarrantyClaim.all_objects.filter(tenant=tenant).delete()
        WarrantyRegistration.all_objects.filter(tenant=tenant).delete()
        WarrantyPolicy.all_objects.filter(tenant=tenant).delete()
        RMALine.all_objects.filter(tenant=tenant).delete()  # cascades approvals via request
        RMARequest.all_objects.filter(tenant=tenant).delete()
        RMAReason.all_objects.filter(tenant=tenant).delete()
        FailureMode.all_objects.filter(tenant=tenant).delete()
        RootCauseCategory.all_objects.filter(tenant=tenant).delete()
        self.stdout.write('  Flushed existing RMA rows.')

    def _seed_tenant(self, tenant):
        today = timezone.now().date()

        # ---- 18.1 catalogs: reasons ----
        reasons = {}
        for name, category in REASONS:
            obj, _ = RMAReason.all_objects.get_or_create(
                tenant=tenant, name=name,
                defaults={'category': category, 'is_active': True},
            )
            reasons[name] = obj
        self.stdout.write(f'  RMA reasons: {len(reasons)}')

        # ---- 18.5 catalogs: failure modes + root causes ----
        failure_modes = {}
        for name, category in FAILURE_MODES:
            obj, _ = FailureMode.all_objects.get_or_create(
                tenant=tenant, name=name,
                defaults={'category': category, 'is_active': True},
            )
            failure_modes[name] = obj
        root_causes = {}
        for name, area in ROOT_CAUSES:
            obj, _ = RootCauseCategory.all_objects.get_or_create(
                tenant=tenant, name=name,
                defaults={'responsible_area': area, 'is_active': True},
            )
            root_causes[name] = obj
        self.stdout.write(
            f'  Failure modes: {len(failure_modes)}  '
            f'Root causes: {len(root_causes)}',
        )

        # ---- 18.4 catalogs: warranty policies ----
        policies = []
        for name, coverage, months in POLICIES:
            obj = WarrantyPolicy.all_objects.filter(tenant=tenant, name=name).first()
            if obj is None:
                obj = WarrantyPolicy(
                    tenant=tenant, name=name, coverage_type=coverage,
                    duration_months=months, is_active=True,
                    terms=f'{name} - {coverage} coverage for {months} months.',
                )
                obj.save()
            policies.append(obj)
        self.stdout.write(f'  Warranty policies: {len(policies)}')

        # ---- cross-module dependencies (best effort) ----
        customers = products = suppliers = employees = []
        try:
            from apps.sales.models import Customer
            customers = list(Customer.objects.filter(tenant=tenant)[:5])
        except Exception:
            customers = []
        try:
            from apps.plm.models import Product
            products = list(Product.objects.filter(tenant=tenant)[:5])
        except Exception:
            products = []
        try:
            from apps.procurement.models import Supplier
            suppliers = list(Supplier.objects.filter(tenant=tenant)[:3])
        except Exception:
            suppliers = []
        try:
            from apps.labor.models import Employee
            employees = list(Employee.objects.filter(tenant=tenant)[:3])
        except Exception:
            employees = []

        if not customers or not products:
            self.stdout.write(self.style.WARNING(
                '  No sales.Customer / plm.Product rows - skipping RMA requests, '
                'receipts, repairs, warranty and analytics seed.',
            ))
            return

        # ---- 18.1 RMA requests (one per status) ----
        warehouse = None
        try:
            from apps.inventory.models import Warehouse
            warehouse = (
                Warehouse.objects.filter(tenant=tenant, is_default=True).first()
                or Warehouse.objects.filter(tenant=tenant).first()
            )
        except Exception:
            warehouse = None

        reason_list = list(reasons.values())
        rma_specs = [
            ('draft', 'refund'),
            ('submitted', 'replace'),
            ('approved', 'repair'),
            ('rejected', 'credit_note'),
            ('cancelled', 'refund'),
        ]
        rmas = []
        for i, (target_status, action) in enumerate(rma_specs):
            cust = customers[i % len(customers)]
            ref = f'DEMO-CMP-{i + 1:03d}'
            existing = RMARequest.all_objects.filter(
                tenant=tenant, customer=cust, customer_reference=ref,
            ).first()
            if existing:
                rmas.append(existing)
                continue
            rma = RMARequest(
                tenant=tenant, customer=cust,
                request_date=today - timedelta(days=20 - i * 3),
                requested_action=action, status='draft',
                customer_reference=ref,
                reason_summary=f'Customer return - {reason_list[i % len(reason_list)].name}',
                customer_notes='Seeded demo RMA request.',
            )
            rma.save()
            for j, product in enumerate(products[:2]):
                RMALine(
                    tenant=tenant, rma=rma, product=product,
                    quantity=Decimal('2') + Decimal(j),
                    unit_price=Decimal('120.00') - Decimal(j * 15),
                    reason=reason_list[(i + j) % len(reason_list)],
                    condition_reported='defective' if j == 0 else 'damaged',
                    serial_number=f'SN-{tenant.id}-{i}{j}',
                ).save()
            # Walk to the target status (signals only fire on save()).
            if target_status != 'draft':
                rma.status = 'submitted'
                rma.submitted_at = timezone.now()
                rma.save()
            if target_status in ('approved', 'rejected', 'cancelled'):
                rma.status = target_status
                rma.decided_at = timezone.now()
                rma.save()
            rmas.append(rma)
        self.stdout.write(
            f'  RMA requests: {len(rmas)} (' + ', '.join(r.status for r in rmas) + ')',
        )

        approved_rma = next((r for r in rmas if r.status == 'approved'), None)

        # ---- 18.2 Return receipt (auto-drafted by signal on approval) ----
        receipt_lines_created = 0
        receipt = None
        if approved_rma:
            receipt = ReturnReceipt.all_objects.filter(rma=approved_rma).first()
            if receipt and not receipt.lines.exists():
                if warehouse and not receipt.warehouse_id:
                    receipt.warehouse = warehouse
                    receipt.received_by = None
                    receipt.save(update_fields=['warehouse', 'updated_at'])
                dispositions = ['restock', 'repair']
                for k, rma_line in enumerate(approved_rma.lines.all()):
                    ReturnReceiptLine(
                        tenant=tenant, receipt=receipt, rma_line=rma_line,
                        quantity_received=rma_line.quantity,
                        condition_assessed='defective' if k else 'like_new',
                        disposition=dispositions[k % len(dispositions)],
                        inspection_notes='Seeded inspection result.',
                    ).save()
                    receipt_lines_created += 1
                receipt.status = 'inspecting'
                receipt.save(update_fields=['status', 'updated_at'])
        self.stdout.write(
            f'  Return receipts: {1 if receipt else 0}  '
            f'inspection lines: {receipt_lines_created}',
        )

        # ---- 18.3 Repair order (auto-drafted by 'repair' disposition signal) ----
        parts_logged = labor_logged = 0
        repair = RepairOrder.all_objects.filter(tenant=tenant).order_by('id').first()
        if repair:
            if not repair.part_usages.exists():
                RepairPartUsage(
                    tenant=tenant, repair_order=repair, part=products[0],
                    quantity=Decimal('1'), unit_cost=Decimal('18.50'),
                    notes='Seeded replacement part.',
                ).save()
                parts_logged = 1
            if not repair.labor_logs.exists():
                RepairLaborLog(
                    tenant=tenant, repair_order=repair,
                    employee=employees[0] if employees else None,
                    work_date=today, minutes=90, hourly_rate=Decimal('45.00'),
                    notes='Seeded repair labor.',
                ).save()
                labor_logged = 1
            if repair.status == 'draft':
                repair.status = 'in_progress'
                repair.started_at = timezone.now()
                repair.save(update_fields=['status', 'started_at', 'updated_at'])
        self.stdout.write(
            f'  Repair orders: {1 if repair else 0}  '
            f'parts: {parts_logged}  labor: {labor_logged}',
        )

        # ---- 18.4 Warranty registrations + claims ----
        regs = []
        for i, product in enumerate(products[:4]):
            cust = customers[i % len(customers)]
            serial = f'WSN-{tenant.id}-{i:03d}'
            existing = WarrantyRegistration.all_objects.filter(
                tenant=tenant, serial_number=serial,
            ).first()
            if existing:
                regs.append(existing)
                continue
            policy = policies[i % len(policies)]
            # Age the last registration so it is already expired.
            start = today - (timedelta(days=900) if i == 3 else timedelta(days=60))
            reg = WarrantyRegistration(
                tenant=tenant, product=product, customer=cust, policy=policy,
                serial_number=serial, purchase_date=start, start_date=start,
                status='active',
            )
            reg.save()
            if reg.end_date and reg.end_date < today:
                WarrantyRegistration.all_objects.filter(pk=reg.pk).update(
                    status='expired',
                )
                reg.refresh_from_db()
            regs.append(reg)
        self.stdout.write(f'  Warranty registrations: {len(regs)}')

        claims = []
        active_regs = [r for r in regs if r.status == 'active']
        claim_specs = [('approved', 'replace'), ('submitted', 'repair')]
        for i, (target_status, resolution) in enumerate(claim_specs):
            if i >= len(active_regs):
                break
            reg = active_regs[i]
            existing = WarrantyClaim.all_objects.filter(
                tenant=tenant, registration=reg,
            ).first()
            if existing:
                claims.append(existing)
                continue
            claim = WarrantyClaim(
                tenant=tenant, registration=reg, status='submitted',
                resolution=resolution,
                defect_description='Seeded warranty claim defect description.',
            )
            claim.save()
            if target_status != 'submitted':
                claim.status = 'validated'
                claim.save()
                claim.status = 'approved'
                claim.decided_at = timezone.now()
                claim.save()
            claims.append(claim)
        self.stdout.write(f'  Warranty claims: {len(claims)}')

        # ---- 18.5 Return analyses + supplier chargeback ----
        analyses = []
        analysis_source_lines = list(
            RMALine.all_objects.filter(tenant=tenant).order_by('id')[:2]
        )
        fm_list = list(failure_modes.values())
        rc_list = list(root_causes.values())
        for i, rma_line in enumerate(analysis_source_lines):
            existing = ReturnAnalysis.all_objects.filter(
                tenant=tenant, rma_line=rma_line,
            ).first()
            if existing:
                analyses.append(existing)
                continue
            analysis = ReturnAnalysis(
                tenant=tenant, rma_line=rma_line,
                failure_mode=fm_list[i % len(fm_list)],
                root_cause_category=rc_list[i % len(rc_list)],
                supplier=suppliers[0] if suppliers else None,
                analysis_notes='Seeded root-cause analysis.',
                corrective_action='Seeded corrective action - update inspection plan.',
            )
            analysis.save()
            analyses.append(analysis)
        self.stdout.write(f'  Return analyses: {len(analyses)}')

        chargebacks = 0
        if analyses and suppliers:
            analysis = analyses[0]
            if not SupplierChargeback.all_objects.filter(
                tenant=tenant, analysis=analysis,
            ).exists():
                SupplierChargeback(
                    tenant=tenant, analysis=analysis, supplier=suppliers[0],
                    amount=Decimal('450.00'), currency='USD', status='pending',
                    reference='Seeded debit note',
                ).save()
                chargebacks = 1
        self.stdout.write(f'  Supplier chargebacks: {chargebacks}')
