"""Module 13 - Compliance & Regulatory Management.

Sub-modules:
    13.1 Environmental Health & Safety   (IncidentType, IncidentReport,
                                          RiskAssessment,
                                          SafetyAuditChecklist,
                                          SafetyAudit, SafetyAuditItem)
    13.2 Regulatory Document Control     (ComplianceDocument,
                                          DocumentApproval,
                                          ElectronicSignature)
    13.3 Audit Trail & Data Integrity    (relies on tenants.TenantAuditLog;
                                          AuditLogArchive snapshots)
    13.4 Waste & Emission Tracking       (WasteCategory, WasteManifest,
                                          WasteDisposalRecord)
    13.5 Recall & Traceability           (ProductRecall, RecallAffectedLot,
                                          RecallNotice)

Cross-module integration (additive, no schema changes to other apps):
    - mes.AndonAlert(type='safety').post_save  -> IncidentReport
      (idempotent on source_andon FK)
    - inventory.Lot                            <-> RecallAffectedLot (FK)
    - utility.CarbonEmission                   referenced from waste section
      (no FK; the README describes the relationship)

Lessons applied (all proven in Module 12 / 14):
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal carries explicit MinValueValidator
    * L-03 view+template status gate parity via is_*() helpers
    * L-12 auto-numbering retry loop via save() (mirrors cost / utility)
    * L-13 transaction.atomic() around denorm bumps
    * L-14 per-workflow forms enforce required fields (cancel/sign/close)
    * L-17 PROTECT on audit-trail children (ElectronicSignature.document,
            RecallAffectedLot.recall, WasteDisposalRecord.manifest)
    * L-18 weak=False + dispatch_uid on every closure receiver
    * L-22 — file uploads validate extension + content_type + size cap +
            magic-byte sniff (mirrors utility.UtilityConsumptionImportForm).
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator, MinValueValidator, MaxValueValidator,
)
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


NON_NEG = MinValueValidator(Decimal('0'))
PCT_MAX = MaxValueValidator(Decimal('100'))
RISK_MAX = MaxValueValidator(5)
RISK_MIN = MinValueValidator(1)


# ============================================================================
# 13.1  ENVIRONMENTAL HEALTH & SAFETY
# ============================================================================

class IncidentType(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of incident classifications."""

    CATEGORY_CHOICES = [
        ('injury', 'Personal Injury'),
        ('near_miss', 'Near Miss'),
        ('environmental', 'Environmental'),
        ('property_damage', 'Property Damage'),
        ('security', 'Security'),
        ('other', 'Other'),
    ]

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class IncidentReport(TenantAwareModel, TimeStampedModel):
    """EHS incident report (auto-numbered ``INC-NNNNN``).

    Workflow: reported -> investigating -> corrective_action -> closed
                                       \\-> cancelled
    """

    SEVERITY_CHOICES = [
        ('low', 'Low - First Aid'),
        ('medium', 'Medium - Medical Treatment'),
        ('high', 'High - Lost Time'),
        ('critical', 'Critical - Fatality / Major'),
    ]
    STATUS_CHOICES = [
        ('reported', 'Reported'),
        ('investigating', 'Investigating'),
        ('corrective_action', 'Corrective Action'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    incident_number = models.CharField(max_length=15)
    incident_type = models.ForeignKey(
        IncidentType, on_delete=models.PROTECT, related_name='incidents',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    occurred_at = models.DateTimeField()
    location = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='compliance_incidents',
    )
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='low')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reported')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reported_incidents',
    )
    witnesses = models.TextField(
        blank=True, help_text='Comma-separated names or descriptions.',
    )
    immediate_actions = models.TextField(blank=True)
    root_cause = models.TextField(blank=True)
    corrective_actions = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='closed_incidents',
    )
    cancellation_reason = models.CharField(max_length=200, blank=True)
    source_andon = models.ForeignKey(
        'mes.AndonAlert', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='compliance_incidents',
    )
    source_ncr = models.ForeignKey(
        'qms.NonConformanceReport', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='compliance_incidents',
        help_text='Auto-populated when a critical NCR triggers an incident report.',
    )

    class Meta:
        ordering = ['-occurred_at']
        unique_together = ('tenant', 'incident_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-occurred_at']),
            models.Index(fields=['tenant', 'severity']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_andon'],
                condition=models.Q(source_andon__isnull=False),
                name='compliance_incident_unique_andon',
            ),
            models.UniqueConstraint(
                fields=['source_ncr'],
                condition=models.Q(source_ncr__isnull=False),
                name='compliance_incident_unique_ncr',
            ),
        ]

    def __str__(self):
        return f'{self.incident_number} | {self.title}'

    def is_investigatable(self) -> bool:
        return self.status == 'reported'

    def is_actionable(self) -> bool:
        return self.status == 'investigating'

    def is_closeable(self) -> bool:
        return self.status == 'corrective_action'

    def is_cancellable(self) -> bool:
        return self.status in ('reported', 'investigating', 'corrective_action')

    def is_editable(self) -> bool:
        return self.status not in ('closed', 'cancelled')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.incident_number and self.tenant_id:
            last = (
                IncidentReport.all_objects
                .filter(tenant_id=self.tenant_id, incident_number__startswith='INC-')
                .order_by('-incident_number').first()
            )
            n = 1
            if last and last.incident_number.startswith('INC-'):
                try:
                    n = int(last.incident_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.incident_number = f'INC-{n:05d}'
        super().save(*args, **kwargs)


class RiskAssessment(TenantAwareModel, TimeStampedModel):
    """Hazard risk assessment with 5x5 matrix scoring (auto ``RA-NNNNN``).

    risk_score = likelihood * severity (computed in save).
    Workflow: draft -> in_review -> approved -> archived
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ]

    assessment_number = models.CharField(max_length=15)
    title = models.CharField(max_length=200)
    hazard = models.TextField()
    location = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='risk_assessments',
    )
    likelihood = models.PositiveSmallIntegerField(
        validators=[RISK_MIN, RISK_MAX],
        help_text='1 (rare) - 5 (almost certain)',
    )
    severity = models.PositiveSmallIntegerField(
        validators=[RISK_MIN, RISK_MAX],
        help_text='1 (negligible) - 5 (catastrophic)',
    )
    risk_score = models.PositiveSmallIntegerField(default=1)
    control_measures = models.TextField(blank=True)
    residual_likelihood = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[RISK_MIN, RISK_MAX],
    )
    residual_severity = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[RISK_MIN, RISK_MAX],
    )
    residual_score = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_risk_assessments',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-risk_score', 'assessment_number']
        unique_together = ('tenant', 'assessment_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-risk_score']),
        ]

    def __str__(self):
        return f'{self.assessment_number} | {self.title} | {self.risk_score}'

    def is_submittable(self) -> bool:
        return self.status == 'draft'

    def is_approvable(self) -> bool:
        return self.status == 'in_review'

    def is_archivable(self) -> bool:
        return self.status == 'approved'

    def is_editable(self) -> bool:
        return self.status in ('draft', 'in_review')

    @property
    def risk_band(self) -> str:
        """Map score to a colored band for the UI."""
        s = self.risk_score
        if s >= 16:
            return 'critical'
        if s >= 9:
            return 'high'
        if s >= 4:
            return 'medium'
        return 'low'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.assessment_number and self.tenant_id:
            last = (
                RiskAssessment.all_objects
                .filter(tenant_id=self.tenant_id, assessment_number__startswith='RA-')
                .order_by('-assessment_number').first()
            )
            n = 1
            if last and last.assessment_number.startswith('RA-'):
                try:
                    n = int(last.assessment_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.assessment_number = f'RA-{n:05d}'
        # Computed scores.
        self.risk_score = (self.likelihood or 1) * (self.severity or 1)
        if self.residual_likelihood and self.residual_severity:
            self.residual_score = self.residual_likelihood * self.residual_severity
        else:
            self.residual_score = None
        super().save(*args, **kwargs)


class SafetyAuditChecklist(TenantAwareModel, TimeStampedModel):
    """Per-tenant audit checklist template.

    ``items`` is a JSON list of dicts: ``[{"order": 1, "question": "..."}]``.
    """

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    items = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'

    @property
    def item_count(self) -> int:
        return len(self.items or [])


class SafetyAudit(TenantAwareModel, TimeStampedModel):
    """Per-instance run of a checklist (auto ``AUD-NNNNN``).

    Workflow: scheduled -> in_progress -> completed
    """

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    audit_number = models.CharField(max_length=15)
    checklist = models.ForeignKey(
        SafetyAuditChecklist, on_delete=models.PROTECT, related_name='audits',
    )
    location = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='safety_audits',
    )
    scheduled_for = models.DateField()
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='safety_audits',
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='scheduled')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    pass_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    na_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-scheduled_for']
        unique_together = ('tenant', 'audit_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-scheduled_for']),
        ]

    def __str__(self):
        return f'{self.audit_number} | {self.checklist.code} | {self.status}'

    def is_startable(self) -> bool:
        return self.status == 'scheduled'

    def is_completable(self) -> bool:
        return self.status == 'in_progress'

    def is_cancellable(self) -> bool:
        return self.status in ('scheduled', 'in_progress')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.audit_number and self.tenant_id:
            last = (
                SafetyAudit.all_objects
                .filter(tenant_id=self.tenant_id, audit_number__startswith='AUD-')
                .order_by('-audit_number').first()
            )
            n = 1
            if last and last.audit_number.startswith('AUD-'):
                try:
                    n = int(last.audit_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.audit_number = f'AUD-{n:05d}'
        super().save(*args, **kwargs)


class SafetyAuditItem(TenantAwareModel, TimeStampedModel):
    """One filled-in item per audit per checklist question."""

    RESULT_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('na', 'Not Applicable'),
    ]

    audit = models.ForeignKey(
        SafetyAudit, on_delete=models.CASCADE, related_name='item_results',
    )
    item_order = models.PositiveSmallIntegerField()
    question = models.CharField(max_length=400)
    result = models.CharField(max_length=4, choices=RESULT_CHOICES, default='na')
    finding = models.TextField(blank=True)

    class Meta:
        ordering = ['audit', 'item_order']
        unique_together = ('audit', 'item_order')

    def __str__(self):
        return f'{self.audit.audit_number} #{self.item_order} {self.result}'


# ============================================================================
# 13.2  REGULATORY DOCUMENT CONTROL
# ============================================================================

def compliance_doc_upload_path(instance, filename):
    return (
        f'compliance/documents/'
        f'{instance.tenant_id or "unscoped"}/{instance.doc_number}/{filename}'
    )


class ComplianceDocument(TenantAwareModel, TimeStampedModel):
    """Versioned regulatory / SOP / WI document (auto ``DOC-NNNNN``).

    Per FDA 21 CFR Part 11 & ISO 9001/14001:
        - Version history via ``supersedes`` self-FK chain.
        - Immutable once approved (effective_from is set on first approval).
        - Approvals + e-signatures are kept in sibling tables for audit.

    File upload caps + extension allow-list per L-22.
    """

    DOC_TYPE_CHOICES = [
        ('iso_9001', 'ISO 9001 QMS'),
        ('iso_14001', 'ISO 14001 EMS'),
        ('iso_45001', 'ISO 45001 OHSAS'),
        ('sop', 'Standard Operating Procedure'),
        ('wi', 'Work Instruction'),
        ('form', 'Form / Record'),
        ('policy', 'Policy'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('effective', 'Effective'),
        ('superseded', 'Superseded'),
        ('retired', 'Retired'),
    ]
    ALLOWED_DOC_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg']

    doc_number = models.CharField(max_length=15)
    doc_type = models.CharField(max_length=15, choices=DOC_TYPE_CHOICES, default='sop')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=20, default='1.0')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    supersedes = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='superseded_by',
    )
    attachment = models.FileField(
        upload_to=compliance_doc_upload_path, null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='owned_compliance_docs',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['doc_number', '-version']
        unique_together = (
            ('tenant', 'doc_number'),
            ('tenant', 'doc_number', 'version'),
        )
        indexes = [
            models.Index(fields=['tenant', 'doc_type', 'status']),
        ]

    def __str__(self):
        return f'{self.doc_number} v{self.version} | {self.title}'

    def is_submittable(self) -> bool:
        return self.status == 'draft'

    def is_approvable(self) -> bool:
        return self.status == 'in_review'

    def is_publishable(self) -> bool:
        return self.status == 'approved'

    def is_supersedable(self) -> bool:
        return self.status == 'effective'

    def is_editable(self) -> bool:
        return self.status in ('draft', 'in_review')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.doc_number and self.tenant_id:
            last = (
                ComplianceDocument.all_objects
                .filter(tenant_id=self.tenant_id, doc_number__startswith='DOC-')
                .order_by('-doc_number').first()
            )
            n = 1
            if last and last.doc_number.startswith('DOC-'):
                try:
                    n = int(last.doc_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.doc_number = f'DOC-{n:05d}'
        super().save(*args, **kwargs)


class DocumentApproval(TenantAwareModel, TimeStampedModel):
    """Approval record for a ComplianceDocument lifecycle step.

    Append-only — each transition logs a row. PROTECT on document so a
    deletion is blocked while approvals exist (forces explicit retire).
    """

    ACTION_CHOICES = [
        ('submit', 'Submitted for Review'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('publish', 'Published as Effective'),
        ('supersede', 'Superseded'),
        ('retire', 'Retired'),
    ]

    document = models.ForeignKey(
        ComplianceDocument, on_delete=models.PROTECT, related_name='approvals',
    )
    action = models.CharField(max_length=15, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='document_approvals',
    )
    acted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-acted_at']
        indexes = [
            models.Index(fields=['tenant', 'document', '-acted_at']),
        ]

    def __str__(self):
        return f'{self.document.doc_number} {self.action} @ {self.acted_at:%Y-%m-%d}'


class ElectronicSignature(TenantAwareModel, TimeStampedModel):
    """FDA 21 CFR §11.50-compliant electronic signature.

    Captures: typed_name + reason + role + document FK + timestamp.
    Immutable: ``save()`` raises ``ValidationError`` if pk is already set —
    a signature row cannot be edited or re-saved once stored.
    """

    REASON_CHOICES = [
        ('authorship', 'Authorship'),
        ('review', 'Review'),
        ('approval', 'Approval'),
        ('responsibility', 'Responsibility'),
        ('verification', 'Verification'),
    ]

    document = models.ForeignKey(
        ComplianceDocument, on_delete=models.PROTECT, related_name='signatures',
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='electronic_signatures',
    )
    typed_name = models.CharField(
        max_length=200, help_text='Full legal name as typed by the signer.',
    )
    role = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default='approval')
    signed_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-signed_at']
        indexes = [
            models.Index(fields=['tenant', 'document', '-signed_at']),
        ]

    def __str__(self):
        return f'{self.signer} signed {self.document.doc_number} ({self.reason})'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(
                'Electronic signatures are immutable; create a new row instead.'
            )
        if not self.tenant_id and self.document_id:
            self.tenant_id = self.document.tenant_id
        super().save(*args, **kwargs)


# ============================================================================
# 13.3  AUDIT TRAIL & DATA INTEGRITY
# ============================================================================

class AuditLogArchive(TenantAwareModel, TimeStampedModel):
    """Periodic snapshot of ``tenants.TenantAuditLog`` rows (auto ``ALA-NNNNN``).

    ``hash_chain`` stores a SHA-256 digest of ``previous.hash_chain || rows``
    so any tampering with prior archives is detectable. The archive itself
    is never deleted via the UI; per L-17 we PROTECT on parent FKs in
    sister modules.
    """

    archive_number = models.CharField(max_length=15)
    period_start = models.DateField()
    period_end = models.DateField()
    record_count = models.PositiveIntegerField(default=0)
    hash_chain = models.CharField(
        max_length=64, blank=True,
        help_text='SHA-256 hex digest of previous_chain || archived rows.',
    )
    previous_archive = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='next_archives',
    )
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_compliance_archives',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_end']
        unique_together = (
            ('tenant', 'archive_number'),
            ('tenant', 'period_start', 'period_end'),
        )

    def __str__(self):
        return f'{self.archive_number} | {self.period_start}..{self.period_end}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.archive_number and self.tenant_id:
            last = (
                AuditLogArchive.all_objects
                .filter(tenant_id=self.tenant_id, archive_number__startswith='ALA-')
                .order_by('-archive_number').first()
            )
            n = 1
            if last and last.archive_number.startswith('ALA-'):
                try:
                    n = int(last.archive_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.archive_number = f'ALA-{n:05d}'
        super().save(*args, **kwargs)


# ============================================================================
# 13.4  WASTE & EMISSION TRACKING (carbon/ESG defers to apps.utility)
# ============================================================================

class WasteCategory(TenantAwareModel, TimeStampedModel):
    """Catalog of waste streams (hazardous chemical / e-waste / biohazard / ...)."""

    HAZARD_CHOICES = [
        ('hazardous_chemical', 'Hazardous Chemical'),
        ('e_waste', 'Electronic Waste'),
        ('biohazard', 'Biohazardous'),
        ('radioactive', 'Radioactive'),
        ('general', 'General / Solid'),
        ('recyclable', 'Recyclable'),
        ('liquid', 'Liquid Waste'),
    ]

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=120)
    hazard_class = models.CharField(
        max_length=20, choices=HAZARD_CHOICES, default='general',
    )
    epa_code = models.CharField(
        max_length=10, blank=True,
        help_text='Optional EPA / regulatory waste code (e.g. D001, F003).',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class WasteManifest(TenantAwareModel, TimeStampedModel):
    """Hazardous-waste manifest (auto ``WM-NNNNN``).

    Workflow: draft -> in_transit -> disposed -> reconciled
                                 \\-> cancelled
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_transit', 'In Transit'),
        ('disposed', 'Disposed'),
        ('reconciled', 'Reconciled'),
        ('cancelled', 'Cancelled'),
    ]

    manifest_number = models.CharField(max_length=15)
    category = models.ForeignKey(
        WasteCategory, on_delete=models.PROTECT, related_name='manifests',
    )
    generator = models.CharField(max_length=200, help_text='Generator (this facility).')
    transporter = models.CharField(max_length=200, blank=True)
    disposal_facility = models.CharField(max_length=200, blank=True)
    epa_id = models.CharField(max_length=30, blank=True)
    manifest_date = models.DateField()
    pickup_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    total_quantity_kg = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    cancellation_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-manifest_date']
        unique_together = ('tenant', 'manifest_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-manifest_date']),
            models.Index(fields=['tenant', 'category']),
        ]

    def __str__(self):
        return f'{self.manifest_number} | {self.category.code} | {self.status}'

    def is_dispatchable(self) -> bool:
        return self.status == 'draft'

    def is_disposable(self) -> bool:
        return self.status == 'in_transit'

    def is_reconcilable(self) -> bool:
        return self.status == 'disposed'

    def is_cancellable(self) -> bool:
        return self.status in ('draft', 'in_transit')

    def is_editable(self) -> bool:
        return self.status == 'draft'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.manifest_number and self.tenant_id:
            last = (
                WasteManifest.all_objects
                .filter(tenant_id=self.tenant_id, manifest_number__startswith='WM-')
                .order_by('-manifest_number').first()
            )
            n = 1
            if last and last.manifest_number.startswith('WM-'):
                try:
                    n = int(last.manifest_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.manifest_number = f'WM-{n:05d}'
        super().save(*args, **kwargs)


class WasteDisposalRecord(TenantAwareModel, TimeStampedModel):
    """Per-line disposal record under a manifest."""

    DISPOSAL_METHOD_CHOICES = [
        ('landfill', 'Landfill'),
        ('incineration', 'Incineration'),
        ('recycling', 'Recycling / Recovery'),
        ('treatment', 'Treatment'),
        ('reuse', 'Reuse'),
        ('storage', 'Permanent Storage'),
    ]
    CONTAINER_CHOICES = [
        ('drum_55gal', '55-gal Drum'),
        ('tote_330gal', '330-gal IBC Tote'),
        ('cubic_yard', 'Cubic-Yard Box'),
        ('bag', 'Bag'),
        ('other', 'Other'),
    ]

    manifest = models.ForeignKey(
        WasteManifest, on_delete=models.PROTECT, related_name='disposal_records',
    )
    line_number = models.PositiveSmallIntegerField(default=1)
    description = models.CharField(max_length=200)
    quantity_kg = models.DecimalField(
        max_digits=14, decimal_places=4, validators=[NON_NEG],
    )
    container_type = models.CharField(
        max_length=15, choices=CONTAINER_CHOICES, default='drum_55gal',
    )
    container_count = models.PositiveSmallIntegerField(default=1)
    disposal_method = models.CharField(
        max_length=15, choices=DISPOSAL_METHOD_CHOICES, default='landfill',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['manifest', 'line_number']
        unique_together = ('manifest', 'line_number')

    def __str__(self):
        return f'{self.manifest.manifest_number} #{self.line_number} {self.quantity_kg}kg'

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.manifest_id:
            self.tenant_id = self.manifest.tenant_id
        super().save(*args, **kwargs)


# ============================================================================
# 13.5  RECALL & TRACEABILITY MANAGEMENT
# ============================================================================

class ProductRecall(TenantAwareModel, TimeStampedModel):
    """Product recall (auto ``RCL-NNNNN``) per FDA Class I/II/III.

    Workflow: initiated -> in_progress -> completed -> closed
                                       \\-> cancelled
    Reuses ``inventory.Lot`` for traceability via ``RecallAffectedLot``
    rather than creating a parallel lot model.
    """

    SEVERITY_CHOICES = [
        ('class_i', 'Class I - Probable serious health consequence'),
        ('class_ii', 'Class II - Possible reversible health consequence'),
        ('class_iii', 'Class III - Unlikely health consequence'),
    ]
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    recall_number = models.CharField(max_length=15)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='compliance_recalls',
    )
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='class_iii')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='initiated')
    initiated_at = models.DateTimeField(default=timezone.now)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='initiated_recalls',
    )
    root_cause = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    affected_quantity = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
        help_text='Total units across all affected lots (denorm — recomputed).',
    )
    recovered_quantity = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-initiated_at']
        unique_together = ('tenant', 'recall_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-initiated_at']),
            models.Index(fields=['tenant', 'severity']),
        ]

    def __str__(self):
        return f'{self.recall_number} | {self.product.sku} | {self.status}'

    def is_progressable(self) -> bool:
        return self.status == 'initiated'

    def is_completable(self) -> bool:
        return self.status == 'in_progress'

    def is_closeable(self) -> bool:
        return self.status == 'completed'

    def is_cancellable(self) -> bool:
        return self.status in ('initiated', 'in_progress')

    def is_editable(self) -> bool:
        return self.status not in ('closed', 'cancelled')

    @property
    def recovery_pct(self) -> Decimal:
        if not self.affected_quantity:
            return Decimal('0')
        return (
            (self.recovered_quantity or Decimal('0')) / self.affected_quantity
            * Decimal('100')
        ).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.recall_number and self.tenant_id:
            last = (
                ProductRecall.all_objects
                .filter(tenant_id=self.tenant_id, recall_number__startswith='RCL-')
                .order_by('-recall_number').first()
            )
            n = 1
            if last and last.recall_number.startswith('RCL-'):
                try:
                    n = int(last.recall_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.recall_number = f'RCL-{n:05d}'
        super().save(*args, **kwargs)


class RecallAffectedLot(TenantAwareModel, TimeStampedModel):
    """Link table: a recall affects N inventory lots.

    `post_recall_movement_count` and `last_leak_at` are denorms updated by the
    `inventory.StockMovement.post_save` -> `services.recall.on_movement_for_lot`
    hook (C.7). They surface when a recalled lot is still being moved out of
    the warehouse AFTER the recall is filed — operators must verify and
    adjust before the recall can be closed.
    """

    recall = models.ForeignKey(
        ProductRecall, on_delete=models.PROTECT, related_name='affected_lots',
    )
    lot = models.ForeignKey(
        'inventory.Lot', on_delete=models.PROTECT, related_name='recall_links',
    )
    affected_quantity = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    recovered_quantity = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    post_recall_movement_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of outbound StockMovements posted on this lot AFTER the recall was filed.',
    )
    last_leak_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Timestamp of the most recent post-recall outbound movement.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['recall', 'lot']
        unique_together = ('recall', 'lot')

    def __str__(self):
        return f'{self.recall.recall_number} | {self.lot}'

    @property
    def has_leaks(self) -> bool:
        return self.post_recall_movement_count > 0

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.recall_id:
            self.tenant_id = self.recall.tenant_id
        super().save(*args, **kwargs)


class RecallNotice(TenantAwareModel, TimeStampedModel):
    """Customer notification record (auto ``RCN-NNNNN``)."""

    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('letter', 'Letter'),
        ('press_release', 'Press Release'),
        ('website', 'Website Banner'),
        ('regulatory', 'Regulatory Filing'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
    ]

    notice_number = models.CharField(max_length=15)
    recall = models.ForeignKey(
        ProductRecall, on_delete=models.PROTECT, related_name='notices',
    )
    channel = models.CharField(max_length=15, choices=CHANNEL_CHOICES, default='email')
    audience = models.CharField(
        max_length=200,
        help_text='Customer segment / distributor / regulator name.',
    )
    recipient_email = models.EmailField(
        blank=True,
        help_text='Required when channel=email; left blank for non-email channels.',
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at', 'notice_number']
        unique_together = ('tenant', 'notice_number')

    def __str__(self):
        return f'{self.notice_number} | {self.recall.recall_number} | {self.channel}'

    def is_sendable(self) -> bool:
        return self.status == 'draft'

    def is_acknowledgable(self) -> bool:
        return self.status == 'sent'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.notice_number and self.tenant_id:
            last = (
                RecallNotice.all_objects
                .filter(tenant_id=self.tenant_id, notice_number__startswith='RCN-')
                .order_by('-notice_number').first()
            )
            n = 1
            if last and last.notice_number.startswith('RCN-'):
                try:
                    n = int(last.notice_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.notice_number = f'RCN-{n:05d}'
        super().save(*args, **kwargs)
