"""Module 7 - Quality Management (QMS).

Sub-modules:
    7.1  Incoming Quality Control (IQC)   (IncomingInspectionPlan,
                                           InspectionCharacteristic,
                                           IncomingInspection,
                                           InspectionMeasurement)
    7.2  In-Process Quality Control (IPQC) (ProcessInspectionPlan,
                                            ProcessInspection,
                                            SPCChart,
                                            ControlChartPoint)
    7.3  Final Quality Control (FQC)      (FinalInspectionPlan,
                                           FinalTestSpec,
                                           FinalInspection,
                                           FinalTestResult,
                                           CertificateOfAnalysis)
    7.4  Non-Conformance & CAPA           (NonConformanceReport,
                                           RootCauseAnalysis,
                                           CorrectiveAction,
                                           PreventiveAction,
                                           NCRAttachment)
    7.5  Calibration Management           (MeasurementEquipment,
                                           CalibrationRecord,
                                           CalibrationStandard,
                                           ToleranceVerification)

Reuses:
    apps.plm.models.Product               - what is being inspected
    apps.pps.models.RoutingOperation      - IPQC checkpoint anchor
    apps.pps.models.WorkCenter            - equipment assigned location
    apps.mes.models.MESWorkOrder          - FQC inspection lot link
    apps.mes.models.MESWorkOrderOperation - IPQC inspection link
    apps.accounts.models.User             - inspector / actor identity

Notes:
    Procurement (Module 9) is not shipped yet. ``IncomingInspection.supplier_name``
    and ``IncomingInspection.po_reference`` are free-text strings. When Module 9
    ships these will be replaced with FKs to ``procurement.PurchaseOrder``.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.mes.models import MESWorkOrder, MESWorkOrderOperation
from apps.plm.models import Product
from apps.pps.models import RoutingOperation, WorkCenter


# ============================================================================
# Shared upload allowlists (mirrors PLM / MES pattern)
# ============================================================================

QMS_FILE_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

NCR_ATTACHMENT_EXT_ALLOWLIST = (
    '.pdf', '.png', '.jpg', '.jpeg', '.docx', '.xlsx', '.txt', '.zip',
)
CALIBRATION_CERT_EXT_ALLOWLIST = ('.pdf', '.png', '.jpg', '.jpeg')
IPQC_ATTACHMENT_EXT_ALLOWLIST = ('.pdf', '.png', '.jpg', '.jpeg')


def _ncr_attachment_upload_path(instance, filename):
    tenant_id = instance.ncr.tenant_id if instance.ncr_id else 'unscoped'
    return f'qms/ncr/{tenant_id}/{instance.ncr_id or 0}/{filename}'


def _calibration_certificate_upload_path(instance, filename):
    tenant_id = instance.equipment.tenant_id if instance.equipment_id else 'unscoped'
    return f'qms/calibration/{tenant_id}/{instance.equipment_id or 0}/{filename}'


def _ipqc_attachment_upload_path(instance, filename):
    tenant_id = instance.tenant_id or 'unscoped'
    return f'qms/ipqc/{tenant_id}/{instance.plan_id or 0}/{filename}'


# ============================================================================
# 7.1  INCOMING QUALITY CONTROL (IQC)
# ============================================================================

class IncomingInspectionPlan(TenantAwareModel, TimeStampedModel):
    """Per-product IQC plan: AQL level + sample method + characteristic list."""

    AQL_LEVEL_CHOICES = [
        ('I', 'General Level I'),
        ('II', 'General Level II'),
        ('III', 'General Level III'),
    ]
    SAMPLE_METHOD_CHOICES = [
        ('single', 'Single Sampling'),
        ('double', 'Double Sampling'),
        ('reduced', 'Reduced Sampling'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='iqc_plans',
    )
    aql_level = models.CharField(
        max_length=4, choices=AQL_LEVEL_CHOICES, default='II',
        help_text='ANSI/ASQ Z1.4 general inspection level.',
    )
    sample_method = models.CharField(
        max_length=10, choices=SAMPLE_METHOD_CHOICES, default='single',
    )
    aql_value = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('2.5'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100'))],
        help_text='Acceptable Quality Limit (e.g. 1.0, 2.5, 4.0).',
    )
    version = models.CharField(max_length=20, default='1.0')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['product', 'version']
        unique_together = ('tenant', 'product', 'version')
        verbose_name = 'Incoming Inspection Plan'

    def __str__(self):
        return f'IQC Plan {self.product.sku} v{self.version}'


class InspectionCharacteristic(TenantAwareModel, TimeStampedModel):
    """A single characteristic to measure under an IQC plan."""

    TYPE_CHOICES = [
        ('dimensional', 'Dimensional'),
        ('visual', 'Visual'),
        ('functional', 'Functional'),
        ('chemical', 'Chemical'),
        ('mechanical', 'Mechanical'),
        ('other', 'Other'),
    ]

    plan = models.ForeignKey(
        IncomingInspectionPlan, on_delete=models.CASCADE,
        related_name='characteristics',
    )
    sequence = models.PositiveIntegerField(default=10)
    name = models.CharField(max_length=255)
    characteristic_type = models.CharField(
        max_length=15, choices=TYPE_CHOICES, default='dimensional',
    )
    nominal = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    usl = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='Upper Specification Limit.',
    )
    lsl = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='Lower Specification Limit.',
    )
    unit_of_measure = models.CharField(max_length=20, blank=True)
    is_critical = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['plan', 'sequence']
        unique_together = ('plan', 'sequence')
        verbose_name = 'Inspection Characteristic'

    def __str__(self):
        return f'{self.plan} #{self.sequence:03d} {self.name}'


class IncomingInspection(TenantAwareModel, TimeStampedModel):
    """One IQC event against a received lot."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_inspection', 'In Inspection'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('accepted_with_deviation', 'Accepted With Deviation'),
    ]

    inspection_number = models.CharField(max_length=30)
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='incoming_inspections',
    )
    plan = models.ForeignKey(
        IncomingInspectionPlan, on_delete=models.PROTECT,
        related_name='inspections', null=True, blank=True,
    )
    # Free-text procurement placeholders (preserved for legacy IQCs).
    supplier_name = models.CharField(max_length=255, blank=True)
    po_reference = models.CharField(max_length=60, blank=True)
    # Module 9 - Procurement bridge (additive, nullable; legacy text columns kept).
    supplier = models.ForeignKey(
        'procurement.Supplier', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='incoming_inspections',
    )
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='incoming_inspections',
    )
    lot_number = models.CharField(max_length=60, blank=True)
    received_qty = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    sample_size = models.PositiveIntegerField(
        default=0,
        help_text='Computed from AQL table at create time.',
    )
    accept_number = models.PositiveIntegerField(default=0)
    reject_number = models.PositiveIntegerField(default=0)
    accepted_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    rejected_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='iqc_inspections',
    )
    inspected_at = models.DateTimeField(null=True, blank=True)
    deviation_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'inspection_number')
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'product']),
        ]
        verbose_name = 'Incoming Inspection'

    def __str__(self):
        return f'{self.inspection_number} {self.product.sku} x{self.received_qty}'

    def is_editable(self):
        return self.status in ('pending', 'in_inspection')

    def can_start(self):
        return self.status == 'pending'

    def can_accept(self):
        return self.status == 'in_inspection'

    def can_reject(self):
        return self.status == 'in_inspection'


class InspectionMeasurement(TenantAwareModel, TimeStampedModel):
    """One measurement against one characteristic for one inspection."""

    inspection = models.ForeignKey(
        IncomingInspection, on_delete=models.CASCADE, related_name='measurements',
    )
    characteristic = models.ForeignKey(
        InspectionCharacteristic, on_delete=models.PROTECT,
        related_name='measurements',
    )
    measured_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    is_pass = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['inspection', 'characteristic']
        unique_together = ('inspection', 'characteristic')
        verbose_name = 'Inspection Measurement'

    def __str__(self):
        return f'{self.inspection.inspection_number} - {self.characteristic.name} {"PASS" if self.is_pass else "FAIL"}'


# ============================================================================
# 7.2  IN-PROCESS QUALITY CONTROL (IPQC)
# ============================================================================

class ProcessInspectionPlan(TenantAwareModel, TimeStampedModel):
    """Per-routing-operation in-process inspection plan + SPC config."""

    FREQUENCY_CHOICES = [
        ('every_part', 'Every Part'),
        ('every_n_parts', 'Every N Parts'),
        ('every_n_minutes', 'Every N Minutes'),
        ('shift_start', 'At Shift Start'),
        ('lot_change', 'On Lot Change'),
    ]
    CHART_CHOICES = [
        ('none', 'None'),
        ('x_bar_r', 'X-bar / R'),
        ('p', 'p Chart (proportion defective)'),
        ('np', 'np Chart (number defective)'),
        ('c', 'c Chart (defects per unit)'),
        ('u', 'u Chart (defects per unit, variable)'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='ipqc_plans',
    )
    routing_operation = models.ForeignKey(
        RoutingOperation, on_delete=models.PROTECT,
        related_name='ipqc_plans',
    )
    name = models.CharField(max_length=255)
    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default='every_n_parts',
    )
    frequency_value = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100000)],
    )
    chart_type = models.CharField(max_length=10, choices=CHART_CHOICES, default='x_bar_r')
    subgroup_size = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(2), MaxValueValidator(25)],
        help_text='Number of measurements per subgroup (X-bar/R).',
    )
    nominal = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    usl = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    lsl = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    unit_of_measure = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['product', 'routing_operation']
        unique_together = ('tenant', 'product', 'routing_operation')
        verbose_name = 'Process Inspection Plan'

    def __str__(self):
        return f'IPQC {self.product.sku} @ {self.routing_operation}'


class ProcessInspection(TenantAwareModel, TimeStampedModel):
    """A single in-process inspection event against an MES op."""

    RESULT_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('borderline', 'Borderline'),
    ]

    inspection_number = models.CharField(max_length=30)
    plan = models.ForeignKey(
        ProcessInspectionPlan, on_delete=models.PROTECT,
        related_name='inspections',
    )
    work_order_operation = models.ForeignKey(
        MESWorkOrderOperation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ipqc_inspections',
    )
    inspected_at = models.DateTimeField()
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ipqc_inspections',
    )
    subgroup_index = models.PositiveIntegerField(default=1)
    measured_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default='pass')
    attachment = models.FileField(
        upload_to=_ipqc_attachment_upload_path, blank=True, null=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-inspected_at']
        unique_together = ('tenant', 'inspection_number')
        indexes = [
            models.Index(fields=['tenant', 'plan', 'inspected_at']),
            models.Index(fields=['tenant', 'result']),
        ]
        verbose_name = 'Process Inspection'

    def __str__(self):
        return f'{self.inspection_number} {self.plan.product.sku} {self.result}'


class SPCChart(TenantAwareModel, TimeStampedModel):
    """SPC chart definition per IPQC plan, with computed UCL/LCL/CL."""

    plan = models.OneToOneField(
        ProcessInspectionPlan, on_delete=models.CASCADE,
        related_name='spc_chart',
    )
    chart_type = models.CharField(
        max_length=10, choices=ProcessInspectionPlan.CHART_CHOICES,
        default='x_bar_r',
    )
    subgroup_size = models.PositiveIntegerField(default=5)
    ucl = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cl = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    lcl = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    ucl_r = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cl_r = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    lcl_r = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    sample_size_used = models.PositiveIntegerField(default=0)
    recomputed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['plan']
        verbose_name = 'SPC Chart'

    def __str__(self):
        return f'SPC {self.get_chart_type_display()} {self.plan}'


class ControlChartPoint(TenantAwareModel, TimeStampedModel):
    """Append-only point on an SPC chart."""

    chart = models.ForeignKey(
        SPCChart, on_delete=models.CASCADE, related_name='points',
    )
    inspection = models.ForeignKey(
        ProcessInspection, on_delete=models.CASCADE,
        related_name='chart_points', null=True, blank=True,
    )
    subgroup_index = models.PositiveIntegerField()
    value = models.DecimalField(max_digits=14, decimal_places=4)
    range_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='R value for the subgroup (X-bar/R chart).',
    )
    is_out_of_control = models.BooleanField(default=False)
    rule_violations = models.JSONField(default=list, blank=True)
    recorded_at = models.DateTimeField()

    class Meta:
        ordering = ['chart', 'subgroup_index']
        indexes = [
            models.Index(fields=['tenant', 'chart', 'subgroup_index']),
        ]
        verbose_name = 'Control Chart Point'

    def __str__(self):
        flag = ' (OOC)' if self.is_out_of_control else ''
        return f'{self.chart.plan} #{self.subgroup_index} {self.value}{flag}'


# ============================================================================
# 7.3  FINAL QUALITY CONTROL (FQC)
# ============================================================================

class FinalInspectionPlan(TenantAwareModel, TimeStampedModel):
    """Finished-good test protocol."""

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='fqc_plans',
    )
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=20, default='1.0')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['product', 'version']
        unique_together = ('tenant', 'product', 'version')
        verbose_name = 'Final Inspection Plan'

    def __str__(self):
        return f'FQC Plan {self.product.sku} v{self.version}'


class FinalTestSpec(TenantAwareModel, TimeStampedModel):
    """One test in a final inspection plan."""

    METHOD_CHOICES = [
        ('mechanical', 'Mechanical'),
        ('electrical', 'Electrical'),
        ('dimensional', 'Dimensional'),
        ('visual', 'Visual'),
        ('chemical', 'Chemical'),
        ('performance', 'Performance'),
        ('other', 'Other'),
    ]

    plan = models.ForeignKey(
        FinalInspectionPlan, on_delete=models.CASCADE, related_name='specs',
    )
    sequence = models.PositiveIntegerField(default=10)
    test_name = models.CharField(max_length=255)
    test_method = models.CharField(max_length=15, choices=METHOD_CHOICES, default='mechanical')
    expected_result = models.CharField(max_length=255, blank=True)
    nominal = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    usl = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    lsl = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    unit_of_measure = models.CharField(max_length=20, blank=True)
    is_critical = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['plan', 'sequence']
        unique_together = ('plan', 'sequence')
        verbose_name = 'Final Test Specification'

    def __str__(self):
        return f'{self.plan} #{self.sequence:03d} {self.test_name}'


class FinalInspection(TenantAwareModel, TimeStampedModel):
    """A finished-goods inspection event against a MES work order lot."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_inspection', 'In Inspection'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('released_with_deviation', 'Released With Deviation'),
    ]

    inspection_number = models.CharField(max_length=30)
    plan = models.ForeignKey(
        FinalInspectionPlan, on_delete=models.PROTECT,
        related_name='inspections',
    )
    work_order = models.ForeignKey(
        MESWorkOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fqc_inspections',
    )
    lot_number = models.CharField(max_length=60, blank=True)
    quantity_tested = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    accepted_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    rejected_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fqc_inspections',
    )
    inspected_at = models.DateTimeField(null=True, blank=True)
    deviation_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'inspection_number')
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]
        verbose_name = 'Final Inspection'

    def __str__(self):
        return f'{self.inspection_number} {self.plan.product.sku} x{self.quantity_tested}'

    def is_editable(self):
        return self.status in ('pending', 'in_inspection')

    def can_start(self):
        return self.status == 'pending'

    def can_pass(self):
        return self.status == 'in_inspection'

    def can_fail(self):
        return self.status == 'in_inspection'

    def can_generate_coa(self):
        return self.status in ('passed', 'released_with_deviation')


class FinalTestResult(TenantAwareModel, TimeStampedModel):
    """One test result for one final inspection."""

    inspection = models.ForeignKey(
        FinalInspection, on_delete=models.CASCADE, related_name='results',
    )
    spec = models.ForeignKey(
        FinalTestSpec, on_delete=models.PROTECT, related_name='results',
    )
    measured_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    measured_text = models.CharField(max_length=255, blank=True)
    is_pass = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['inspection', 'spec']
        unique_together = ('inspection', 'spec')
        verbose_name = 'Final Test Result'

    def __str__(self):
        return f'{self.inspection.inspection_number} - {self.spec.test_name} {"PASS" if self.is_pass else "FAIL"}'


class CertificateOfAnalysis(TenantAwareModel, TimeStampedModel):
    """Generated CoA, one-to-one with a passed (or release-with-deviation) FQC inspection."""

    inspection = models.OneToOneField(
        FinalInspection, on_delete=models.CASCADE, related_name='coa',
    )
    coa_number = models.CharField(max_length=30)
    issued_at = models.DateTimeField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coas_issued',
    )
    customer_name = models.CharField(max_length=255, blank=True)
    customer_reference = models.CharField(max_length=120, blank=True)
    released_to_customer = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coas_released',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-issued_at']
        unique_together = ('tenant', 'coa_number')
        verbose_name = 'Certificate of Analysis'

    def __str__(self):
        return f'{self.coa_number} for {self.inspection.inspection_number}'


# ============================================================================
# 7.4  NON-CONFORMANCE & CAPA
# ============================================================================

class NonConformanceReport(TenantAwareModel, TimeStampedModel):
    """NCR header. Source-of-record for a quality non-conformance."""

    SOURCE_CHOICES = [
        ('iqc', 'Incoming Inspection'),
        ('ipqc', 'In-Process Inspection'),
        ('fqc', 'Final Inspection'),
        ('customer', 'Customer Complaint'),
        ('internal_audit', 'Internal Audit'),
        ('supplier_audit', 'Supplier Audit'),
        ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [
        ('minor', 'Minor'),
        ('major', 'Major'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('awaiting_capa', 'Awaiting CAPA'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    ncr_number = models.CharField(max_length=30)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='ipqc')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='minor')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='non_conformances',
    )
    lot_number = models.CharField(max_length=60, blank=True)
    quantity_affected = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    # Optional discriminator FKs - exactly one is typically populated.
    iqc_inspection = models.ForeignKey(
        IncomingInspection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs',
    )
    ipqc_inspection = models.ForeignKey(
        ProcessInspection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs',
    )
    fqc_inspection = models.ForeignKey(
        FinalInspection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs',
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs_reported',
    )
    reported_at = models.DateTimeField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs_assigned',
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncrs_closed',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)

    class Meta:
        ordering = ['-reported_at']
        unique_together = ('tenant', 'ncr_number')
        indexes = [
            models.Index(fields=['tenant', 'status', 'severity']),
            models.Index(fields=['tenant', 'source']),
        ]
        verbose_name = 'Non-Conformance Report'

    def __str__(self):
        return f'{self.ncr_number} {self.get_severity_display()}: {self.title[:40]}'

    def is_editable(self):
        return self.status in ('open', 'investigating')

    def can_investigate(self):
        return self.status == 'open'

    def can_await_capa(self):
        return self.status == 'investigating'

    def can_resolve(self):
        return self.status in ('investigating', 'awaiting_capa')

    def can_close(self):
        return self.status == 'resolved'

    def can_cancel(self):
        return self.status not in ('closed', 'cancelled')


class RootCauseAnalysis(TenantAwareModel, TimeStampedModel):
    """One-to-one RCA attached to a NCR."""

    METHOD_CHOICES = [
        ('five_why', '5 Why'),
        ('fishbone', 'Fishbone (Ishikawa)'),
        ('pareto', 'Pareto Analysis'),
        ('fmea', 'FMEA'),
        ('other', 'Other'),
    ]

    ncr = models.OneToOneField(
        NonConformanceReport, on_delete=models.CASCADE, related_name='rca',
    )
    method = models.CharField(max_length=15, choices=METHOD_CHOICES, default='five_why')
    analysis_text = models.TextField(blank=True)
    root_cause_summary = models.TextField(blank=True)
    analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rcas_analyzed',
    )
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Root Cause Analysis'

    def __str__(self):
        return f'RCA for {self.ncr.ncr_number}'


class CorrectiveAction(TenantAwareModel, TimeStampedModel):
    """A corrective action item linked to an NCR."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    ncr = models.ForeignKey(
        NonConformanceReport, on_delete=models.CASCADE,
        related_name='corrective_actions',
    )
    sequence = models.PositiveIntegerField(default=10)
    action_text = models.TextField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='corrective_actions_owned',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='corrective_actions_completed',
    )
    effectiveness_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['ncr', 'sequence']
        verbose_name = 'Corrective Action'

    def __str__(self):
        return f'CA #{self.sequence} for {self.ncr.ncr_number}'

    def can_complete(self):
        return self.status in ('open', 'in_progress')


class PreventiveAction(TenantAwareModel, TimeStampedModel):
    """A preventive action item linked to an NCR."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    ncr = models.ForeignKey(
        NonConformanceReport, on_delete=models.CASCADE,
        related_name='preventive_actions',
    )
    sequence = models.PositiveIntegerField(default=10)
    action_text = models.TextField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='preventive_actions_owned',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='preventive_actions_completed',
    )
    effectiveness_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['ncr', 'sequence']
        verbose_name = 'Preventive Action'

    def __str__(self):
        return f'PA #{self.sequence} for {self.ncr.ncr_number}'

    def can_complete(self):
        return self.status in ('open', 'in_progress')


class NCRAttachment(TenantAwareModel, TimeStampedModel):
    """File attachment on a NCR (photos, lab reports, etc.)."""

    ncr = models.ForeignKey(
        NonConformanceReport, on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(upload_to=_ncr_attachment_upload_path)
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ncr_attachments_uploaded',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'NCR Attachment'

    def __str__(self):
        return f'Attachment {self.pk} on {self.ncr.ncr_number}'


# ============================================================================
# 7.5  CALIBRATION MANAGEMENT
# ============================================================================

class MeasurementEquipment(TenantAwareModel, TimeStampedModel):
    """Gauges, calipers, scales etc. that need periodic calibration."""

    EQUIPMENT_TYPE_CHOICES = [
        ('caliper', 'Caliper'),
        ('micrometer', 'Micrometer'),
        ('gauge', 'Gauge'),
        ('thermometer', 'Thermometer'),
        ('scale', 'Scale / Balance'),
        ('multimeter', 'Multimeter'),
        ('pressure', 'Pressure Gauge'),
        ('torque', 'Torque Wrench'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('out_of_service', 'Out of Service'),
        ('retired', 'Retired'),
    ]

    equipment_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    equipment_type = models.CharField(
        max_length=15, choices=EQUIPMENT_TYPE_CHOICES, default='caliper',
    )
    serial_number = models.CharField(max_length=120)
    manufacturer = models.CharField(max_length=120, blank=True)
    model_number = models.CharField(max_length=120, blank=True)
    assigned_work_center = models.ForeignKey(
        WorkCenter, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='measurement_equipment',
    )
    range_min = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    range_max = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    unit_of_measure = models.CharField(max_length=20, blank=True)
    tolerance = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    calibration_interval_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(1), MaxValueValidator(3650)],
    )
    last_calibrated_at = models.DateTimeField(null=True, blank=True)
    next_due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['equipment_number']
        unique_together = (
            ('tenant', 'equipment_number'),
            ('tenant', 'serial_number'),
        )
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'next_due_at']),
        ]
        verbose_name = 'Measurement Equipment'
        verbose_name_plural = 'Measurement Equipment'

    def __str__(self):
        return f'{self.equipment_number} {self.name}'

    def is_editable(self):
        return self.status != 'retired'


class CalibrationStandard(TenantAwareModel, TimeStampedModel):
    """Reference standard catalog entry (e.g. NIST-traceable gauge block)."""

    name = models.CharField(max_length=255)
    standard_number = models.CharField(max_length=120)
    traceable_to = models.CharField(
        max_length=120, blank=True,
        help_text='e.g. NIST, NPL, PTB - the national metrology institute.',
    )
    description = models.TextField(blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'standard_number')
        verbose_name = 'Calibration Standard'

    def __str__(self):
        return f'{self.standard_number} - {self.name}'


class CalibrationRecord(TenantAwareModel, TimeStampedModel):
    """Append-only record of a calibration event for a piece of equipment."""

    RESULT_CHOICES = [
        ('pass', 'Pass'),
        ('pass_with_adjustment', 'Pass With Adjustment'),
        ('fail', 'Fail'),
    ]

    record_number = models.CharField(max_length=30)
    # PROTECT so a deleted equipment record cannot silently erase its
    # calibration history. The view layer surfaces ProtectedError as a
    # toast: "Cannot delete - equipment has calibration history."
    equipment = models.ForeignKey(
        MeasurementEquipment, on_delete=models.PROTECT,
        related_name='calibration_records',
    )
    calibrated_at = models.DateTimeField()
    calibrated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calibration_records_performed',
    )
    external_lab_name = models.CharField(max_length=255, blank=True)
    standard = models.ForeignKey(
        CalibrationStandard, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calibration_records',
    )
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='pass')
    next_due_at = models.DateTimeField(null=True, blank=True)
    certificate_file = models.FileField(
        upload_to=_calibration_certificate_upload_path, blank=True, null=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-calibrated_at']
        unique_together = ('tenant', 'record_number')
        indexes = [
            models.Index(fields=['tenant', 'equipment', 'calibrated_at']),
            models.Index(fields=['tenant', 'result']),
        ]
        verbose_name = 'Calibration Record'

    def __str__(self):
        return f'{self.record_number} {self.equipment.equipment_number} {self.result}'

    def clean(self):
        super().clean()
        if self.result == 'fail' and not (self.notes or '').strip():
            raise ValidationError(
                {'notes': 'Notes are required when calibration result is Fail.'}
            )


class ToleranceVerification(TenantAwareModel, TimeStampedModel):
    """A single tolerance check measured during a calibration."""

    record = models.ForeignKey(
        CalibrationRecord, on_delete=models.CASCADE,
        related_name='tolerance_checks',
    )
    sequence = models.PositiveIntegerField(default=10)
    description = models.CharField(max_length=255)
    nominal = models.DecimalField(max_digits=14, decimal_places=4)
    as_found = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    as_left = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    tolerance = models.DecimalField(max_digits=14, decimal_places=4)
    is_within_tolerance = models.BooleanField(default=True)
    unit_of_measure = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['record', 'sequence']
        unique_together = ('record', 'sequence')
        verbose_name = 'Tolerance Verification'

    def __str__(self):
        return f'{self.record.record_number} #{self.sequence} {self.description}'
