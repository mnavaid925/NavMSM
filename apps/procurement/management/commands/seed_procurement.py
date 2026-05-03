"""Idempotent seeder for Module 9 - Procurement & Supplier Portal.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists.
  - Auto-numbered records (PUR-, RFQ-, QUO-, ASN-, SUPINV-, BPO-, REL-) check
    existence before creating.

Per Lesson L-09, all stdout text is plain ASCII - no Unicode arrows / dots /
emoji. The Windows cp1252 console crashes on them.

Per Lesson L-08, scorecard period horizon and event-emission align with what
the consumer model expects so KPIs are non-zero on first seed.

Per tenant produces:
    - 8 Suppliers (mix approved/unapproved, mix risk levels) + 1-2 contacts each
    - 1 Supplier portal user (supplier_<slug>_demo / Welcome@123) attached to
      one of the suppliers
    - 4 RFQs (1 draft / 1 issued / 1 closed / 1 awarded), each with 2-3 lines,
      3 invited suppliers, 3 quotations on the awarded one
    - 6 Purchase Orders (statuses: draft/submitted/approved/acknowledged/
      in_progress/received). One PO carries 2 revisions
    - 2 ASNs (1 in_transit, 1 received)
    - 2 Supplier Invoices (1 under_review, 1 approved with payment ref)
    - 1 Blanket Order (active, 3 lines), 2 Releases (1 released, 1 received)
    - SupplierMetricEvents back-filled from POs/GRNs/IQCs over the previous month
    - 1 SupplierScorecard per active supplier for the previous month
"""
from datetime import date, timedelta
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.core.models import Tenant
from apps.plm.models import Product

from apps.procurement.models import (
    BlanketOrder, BlanketOrderLine,
    PurchaseOrder, PurchaseOrderApproval, PurchaseOrderLine, PurchaseOrderRevision,
    QuotationAward, QuotationLine,
    RequestForQuotation, RFQLine, RFQSupplier,
    ScheduleRelease, ScheduleReleaseLine,
    Supplier, SupplierASN, SupplierASNLine, SupplierContact,
    SupplierInvoice, SupplierInvoiceLine, SupplierMetricEvent,
    SupplierQuotation, SupplierScorecard,
)
from apps.procurement.services.po_revision import next_revision_number, snapshot_po
from apps.procurement.services.scorecard import compute_scorecard


SUPPLIER_SEED = [
    ('SUP001', 'Globex Components', 'orders@globex.example', 'low', True),
    ('SUP002', 'Acme Steel Co', 'sales@acmesteel.example', 'low', True),
    ('SUP003', 'Bright Plastics Ltd', 'info@brightplastics.example', 'medium', True),
    ('SUP004', 'NorthLine Logistics', 'ops@northline.example', 'medium', True),
    ('SUP005', 'Apex Electronics', 'sales@apexelectronics.example', 'low', True),
    ('SUP006', 'Riverstone Castings', 'orders@riverstone.example', 'high', False),
    ('SUP007', 'Quantum Polymers', 'sales@quantumpolymers.example', 'medium', True),
    ('SUP008', 'EastBay Fabrication', 'hello@eastbayfab.example', 'low', False),
]


def _seed_suppliers(tenant, stdout):
    if Supplier.all_objects.filter(tenant=tenant).exists():
        stdout.write('  suppliers: skipped (already seeded)')
        return list(Supplier.all_objects.filter(tenant=tenant).order_by('code'))

    suppliers = []
    for code, name, email, risk, approved in SUPPLIER_SEED:
        sup = Supplier.all_objects.create(
            tenant=tenant, code=code, name=name, legal_name=f'{name} Inc.',
            email=email, phone='+1-555-0100', website=f'https://{name.lower().split()[0]}.example',
            tax_id=f'TX-{code}', address=f'200 Industrial Park\nUnit {code}',
            country='US', currency='USD',
            payment_terms='NET30', delivery_terms='FOB',
            is_active=True, is_approved=approved, risk_rating=risk,
            notes='Seed data.',
        )
        SupplierContact.all_objects.create(
            tenant=tenant, supplier=sup, name=f'{name.split()[0]} Sales',
            role='Sales Manager', email=email, phone='+1-555-0200',
            is_primary=True, is_active=True,
        )
        suppliers.append(sup)
    stdout.write(f'  suppliers: created {len(suppliers)}')
    return suppliers


def _seed_supplier_user(tenant, suppliers, stdout):
    """Create one supplier-portal user per tenant attached to suppliers[0]."""
    if not suppliers:
        return None
    target_supplier = suppliers[0]
    username = f'supplier_{tenant.slug}_demo'
    existing = User.objects.filter(username=username).first()
    if existing:
        stdout.write('  supplier user: already exists')
        return existing
    u = User.objects.create_user(
        username=username,
        email=target_supplier.email,
        password='Welcome@123',
        first_name=target_supplier.name.split()[0],
        last_name='Portal',
        tenant=tenant, role='supplier',
        supplier_company=target_supplier,
    )
    UserProfile.objects.get_or_create(user=u)
    stdout.write(f'  supplier user: {username} (Welcome@123) -> {target_supplier.code}')
    return u


def _purchasable_products(tenant, k=3):
    return list(
        Product.all_objects.filter(
            tenant=tenant, product_type__in=('raw_material', 'component'),
        )[:k]
    )


def _seed_rfqs(tenant, suppliers, admin, stdout):
    if RequestForQuotation.all_objects.filter(tenant=tenant).exists():
        stdout.write('  rfqs: skipped (already seeded)')
        return

    products = _purchasable_products(tenant, k=3)
    if not products:
        stdout.write('  rfqs: no purchasable products; skipping')
        return

    today = timezone.now().date()
    rfq_seed = [
        ('RFQ Draft - Steel sheets',     'draft',    today,                    today + timedelta(days=14)),
        ('RFQ Issued - PCB components',  'issued',   today - timedelta(days=3), today + timedelta(days=11)),
        ('RFQ Closed - Castings batch',  'closed',   today - timedelta(days=14), today - timedelta(days=2)),
        ('RFQ Awarded - Resin Q2',       'awarded',  today - timedelta(days=21), today - timedelta(days=7)),
    ]
    rfqs = []
    for title, status, issued, due in rfq_seed:
        r = RequestForQuotation.all_objects.create(
            tenant=tenant, title=title,
            description=f'Seeded RFQ: {title}',
            currency='USD',
            issued_date=issued if status != 'draft' else None,
            response_due_date=due,
            round_number=1, status=status, created_by=admin,
        )
        for i, prod in enumerate(products[:2], start=1):
            RFQLine.all_objects.create(
                tenant=tenant, rfq=r, product=prod,
                description=prod.name, quantity=Decimal('100'),
                unit_of_measure='EA', target_price=Decimal('10.00'),
                required_date=due,
            )
        # Invite first 3 suppliers
        for sup in suppliers[:3]:
            RFQSupplier.all_objects.create(
                tenant=tenant, rfq=r, supplier=sup,
                participation_status='quoted' if status in ('closed', 'awarded') else 'invited',
                responded_at=timezone.now() if status in ('closed', 'awarded') else None,
            )
        rfqs.append(r)

    # Add quotations + award on the last (awarded) RFQ
    awarded_rfq = rfqs[-1]
    quotations = []
    rfq_lines = list(awarded_rfq.lines.all())
    for idx, sup in enumerate(suppliers[:3]):
        q = SupplierQuotation.all_objects.create(
            tenant=tenant, rfq=awarded_rfq, supplier=sup,
            quote_date=awarded_rfq.issued_date + timedelta(days=2),
            valid_until=awarded_rfq.issued_date + timedelta(days=60),
            currency='USD',
            payment_terms='NET30', delivery_terms='FOB',
            status='accepted' if idx == 0 else 'rejected',
            notes='Seeded quote.',
        )
        for line in rfq_lines:
            QuotationLine.all_objects.create(
                tenant=tenant, quotation=q, rfq_line=line,
                unit_price=Decimal('9.50') + Decimal(str(idx * 0.5)),
                lead_time_days=14 + idx * 3,
                min_order_qty=Decimal('50'),
                comments=f'Bid by {sup.code}',
            )
        q.refresh_from_db()
        q.recompute_totals()
        quotations.append(q)
    QuotationAward.all_objects.create(
        tenant=tenant, rfq=awarded_rfq, quotation=quotations[0],
        awarded_by=admin, awarded_at=timezone.now() - timedelta(days=5),
        award_notes='Best price + acceptable lead time.',
        auto_create_po=False,
    )
    stdout.write(f'  rfqs: created 4 (1 awarded with 3 quotations + winner)')


def _seed_purchase_orders(tenant, suppliers, admin, stdout):
    if PurchaseOrder.all_objects.filter(tenant=tenant).exists():
        stdout.write('  POs: skipped (already seeded)')
        return list(PurchaseOrder.all_objects.filter(tenant=tenant).order_by('id'))

    products = _purchasable_products(tenant, k=4)
    if not products:
        stdout.write('  POs: no purchasable products; skipping')
        return []

    today = timezone.now().date()
    po_seed = [
        ('draft',        suppliers[0], 'normal'),
        ('submitted',    suppliers[1], 'normal'),
        ('approved',     suppliers[2], 'high'),
        ('acknowledged', suppliers[0], 'normal'),
        ('in_progress',  suppliers[3], 'rush'),
        ('received',     suppliers[1], 'normal'),
    ]
    pos = []
    for idx, (status, sup, prio) in enumerate(po_seed):
        po = PurchaseOrder(
            tenant=tenant, supplier=sup,
            order_date=today - timedelta(days=20 - idx * 3),
            required_date=today + timedelta(days=14),
            currency='USD',
            payment_terms='NET30', delivery_terms='FOB',
            priority=prio, status='draft',
            notes=f'Seeded PO ({status}).',
            created_by=admin,
        )
        po.save()
        # Add 2 lines
        for j, prod in enumerate(products[:2], start=1):
            PurchaseOrderLine.all_objects.create(
                tenant=tenant, po=po, product=prod,
                description=prod.name,
                quantity=Decimal('25') + Decimal(str(j * 5)),
                unit_of_measure='EA',
                unit_price=Decimal('12.50'),
                tax_pct=Decimal('5.00'), discount_pct=Decimal('0'),
                required_date=today + timedelta(days=14),
            )
        po.refresh_from_db()
        po.recompute_totals()
        # Move to target status (bypassing signals so we don't bloat audit log).
        extra = {'status': status}
        if status in ('approved', 'acknowledged', 'in_progress', 'received'):
            extra['approved_by'] = admin
            extra['approved_at'] = timezone.now() - timedelta(days=5)
        if status in ('acknowledged', 'in_progress', 'received'):
            extra['acknowledged_by'] = admin
            extra['acknowledged_at'] = timezone.now() - timedelta(days=4)
        PurchaseOrder.all_objects.filter(pk=po.pk).update(**extra)

        if status == 'approved':
            PurchaseOrderApproval.all_objects.create(
                tenant=tenant, po=po, approver=admin,
                decision='approved', comments='Approved via seed.',
            )
        pos.append(po)

    # Add 2 revisions to the second-to-last PO so the revision UI demo works.
    target_po = pos[-2]
    target_po.refresh_from_db()
    for rev_n, summary in [(1, 'Initial draft snapshot'), (2, 'Updated qty per ECO')]:
        PurchaseOrderRevision.all_objects.create(
            tenant=tenant, po=target_po, revision_number=rev_n,
            change_summary=summary, changed_by=admin,
            snapshot_json=snapshot_po(target_po),
        )
    stdout.write(f'  POs: created {len(pos)} ({len(po_seed)} statuses, 2 revisions on one)')
    return pos


def _seed_asns(tenant, pos, stdout):
    if SupplierASN.all_objects.filter(tenant=tenant).exists():
        stdout.write('  ASNs: skipped (already seeded)')
        return

    candidates = [p for p in pos if p.status in ('acknowledged', 'in_progress', 'received')]
    if not candidates:
        stdout.write('  ASNs: no acknowledged POs; skipping')
        return
    today = timezone.now().date()
    asn_seed = [
        ('in_transit', candidates[0], today - timedelta(days=2)),
        ('received', candidates[-1], today - timedelta(days=10)),
    ]
    for status, po, ship in asn_seed:
        asn = SupplierASN(
            tenant=tenant, purchase_order=po,
            ship_date=ship, expected_arrival_date=ship + timedelta(days=4),
            carrier='UPS Freight', tracking_number=f'1Z9999W{po.pk:08d}',
            total_packages=2, status='draft',
            notes='Seeded ASN.',
        )
        asn.save()
        for line in po.lines.all()[:2]:
            SupplierASNLine.all_objects.create(
                tenant=tenant, asn=asn, po_line=line,
                quantity_shipped=line.quantity,
                lot_number=f'LOT-{po.po_number}',
            )
        SupplierASN.all_objects.filter(pk=asn.pk).update(
            status=status,
            submitted_at=timezone.now() - timedelta(days=2),
            received_at=timezone.now() - timedelta(days=1) if status == 'received' else None,
        )
    stdout.write('  ASNs: created 2 (1 in_transit, 1 received)')


def _seed_invoices(tenant, suppliers, pos, admin, stdout):
    if SupplierInvoice.all_objects.filter(tenant=tenant).exists():
        stdout.write('  invoices: skipped (already seeded)')
        return

    candidates = [p for p in pos if p.status in ('acknowledged', 'in_progress', 'received')]
    if not candidates:
        stdout.write('  invoices: no candidate POs; skipping')
        return

    today = timezone.now().date()
    seed = [
        ('under_review', candidates[0], 'INV-A-1001'),
        ('approved',     candidates[-1], 'INV-B-2002'),
    ]
    for status, po, vendor_no in seed:
        inv = SupplierInvoice(
            tenant=tenant, vendor_invoice_number=vendor_no, supplier=po.supplier,
            purchase_order=po,
            invoice_date=today - timedelta(days=5),
            due_date=today + timedelta(days=25),
            currency='USD',
            subtotal=po.subtotal, tax_total=po.tax_total, grand_total=po.grand_total,
            status='submitted',
            notes='Seeded invoice.',
            submitted_by=admin,
        )
        inv.save()
        SupplierInvoiceLine.all_objects.create(
            tenant=tenant, invoice=inv, po_line=po.lines.first(),
            description=po.lines.first().description or 'Goods',
            quantity=po.lines.first().quantity,
            unit_price=po.lines.first().unit_price,
        )
        SupplierInvoice.all_objects.filter(pk=inv.pk).update(
            status=status,
            payment_reference='PAY-2026-0001' if status == 'approved' else '',
        )
    stdout.write('  invoices: created 2 (1 under_review, 1 approved)')


def _seed_blanket(tenant, suppliers, admin, stdout):
    if BlanketOrder.all_objects.filter(tenant=tenant).exists():
        stdout.write('  blanket: skipped (already seeded)')
        return

    products = _purchasable_products(tenant, k=3)
    if not products:
        stdout.write('  blanket: no products; skipping')
        return

    today = timezone.now().date()
    bpo = BlanketOrder(
        tenant=tenant, supplier=suppliers[1],
        start_date=today - timedelta(days=30), end_date=today + timedelta(days=335),
        currency='USD',
        total_committed_value=Decimal('100000.00'), consumed_value=Decimal('0'),
        status='draft',
        notes='12-month framework agreement.',
        created_by=admin,
    )
    bpo.save()
    bol_objs = []
    for prod in products[:3]:
        bol = BlanketOrderLine.all_objects.create(
            tenant=tenant, blanket_order=bpo, product=prod,
            description=prod.name,
            total_quantity=Decimal('500'), consumed_quantity=Decimal('0'),
            unit_of_measure='EA', unit_price=Decimal('15.00'),
        )
        bol_objs.append(bol)
    BlanketOrder.all_objects.filter(pk=bpo.pk).update(
        status='active',
        signed_at=timezone.now() - timedelta(days=30), signed_by=admin,
    )
    bpo.refresh_from_db()

    # Two releases - one released (consumes), one received (already counted).
    rel1 = ScheduleRelease(
        tenant=tenant, blanket_order=bpo,
        release_date=today - timedelta(days=15),
        required_date=today - timedelta(days=5),
        status='draft', created_by=admin,
    )
    rel1.save()
    for bol in bol_objs:
        ScheduleReleaseLine.all_objects.create(
            tenant=tenant, release=rel1, blanket_order_line=bol,
            quantity=Decimal('50'), required_date=today - timedelta(days=5),
        )
    rel1.refresh_from_db()
    rel1.recompute_total()
    # Apply consumption manually to denorms (avoid signal cascade).
    ScheduleRelease.all_objects.filter(pk=rel1.pk).update(status='received')
    consumed_total = Decimal('0')
    for bol in bol_objs:
        BlanketOrderLine.all_objects.filter(pk=bol.pk).update(
            consumed_quantity=Decimal('50'),
        )
        consumed_total += Decimal('50') * bol.unit_price
    BlanketOrder.all_objects.filter(pk=bpo.pk).update(consumed_value=consumed_total)

    rel2 = ScheduleRelease(
        tenant=tenant, blanket_order=bpo,
        release_date=today - timedelta(days=2),
        required_date=today + timedelta(days=10),
        status='draft', created_by=admin,
    )
    rel2.save()
    for bol in bol_objs:
        ScheduleReleaseLine.all_objects.create(
            tenant=tenant, release=rel2, blanket_order_line=bol,
            quantity=Decimal('25'),
            required_date=today + timedelta(days=10),
        )
    rel2.refresh_from_db()
    rel2.recompute_total()
    ScheduleRelease.all_objects.filter(pk=rel2.pk).update(status='released')

    stdout.write('  blanket: created 1 active blanket (3 lines) + 2 releases (1 received, 1 released)')


def _seed_metric_events_and_scorecards(tenant, suppliers, pos, admin, stdout):
    if SupplierScorecard.all_objects.filter(tenant=tenant).exists():
        stdout.write('  scorecards: skipped (already seeded)')
        return

    today = timezone.now().date()
    period_end = date(today.year, today.month, 1) - timedelta(days=1)
    period_start = date(period_end.year, period_end.month, 1)

    rng = random.Random(tenant.pk)
    for sup in suppliers:
        if not sup.is_active:
            continue
        # Synthesize 8-12 events per supplier across the period.
        n_events = rng.randint(8, 12)
        for _ in range(n_events):
            roll = rng.random()
            if roll < 0.55:
                ev_type = 'po_received_on_time'
                value = 0
            elif roll < 0.80:
                ev_type = 'po_received_late'
                value = rng.randint(1, 7)
            elif roll < 0.92:
                ev_type = 'quality_pass'
                value = 0
            else:
                ev_type = 'quality_fail'
                value = 1
            posted_at = timezone.make_aware(
                timezone.datetime.combine(
                    period_start + timedelta(days=rng.randint(0, 27)),
                    timezone.datetime.min.time(),
                )
            )
            SupplierMetricEvent.all_objects.create(
                tenant=tenant, supplier=sup,
                event_type=ev_type, value=Decimal(str(value)),
                posted_at=posted_at,
                reference_type='seed', reference_id=str(sup.pk),
                notes='Seed metric event.',
            )

    # Compute scorecards.
    rankings = []
    for sup in suppliers:
        if not sup.is_active:
            continue
        events = list(SupplierMetricEvent.all_objects.filter(
            tenant=tenant, supplier=sup,
            posted_at__date__gte=period_start, posted_at__date__lte=period_end,
        ))
        result = compute_scorecard(events)
        total_pos = sum(
            1 for ev in events if ev.event_type in ('po_received_on_time', 'po_received_late')
        )
        sc = SupplierScorecard.all_objects.create(
            tenant=tenant, supplier=sup,
            period_start=period_start, period_end=period_end,
            otd_pct=result.otd_pct,
            quality_rating=result.quality_rating,
            defect_rate_pct=result.defect_rate_pct,
            price_variance_pct=result.price_variance_pct,
            responsiveness_rating=result.responsiveness_rating,
            overall_score=result.overall_score,
            total_pos=total_pos,
            total_value=Decimal('0'),
            computed_at=timezone.now(), computed_by=admin,
        )
        rankings.append(sc)

    rankings.sort(key=lambda x: -x.overall_score)
    for idx, sc in enumerate(rankings, start=1):
        SupplierScorecard.all_objects.filter(pk=sc.pk).update(rank=idx)

    stdout.write(
        f'  scorecards: created {len(rankings)} for period {period_start}..{period_end}'
    )


class Command(BaseCommand):
    help = 'Seed Module 9 (Procurement & Supplier Portal) demo data per tenant. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe all procurement data first.')

    def handle(self, *args, **options):
        if options.get('flush'):
            self.stdout.write('flushing all procurement data...')
            for model in (
                ScheduleReleaseLine, ScheduleRelease, BlanketOrderLine, BlanketOrder,
                SupplierInvoiceLine, SupplierInvoice,
                SupplierASNLine, SupplierASN,
                SupplierScorecard, SupplierMetricEvent,
                QuotationAward, QuotationLine, SupplierQuotation,
                RFQSupplier, RFQLine, RequestForQuotation,
                PurchaseOrderApproval, PurchaseOrderRevision, PurchaseOrderLine, PurchaseOrder,
                SupplierContact, Supplier,
            ):
                model.all_objects.all().delete()

        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING('No active tenants. Run seed_tenants first.'))
            return

        for tenant in tenants:
            self.stdout.write(self.style.HTTP_INFO(f'-> tenant: {tenant.slug}'))
            admin = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
            if admin is None:
                self.stdout.write(self.style.WARNING(f'  no tenant admin for {tenant.slug}; skipping.'))
                continue
            suppliers = _seed_suppliers(tenant, self.stdout)
            _seed_supplier_user(tenant, suppliers, self.stdout)
            _seed_rfqs(tenant, suppliers, admin, self.stdout)
            pos = _seed_purchase_orders(tenant, suppliers, admin, self.stdout)
            _seed_asns(tenant, pos, self.stdout)
            _seed_invoices(tenant, suppliers, pos, admin, self.stdout)
            _seed_blanket(tenant, suppliers, admin, self.stdout)
            _seed_metric_events_and_scorecards(tenant, suppliers, pos, admin, self.stdout)

        self.stdout.write(self.style.SUCCESS('seed_procurement: done.'))
        self.stdout.write(
            'Log in as a tenant admin (admin_acme / Welcome@123) to view the data, '
            'or as a supplier-portal demo user (e.g. supplier_acme_demo / Welcome@123).'
        )
        self.stdout.write(
            'WARNING: Django superuser has tenant=None and will see empty pages by design.'
        )
