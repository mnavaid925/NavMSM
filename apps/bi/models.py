"""Module 16 - Business Intelligence & Analytics.

Sub-modules:
    16.1  Manufacturing KPI Dashboards   (KPIDefinition, KPIDashboard,
                                          KPIWidget, KPISnapshot)
    16.2  Ad-Hoc Report Builder          (ReportDataSource, ReportDefinition,
                                          ReportField, ReportFilter, ReportRun)
    16.3  Predictive Analytics           (PredictiveModel, PredictionRun,
                                          PredictionResult, TrendAnalysis)
    16.4  Tenant-Isolated Data Warehouse (DataMart, DataMartColumn,
                                          DataMartSnapshot, DataMartRow)
    16.5  Automated Report Distribution  (ReportSchedule, ReportRecipient,
                                          ReportDelivery, ReportExport)

This module is **read-mostly** over the rest of the platform - it aggregates
operational data from mes / iot / qms / cost / utility / procurement / eam /
mrp / inventory and surfaces dashboards, ad-hoc reports, heuristic predictions,
materialized data marts and scheduled email distribution.

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal carries explicit Min/MaxValueValidator
    * L-12 auto-numbering retry handled in save() (last-row + 1 pattern)
    * L-13 transaction.atomic() around denorm bumps in services
    * L-14 per-workflow forms enforce required fields
    * L-17 PROTECT on audit/log child FKs
    * L-18 weak=False on factory-bound signal handlers (see signals.py)
    * L-22 file upload allowlist + 25 MB cap on ReportExport.file
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# Common decimal validators (mirrors apps/iot/models.py and apps/utility/models.py).
NEG_BOUND = Decimal('-99999999.9999')
NON_NEG = MinValueValidator(Decimal('0'))
SIGNED = MinValueValidator(NEG_BOUND)
PCT_MAX = MaxValueValidator(Decimal('100'))


def _next_number(model_cls, tenant_id, prefix, field):
    """Return the next ``<prefix>-NNNNN`` string for the given tenant.

    Single source of truth for auto-numbered tenant-scoped models. Uses
    ``all_objects`` so the lookup is not auto-filtered by the thread-local
    tenant (idempotent in seed / manage shell contexts).
    """
    qs = (
        model_cls.all_objects
        .filter(tenant_id=tenant_id, **{f'{field}__startswith': f'{prefix}-'})
        .order_by(f'-{field}')
    )
    last = qs.first()
    n = 1
    if last:
        last_val = getattr(last, field, '') or ''
        if last_val.startswith(f'{prefix}-'):
            try:
                n = int(last_val.split('-')[-1]) + 1
            except (ValueError, IndexError):
                n = 1
    return f'{prefix}-{n:05d}'


# ============================================================================
# 16.1  MANUFACTURING KPI DASHBOARDS
# ============================================================================

class KPIDefinition(TenantAwareModel, TimeStampedModel):
    """A KPI recipe registered against a tenant.

    The ``code`` field is the dispatch key into ``services/kpi.py`` -
    e.g. ``oee`` -> ``compute_oee_kpi``. Adding a KPI means adding ONE row
    here and ONE function in ``services/kpi.py``.
    """

    CODE_CHOICES = [
        ('oee', 'Overall Equipment Effectiveness'),
        ('throughput', 'Throughput (good units)'),
        ('yield', 'First-Pass Yield %'),
        ('scrap_rate', 'Scrap Rate %'),
        ('on_time_delivery', 'On-Time Delivery %'),
        ('gross_margin', 'Gross Margin %'),
        ('energy_intensity', 'Energy Intensity (kWh / unit)'),
        ('carbon_intensity', 'Carbon Intensity (kgCO2e / unit)'),
        ('supplier_otd', 'Supplier On-Time Delivery %'),
    ]
    DIRECTION_CHOICES = [
        ('higher_is_better', 'Higher is better'),
        ('lower_is_better', 'Lower is better'),
    ]

    code = models.CharField(max_length=30, choices=CODE_CHOICES)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, blank=True, help_text='%, ea, kWh, kgCO2e, etc.')
    direction = models.CharField(
        max_length=20, choices=DIRECTION_CHOICES, default='higher_is_better',
    )
    target_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    warning_threshold = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
        help_text='Value at which the KPI flips to warning.',
    )
    critical_threshold = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
        help_text='Value at which the KPI flips to critical.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class KPIDashboard(TenantAwareModel, TimeStampedModel):
    """A named dashboard surface scoped to a tenant.

    Each dashboard groups several ``KPIWidget`` placements. Owner is optional
    (None means tenant-shared by default).
    """

    PERIOD_CHOICES = [
        ('last_7d', 'Last 7 days'),
        ('last_30d', 'Last 30 days'),
        ('mtd', 'Month-to-date'),
        ('qtd', 'Quarter-to-date'),
        ('ytd', 'Year-to-date'),
        ('custom', 'Custom range'),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='owned_bi_dashboards',
    )
    is_shared = models.BooleanField(default=True, help_text='If False, only the owner sees this dashboard.')
    default_period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='last_30d')
    auto_refresh_minutes = models.PositiveIntegerField(default=15)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'slug')

    def __str__(self):
        return self.name


class KPIWidget(TenantAwareModel, TimeStampedModel):
    """A placement of a KPI on a dashboard."""

    CHART_TYPE_CHOICES = [
        ('kpi_card', 'KPI Card'),
        ('line', 'Line Chart'),
        ('bar', 'Bar Chart'),
        ('donut', 'Donut Chart'),
        ('gauge', 'Gauge'),
        ('sparkline', 'Sparkline'),
    ]

    dashboard = models.ForeignKey(
        KPIDashboard, on_delete=models.CASCADE, related_name='widgets',
    )
    kpi_definition = models.ForeignKey(
        KPIDefinition, on_delete=models.PROTECT, related_name='widgets',
    )
    position = models.PositiveIntegerField(default=0)
    chart_type = models.CharField(max_length=15, choices=CHART_TYPE_CHOICES, default='kpi_card')
    scope_filter = models.JSONField(default=dict, blank=True)
    compare_to_previous = models.BooleanField(default=True)
    title_override = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['dashboard', 'position', 'id']
        unique_together = ('tenant', 'dashboard', 'kpi_definition', 'position')

    def __str__(self):
        return f'{self.dashboard.name} / {self.kpi_definition.code}'


class KPISnapshot(TenantAwareModel, TimeStampedModel):
    """Materialized period roll-up so widgets render in O(1).

    PROTECT on ``kpi_definition`` (Lesson L-17) so the audit trail cannot
    drift even if a definition is mid-deletion.
    """

    SCOPE_CHOICES = [
        ('tenant', 'Tenant-wide'),
        ('plant', 'Plant / Warehouse'),
        ('cost_center', 'Cost Center'),
        ('product', 'Product'),
        ('asset', 'Asset'),
        ('supplier', 'Supplier'),
    ]
    STATUS_CHOICES = [
        ('on_target', 'On Target'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    kpi_definition = models.ForeignKey(
        KPIDefinition, on_delete=models.PROTECT, related_name='snapshots',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    scope_type = models.CharField(max_length=15, choices=SCOPE_CHOICES, default='tenant')
    scope_pk = models.PositiveIntegerField(null=True, blank=True)
    scope_label = models.CharField(max_length=120, blank=True)
    value = models.DecimalField(
        max_digits=18, decimal_places=4, validators=[SIGNED],
    )
    prior_period_value = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='on_target')
    sample_size = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-period_end', 'kpi_definition__code']
        unique_together = ('tenant', 'kpi_definition', 'period_start', 'scope_type', 'scope_pk')
        indexes = [
            models.Index(fields=['tenant', 'kpi_definition', 'period_end']),
            models.Index(fields=['tenant', 'scope_type', 'scope_pk']),
        ]

    def __str__(self):
        return f'{self.kpi_definition.code} @ {self.period_end}: {self.value}'

    @property
    def delta_vs_prior(self):
        if self.prior_period_value is None:
            return None
        return self.value - self.prior_period_value

    @property
    def delta_pct_vs_prior(self):
        if not self.prior_period_value:
            return None
        try:
            return ((self.value - self.prior_period_value) / abs(self.prior_period_value)) * Decimal('100')
        except (ZeroDivisionError, ArithmeticError):
            return None


# ============================================================================
# 16.2  AD-HOC REPORT BUILDER
# ============================================================================

class ReportDataSource(TenantAwareModel, TimeStampedModel):
    """A registered data source the report builder may query.

    The actual model + allowed fields are validated against the static
    whitelist in ``services/registry.py`` - this row is a tenant-facing
    catalog entry that ties a slug to a model_label + the allowed fields.
    """

    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    model_label = models.CharField(
        max_length=80,
        help_text='Django app_label.model_name, e.g. mes.ProductionReport',
    )
    allowed_fields = models.JSONField(default=list, blank=True)
    default_filters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} ({self.model_label})'


class ReportDefinition(TenantAwareModel, TimeStampedModel):
    """A saved ad-hoc report definition. Auto-numbered ``RPT-00001``."""

    SORT_DIR_CHOICES = [
        ('asc', 'Ascending'),
        ('desc', 'Descending'),
    ]

    report_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    data_source = models.ForeignKey(
        ReportDataSource, on_delete=models.PROTECT, related_name='reports',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_reports',
    )
    is_shared = models.BooleanField(default=True)
    group_by_field = models.CharField(max_length=80, blank=True)
    sort_field = models.CharField(max_length=80, blank=True)
    sort_direction = models.CharField(max_length=4, choices=SORT_DIR_CHOICES, default='desc')
    row_limit = models.PositiveIntegerField(default=1000)

    class Meta:
        ordering = ['-id']
        unique_together = (
            ('tenant', 'report_number'),
            ('tenant', 'name'),
        )

    def __str__(self):
        return f'{self.report_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.report_number and self.tenant_id:
            self.report_number = _next_number(ReportDefinition, self.tenant_id, 'RPT', 'report_number')
        super().save(*args, **kwargs)


class ReportField(TenantAwareModel, TimeStampedModel):
    """One field/column included in a report definition."""

    AGG_CHOICES = [
        ('none', 'None'),
        ('sum', 'Sum'),
        ('avg', 'Average'),
        ('count', 'Count'),
        ('min', 'Min'),
        ('max', 'Max'),
    ]

    report = models.ForeignKey(
        ReportDefinition, on_delete=models.CASCADE, related_name='fields',
    )
    field_name = models.CharField(max_length=80)
    display_name = models.CharField(max_length=120, blank=True)
    aggregation = models.CharField(max_length=10, choices=AGG_CHOICES, default='none')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['report', 'position', 'id']
        unique_together = ('tenant', 'report', 'field_name')

    def __str__(self):
        return f'{self.report.report_number} / {self.field_name}'


class ReportFilter(TenantAwareModel, TimeStampedModel):
    """One where-clause row applied to a report definition."""

    OP_CHOICES = [
        ('eq', '='),
        ('ne', '!='),
        ('gt', '>'),
        ('gte', '>='),
        ('lt', '<'),
        ('lte', '<='),
        ('contains', 'Contains'),
        ('startswith', 'Starts with'),
        ('endswith', 'Ends with'),
        ('in', 'In list'),
        ('between', 'Between'),
        ('isnull', 'Is null'),
    ]

    report = models.ForeignKey(
        ReportDefinition, on_delete=models.CASCADE, related_name='filters',
    )
    field_name = models.CharField(max_length=80)
    operator = models.CharField(max_length=12, choices=OP_CHOICES, default='eq')
    value = models.CharField(max_length=512, blank=True)
    value_to = models.CharField(max_length=512, blank=True, help_text='Upper bound for "between".')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['report', 'position', 'id']

    def __str__(self):
        return f'{self.report.report_number} / {self.field_name} {self.operator}'


class ReportRun(TenantAwareModel, TimeStampedModel):
    """Audit ledger of every report execution. Auto-numbered ``RR-00001``."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    run_number = models.CharField(max_length=15)
    report = models.ForeignKey(
        ReportDefinition, on_delete=models.PROTECT, related_name='runs',
    )
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_report_runs',
    )
    run_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    row_count = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    parameters = models.JSONField(default=dict, blank=True)
    result_preview = models.JSONField(default=list, blank=True, help_text='First 50 rows for inline preview.')
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-run_at', '-id']
        unique_together = ('tenant', 'run_number')

    def __str__(self):
        return self.run_number

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.run_number and self.tenant_id:
            self.run_number = _next_number(ReportRun, self.tenant_id, 'RR', 'run_number')
        super().save(*args, **kwargs)


# ============================================================================
# 16.3  PREDICTIVE ANALYTICS
# ============================================================================

class PredictiveModel(TenantAwareModel, TimeStampedModel):
    """A heuristic prediction recipe registered against a tenant.

    Heuristic-only by design (Lesson: no scikit-learn dep). New recipes are
    added by registering one row here and one function in
    ``services/predictions.py``.
    """

    CODE_CHOICES = [
        ('demand_forecast', 'Demand Forecast (linear regression)'),
        ('failure_likelihood', 'Failure Likelihood (rolling failure rate)'),
        ('quality_trend', 'Quality Trend (SPC slope)'),
        ('scrap_drift', 'Scrap Drift (scrap-rate slope)'),
        ('cost_drift', 'Cost Drift (variance vs. standard)'),
        ('energy_drift', 'Energy Drift (kWh/unit slope)'),
    ]

    code = models.CharField(max_length=30, choices=CODE_CHOICES)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    target_model_label = models.CharField(
        max_length=80, blank=True,
        help_text='Optional: app_label.model_name the prediction targets (e.g. plm.Product).',
    )
    lookback_days = models.PositiveIntegerField(default=90)
    forecast_horizon_days = models.PositiveIntegerField(default=30)
    parameters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code', 'name')

    def __str__(self):
        return f'{self.code} - {self.name}'


class PredictionRun(TenantAwareModel, TimeStampedModel):
    """A single execution of a PredictiveModel. Auto-numbered ``PR-00001``."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    run_number = models.CharField(max_length=15)
    predictive_model = models.ForeignKey(
        PredictiveModel, on_delete=models.PROTECT, related_name='runs',
    )
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_prediction_runs',
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    result_count = models.PositiveIntegerField(default=0)
    parameters = models.JSONField(default=dict, blank=True)
    cancellation_reason = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at', '-id']
        unique_together = ('tenant', 'run_number')

    def __str__(self):
        return self.run_number

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.run_number and self.tenant_id:
            self.run_number = _next_number(PredictionRun, self.tenant_id, 'PR', 'run_number')
        super().save(*args, **kwargs)

    def is_cancelable(self):
        return self.status in ('queued', 'running')


class PredictionResult(TenantAwareModel, TimeStampedModel):
    """One predicted row from a PredictionRun.

    PROTECT on the parent run (L-17) so audit results survive the parent
    survives only via terminal/archival deletes.
    """

    TARGET_TYPE_CHOICES = [
        ('product', 'Product'),
        ('asset', 'Asset'),
        ('supplier', 'Supplier'),
        ('spc_chart', 'SPC Chart'),
        ('cost_center', 'Cost Center'),
        ('tenant', 'Tenant'),
    ]

    run = models.ForeignKey(
        PredictionRun, on_delete=models.PROTECT, related_name='results',
    )
    target_type = models.CharField(max_length=15, choices=TARGET_TYPE_CHOICES, default='product')
    target_pk = models.PositiveIntegerField(null=True, blank=True)
    target_label = models.CharField(max_length=120, blank=True)
    period_date = models.DateField()
    predicted_value = models.DecimalField(
        max_digits=18, decimal_places=4, validators=[SIGNED],
    )
    lower_bound = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    upper_bound = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    confidence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[NON_NEG, PCT_MAX],
    )

    class Meta:
        ordering = ['run', 'period_date', 'target_pk']
        indexes = [
            models.Index(fields=['tenant', 'run', 'period_date']),
            models.Index(fields=['tenant', 'target_type', 'target_pk']),
        ]

    def __str__(self):
        return f'{self.run.run_number} @ {self.period_date}'


class TrendAnalysis(TenantAwareModel, TimeStampedModel):
    """Sliding-window trend on any numeric time series. Auto-numbered ``TA-00001``."""

    SOURCE_CHOICES = [
        ('kpi', 'KPI series'),
        ('spc_chart', 'SPC chart'),
        ('production', 'Production report'),
        ('cost', 'Cost variance'),
        ('energy', 'Utility consumption'),
        ('carbon', 'Carbon emission'),
    ]
    DIRECTION_CHOICES = [
        ('improving', 'Improving'),
        ('steady', 'Steady'),
        ('worsening', 'Worsening'),
    ]

    trend_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    source_metric = models.CharField(max_length=15, choices=SOURCE_CHOICES, default='kpi')
    target_label = models.CharField(max_length=120, blank=True)
    target_pk = models.PositiveIntegerField(null=True, blank=True)
    window_days = models.PositiveIntegerField(default=30)
    sample_size = models.PositiveIntegerField(default=0)
    slope = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal('0'), validators=[SIGNED],
    )
    intercept = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal('0'), validators=[SIGNED],
    )
    r_squared = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal('0'),
        validators=[NON_NEG, MaxValueValidator(Decimal('1'))],
    )
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='steady')
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-computed_at', '-id']
        unique_together = ('tenant', 'trend_number')
        indexes = [
            models.Index(fields=['tenant', 'source_metric', 'target_pk']),
        ]

    def __str__(self):
        return f'{self.trend_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.trend_number and self.tenant_id:
            self.trend_number = _next_number(TrendAnalysis, self.tenant_id, 'TA', 'trend_number')
        super().save(*args, **kwargs)


# ============================================================================
# 16.4  TENANT-ISOLATED DATA WAREHOUSE
# ============================================================================

class DataMart(TenantAwareModel, TimeStampedModel):
    """A materialized cross-module view scoped to a tenant. Auto-numbered ``DM-00001``.

    Row-level security: every ``DataMartRow`` is ``TenantAwareModel``, so
    queries auto-filter to ``request.tenant`` via the default manager.
    Industry-average rows (when implemented) follow the
    ``apps.utility.BenchmarkSnapshot`` ``tenant=NULL`` + custom
    ``for_tenant`` manager pattern (D-10 lesson).
    """

    FREQUENCY_CHOICES = [
        ('on_demand', 'On demand'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    mart_number = models.CharField(max_length=15)
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    source_definition = models.JSONField(default=dict, blank=True)
    refresh_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='daily')
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_row_count = models.PositiveIntegerField(default=0)
    row_level_security_field = models.CharField(
        max_length=60, blank=True,
        help_text='Optional secondary scope (e.g. cost_center, owner) for extra RLS.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = (
            ('tenant', 'mart_number'),
            ('tenant', 'code'),
        )

    def __str__(self):
        return f'{self.mart_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.mart_number and self.tenant_id:
            self.mart_number = _next_number(DataMart, self.tenant_id, 'DM', 'mart_number')
        super().save(*args, **kwargs)


class DataMartColumn(TenantAwareModel, TimeStampedModel):
    """Typed column metadata for a data mart."""

    DATA_TYPE_CHOICES = [
        ('text', 'Text'),
        ('int', 'Integer'),
        ('decimal', 'Decimal'),
        ('date', 'Date'),
        ('datetime', 'DateTime'),
        ('bool', 'Boolean'),
    ]

    data_mart = models.ForeignKey(
        DataMart, on_delete=models.CASCADE, related_name='columns',
    )
    code = models.SlugField(max_length=40)
    display_name = models.CharField(max_length=120)
    data_type = models.CharField(max_length=10, choices=DATA_TYPE_CHOICES, default='text')
    is_dimension = models.BooleanField(default=False)
    is_measure = models.BooleanField(default=False)
    aggregation_hint = models.CharField(max_length=20, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['data_mart', 'position', 'id']
        unique_together = ('tenant', 'data_mart', 'code')

    def __str__(self):
        return f'{self.data_mart.mart_number} / {self.code}'


class DataMartSnapshot(TenantAwareModel, TimeStampedModel):
    """One refresh event for a data mart.

    ``PROTECT`` on ``data_mart`` so a snapshot cannot be orphaned without
    also detaching every child row (Lesson L-17).
    """

    TRIGGERED_BY_CHOICES = [
        ('manual', 'Manual refresh'),
        ('schedule', 'Scheduled refresh'),
        ('signal', 'Signal-driven refresh'),
        ('seed', 'Seed fixture'),
    ]

    data_mart = models.ForeignKey(
        DataMart, on_delete=models.PROTECT, related_name='snapshots',
    )
    snapshot_at = models.DateTimeField(default=timezone.now)
    row_count = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    triggered_by = models.CharField(max_length=10, choices=TRIGGERED_BY_CHOICES, default='manual')
    triggered_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_mart_snapshots',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-snapshot_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'data_mart', 'snapshot_at']),
        ]

    def __str__(self):
        return f'{self.data_mart.mart_number} @ {self.snapshot_at:%Y-%m-%d %H:%M}'


class DataMartRow(TenantAwareModel, TimeStampedModel):
    """One materialized row in a data mart.

    Each row carries its column values in ``row_data`` JSON and a
    denormalized ``dimension_keys`` JSON for fast filtering. PROTECT on
    the ``snapshot`` FK so deleting an active snapshot blocks - call
    ``DataMart.refresh()`` instead, which is idempotent and cleans rows
    inside an atomic block.
    """

    data_mart = models.ForeignKey(
        DataMart, on_delete=models.CASCADE, related_name='rows',
    )
    snapshot = models.ForeignKey(
        DataMartSnapshot, on_delete=models.PROTECT, related_name='rows',
    )
    row_data = models.JSONField(default=dict, blank=True)
    dimension_keys = models.JSONField(default=dict, blank=True)
    measure_total = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal('0'), validators=[SIGNED],
        help_text='Optional pre-computed scalar (e.g. row sum) for sort/filter speed.',
    )

    class Meta:
        ordering = ['data_mart', '-snapshot', 'id']
        indexes = [
            models.Index(fields=['tenant', 'data_mart', 'snapshot']),
        ]

    def __str__(self):
        return f'{self.data_mart.mart_number} row #{self.id}'


# ============================================================================
# 16.5  AUTOMATED REPORT DISTRIBUTION
# ============================================================================

class ReportSchedule(TenantAwareModel, TimeStampedModel):
    """Cron-style schedule for a saved report or dashboard. Auto-numbered ``SCH-00001``.

    XOR validation: exactly one of ``report`` / ``dashboard`` must be set
    (enforced in the form layer).
    """

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom cron'),
    ]
    FORMAT_CHOICES = [
        ('csv', 'CSV file'),
        ('xlsx', 'Excel file'),
        ('pdf_html', 'PDF (HTML print)'),
        ('inline_email', 'Inline HTML email'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('disabled', 'Disabled'),
    ]

    schedule_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    report = models.ForeignKey(
        ReportDefinition, on_delete=models.PROTECT,
        null=True, blank=True, related_name='schedules',
    )
    dashboard = models.ForeignKey(
        KPIDashboard, on_delete=models.PROTECT,
        null=True, blank=True, related_name='schedules',
    )
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='daily')
    cron_expression = models.CharField(
        max_length=120, blank=True,
        help_text='5-field cron expression for frequency=custom. Empty for daily/weekly/monthly.',
    )
    timezone_name = models.CharField(max_length=50, default='UTC')
    next_run_at = models.DateTimeField(default=timezone.now)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True)
    format = models.CharField(max_length=15, choices=FORMAT_CHOICES, default='csv')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    disabled_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_report_schedules',
    )

    class Meta:
        ordering = ['next_run_at', '-id']
        unique_together = (
            ('tenant', 'schedule_number'),
            ('tenant', 'name'),
        )

    def __str__(self):
        return f'{self.schedule_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.schedule_number and self.tenant_id:
            self.schedule_number = _next_number(ReportSchedule, self.tenant_id, 'SCH', 'schedule_number')
        super().save(*args, **kwargs)

    def is_active_status(self):
        return self.status == 'active'

    def is_pausable(self):
        return self.status == 'active'

    def is_resumable(self):
        return self.status == 'paused'


class ReportRecipient(TenantAwareModel, TimeStampedModel):
    """Email recipient bound to a schedule.

    ``email`` is the canonical contact channel; ``user`` is an optional FK
    for resolving to an in-app user.
    """

    schedule = models.ForeignKey(
        ReportSchedule, on_delete=models.CASCADE, related_name='recipients',
    )
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_report_subscriptions',
    )
    notify_on_failure = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['schedule', 'email']
        unique_together = ('tenant', 'schedule', 'email')

    def __str__(self):
        return f'{self.schedule.schedule_number} -> {self.email}'


class ReportExport(TenantAwareModel, TimeStampedModel):
    """A rendered artifact (CSV / xlsx / HTML print).

    File upload uses an allowlist + 25 MB cap (Lesson L-22) enforced in
    the form layer (no untrusted user uploads here - generated server-side
    by ``services/scheduler.render_export``).
    """

    FORMAT_CHOICES = ReportSchedule.FORMAT_CHOICES
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('rendering', 'Rendering'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ]

    export_number = models.CharField(max_length=15)
    report = models.ForeignKey(
        ReportDefinition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='exports',
    )
    dashboard = models.ForeignKey(
        KPIDashboard, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='exports',
    )
    format = models.CharField(max_length=15, choices=FORMAT_CHOICES, default='csv')
    file = models.FileField(upload_to='bi/exports/', null=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    file_size_bytes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bi_report_exports',
    )
    error_message = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-generated_at', '-id']
        unique_together = ('tenant', 'export_number')

    def __str__(self):
        return self.export_number

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.export_number and self.tenant_id:
            self.export_number = _next_number(ReportExport, self.tenant_id, 'EXP', 'export_number')
        super().save(*args, **kwargs)


class ReportDelivery(TenantAwareModel, TimeStampedModel):
    """One delivery attempt of a ReportExport to a ReportRecipient. Auto-numbered ``DLV-00001``."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('bounced', 'Bounced'),
    ]

    delivery_number = models.CharField(max_length=15)
    schedule = models.ForeignKey(
        ReportSchedule, on_delete=models.PROTECT, related_name='deliveries',
    )
    recipient = models.ForeignKey(
        ReportRecipient, on_delete=models.PROTECT, related_name='deliveries',
    )
    export = models.ForeignKey(
        ReportExport, on_delete=models.PROTECT, related_name='deliveries',
        null=True, blank=True,
    )
    attempted_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    subject = models.CharField(max_length=255, blank=True)
    message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-attempted_at', '-id']
        unique_together = ('tenant', 'delivery_number')
        indexes = [
            models.Index(fields=['tenant', 'schedule', 'attempted_at']),
        ]

    def __str__(self):
        return self.delivery_number

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.delivery_number and self.tenant_id:
            self.delivery_number = _next_number(ReportDelivery, self.tenant_id, 'DLV', 'delivery_number')
        super().save(*args, **kwargs)
