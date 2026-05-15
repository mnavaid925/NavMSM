"""Module 19 - Document & Knowledge Management.

Sub-modules:
    19.1  Controlled Document Repository
            (DocumentCategory, Document, DocumentVersion, DocumentAccessRule)
    19.2  SOP & Work Instruction Authoring
            (DocumentTemplate, TemplateField, MediaAttachment)
    19.3  Document Approval Workflows
            (ApprovalWorkflow, ApprovalStage, DocumentApprovalRequest,
             ApprovalAction, DocumentSignature - immutable, FDA 21 CFR Part 11)
    19.4  Training Document Assignment
            (DocumentAssignment, AssignmentTarget, ReadAcknowledgment)
    19.5  Archive & Retention Policy
            (RetentionPolicy, DocumentArchive, LegalHold)

Cross-module integration (see apps/dms/signals.py):
    - DocumentVersion.status='released' supersedes prior releases on the
      same document and updates Document.current_version.
    - DocumentApprovalRequest.status='approved' flips Document.status='effective'
      and sets Document.effective_date.
    - LegalHold.status='active' cascades Document.is_locked=True.
    - RetentionPolicy / Document recompute Document.retention_until via signal.
    - DocumentSignature is immutable (pre_save blocks updates).

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal / IntegerField carries explicit validators
    * L-03 view+template status gate parity via is_*() / can_*() helpers
    * L-12 auto-numbering retry loop via save() (mirrors rma)
    * L-13 transaction.atomic() around denorm bumps (signals)
    * L-14 per-workflow forms enforce required fields at transition
    * L-17 PROTECT on audit-trail children (DocumentSignature.document,
            DocumentArchive.document, ApprovalAction.request,
            ReadAcknowledgment.document_version)
    * L-18 weak=False + dispatch_uid on every closure receiver (signals.py)
    * L-21 time-driven status flip (archive_due_documents cron)
    * L-22 file uploads validate extension + size cap (forms.py)
    * L-23 audit emit failures logged at WARNING, never raise
    * L-25 preflight _meta.fields printout before writing FKs
    * L-26 row-level visual cues for denorm fields (templates)
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator, MaxValueValidator, MinValueValidator,
)
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.dms.services.numbering import next_code


# ============================================================================
# 19.1  CONTROLLED DOCUMENT REPOSITORY
# ============================================================================

class DocumentCategory(TenantAwareModel, TimeStampedModel):
    """Hierarchical category catalog (e.g. Quality / Production / HR / Safety)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Document categories'

    def __str__(self):
        return self.name


DOC_TYPE_CHOICES = [
    ('sop', 'Standard Operating Procedure'),
    ('work_instruction', 'Work Instruction'),
    ('policy', 'Policy'),
    ('form', 'Form / Template'),
    ('manual', 'Manual / Handbook'),
    ('specification', 'Specification'),
    ('report', 'Report'),
    ('drawing', 'Drawing'),
    ('training_material', 'Training Material'),
    ('other', 'Other'),
]


class Document(TenantAwareModel, TimeStampedModel):
    """Root document record.

    Workflow:
        draft -> in_review -> approved -> effective -> superseded | archived

    A `Document` row aggregates one or more `DocumentVersion` rows. The
    `current_version` denorm points at the latest released version.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('effective', 'Effective'),
        ('superseded', 'Superseded'),
        ('archived', 'Archived'),
    ]

    code = models.CharField(max_length=20, blank=True)
    title = models.CharField(max_length=255)
    doc_type = models.CharField(
        max_length=30, choices=DOC_TYPE_CHOICES, default='sop',
    )
    category = models.ForeignKey(
        DocumentCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='documents',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='owned_documents',
    )
    current_version = models.ForeignKey(
        'DocumentVersion', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    retention_policy = models.ForeignKey(
        'RetentionPolicy', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='documents',
    )
    retention_until = models.DateField(null=True, blank=True)
    is_locked = models.BooleanField(
        default=False,
        help_text='Set by an active LegalHold. Blocks archive / purge.',
    )
    summary = models.TextField(blank=True)
    keywords = models.CharField(
        max_length=255, blank=True,
        help_text='Comma-separated keywords for search.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or self.title

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(Document, self.tenant, 'DOC')
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'in_review') and not self.is_locked

    def can_submit(self):
        return self.status == 'draft' and self.versions.exists()

    def can_archive(self):
        return self.status not in ('archived',) and not self.is_locked

    def is_expiring_soon(self, within_days: int = 30) -> bool:
        if not self.expiry_date:
            return False
        delta = (self.expiry_date - timezone.localdate()).days
        return 0 <= delta <= within_days

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days


DOC_FILE_ALLOWLIST = [
    'pdf', 'docx', 'xlsx', 'pptx', 'txt', 'md', 'html',
    'png', 'jpg', 'jpeg', 'svg',
]


class DocumentVersion(TenantAwareModel, TimeStampedModel):
    """One revision of a Document.

    Check-in / check-out is application-level (services/checkout.py).
    `status` walks draft -> under_review -> released -> superseded.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('released', 'Released'),
        ('superseded', 'Superseded'),
    ]

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='versions',
    )
    version = models.CharField(max_length=30)
    file = models.FileField(
        upload_to='dms/versions/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=DOC_FILE_ALLOWLIST)],
        help_text='PDF / Office docs / images. Max 25 MB.',
    )
    content_html = models.TextField(
        blank=True,
        help_text='Optional in-app rich body (sanitized at save time).',
    )
    change_notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_dms_versions',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_checked_out_versions',
    )
    checked_out_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['document', '-id']
        unique_together = ('document', 'version')

    def __str__(self):
        return f'{self.document.code} v{self.version}'

    def is_locked(self) -> bool:
        return self.checked_out_by_id is not None


class DocumentAccessRule(TenantAwareModel, TimeStampedModel):
    """Per-document RBAC override.

    Exactly one of (user, department, position) must be set. Enforced in
    forms via XOR clean(); the DB allows any combination so the same
    Document can have one rule per principal kind.
    """

    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('editor', 'Editor'),
        ('approver', 'Approver'),
        ('owner', 'Owner'),
    ]

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='access_rules',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_access_rules',
    )
    department = models.ForeignKey(
        'labor.Department', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_access_rules',
    )
    position = models.ForeignKey(
        'labor.Position', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_access_rules',
    )

    class Meta:
        ordering = ['document', 'role']

    def __str__(self):
        target = self.user or self.department or self.position or 'unset'
        return f'{self.document.code}: {self.role} -> {target}'


# ============================================================================
# 19.2  SOP & WORK INSTRUCTION AUTHORING
# ============================================================================

class DocumentTemplate(TenantAwareModel, TimeStampedModel):
    """Reusable authoring template for a class of documents."""

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    applies_to_doc_type = models.CharField(
        max_length=30,
        choices=DOC_TYPE_CHOICES + [('any', 'Any')],
        default='sop',
    )
    body = models.TextField(
        blank=True,
        help_text='Template skeleton (supports {{placeholder}} markers).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.code or self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(DocumentTemplate, self.tenant, 'TPL')
        super().save(*args, **kwargs)


class TemplateField(TenantAwareModel, TimeStampedModel):
    """A typed placeholder inside a DocumentTemplate's body."""

    FIELD_TYPE_CHOICES = [
        ('text', 'Single-line text'),
        ('textarea', 'Multi-line text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Select (one of)'),
        ('boolean', 'Yes / No'),
    ]

    template = models.ForeignKey(
        DocumentTemplate, on_delete=models.CASCADE, related_name='fields',
    )
    field_name = models.SlugField(max_length=60)
    label = models.CharField(max_length=120)
    field_type = models.CharField(
        max_length=20, choices=FIELD_TYPE_CHOICES, default='text',
    )
    choices = models.TextField(
        blank=True,
        help_text='One option per line. Only used when field_type=select.',
    )
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(999)],
    )

    class Meta:
        ordering = ['template', 'order', 'field_name']
        unique_together = ('template', 'field_name')

    def __str__(self):
        return f'{self.template.name}::{self.field_name}'


MEDIA_FILE_ALLOWLIST = [
    'png', 'jpg', 'jpeg', 'gif', 'svg',
    'pdf', 'mp4', 'webm', 'mov',
    'mp3', 'wav', 'ogg',
]


class MediaAttachment(TenantAwareModel, TimeStampedModel):
    """Image / video / audio / pdf attached to a specific DocumentVersion."""

    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('pdf', 'PDF'),
        ('other', 'Other'),
    ]

    document_version = models.ForeignKey(
        DocumentVersion, on_delete=models.CASCADE, related_name='attachments',
    )
    media_type = models.CharField(
        max_length=20, choices=MEDIA_TYPE_CHOICES, default='image',
    )
    file = models.FileField(
        upload_to='dms/media/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=MEDIA_FILE_ALLOWLIST)],
    )
    video_url = models.URLField(
        blank=True,
        help_text='Optional embed URL (YouTube / Vimeo). http / https only.',
    )
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_uploaded_media',
    )
    order = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(999)],
    )

    class Meta:
        ordering = ['document_version', 'order', 'id']

    def __str__(self):
        return f'{self.document_version} :: {self.media_type}'


# ============================================================================
# 19.3  DOCUMENT APPROVAL WORKFLOWS
# ============================================================================

class ApprovalWorkflow(TenantAwareModel, TimeStampedModel):
    """Reusable multi-stage approval template."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    applies_to_doc_type = models.CharField(
        max_length=30,
        choices=DOC_TYPE_CHOICES + [('any', 'Any')],
        default='any',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


APPROVER_ROLE_CHOICES = [
    ('department_head', 'Department Head'),
    ('quality_manager', 'Quality Manager'),
    ('compliance_officer', 'Compliance Officer'),
    ('plant_manager', 'Plant Manager'),
    ('cfo', 'CFO'),
    ('other', 'Other'),
]


class ApprovalStage(TenantAwareModel, TimeStampedModel):
    """One ordered stage of an ApprovalWorkflow."""

    workflow = models.ForeignKey(
        ApprovalWorkflow, on_delete=models.CASCADE, related_name='stages',
    )
    stage_no = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    name = models.CharField(max_length=120)
    approver_role = models.CharField(
        max_length=30, choices=APPROVER_ROLE_CHOICES, default='department_head',
    )
    min_approvals = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    requires_signature = models.BooleanField(default=True)

    class Meta:
        ordering = ['workflow', 'stage_no']
        unique_together = ('workflow', 'stage_no')

    def __str__(self):
        return f'{self.workflow.name} :: stage {self.stage_no} ({self.name})'


class DocumentApprovalRequest(TenantAwareModel, TimeStampedModel):
    """One walk-through of an ApprovalWorkflow against a Document."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name='approval_requests',
    )
    workflow = models.ForeignKey(
        ApprovalWorkflow, on_delete=models.PROTECT, related_name='requests',
    )
    current_stage_no = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requested_dms_approvals',
    )
    requested_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    effective_date = models.DateField(
        null=True, blank=True,
        help_text='Applied to Document.effective_date on final approval.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(approval #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(DocumentApprovalRequest, self.tenant, 'AR')
        super().save(*args, **kwargs)

    def is_open(self):
        return self.status in ('pending', 'in_progress')

    def can_cancel(self):
        return self.is_open()


class ApprovalAction(TenantAwareModel, TimeStampedModel):
    """Append-only audit row: one approver decision at one stage."""

    DECISION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('return_for_revision', 'Return for revision'),
    ]

    request = models.ForeignKey(
        DocumentApprovalRequest, on_delete=models.PROTECT, related_name='actions',
    )
    stage_no = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    decision = models.CharField(max_length=30, choices=DECISION_CHOICES)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_approval_actions',
    )
    decided_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    signature = models.ForeignKey(
        'DocumentSignature', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['-decided_at', '-id']

    def __str__(self):
        return f'{self.request.code} stage {self.stage_no}: {self.decision}'


class DocumentSignature(TenantAwareModel, TimeStampedModel):
    """Immutable e-sig (FDA 21 CFR Part 11).

    `pre_save` raises if a PK already exists and the row's content has
    changed; admin readonly_fields = '__all__' enforces the same in
    Django admin. Only INSERT is allowed.
    """

    MEANING_CHOICES = [
        ('author', 'Author'),
        ('reviewer', 'Reviewer'),
        ('approver', 'Approver'),
        ('witness', 'Witness'),
    ]

    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name='signatures',
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='dms_signatures',
    )
    signed_at = models.DateTimeField(default=timezone.now)
    meaning = models.CharField(max_length=20, choices=MEANING_CHOICES, default='approver')
    typed_name = models.CharField(
        max_length=160,
        help_text='Captured at sign time (User.get_full_name snapshot).',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-signed_at', '-id']

    def __str__(self):
        return f'{self.document.code} {self.meaning} by {self.typed_name}'


# ============================================================================
# 19.4  TRAINING DOCUMENT ASSIGNMENT
# ============================================================================

class DocumentAssignment(TenantAwareModel, TimeStampedModel):
    """A read-and-acknowledge campaign for a Document.

    `targets` (M2O via AssignmentTarget) expands to a set of Users
    expected to acknowledge. Ack rows are created lazily when each user
    clicks "Acknowledge".
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name='assignments',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_assignments_made',
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    instructions = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(assignment #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(DocumentAssignment, self.tenant, 'DA')
        super().save(*args, **kwargs)

    def is_overdue(self):
        if not self.due_date or self.status != 'active':
            return False
        return self.due_date < timezone.localdate()


class AssignmentTarget(TenantAwareModel, TimeStampedModel):
    """One targeted principal on a DocumentAssignment.

    XOR: exactly one of (role, department, position, employee, user) is set.
    Enforced in the form clean() (L-01).
    """

    USER_ROLE_CHOICES = [
        ('tenant_admin', 'Tenant Admin'),
        ('production_manager', 'Production Manager'),
        ('plant_manager', 'Plant Manager'),
        ('supervisor', 'Supervisor'),
        ('operator', 'Operator'),
        ('quality_inspector', 'Quality Inspector'),
        ('warehouse_staff', 'Warehouse Staff'),
        ('procurement', 'Procurement'),
        ('accountant', 'Accountant'),
        ('sales', 'Sales'),
        ('viewer', 'Viewer'),
    ]

    assignment = models.ForeignKey(
        DocumentAssignment, on_delete=models.CASCADE, related_name='targets',
    )
    role = models.CharField(
        max_length=30, choices=USER_ROLE_CHOICES, blank=True,
    )
    department = models.ForeignKey(
        'labor.Department', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_assignment_targets',
    )
    position = models.ForeignKey(
        'labor.Position', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_assignment_targets',
    )
    employee = models.ForeignKey(
        'labor.Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_assignment_targets',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_assignment_targets',
    )

    class Meta:
        ordering = ['assignment', 'id']

    def __str__(self):
        target = (
            self.user or self.employee or self.position or self.department
            or self.role or 'unset'
        )
        return f'{self.assignment.code} -> {target}'

    @property
    def is_xor_valid(self) -> bool:
        """Exactly one of the five target fields must be set."""
        flags = [
            bool(self.role),
            bool(self.department_id),
            bool(self.position_id),
            bool(self.employee_id),
            bool(self.user_id),
        ]
        return sum(flags) == 1


class ReadAcknowledgment(TenantAwareModel, TimeStampedModel):
    """A user's typed-signature acknowledgment of a specific DocumentVersion."""

    code = models.CharField(max_length=20, blank=True)
    assignment = models.ForeignKey(
        DocumentAssignment, on_delete=models.CASCADE, related_name='acknowledgments',
    )
    document_version = models.ForeignKey(
        DocumentVersion, on_delete=models.PROTECT, related_name='acknowledgments',
    )
    acknowledger = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='dms_acknowledgments',
    )
    acknowledged_at = models.DateTimeField(default=timezone.now)
    typed_name = models.CharField(max_length=160)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-acknowledged_at', '-id']
        unique_together = ('assignment', 'acknowledger', 'document_version')

    def __str__(self):
        return self.code or f'(ack #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(ReadAcknowledgment, self.tenant, 'ACK')
        super().save(*args, **kwargs)


# ============================================================================
# 19.5  ARCHIVE & RETENTION POLICY
# ============================================================================

class RetentionPolicy(TenantAwareModel, TimeStampedModel):
    """Reusable retention rule (e.g. 'Quality records - 7 years')."""

    ARCHIVE_ACTION_CHOICES = [
        ('archive', 'Move to archive'),
        ('soft_delete', 'Soft delete'),
        ('hard_delete', 'Hard delete (irreversible)'),
    ]

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    applies_to_doc_type = models.CharField(
        max_length=30,
        choices=DOC_TYPE_CHOICES + [('any', 'Any')],
        default='any',
    )
    retention_years = models.PositiveIntegerField(
        default=5, validators=[MinValueValidator(0), MaxValueValidator(99)],
    )
    archive_action = models.CharField(
        max_length=20, choices=ARCHIVE_ACTION_CHOICES, default='archive',
    )
    legal_hold_compatible = models.BooleanField(
        default=True,
        help_text='When False, legal hold blocks the auto-archive action.',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')
        verbose_name_plural = 'Retention policies'

    def __str__(self):
        return self.code or self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(RetentionPolicy, self.tenant, 'RP')
        super().save(*args, **kwargs)


class DocumentArchive(TenantAwareModel, TimeStampedModel):
    """One archive event per Document.

    A Document can only have one open (status='archived') archive at a
    time; restoring creates a status='restored' row but leaves the
    historical archived row in place.
    """

    STATUS_CHOICES = [
        ('archived', 'Archived'),
        ('restored', 'Restored'),
        ('purged', 'Purged'),
    ]

    code = models.CharField(max_length=20, blank=True)
    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name='archives',
    )
    archived_at = models.DateTimeField(default=timezone.now)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_archives_made',
    )
    retention_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='archived')
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_archives_restored',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-archived_at', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(archive #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(DocumentArchive, self.tenant, 'ARC')
        super().save(*args, **kwargs)

    def can_restore(self):
        return self.status == 'archived' and not self.document.is_locked


class LegalHold(TenantAwareModel, TimeStampedModel):
    """A litigation / audit hold pinning one or more Documents from purge.

    While `status='active'`, every linked Document has `is_locked=True`.
    Releasing the hold re-evaluates each Document; if no other active
    hold references it, the lock clears (services/legal_hold.release_hold).
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('released', 'Released'),
    ]

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=160)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_legal_holds_requested',
    )
    requested_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dms_legal_holds_released',
    )
    release_notes = models.TextField(blank=True)
    documents = models.ManyToManyField(
        Document, related_name='legal_holds', blank=True,
    )

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(LegalHold, self.tenant, 'LH')
        super().save(*args, **kwargs)

    def is_active(self):
        return self.status == 'active'
