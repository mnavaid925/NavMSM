"""Seed Module 16 demo data per tenant.

Idempotent. Skips a tenant if BI seed data is already present.
Use ``--flush`` to wipe + re-seed.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.bi import models
from apps.bi.services import kpi as kpi_svc
from apps.bi.services import datamart as datamart_svc
from apps.bi.services import predictions as predictions_svc
from apps.bi.services.registry import REGISTERED_SOURCES
from apps.core.models import Tenant


class Command(BaseCommand):
    help = 'Seed Module 16 (Business Intelligence) demo data per tenant. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe BI data first.')
        parser.add_argument('--tenant', help='Limit to a single tenant slug.')

    def handle(self, *args, **options):
        flush = options.get('flush')
        slug = options.get('tenant')

        tenants = Tenant.objects.filter(is_active=True)
        if slug:
            tenants = tenants.filter(slug=slug)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants matched. Skipping.'))
            return

        if flush:
            self.stdout.write('Flushing BI data...')
            for cls in (
                models.ReportDelivery, models.ReportExport, models.ReportRecipient,
                models.ReportSchedule, models.DataMartRow, models.DataMartSnapshot,
                models.DataMartColumn, models.DataMart, models.PredictionResult,
                models.PredictionRun, models.PredictiveModel, models.TrendAnalysis,
                models.ReportRun, models.ReportField, models.ReportFilter,
                models.ReportDefinition, models.ReportDataSource, models.KPISnapshot,
                models.KPIWidget, models.KPIDashboard, models.KPIDefinition,
            ):
                if slug:
                    cls.all_objects.filter(tenant__slug=slug).delete()
                else:
                    cls.all_objects.all().delete()

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write(self.style.SUCCESS('BI seeding complete.'))
        self.stdout.write('Log in as a tenant admin (e.g. admin_acme / Welcome@123) to view.')
        self.stdout.write(self.style.WARNING(
            'Superuser "admin" has tenant=None so BI screens will appear empty when signed in as it.'
        ))

    def _seed_tenant(self, tenant):
        if models.KPIDefinition.all_objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  {tenant.slug}: BI data already exists. Skipping (use --flush to re-seed).')
            return

        self.stdout.write(self.style.SUCCESS(f'Seeding BI for tenant: {tenant.slug}'))

        # ---- KPI Definitions ----
        kpi_defs = [
            ('oee', 'Overall Equipment Effectiveness', '%', 'higher_is_better', '85', '70', '60'),
            ('throughput', 'Daily Throughput (good units)', 'units', 'higher_is_better', '500', '300', '150'),
            ('yield', 'First-Pass Yield', '%', 'higher_is_better', '95', '90', '80'),
            ('scrap_rate', 'Scrap Rate', '%', 'lower_is_better', '2', '5', '10'),
            ('on_time_delivery', 'On-Time Delivery', '%', 'higher_is_better', '95', '85', '75'),
            ('supplier_otd', 'Supplier On-Time Delivery', '%', 'higher_is_better', '90', '80', '70'),
            ('gross_margin', 'Gross Margin', '%', 'higher_is_better', '30', '20', '10'),
            ('energy_intensity', 'Energy Intensity', 'kWh/unit', 'lower_is_better', '1.5', '2.0', '3.0'),
            ('carbon_intensity', 'Carbon Intensity', 'kgCO2e/unit', 'lower_is_better', '0.5', '0.8', '1.2'),
        ]
        defs = {}
        for code, name, unit, direction, target, warn, crit in kpi_defs:
            d, _ = models.KPIDefinition.all_objects.get_or_create(
                tenant=tenant, code=code,
                defaults=dict(
                    name=name, unit=unit, direction=direction,
                    target_value=Decimal(target),
                    warning_threshold=Decimal(warn),
                    critical_threshold=Decimal(crit),
                ),
            )
            defs[code] = d
        self.stdout.write(f'  - {len(defs)} KPI definitions')

        # ---- KPI Dashboards + Widgets ----
        dashboard = models.KPIDashboard.all_objects.create(
            tenant=tenant, name='Plant Operations',
            slug=f'plant-operations-{tenant.slug}',
            description='Daily operations summary across OEE, throughput, yield, OTD.',
            is_shared=True, default_period='last_30d', auto_refresh_minutes=15,
        )
        widget_specs = [
            ('oee', 'kpi_card', 0),
            ('throughput', 'kpi_card', 1),
            ('yield', 'kpi_card', 2),
            ('scrap_rate', 'kpi_card', 3),
            ('on_time_delivery', 'gauge', 4),
            ('gross_margin', 'kpi_card', 5),
        ]
        for code, chart_type, pos in widget_specs:
            if code in defs:
                models.KPIWidget.all_objects.create(
                    tenant=tenant, dashboard=dashboard, kpi_definition=defs[code],
                    position=pos, chart_type=chart_type, compare_to_previous=True,
                )
        self.stdout.write(f'  - 1 dashboard with {len(widget_specs)} widgets')

        # ---- KPI Snapshots (last 30 days, tenant scope) ----
        today = date.today()
        snap_count = 0
        for d in defs.values():
            try:
                kpi_svc.refresh_snapshot(
                    d, today - timedelta(days=30), today,
                    scope_type='tenant', scope_pk=None, scope_label='All tenant',
                )
                snap_count += 1
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'    KPI {d.code} skipped: {exc}'))
        self.stdout.write(f'  - {snap_count} KPI snapshots')

        # ---- Report Data Sources ----
        ds_codes = ['production_orders', 'production_reports', 'non_conformance_reports',
                    'oee_periods', 'supplier_invoices', 'utility_consumption']
        for code in ds_codes:
            info = REGISTERED_SOURCES[code]
            models.ReportDataSource.all_objects.get_or_create(
                tenant=tenant, code=code,
                defaults=dict(
                    name=info['name'], description=info['description'],
                    model_label=info['model_label'],
                    allowed_fields=info['allowed_fields'],
                    is_active=True,
                ),
            )
        self.stdout.write(f'  - {len(ds_codes)} report data sources')

        # ---- Report Definition + fields + filters + run ----
        ds = models.ReportDataSource.all_objects.get(tenant=tenant, code='production_reports')
        report = models.ReportDefinition.all_objects.create(
            tenant=tenant, data_source=ds, name='Daily Production Summary',
            description='Good vs scrap per product per day.',
            group_by_field='work_order_operation__work_order__production_order__product__sku',
            sort_field='work_order_operation__work_order__production_order__product__sku',
            sort_direction='asc', row_limit=200, is_shared=True,
        )
        for i, (field_name, display, agg) in enumerate([
            ('work_order_operation__work_order__production_order__product__sku', 'Product', 'none'),
            ('good_qty', 'Good Qty', 'sum'),
            ('scrap_qty', 'Scrap Qty', 'sum'),
            ('rework_qty', 'Rework Qty', 'sum'),
        ]):
            models.ReportField.all_objects.create(
                tenant=tenant, report=report,
                field_name=field_name, display_name=display,
                aggregation=agg, position=i,
            )
        try:
            from apps.bi.services import reports as reports_svc
            run, rows, csv_text = reports_svc.run_and_persist(report, tenant)
            self.stdout.write(f'  - 1 report (RPT-) + 1 run ({run.row_count} rows)')
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'    Report run skipped: {exc}'))

        # ---- Predictive Models + 1 run ----
        pm = models.PredictiveModel.all_objects.create(
            tenant=tenant, code='demand_forecast', name='30-day demand forecast',
            description='Linear regression on MES good_qty per product.',
            lookback_days=60, forecast_horizon_days=14, is_active=True,
        )
        try:
            run = models.PredictionRun.all_objects.create(
                tenant=tenant, predictive_model=pm,
                started_at=timezone.now(), status='running',
            )
            count, rows = predictions_svc.run_prediction(pm)
            for row in rows:
                models.PredictionResult.all_objects.create(tenant=tenant, run=run, **row)
            run.result_count = count
            run.status = 'completed'
            run.finished_at = timezone.now()
            run.save(update_fields=['result_count', 'status', 'finished_at'])
            self.stdout.write(f'  - 1 predictive model + 1 run ({count} results)')
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'    Prediction run skipped: {exc}'))

        # Also seed a failure-likelihood model (often returns 0 rows in seed data,
        # but the model row is useful for the UI).
        models.PredictiveModel.all_objects.create(
            tenant=tenant, code='failure_likelihood', name='Asset failure likelihood',
            description='Rolling failure rate per asset.',
            lookback_days=90, forecast_horizon_days=30, is_active=True,
        )

        # ---- Data Mart ----
        mart = models.DataMart.all_objects.create(
            tenant=tenant, code='production_daily', name='Production Daily',
            description='Per-product daily production aggregates (last 30 days).',
            source_definition={
                'model_label': 'mes.ProductionReport',
                'group_by': ['work_order_operation__work_order__production_order__product__sku'],
                'measures': {
                    'good_qty_sum': {'field': 'good_qty', 'agg': 'sum'},
                    'scrap_qty_sum': {'field': 'scrap_qty', 'agg': 'sum'},
                    'rework_qty_sum': {'field': 'rework_qty', 'agg': 'sum'},
                    'report_count': {'field': 'id', 'agg': 'count'},
                },
                'date_field': 'reported_at',
                'lookback_days': 30,
            },
            refresh_frequency='daily', is_active=True,
        )
        for i, (code, display, dtype, is_dim, is_meas) in enumerate([
            ('product_sku', 'Product SKU', 'text', True, False),
            ('good_qty_sum', 'Good Qty', 'decimal', False, True),
            ('scrap_qty_sum', 'Scrap Qty', 'decimal', False, True),
            ('rework_qty_sum', 'Rework Qty', 'decimal', False, True),
            ('report_count', 'Reports', 'int', False, True),
        ]):
            models.DataMartColumn.all_objects.create(
                tenant=tenant, data_mart=mart, code=code,
                display_name=display, data_type=dtype,
                is_dimension=is_dim, is_measure=is_meas, position=i,
            )
        try:
            datamart_svc.refresh_mart(mart, triggered_by='seed')
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'    DataMart refresh skipped: {exc}'))
        self.stdout.write(f'  - 1 data mart ({mart.last_row_count} rows materialized)')

        # ---- Report Schedule + Recipient + 1 manual delivery placeholder ----
        schedule = models.ReportSchedule.all_objects.create(
            tenant=tenant, name='Weekly production summary',
            description='Email every Monday 08:00 to ops team.',
            report=report, frequency='weekly',
            next_run_at=timezone.now() + timedelta(days=1),
            format='csv', status='active',
        )
        models.ReportRecipient.all_objects.create(
            tenant=tenant, schedule=schedule,
            email=f'ops@{tenant.slug}.example.com', name='Ops Team',
            is_active=True, notify_on_failure=True,
        )
        self.stdout.write(f'  - 1 schedule + 1 recipient (next run: {schedule.next_run_at:%Y-%m-%d %H:%M})')

        self.stdout.write(self.style.SUCCESS(f'  Done seeding {tenant.slug}.'))
