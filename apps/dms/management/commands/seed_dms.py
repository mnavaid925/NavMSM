"""Idempotent demo seeder for Module 19 - Document & Knowledge Management.

Seeds per tenant across all 5 sub-modules:
    19.1  5 categories (Quality / Production / HR / Safety / Engineering);
          5 Documents (sop / work_instruction / policy / form / manual)
          with 1-2 versions each (one effective, one draft + checkout
          example); 1 DocumentAccessRule per Document
    19.2  2 DocumentTemplates (SOP + Work Instruction) with 3-4 fields each
    19.3  1 ApprovalWorkflow ('Standard 2-Stage') with 2 stages; 1 approved
          ApprovalRequest + 2 ApprovalActions + 2 DocumentSignatures
    19.4  2 DocumentAssignments (1 role-based, 1 department-based) with
          2 ReadAcknowledgments seeded against the first assignment
    19.5  2 RetentionPolicies (5-year, 7-year); 1 archived Document with a
          DocumentArchive row; 1 active LegalHold pinning 1 Document

Safe to rerun without `--flush`. Use `--flush` to wipe DMS data for the
chosen tenants before reseeding.

Note: no actual file uploads - DocumentVersion.file is left blank.
Upload real files via the UI to exercise the download view.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.dms.models import (
    ApprovalAction,
    ApprovalStage,
    ApprovalWorkflow,
    AssignmentTarget,
    Document,
    DocumentApprovalRequest,
    DocumentArchive,
    DocumentAccessRule,
    DocumentAssignment,
    DocumentCategory,
    DocumentSignature,
    DocumentTemplate,
    DocumentVersion,
    LegalHold,
    ReadAcknowledgment,
    RetentionPolicy,
    TemplateField,
)
from apps.dms.services.legal_hold import apply_hold


CATEGORIES = [
    ('quality', 'Quality'),
    ('production', 'Production'),
    ('hr', 'Human Resources'),
    ('safety', 'Safety & EHS'),
    ('engineering', 'Engineering'),
]

POLICIES = [
    ('Quality Records - 7 Years', 'quality', 7),
    ('Operational Records - 5 Years', 'production', 5),
]

DOCUMENTS = [
    {
        'title': 'CNC Machining Standard Operating Procedure',
        'doc_type': 'sop',
        'category_code': 'production',
        'policy_name': 'Operational Records - 5 Years',
        'summary': 'Steps for daily setup and operation of CNC machining centres.',
        'keywords': 'cnc, machining, setup, daily',
        'versions': [('1.0', 'released'), ('1.1', 'draft')],
    },
    {
        'title': 'Visual Inspection Work Instruction',
        'doc_type': 'work_instruction',
        'category_code': 'quality',
        'policy_name': 'Quality Records - 7 Years',
        'summary': 'Acceptance criteria for incoming visual inspection.',
        'keywords': 'iqc, inspection, visual',
        'versions': [('A', 'released')],
    },
    {
        'title': 'Information Security Policy',
        'doc_type': 'policy',
        'category_code': 'hr',
        'policy_name': 'Operational Records - 5 Years',
        'summary': 'Mandatory information-handling policy for all staff.',
        'keywords': 'security, infosec, policy',
        'versions': [('1.0', 'released')],
    },
    {
        'title': 'Lockout-Tagout Form',
        'doc_type': 'form',
        'category_code': 'safety',
        'policy_name': 'Quality Records - 7 Years',
        'summary': 'Pre-maintenance lockout-tagout authorisation form.',
        'keywords': 'safety, loto, maintenance',
        'versions': [('F-01', 'released')],
    },
    {
        'title': 'Operator Handbook',
        'doc_type': 'manual',
        'category_code': 'production',
        'policy_name': 'Operational Records - 5 Years',
        'summary': 'Onboarding manual for new shop-floor operators.',
        'keywords': 'training, onboarding, operator',
        'versions': [('2025-01', 'released')],
    },
]

TEMPLATES = [
    {
        'name': 'Standard SOP Template',
        'applies_to_doc_type': 'sop',
        'body': '# Purpose\n{{purpose}}\n\n# Scope\n{{scope}}\n\n# Procedure\n{{steps}}\n\n# Records\n{{records}}',
        'fields': [
            ('purpose', 'Purpose', 'textarea', True, 1),
            ('scope', 'Scope', 'textarea', True, 2),
            ('steps', 'Procedure steps', 'textarea', True, 3),
            ('records', 'Records to retain', 'textarea', False, 4),
        ],
    },
    {
        'name': 'Work Instruction Template',
        'applies_to_doc_type': 'work_instruction',
        'body': '# Task\n{{task}}\n\n# Tools required\n{{tools}}\n\n# Steps\n{{steps}}\n\n# Acceptance criteria\n{{criteria}}',
        'fields': [
            ('task', 'Task description', 'text', True, 1),
            ('tools', 'Tools required', 'textarea', True, 2),
            ('steps', 'Procedure steps', 'textarea', True, 3),
            ('criteria', 'Acceptance criteria', 'textarea', True, 4),
        ],
    },
]


class Command(BaseCommand):
    help = 'Idempotent demo seeder for Module 19 - Document & Knowledge Management.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug of a single tenant to seed (default: all).')
        parser.add_argument('--flush', action='store_true',
                            help='Delete existing DMS data before seeding.')

    def handle(self, *args, **opts):
        tenants = Tenant.objects.filter(is_active=True)
        if opts['tenant']:
            tenants = tenants.filter(slug=opts['tenant'])
        if not tenants:
            self.stdout.write(self.style.WARNING('No active tenants found.'))
            return

        for tenant in tenants:
            self.stdout.write(self.style.NOTICE(f'== Seeding DMS for {tenant.slug} =='))
            if opts['flush']:
                self._flush(tenant)
            with transaction.atomic():
                self._seed_tenant(tenant)
            self.stdout.write(self.style.SUCCESS(f'  done.'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Log in as admin_<slug> / Welcome@123 to see DMS data; '
            "the 'admin' superuser has no tenant and will see an empty dashboard."
        ))

    # ------------------------------------------------------------------ flush
    def _flush(self, tenant):
        # Step 1: release every legal hold + unlock every document so the
        # Document.pre_delete guard doesn't reject the cascade.
        LegalHold.all_objects.filter(tenant=tenant).update(status='released')
        for hold in LegalHold.all_objects.filter(tenant=tenant):
            hold.documents.clear()
        Document.all_objects.filter(tenant=tenant).update(is_locked=False)

        # Step 2: cascade-delete in child-to-parent order.
        for M in (
            ReadAcknowledgment, AssignmentTarget, DocumentAssignment,
            DocumentSignature, ApprovalAction, DocumentApprovalRequest,
            ApprovalStage, ApprovalWorkflow,
            DocumentArchive, LegalHold,
            DocumentAccessRule, DocumentVersion, Document,
            TemplateField, DocumentTemplate,
            RetentionPolicy, DocumentCategory,
        ):
            qs = M.all_objects.filter(tenant=tenant)
            n = qs.count()
            if n:
                qs.delete()
                self.stdout.write(f'  flushed {n} {M.__name__}')

    # ------------------------------------------------------------------ seed
    def _seed_tenant(self, tenant):
        # Skip-if-exists guard per CLAUDE.md.
        if Document.objects.filter(tenant=tenant).exists():
            self.stdout.write('  data already exists - use --flush to re-seed.')
            return

        owner = (
            User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
            or User.objects.filter(tenant=tenant).first()
        )

        # 19.1 Categories
        cats: dict[str, DocumentCategory] = {}
        for code, name in CATEGORIES:
            cat, _ = DocumentCategory.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={'name': name, 'is_active': True},
            )
            cats[code] = cat
        self.stdout.write(f'  categories: {len(cats)}')

        # 19.5 Retention policies (must exist before documents)
        policies: dict[str, RetentionPolicy] = {}
        for name, applies, years in POLICIES:
            existing = RetentionPolicy.objects.filter(tenant=tenant, name=name).first()
            if existing:
                policies[name] = existing
                continue
            p = RetentionPolicy(
                tenant=tenant, name=name,
                applies_to_doc_type=applies if applies != 'production' else 'any',
                retention_years=years,
                archive_action='archive',
            )
            p.save()
            policies[name] = p
        self.stdout.write(f'  retention policies: {len(policies)}')

        # 19.2 Document templates
        templates: dict[str, DocumentTemplate] = {}
        for spec in TEMPLATES:
            existing = DocumentTemplate.objects.filter(tenant=tenant, name=spec['name']).first()
            if existing:
                templates[spec['name']] = existing
                continue
            tpl = DocumentTemplate(
                tenant=tenant, name=spec['name'],
                applies_to_doc_type=spec['applies_to_doc_type'],
                body=spec['body'],
            )
            tpl.save()
            templates[spec['name']] = tpl
            for fname, label, ftype, required, order in spec['fields']:
                TemplateField.objects.get_or_create(
                    tenant=tenant, template=tpl, field_name=fname,
                    defaults={
                        'label': label, 'field_type': ftype,
                        'is_required': required, 'order': order,
                    },
                )
        self.stdout.write(f'  templates: {len(templates)}')

        # 19.1 Documents + versions
        today = timezone.localdate()
        docs: list[Document] = []
        for spec in DOCUMENTS:
            existing = Document.objects.filter(tenant=tenant, title=spec['title']).first()
            if existing:
                docs.append(existing)
                continue
            d = Document(
                tenant=tenant,
                title=spec['title'],
                doc_type=spec['doc_type'],
                category=cats.get(spec['category_code']),
                owner=owner,
                retention_policy=policies.get(spec['policy_name']),
                effective_date=today - timedelta(days=30),
                summary=spec['summary'],
                keywords=spec['keywords'],
                status='draft',
            )
            d.save()
            # Versions
            released = None
            for ver_str, status in spec['versions']:
                v = DocumentVersion(
                    tenant=tenant, document=d, version=ver_str,
                    content_html=f'<p>Seeded {ver_str} content for {d.title}.</p>',
                    change_notes='Initial seed' if status == 'released' else 'Draft revision',
                    uploaded_by=owner,
                    status=status,
                )
                if status == 'released':
                    v.released_at = timezone.now() - timedelta(days=20)
                v.save()
                if status == 'released' and released is None:
                    released = v
            if released:
                Document.all_objects.filter(pk=d.pk).update(
                    status='effective', current_version=released,
                )
                d.refresh_from_db()
            # One access rule per doc - viewer for owner.
            if owner:
                DocumentAccessRule.objects.get_or_create(
                    tenant=tenant, document=d, role='owner', user=owner,
                    defaults={'department': None, 'position': None},
                )
            docs.append(d)
        self.stdout.write(f'  documents: {len(docs)}')

        # 19.3 Approval workflow + a completed approval request on the first doc
        wf, created = ApprovalWorkflow.objects.get_or_create(
            tenant=tenant, name='Standard 2-Stage Review',
            defaults={
                'description': 'Department head review, then quality manager sign-off.',
                'applies_to_doc_type': 'any',
                'is_active': True,
            },
        )
        if created:
            ApprovalStage.objects.create(
                tenant=tenant, workflow=wf, stage_no=1, name='Department Head',
                approver_role='department_head', min_approvals=1, requires_signature=True,
            )
            ApprovalStage.objects.create(
                tenant=tenant, workflow=wf, stage_no=2, name='Quality Manager',
                approver_role='quality_manager', min_approvals=1, requires_signature=True,
            )
        self.stdout.write(f'  workflow: {wf.name}')

        if docs and owner and not DocumentApprovalRequest.objects.filter(tenant=tenant).exists():
            req = DocumentApprovalRequest(
                tenant=tenant, document=docs[0], workflow=wf,
                current_stage_no=2, status='approved',
                requested_by=owner, decided_at=timezone.now(),
                effective_date=today - timedelta(days=20),
                notes='Initial approval (seeded).',
            )
            req.save()
            # Two signatures + actions.
            for stage_no in (1, 2):
                sig = DocumentSignature.objects.create(
                    tenant=tenant, document=docs[0], signer=owner,
                    meaning='approver',
                    typed_name=owner.get_full_name() or owner.username,
                    ip_address='127.0.0.1',
                )
                ApprovalAction.objects.create(
                    tenant=tenant, request=req, stage_no=stage_no,
                    decision='approve', decided_by=owner,
                    notes=f'Stage {stage_no} approved.',
                    signature=sig,
                )
            self.stdout.write('  approval request: 1 (approved) + 2 actions + 2 signatures')

        # 19.4 Assignments
        asn1_created = asn2_created = False
        if docs:
            asn1, asn1_created = DocumentAssignment.objects.get_or_create(
                tenant=tenant, document=docs[0],
                defaults={
                    'assigned_by': owner,
                    'due_date': today + timedelta(days=30),
                    'instructions': 'Please read by end of month.',
                    'status': 'active',
                },
            )
            if asn1_created:
                AssignmentTarget.objects.create(
                    tenant=tenant, assignment=asn1, role='operator',
                )
            # Ack from any non-admin staff user.
            staff_users = User.objects.filter(tenant=tenant).exclude(pk=owner.pk if owner else 0)[:2]
            if staff_users and asn1.document.current_version_id:
                for u in staff_users:
                    ReadAcknowledgment.objects.get_or_create(
                        tenant=tenant, assignment=asn1, acknowledger=u,
                        document_version=asn1.document.current_version,
                        defaults={
                            'typed_name': u.get_full_name() or u.username,
                            'ip_address': '127.0.0.1',
                        },
                    )

        if len(docs) >= 3:
            asn2, asn2_created = DocumentAssignment.objects.get_or_create(
                tenant=tenant, document=docs[2],
                defaults={
                    'assigned_by': owner,
                    'due_date': today + timedelta(days=14),
                    'instructions': 'Mandatory security policy acknowledgement.',
                    'status': 'active',
                },
            )
            if asn2_created:
                AssignmentTarget.objects.create(
                    tenant=tenant, assignment=asn2, role='tenant_admin',
                )
        self.stdout.write(
            f'  assignments: {int(asn1_created) + int(asn2_created)} new'
        )

        # 19.5 Archive: take the form doc out of circulation
        if len(docs) >= 4 and docs[3].status != 'archived':
            DocumentArchive.objects.create(
                tenant=tenant, document=docs[3],
                retention_until=docs[3].retention_until,
                status='archived',
                notes='Superseded by newer revision (seeded).',
                archived_by=owner,
            )
            Document.all_objects.filter(pk=docs[3].pk).update(status='archived')
            self.stdout.write('  archive: 1 document archived')

        # 19.5 Legal hold: pin the second doc
        if len(docs) >= 2 and not LegalHold.objects.filter(tenant=tenant, status='active').exists():
            hold = LegalHold(
                tenant=tenant,
                name='Audit Hold Q1 2026',
                reason='External regulatory audit in progress.',
                requested_by=owner,
                status='active',
            )
            hold.save()
            hold.documents.add(docs[1])
            apply_hold(hold)
            self.stdout.write('  legal hold: 1 active (pinning 1 document)')
