"""Module 3 — Bill of Materials (BOM) Management.

Sub-modules:
    3.1  Multi-Level BOM                      (BillOfMaterials, BOMLine)
    3.2  BOM Versioning & Revision            (BOMRevision)
    3.3  Alternative & Substitute Materials   (AlternateMaterial, SubstitutionRule)
    3.4  BOM Cost Roll-Up                     (CostElement, BOMCostRollup)
    3.5  EBOM/MBOM/SBOM Synchronization       (BOMSyncMap, BOMSyncLog
                                               + bom_type discriminator on BillOfMaterials)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.plm.models import Product


# ============================================================================
# 3.1  MULTI-LEVEL BOM
# ============================================================================

class BillOfMaterials(TenantAwareModel, TimeStampedModel):
    """BOM header.

    A single Product may have multiple BOMs differentiated by `bom_type`
    (engineering / manufacturing / service) and `version` + `revision`.
    """

    BOM_TYPE_CHOICES = [
        ('ebom', 'Engineering BOM (EBOM)'),
        ('mbom', 'Manufacturing BOM (MBOM)'),
        ('sbom', 'Service BOM (SBOM)'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('released', 'Released'),
        ('obsolete', 'Obsolete'),
    ]

    bom_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='boms',
    )
    bom_type = models.CharField(max_length=10, choices=BOM_TYPE_CHOICES, default='ebom')
    version = models.CharField(max_length=10, default='A')
    revision = models.CharField(max_length=10, default='01')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    description = models.TextField(blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Default BOM of this type for the product (used by cost roll-up cascade and MRP).',
    )
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='boms_created',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='boms_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'product', 'bom_type', 'version', 'revision')
        verbose_name = 'Bill of Materials'
        verbose_name_plural = 'Bills of Materials'

    def __str__(self):
        return f'{self.bom_number} — {self.product.sku} ({self.get_bom_type_display()} v{self.version}.{self.revision})'

    def is_editable(self):
        return self.status in ('draft', 'under_review')

    # --- Helpers used by views, signals, seeder ---

    def root_lines(self):
        return self.lines.filter(parent_line__isnull=True).select_related('component')

    def explode(self, level=0, parent_qty=Decimal('1')):
        """Yield ``(level, line, expanded_qty)`` tuples — multi-level explosion.

        Phantom assemblies are exploded transparently: their own line is
        skipped and their children are emitted at the same level as the
        phantom would have been, with quantities multiplied through.
        """
        for line in self.lines.filter(parent_line__isnull=True).select_related('component').order_by('sequence'):
            yield from _explode_line(line, level, parent_qty)

    def snapshot(self):
        """Return JSON-serializable snapshot of the full BOM tree."""
        def _serialize(line):
            return {
                'id': line.pk,
                'sequence': line.sequence,
                'component_sku': line.component.sku,
                'component_name': line.component.name,
                'quantity': str(line.quantity),
                'unit_of_measure': line.unit_of_measure,
                'scrap_percent': str(line.scrap_percent),
                'is_phantom': line.is_phantom,
                'reference_designator': line.reference_designator,
                'notes': line.notes,
                'children': [_serialize(c) for c in line.children.all().order_by('sequence')],
            }
        return {
            'bom_number': self.bom_number,
            'name': self.name,
            'product_sku': self.product.sku,
            'bom_type': self.bom_type,
            'version': self.version,
            'revision': self.revision,
            'status': self.status,
            'lines': [_serialize(l) for l in self.root_lines().order_by('sequence')],
            'snapshot_at': timezone.now().isoformat(),
        }

    def compute_rollup(self, computed_by=None):
        """Compute or refresh the BOMCostRollup for this BOM.

        For each line: looks up CostElement records on the component product.
        Sub-assembly material cost cascades through the sub-assembly's
        *default released* BOM (config decision: predictable + safe).
        """
        from collections import defaultdict
        totals = defaultdict(lambda: Decimal('0'))
        for line in self.lines.select_related('component'):
            qty = line.effective_quantity()
            line_costs = _resolve_component_costs(line.component, tenant=self.tenant)
            for cost_type, unit_cost in line_costs.items():
                totals[cost_type] += unit_cost * qty
        rollup, _ = BOMCostRollup.objects.update_or_create(
            tenant=self.tenant, bom=self,
            defaults={
                'material_cost': totals['material'],
                'labor_cost': totals['labor'],
                'overhead_cost': totals['overhead'],
                'tooling_cost': totals['tooling'],
                'other_cost': totals['other'],
                'total_cost': sum(totals.values(), Decimal('0')),
                'currency': 'USD',
                'computed_at': timezone.now(),
                'computed_by': computed_by,
            },
        )
        return rollup


def _explode_line(line, level, parent_qty):
    """Recursive helper for BillOfMaterials.explode.

    Phantom lines collapse: their qty multiplies into children but the line
    itself is not yielded.
    """
    expanded_qty = parent_qty * line.quantity
    if not line.is_phantom:
        yield (level, line, expanded_qty)
    for child in line.children.all().order_by('sequence'):
        next_level = level if line.is_phantom else level + 1
        yield from _explode_line(child, next_level, expanded_qty)


def _resolve_component_costs(component, tenant):
    """Return dict {cost_type: unit_cost} for a Product.

    For sub-assemblies, falls back to the unit total of their default
    released BOM rollup if no direct CostElement is recorded.
    """
    from collections import defaultdict
    out = defaultdict(lambda: Decimal('0'))
    direct = CostElement.objects.filter(tenant=tenant, product=component)
    for ce in direct:
        out[ce.cost_type] += ce.unit_cost
    if not direct.exists():
        # Try sub-assembly cascade.
        sub = (BillOfMaterials.objects
               .filter(tenant=tenant, product=component, status='released', is_default=True)
               .first())
        if sub is not None:
            try:
                sub_rollup = sub.cost_rollup
            except BOMCostRollup.DoesNotExist:
                sub_rollup = sub.compute_rollup()
            out['material'] += sub_rollup.material_cost
            out['labor'] += sub_rollup.labor_cost
            out['overhead'] += sub_rollup.overhead_cost
            out['tooling'] += sub_rollup.tooling_cost
            out['other'] += sub_rollup.other_cost
    return out


class BOMLine(TenantAwareModel, TimeStampedModel):
    """A component row on a BOM. Self-FK enables multi-level trees."""

    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.CASCADE, related_name='lines',
    )
    parent_line = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children',
    )
    sequence = models.PositiveIntegerField(default=10)
    component = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='used_in_bom_lines',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_of_measure = models.CharField(
        max_length=10, choices=Product.UOM_CHOICES, default='ea',
    )
    scrap_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        help_text='Percentage scrap factor — added to effective demand.',
        validators=[
            MinValueValidator(Decimal('0')),
            MaxValueValidator(Decimal('100')),
        ],
    )
    is_phantom = models.BooleanField(
        default=False,
        help_text='Phantom assemblies are exploded transparently and never appear in MRP.',
    )
    reference_designator = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['bom', 'sequence', 'pk']
        verbose_name = 'BOM Line'

    def __str__(self):
        return f'{self.bom.bom_number} · {self.component.sku} × {self.quantity}'

    def effective_quantity(self):
        """Quantity scaled by scrap percent (1 + scrap/100)."""
        scrap = (self.scrap_percent or Decimal('0')) / Decimal('100')
        return (self.quantity * (Decimal('1') + scrap)).quantize(Decimal('0.0001'))


# ============================================================================
# 3.2  BOM VERSIONING & REVISION
# ============================================================================

class BOMRevision(TenantAwareModel, TimeStampedModel):
    """Immutable snapshot of a BOM tree, used for revision history + rollback."""

    REVISION_TYPE_CHOICES = [
        ('major', 'Major'),
        ('minor', 'Minor'),
        ('engineering', 'Engineering'),
        ('rollback', 'Rollback'),
    ]

    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.CASCADE, related_name='revisions',
    )
    version = models.CharField(max_length=10)
    revision = models.CharField(max_length=10)
    revision_type = models.CharField(
        max_length=20, choices=REVISION_TYPE_CHOICES, default='minor',
    )
    change_summary = models.TextField(blank=True)
    effective_from = models.DateField(default=timezone.now)
    snapshot_json = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bom_revisions',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.bom.bom_number} v{self.version}.{self.revision} ({self.get_revision_type_display()})'


# ============================================================================
# 3.3  ALTERNATIVE & SUBSTITUTE MATERIALS
# ============================================================================

class AlternateMaterial(TenantAwareModel, TimeStampedModel):
    """An approved or pending substitute for a specific BOM line component."""

    SUBSTITUTION_TYPE_CHOICES = [
        ('direct', 'Direct (drop-in)'),
        ('approved', 'Approved Equivalent'),
        ('emergency', 'Emergency / Last Resort'),
        ('one_to_one', 'One-to-One'),
        ('one_to_many', 'One-to-Many'),
    ]
    APPROVAL_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    bom_line = models.ForeignKey(
        BOMLine, on_delete=models.CASCADE, related_name='alternates',
    )
    alternate_component = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='alternate_for_lines',
    )
    priority = models.PositiveIntegerField(
        default=1, help_text='1 = preferred substitute. Lower number = higher priority.',
    )
    substitution_type = models.CharField(
        max_length=20, choices=SUBSTITUTION_TYPE_CHOICES, default='approved',
    )
    usage_rule = models.TextField(
        blank=True, help_text='Conditions under which this alternate may be used.',
    )
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default='pending',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alternate_approvals',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['bom_line', 'priority']
        unique_together = ('bom_line', 'alternate_component')

    def __str__(self):
        return f'{self.bom_line} ↔ {self.alternate_component.sku} ({self.approval_status})'


class SubstitutionRule(TenantAwareModel, TimeStampedModel):
    """Reusable tenant-level substitution rule (catalog of equivalences)."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    original_component = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='substitution_rules_original',
    )
    substitute_component = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='substitution_rules_substitute',
    )
    condition_text = models.TextField(
        blank=True, help_text='Free-text rule (e.g. "any 10kΩ 1% resistor in 0805 package").',
    )
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ============================================================================
# 3.4  BOM COST ROLL-UP
# ============================================================================

class CostElement(TenantAwareModel, TimeStampedModel):
    """Per-component current cost record by cost type."""

    COST_TYPE_CHOICES = [
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('overhead', 'Overhead'),
        ('tooling', 'Tooling'),
        ('other', 'Other'),
    ]
    SOURCE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('vendor', 'Vendor Quote'),
        ('computed', 'Computed'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='cost_elements',
    )
    cost_type = models.CharField(max_length=20, choices=COST_TYPE_CHOICES, default='material')
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    currency = models.CharField(max_length=8, default='USD')
    effective_date = models.DateField(default=timezone.now)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['product__sku', 'cost_type']
        unique_together = ('tenant', 'product', 'cost_type')

    def __str__(self):
        return f'{self.product.sku} · {self.get_cost_type_display()}: {self.unit_cost} {self.currency}'


class BOMCostRollup(TenantAwareModel, TimeStampedModel):
    """Computed cost snapshot for a BOM (latest only — recomputed on demand)."""

    bom = models.OneToOneField(
        BillOfMaterials, on_delete=models.CASCADE, related_name='cost_rollup',
    )
    material_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    labor_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    overhead_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    tooling_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    other_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    total_cost = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal('0'))
    currency = models.CharField(max_length=8, default='USD')
    computed_at = models.DateTimeField(null=True, blank=True)
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bom_rollups',
    )

    class Meta:
        ordering = ['-computed_at']

    def __str__(self):
        return f'{self.bom.bom_number} rollup = {self.total_cost} {self.currency}'

    def is_stale(self):
        return self.computed_at is None


# ============================================================================
# 3.5  EBOM / MBOM / SBOM SYNCHRONIZATION
# ============================================================================

class BOMSyncMap(TenantAwareModel, TimeStampedModel):
    """Mapping between a source BOM and a target BOM for cross-type sync.

    The classic flow is:
        EBOM (engineering) → MBOM (manufacturing) → SBOM (service)
    """

    SYNC_STATUS_CHOICES = [
        ('pending', 'Pending Sync'),
        ('in_sync', 'In Sync'),
        ('drift_detected', 'Drift Detected'),
        ('manual_override', 'Manual Override'),
    ]

    source_bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.CASCADE, related_name='sync_targets',
    )
    target_bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.CASCADE, related_name='sync_sources',
    )
    sync_status = models.CharField(
        max_length=20, choices=SYNC_STATUS_CHOICES, default='pending',
    )
    drift_summary = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    synced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bom_syncs',
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('source_bom', 'target_bom')

    def __str__(self):
        return f'{self.source_bom.bom_number} → {self.target_bom.bom_number}'


class BOMSyncLog(TenantAwareModel):
    """Append-only event log for sync runs."""

    ACTION_CHOICES = [
        ('created', 'Mapping Created'),
        ('updated', 'Updated'),
        ('drift', 'Drift Detected'),
        ('reconciled', 'Reconciled'),
    ]

    sync_map = models.ForeignKey(
        BOMSyncMap, on_delete=models.CASCADE, related_name='log_entries',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bom_sync_log_entries',
    )
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['sync_map', '-timestamp'])]

    def __str__(self):
        return f'{self.sync_map} · {self.action} @ {self.timestamp:%Y-%m-%d %H:%M}'
