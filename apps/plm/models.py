"""Module 2 — Product Lifecycle Management (PLM).

Sub-modules:
    2.1  Product Master Data       (ProductCategory, Product, ProductRevision,
                                    ProductSpecification, ProductVariant)
    2.2  Engineering Change Orders (EngineeringChangeOrder, ECOImpactedItem,
                                    ECOApproval, ECOAttachment)
    2.3  CAD/Drawing Repository    (CADDocument, CADDocumentVersion)
    2.4  Product Compliance        (ComplianceStandard [shared catalog],
                                    ProductCompliance, ComplianceAuditLog)
    2.5  NPI / Stage-Gate          (NPIProject, NPIStage, NPIDeliverable)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 2.1  PRODUCT MASTER DATA
# ============================================================================

class ProductCategory(TenantAwareModel, TimeStampedModel):
    """Hierarchical product classification (parent-child via self-FK)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Product Categories'

    def __str__(self):
        return self.name


class Product(TenantAwareModel, TimeStampedModel):
    TYPE_CHOICES = [
        ('raw_material', 'Raw Material'),
        ('component', 'Component'),
        ('sub_assembly', 'Sub-Assembly'),
        ('finished_good', 'Finished Good'),
        ('service', 'Service'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('obsolete', 'Obsolete'),
        ('phased_out', 'Phased Out'),
    ]
    UOM_CHOICES = [
        ('ea', 'Each'),
        ('kg', 'Kilogram'),
        ('g', 'Gram'),
        ('lb', 'Pound'),
        ('m', 'Meter'),
        ('cm', 'Centimeter'),
        ('l', 'Liter'),
        ('ml', 'Milliliter'),
        ('box', 'Box'),
        ('set', 'Set'),
    ]

    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        ProductCategory, on_delete=models.PROTECT,
        related_name='products', null=True, blank=True,
    )
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='component')
    unit_of_measure = models.CharField(max_length=10, choices=UOM_CHOICES, default='ea')
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_revision = models.ForeignKey(
        'ProductRevision', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    image = models.ImageField(upload_to='plm/products/', blank=True, null=True)

    class Meta:
        ordering = ['sku']
        unique_together = ('tenant', 'sku')

    def __str__(self):
        return f'{self.sku} — {self.name}'


class ProductRevision(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('superseded', 'Superseded'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='revisions')
    revision_code = models.CharField(max_length=10)
    effective_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    change_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['product', 'revision_code']
        unique_together = ('product', 'revision_code')

    def __str__(self):
        return f'{self.product.sku} rev {self.revision_code}'


class ProductSpecification(TenantAwareModel, TimeStampedModel):
    SPEC_TYPE_CHOICES = [
        ('physical', 'Physical'),
        ('electrical', 'Electrical'),
        ('mechanical', 'Mechanical'),
        ('chemical', 'Chemical'),
        ('performance', 'Performance'),
        ('other', 'Other'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='specifications')
    revision = models.ForeignKey(
        ProductRevision, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='specifications',
    )
    spec_type = models.CharField(max_length=20, choices=SPEC_TYPE_CHOICES, default='other')
    key = models.CharField(max_length=120)
    value = models.CharField(max_length=255)
    unit = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['spec_type', 'key']

    def __str__(self):
        return f'{self.key}: {self.value}'


class ProductVariant(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    variant_sku = models.CharField(max_length=60)
    name = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        ordering = ['variant_sku']
        unique_together = ('tenant', 'variant_sku')

    def __str__(self):
        return f'{self.variant_sku} ({self.product.sku})'


# ============================================================================
# 2.2  ENGINEERING CHANGE ORDERS (ECO)
# ============================================================================

class EngineeringChangeOrder(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('implemented', 'Implemented'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    CHANGE_TYPE_CHOICES = [
        ('design', 'Design'),
        ('specification', 'Specification'),
        ('material', 'Material'),
        ('process', 'Process'),
        ('documentation', 'Documentation'),
    ]

    number = models.CharField(max_length=30)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES, default='design')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    reason = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requested_ecos',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    target_implementation_date = models.DateField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    implemented_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'number')

    def __str__(self):
        return f'{self.number} — {self.title}'

    def is_editable(self):
        return self.status == 'draft'


class ECOImpactedItem(TenantAwareModel, TimeStampedModel):
    eco = models.ForeignKey(
        EngineeringChangeOrder, on_delete=models.CASCADE, related_name='impacted_items',
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='eco_items')
    before_revision = models.ForeignKey(
        ProductRevision, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='eco_before',
    )
    after_revision = models.ForeignKey(
        ProductRevision, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='eco_after',
    )
    change_summary = models.TextField(blank=True)

    class Meta:
        ordering = ['product__sku']

    def __str__(self):
        return f'{self.eco.number} → {self.product.sku}'


class ECOApproval(TenantAwareModel, TimeStampedModel):
    DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    eco = models.ForeignKey(
        EngineeringChangeOrder, on_delete=models.CASCADE, related_name='approvals',
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='eco_approvals',
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default='pending')
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.approver} → {self.decision}'


class ECOAttachment(TenantAwareModel, TimeStampedModel):
    eco = models.ForeignKey(
        EngineeringChangeOrder, on_delete=models.CASCADE, related_name='attachments',
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='plm/eco/')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='eco_uploads',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# ============================================================================
# 2.3  CAD / DRAWING REPOSITORY
# ============================================================================

class CADDocument(TenantAwareModel, TimeStampedModel):
    DOC_TYPE_CHOICES = [
        ('2d_drawing', '2D Drawing'),
        ('3d_model', '3D Model'),
        ('schematic', 'Schematic'),
        ('pcb', 'PCB Layout'),
        ('assembly', 'Assembly Drawing'),
        ('other', 'Other'),
    ]

    drawing_number = models.CharField(max_length=60)
    title = models.CharField(max_length=255)
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cad_documents',
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='2d_drawing')
    description = models.TextField(blank=True)
    current_version = models.ForeignKey(
        'CADDocumentVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['drawing_number']
        unique_together = ('tenant', 'drawing_number')

    def __str__(self):
        return f'{self.drawing_number} — {self.title}'


class CADDocumentVersion(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('released', 'Released'),
        ('obsolete', 'Obsolete'),
    ]

    document = models.ForeignKey(
        CADDocument, on_delete=models.CASCADE, related_name='versions',
    )
    version = models.CharField(max_length=20)
    file = models.FileField(upload_to='plm/cad/')
    change_notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cad_uploads',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['document', '-created_at']
        unique_together = ('document', 'version')

    def __str__(self):
        return f'{self.document.drawing_number} v{self.version}'


# ============================================================================
# 2.4  PRODUCT COMPLIANCE TRACKING
# ============================================================================

class ComplianceStandard(TimeStampedModel):
    """Shared, NOT tenant-scoped — global catalog of regulatory standards."""

    REGION_CHOICES = [
        ('global', 'Global'),
        ('us', 'United States'),
        ('eu', 'Europe'),
        ('apac', 'Asia-Pacific'),
        ('other', 'Other'),
    ]

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    region = models.CharField(max_length=10, choices=REGION_CHOICES, default='global')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} — {self.name}'


class ProductCompliance(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('compliant', 'Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('expired', 'Expired'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='compliance_records',
    )
    standard = models.ForeignKey(
        ComplianceStandard, on_delete=models.PROTECT, related_name='product_records',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    certification_number = models.CharField(max_length=120, blank=True)
    issuing_body = models.CharField(max_length=255, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    certificate_file = models.FileField(upload_to='plm/compliance/', blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'product', 'standard')

    def __str__(self):
        return f'{self.product.sku} · {self.standard.code} ({self.status})'

    def is_expiring_soon(self):
        if not self.expiry_date:
            return False
        delta = (self.expiry_date - timezone.now().date()).days
        return 0 < delta <= 30


class ComplianceAuditLog(TenantAwareModel):
    """Immutable audit trail for compliance changes — no UI edit/delete."""

    EVENT_CHOICES = [
        ('created', 'Created'),
        ('status_changed', 'Status Changed'),
        ('renewed', 'Renewed'),
        ('expired', 'Expired'),
        ('note_added', 'Note Added'),
    ]

    compliance = models.ForeignKey(
        ProductCompliance, on_delete=models.CASCADE, related_name='audit_entries',
    )
    event = models.CharField(max_length=30, choices=EVENT_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_audit_entries',
    )
    performed_at = models.DateTimeField(default=timezone.now)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-performed_at']
        indexes = [models.Index(fields=['compliance', '-performed_at'])]

    def __str__(self):
        return f'{self.event} @ {self.performed_at:%Y-%m-%d %H:%M}'


# ============================================================================
# 2.5  NPI / STAGE-GATE MANAGEMENT
# ============================================================================

class NPIProject(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    STAGE_CHOICES = [
        ('concept', 'Concept'),
        ('feasibility', 'Feasibility'),
        ('design', 'Design'),
        ('development', 'Development'),
        ('validation', 'Validation'),
        ('pilot_production', 'Pilot Production'),
        ('launch', 'Launch'),
    ]

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='npi_projects',
    )
    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='npi_projects',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    current_stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='concept')
    target_launch_date = models.DateField(null=True, blank=True)
    actual_launch_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'


class NPIStage(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    GATE_DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('go', 'Go'),
        ('no_go', 'No-Go'),
        ('recycle', 'Recycle'),
    ]

    project = models.ForeignKey(
        NPIProject, on_delete=models.CASCADE, related_name='stages',
    )
    stage = models.CharField(max_length=20, choices=NPIProject.STAGE_CHOICES)
    sequence = models.PositiveIntegerField(default=0)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    gate_decision = models.CharField(
        max_length=20, choices=GATE_DECISION_CHOICES, default='pending',
    )
    gate_notes = models.TextField(blank=True)
    gate_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gate_decisions',
    )
    gate_decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['project', 'sequence']
        unique_together = ('project', 'stage')

    def __str__(self):
        return f'{self.project.code} · {self.get_stage_display()}'


class NPIDeliverable(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('blocked', 'Blocked'),
    ]

    stage = models.ForeignKey(
        NPIStage, on_delete=models.CASCADE, related_name='deliverables',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='npi_deliverables',
    )
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        ordering = ['stage', 'due_date']

    def __str__(self):
        return f'{self.stage.project.code} · {self.name}'
