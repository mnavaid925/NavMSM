"""Whitelist of report data sources and their queryable fields.

Every entry binds a data-source slug to a Django ``app_label.model_name`` plus
the set of fields the report builder is allowed to project, filter, and sort
on. The executor (``services/reports.execute_report``) rejects any request
that tries to access a field outside its source's allowlist - this is the
single line of defence against:

* SQL injection (we never accept raw column names from user input)
* cross-tenant leakage (we always apply ``tenant=request.tenant`` on top)
* mass-disclosure (a tenant catalog cannot opt-in to fields like
  ``password_hash`` because the static whitelist is the upper bound)

To add a new data source, append one tuple here and one row in the
``ReportDataSource`` seeder.
"""
from collections import OrderedDict


# ``{source_code: {"model_label": "app.Model", "allowed_fields": [...],
#                  "name": "Production Orders", "description": "..."}}``
REGISTERED_SOURCES = OrderedDict([
    ('production_orders', {
        'name': 'Production Orders',
        'description': 'Released / in-progress / completed orders from PPS.',
        'model_label': 'pps.ProductionOrder',
        'allowed_fields': [
            'id', 'order_number', 'product__sku', 'product__name',
            'status', 'priority', 'requested_qty', 'completed_qty',
            'scheduling_method', 'requested_start', 'requested_end',
            'actual_start', 'actual_end', 'created_at',
        ],
    }),
    ('production_reports', {
        'name': 'Production Reports (MES)',
        'description': 'Append-only production reports from MES.',
        'model_label': 'mes.ProductionReport',
        'allowed_fields': [
            'id', 'reported_at', 'good_qty', 'scrap_qty', 'rework_qty',
            'scrap_reason',
            'work_order_operation__work_order__work_order_number',
            'work_order_operation__work_order__production_order__product__sku',
            'reported_by__username',
        ],
    }),
    ('non_conformance_reports', {
        'name': 'Non-Conformance Reports (QMS)',
        'description': 'NCR lifecycle data from QMS.',
        'model_label': 'qms.NonConformanceReport',
        'allowed_fields': [
            'id', 'ncr_number', 'source', 'severity', 'status',
            'product__sku', 'detected_at', 'closed_at',
        ],
    }),
    ('supplier_invoices', {
        'name': 'Supplier Invoices',
        'description': 'Procurement supplier invoice ledger.',
        'model_label': 'procurement.SupplierInvoice',
        'allowed_fields': [
            'id', 'invoice_number', 'supplier__code', 'supplier__name',
            'status', 'total_amount', 'currency',
            'invoice_date', 'due_date', 'paid_at',
        ],
    }),
    ('supplier_metric_events', {
        'name': 'Supplier Performance Events',
        'description': 'OTD + quality pass/fail events feeding scorecards.',
        'model_label': 'procurement.SupplierMetricEvent',
        'allowed_fields': [
            'id', 'supplier__code', 'event_type', 'value', 'posted_at',
        ],
    }),
    ('utility_consumption', {
        'name': 'Utility Consumption',
        'description': 'Append-only meter consumption ledger from Module 14.',
        'model_label': 'utility.UtilityConsumption',
        'allowed_fields': [
            'id', 'consumption_number', 'meter__meter_number',
            'meter__utility_type__code', 'period_start', 'period_end',
            'consumption', 'unit_cost', 'total_cost', 'currency',
        ],
    }),
    ('carbon_emissions', {
        'name': 'Carbon Emissions',
        'description': 'Auto-cascaded carbon ledger from utility consumption.',
        'model_label': 'utility.CarbonEmission',
        'allowed_fields': [
            'id', 'emission_number', 'source_type', 'scope',
            'period__period_number', 'co2e_kg', 'occurred_at',
        ],
    }),
    ('failure_predictions', {
        'name': 'Failure Predictions',
        'description': 'EAM failure-prediction ledger.',
        'model_label': 'eam.FailurePrediction',
        'allowed_fields': [
            'id', 'asset__asset_number', 'asset__name',
            'predicted_failure_date', 'confidence_pct', 'status',
            'detected_at', 'resolved_at',
        ],
    }),
    ('oee_periods', {
        'name': 'OEE Periods',
        'description': 'Computed OEE rollups per asset per shift per day.',
        'model_label': 'iot.OEEPeriod',
        'allowed_fields': [
            'id', 'period_number', 'asset__asset_number', 'period_date',
            'shift', 'availability_pct', 'performance_pct',
            'quality_pct', 'oee_pct',
        ],
    }),
    ('stock_movements', {
        'name': 'Stock Movements',
        'description': 'Append-only inventory movement ledger.',
        'model_label': 'inventory.StockMovement',
        'allowed_fields': [
            'id', 'movement_type', 'qty', 'posted_at',
            'product__sku', 'product__name',
            'bin__code', 'bin__zone__warehouse__code',
        ],
    }),
    ('gross_margin_reports', {
        'name': 'Gross Margin Reports',
        'description': 'Per-product per-period margin computed by Cost module.',
        'model_label': 'cost.GrossMarginReport',
        'allowed_fields': [
            'id', 'period__period_number', 'product__sku', 'product__name',
            'revenue', 'cogs', 'gross_margin', 'margin_percent',
        ],
    }),
    ('cogm_reports', {
        'name': 'COGM Reports',
        'description': 'Cost of Goods Manufactured (period rollup).',
        'model_label': 'cost.COGMReport',
        'allowed_fields': [
            'id', 'report_number', 'period__period_number',
            'opening_wip', 'direct_materials', 'direct_labor',
            'overhead_applied', 'closing_wip', 'cogm',
        ],
    }),
])


def get_source(code):
    """Return the registry entry for a source code, or None."""
    return REGISTERED_SOURCES.get(code)


def assert_field_allowed(source_code, field_name):
    """Raise ValueError if the field is not whitelisted for the source.

    Use at the entry to ``services/reports.execute_report``.
    """
    src = REGISTERED_SOURCES.get(source_code)
    if src is None:
        raise ValueError(f'Unknown data source: {source_code!r}')
    if field_name not in src['allowed_fields']:
        raise ValueError(
            f'Field {field_name!r} is not allowed on data source {source_code!r}.'
        )


def list_sources():
    """Return [(code, name, model_label), ...] for UI dropdowns."""
    return [(code, info['name'], info['model_label']) for code, info in REGISTERED_SOURCES.items()]
