"""Module 16 - Business Intelligence views.

Class-based views mirroring apps/iot/views.py + apps/utility/views.py.

RBAC (L-10):
    * Read surfaces: TenantRequiredMixin
    * Write/workflow surfaces: TenantAdminRequiredMixin
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    datamart as datamart_svc,
    kpi as kpi_svc,
    predictions as predictions_svc,
    reports as reports_svc,
    scheduler as scheduler_svc,
)


PAGE_SIZE = 25


def _paginate(qs, request, size=PAGE_SIZE):
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _period_range(period_code, today=None):
    """Map a default_period code to (start, end) inclusive dates."""
    today = today or date.today()
    if period_code == 'last_7d':
        return today - timedelta(days=7), today
    if period_code == 'last_30d':
        return today - timedelta(days=30), today
    if period_code == 'mtd':
        return today.replace(day=1), today
    if period_code == 'qtd':
        q = (today.month - 1) // 3
        return today.replace(month=q * 3 + 1, day=1), today
    if period_code == 'ytd':
        return today.replace(month=1, day=1), today
    return today - timedelta(days=30), today


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'bi/index.html'

    def get(self, request):
        tenant = request.tenant
        if tenant is None:
            return render(request, self.template_name, {
                'kpi': {}, 'recent_snapshots': [], 'recent_runs': [],
                'oee_trend': [],
            })
        today = date.today()
        thirty = today - timedelta(days=30)

        kpi = {
            'definition_count': models.KPIDefinition.objects.filter(tenant=tenant, is_active=True).count(),
            'dashboard_count': models.KPIDashboard.objects.filter(tenant=tenant).count(),
            'report_count': models.ReportDefinition.objects.filter(tenant=tenant).count(),
            'active_schedules': models.ReportSchedule.objects.filter(tenant=tenant, status='active').count(),
            'recent_runs_30d': models.ReportRun.objects.filter(
                tenant=tenant, run_at__date__gte=thirty,
            ).count(),
            'active_marts': models.DataMart.objects.filter(tenant=tenant, is_active=True).count(),
        }
        recent_snapshots = list(
            models.KPISnapshot.objects.filter(tenant=tenant)
            .select_related('kpi_definition')
            .order_by('-computed_at')[:8]
        )
        recent_runs = list(
            models.ReportRun.objects.filter(tenant=tenant)
            .select_related('report')
            .order_by('-run_at')[:8]
        )
        oee_snapshots = list(
            models.KPISnapshot.objects.filter(
                tenant=tenant,
                kpi_definition__code='oee',
                period_end__gte=thirty,
                scope_type='tenant',
            ).order_by('period_end')
        )
        oee_trend = [
            {'day': s.period_end.strftime('%m-%d'), 'value': float(s.value)}
            for s in oee_snapshots
        ]
        recent_predictions = list(
            models.PredictionRun.objects.filter(tenant=tenant)
            .select_related('predictive_model')
            .order_by('-started_at')[:5]
        )
        return render(request, self.template_name, {
            'kpi': kpi,
            'recent_snapshots': recent_snapshots,
            'recent_runs': recent_runs,
            'recent_predictions': recent_predictions,
            'oee_trend': oee_trend,
        })


# ============================================================================
# Generic list / delete helpers
# ============================================================================

class _TenantListBase(TenantRequiredMixin, View):
    model = None
    template_name = ''
    context_qs_name = 'object_list'
    select_related: tuple = ()
    search_fields: tuple = ()

    def filter_qs(self, qs, request):
        return qs

    def extra_context(self, request):
        return {}

    def get(self, request):
        qs = self.model.objects.filter(tenant=request.tenant)
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        q = (request.GET.get('q') or '').strip()
        if q and self.search_fields:
            ors = Q()
            for f in self.search_fields:
                ors |= Q(**{f'{f}__icontains': q})
            qs = qs.filter(ors)
        qs = self.filter_qs(qs, request)
        page = _paginate(qs, request)
        ctx = {self.context_qs_name: page, 'page_obj': page, 'page': page, 'q': q}
        ctx.update(self.extra_context(request))
        return render(request, self.template_name, ctx)


class _TenantDeleteBase(TenantAdminRequiredMixin, View):
    model = None
    redirect_url_name = ''
    success_message = 'Deleted successfully.'

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, self.success_message)
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Could not delete: {exc}')
        return redirect(self.redirect_url_name)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 16.1  KPI Definitions
# ============================================================================

class KPIDefinitionListView(_TenantListBase):
    model = models.KPIDefinition
    template_name = 'bi/kpi/definitions_list.html'
    context_qs_name = 'definitions'
    search_fields = ('code', 'name')

    def filter_qs(self, qs, request):
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('code')


class KPIDefinitionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        definition = get_object_or_404(models.KPIDefinition, pk=pk, tenant=request.tenant)
        recent_snaps = (
            models.KPISnapshot.objects.filter(tenant=request.tenant, kpi_definition=definition)
            .order_by('-period_end')[:30]
        )
        return render(request, 'bi/kpi/definition_detail.html', {
            'definition': definition,
            'recent_snaps': recent_snaps,
        })


class KPIDefinitionCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.KPIDefinitionForm(tenant=request.tenant)
        return render(request, 'bi/kpi/definition_form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.KPIDefinitionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'KPI "{obj.code}" created.')
            return redirect('bi:kpi_definition_detail', pk=obj.pk)
        return render(request, 'bi/kpi/definition_form.html', {'form': form, 'mode': 'create'})


class KPIDefinitionEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.KPIDefinition, pk=pk, tenant=request.tenant)
        form = forms.KPIDefinitionForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/kpi/definition_form.html', {
            'form': form, 'mode': 'edit', 'definition': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.KPIDefinition, pk=pk, tenant=request.tenant)
        form = forms.KPIDefinitionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'KPI "{obj.code}" updated.')
            return redirect('bi:kpi_definition_detail', pk=obj.pk)
        return render(request, 'bi/kpi/definition_form.html', {
            'form': form, 'mode': 'edit', 'definition': obj,
        })


class KPIDefinitionDeleteView(_TenantDeleteBase):
    model = models.KPIDefinition
    redirect_url_name = 'bi:kpi_definition_list'
    success_message = 'KPI definition deleted.'


class KPIDefinitionRefreshView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        definition = get_object_or_404(models.KPIDefinition, pk=pk, tenant=request.tenant)
        today = date.today()
        start, end = today - timedelta(days=30), today
        try:
            snap = kpi_svc.refresh_snapshot(definition, start, end)
            messages.success(request, f'KPI {definition.code} refreshed: {snap.value}')
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Refresh failed: {exc}')
        return redirect('bi:kpi_definition_detail', pk=pk)


# ============================================================================
# 16.1  KPI Dashboards
# ============================================================================

class KPIDashboardListView(_TenantListBase):
    model = models.KPIDashboard
    template_name = 'bi/dashboards/list.html'
    context_qs_name = 'dashboards'
    search_fields = ('name', 'slug')

    def filter_qs(self, qs, request):
        shared = request.GET.get('shared', '')
        if shared == 'shared':
            qs = qs.filter(is_shared=True)
        elif shared == 'private':
            qs = qs.filter(is_shared=False)
        return qs.order_by('name')


class KPIDashboardDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        dashboard = get_object_or_404(models.KPIDashboard, pk=pk, tenant=request.tenant)
        widgets = (
            models.KPIWidget.objects.filter(tenant=request.tenant, dashboard=dashboard)
            .select_related('kpi_definition').order_by('position', 'id')
        )
        # Build a value lookup for each widget from the latest snapshot.
        start, end = _period_range(dashboard.default_period)
        widget_values = []
        for w in widgets:
            snap = (
                models.KPISnapshot.objects.filter(
                    tenant=request.tenant,
                    kpi_definition=w.kpi_definition,
                    period_start__lte=end,
                    period_end__gte=start,
                    scope_type='tenant',
                ).order_by('-period_end').first()
            )
            widget_values.append({'widget': w, 'snapshot': snap})
        return render(request, 'bi/dashboards/detail.html', {
            'dashboard': dashboard, 'widget_values': widget_values,
            'period_start': start, 'period_end': end,
        })


class KPIDashboardCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.KPIDashboardForm(tenant=request.tenant)
        return render(request, 'bi/dashboards/form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.KPIDashboardForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            if not obj.owner_id:
                obj.owner = request.user
            obj.save()
            messages.success(request, f'Dashboard "{obj.name}" created.')
            return redirect('bi:dashboard_detail', pk=obj.pk)
        return render(request, 'bi/dashboards/form.html', {'form': form, 'mode': 'create'})


class KPIDashboardEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.KPIDashboard, pk=pk, tenant=request.tenant)
        form = forms.KPIDashboardForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/dashboards/form.html', {'form': form, 'mode': 'edit', 'dashboard': obj})

    def post(self, request, pk):
        obj = get_object_or_404(models.KPIDashboard, pk=pk, tenant=request.tenant)
        form = forms.KPIDashboardForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dashboard updated.')
            return redirect('bi:dashboard_detail', pk=obj.pk)
        return render(request, 'bi/dashboards/form.html', {'form': form, 'mode': 'edit', 'dashboard': obj})


class KPIDashboardDeleteView(_TenantDeleteBase):
    model = models.KPIDashboard
    redirect_url_name = 'bi:dashboard_list'
    success_message = 'Dashboard deleted.'


class KPIDashboardRefreshView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        dashboard = get_object_or_404(models.KPIDashboard, pk=pk, tenant=request.tenant)
        start, end = _period_range(dashboard.default_period)
        count = 0
        for w in dashboard.widgets.all():
            try:
                kpi_svc.refresh_snapshot(w.kpi_definition, start, end)
                count += 1
            except Exception as exc:  # noqa: BLE001
                messages.warning(request, f'KPI {w.kpi_definition.code} refresh skipped: {exc}')
        messages.success(request, f'Refreshed {count} widget(s).')
        return redirect('bi:dashboard_detail', pk=pk)


# ============================================================================
# 16.1  Widgets
# ============================================================================

class KPIWidgetCreateView(TenantAdminRequiredMixin, View):
    def get(self, request, dashboard_pk):
        dashboard = get_object_or_404(models.KPIDashboard, pk=dashboard_pk, tenant=request.tenant)
        form = forms.KPIWidgetForm(tenant=request.tenant, initial={'dashboard': dashboard})
        return render(request, 'bi/widgets/form.html', {
            'form': form, 'mode': 'create', 'dashboard': dashboard,
        })

    def post(self, request, dashboard_pk):
        dashboard = get_object_or_404(models.KPIDashboard, pk=dashboard_pk, tenant=request.tenant)
        post = request.POST.copy()
        post['dashboard'] = dashboard.pk
        form = forms.KPIWidgetForm(post, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.dashboard = dashboard
            obj.save()
            messages.success(request, 'Widget added.')
            return redirect('bi:dashboard_detail', pk=dashboard.pk)
        return render(request, 'bi/widgets/form.html', {
            'form': form, 'mode': 'create', 'dashboard': dashboard,
        })


class KPIWidgetEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        widget = get_object_or_404(models.KPIWidget, pk=pk, tenant=request.tenant)
        form = forms.KPIWidgetForm(instance=widget, tenant=request.tenant)
        return render(request, 'bi/widgets/form.html', {
            'form': form, 'mode': 'edit', 'widget': widget, 'dashboard': widget.dashboard,
        })

    def post(self, request, pk):
        widget = get_object_or_404(models.KPIWidget, pk=pk, tenant=request.tenant)
        form = forms.KPIWidgetForm(request.POST, instance=widget, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Widget updated.')
            return redirect('bi:dashboard_detail', pk=widget.dashboard_id)
        return render(request, 'bi/widgets/form.html', {
            'form': form, 'mode': 'edit', 'widget': widget, 'dashboard': widget.dashboard,
        })


class KPIWidgetDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        widget = get_object_or_404(models.KPIWidget, pk=pk, tenant=request.tenant)
        dashboard_id = widget.dashboard_id
        widget.delete()
        messages.success(request, 'Widget removed.')
        return redirect('bi:dashboard_detail', pk=dashboard_id)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 16.1  Snapshots (read-only ledger)
# ============================================================================

class KPISnapshotListView(_TenantListBase):
    model = models.KPISnapshot
    template_name = 'bi/kpi/snapshots_list.html'
    context_qs_name = 'snapshots'
    select_related = ('kpi_definition',)

    def filter_qs(self, qs, request):
        code = request.GET.get('code', '')
        status = request.GET.get('status', '')
        scope = request.GET.get('scope_type', '')
        if code:
            qs = qs.filter(kpi_definition__code=code)
        if status:
            qs = qs.filter(status=status)
        if scope:
            qs = qs.filter(scope_type=scope)
        return qs.order_by('-period_end')

    def extra_context(self, request):
        return {
            'kpi_codes': models.KPIDefinition.CODE_CHOICES,
            'status_choices': models.KPISnapshot.STATUS_CHOICES,
            'scope_choices': models.KPISnapshot.SCOPE_CHOICES,
        }


# ============================================================================
# 16.2  Report data sources
# ============================================================================

class ReportDataSourceListView(_TenantListBase):
    model = models.ReportDataSource
    template_name = 'bi/reports/data_source_list.html'
    context_qs_name = 'data_sources'
    search_fields = ('code', 'name', 'model_label')

    def filter_qs(self, qs, request):
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('code')


class ReportDataSourceCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.ReportDataSourceForm(tenant=request.tenant)
        return render(request, 'bi/reports/data_source_form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.ReportDataSourceForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Data source "{obj.code}" created.')
            return redirect('bi:data_source_list')
        return render(request, 'bi/reports/data_source_form.html', {'form': form, 'mode': 'create'})


class ReportDataSourceEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.ReportDataSource, pk=pk, tenant=request.tenant)
        form = forms.ReportDataSourceForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/reports/data_source_form.html', {
            'form': form, 'mode': 'edit', 'data_source': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ReportDataSource, pk=pk, tenant=request.tenant)
        form = forms.ReportDataSourceForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Data source updated.')
            return redirect('bi:data_source_list')
        return render(request, 'bi/reports/data_source_form.html', {
            'form': form, 'mode': 'edit', 'data_source': obj,
        })


class ReportDataSourceDeleteView(_TenantDeleteBase):
    model = models.ReportDataSource
    redirect_url_name = 'bi:data_source_list'
    success_message = 'Data source deleted.'


# ============================================================================
# 16.2  Report definitions
# ============================================================================

class ReportDefinitionListView(_TenantListBase):
    model = models.ReportDefinition
    template_name = 'bi/reports/definitions_list.html'
    context_qs_name = 'reports'
    select_related = ('data_source',)
    search_fields = ('report_number', 'name')

    def filter_qs(self, qs, request):
        ds = request.GET.get('data_source', '')
        if ds:
            qs = qs.filter(data_source_id=ds)
        return qs.order_by('-id')

    def extra_context(self, request):
        return {
            'data_sources': models.ReportDataSource.objects.filter(tenant=request.tenant, is_active=True),
        }


class ReportDefinitionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(
            models.ReportDefinition.objects.select_related('data_source'),
            pk=pk, tenant=request.tenant,
        )
        fields = report.fields.order_by('position', 'id')
        filters = report.filters.order_by('position', 'id')
        recent_runs = report.runs.order_by('-run_at')[:10]
        return render(request, 'bi/reports/definition_detail.html', {
            'report': report, 'fields': fields, 'filters': filters,
            'recent_runs': recent_runs,
        })


class ReportDefinitionCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.ReportDefinitionForm(tenant=request.tenant)
        return render(request, 'bi/reports/definition_form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.ReportDefinitionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'Report "{obj.report_number}" created. Add fields and filters next.')
            return redirect('bi:report_detail', pk=obj.pk)
        return render(request, 'bi/reports/definition_form.html', {'form': form, 'mode': 'create'})


class ReportDefinitionEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.ReportDefinition, pk=pk, tenant=request.tenant)
        form = forms.ReportDefinitionForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/reports/definition_form.html', {
            'form': form, 'mode': 'edit', 'report': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ReportDefinition, pk=pk, tenant=request.tenant)
        form = forms.ReportDefinitionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Report updated.')
            return redirect('bi:report_detail', pk=obj.pk)
        return render(request, 'bi/reports/definition_form.html', {
            'form': form, 'mode': 'edit', 'report': obj,
        })


class ReportDefinitionDeleteView(_TenantDeleteBase):
    model = models.ReportDefinition
    redirect_url_name = 'bi:report_list'
    success_message = 'Report deleted.'


class ReportRunNowView(TenantRequiredMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(models.ReportDefinition, pk=pk, tenant=request.tenant)
        try:
            run, rows, csv_text = reports_svc.run_and_persist(
                report, request.tenant, user=request.user,
            )
            messages.success(
                request,
                f'Report executed: {run.row_count} row(s), {run.duration_ms} ms.',
            )
            if request.GET.get('format') == 'csv' or request.POST.get('format') == 'csv':
                resp = HttpResponse(csv_text, content_type='text/csv')
                resp['Content-Disposition'] = (
                    f'attachment; filename="{report.report_number}_{timezone.now():%Y%m%d_%H%M%S}.csv"'
                )
                return resp
            return redirect('bi:report_run_detail', pk=run.pk)
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Run failed: {exc}')
            return redirect('bi:report_detail', pk=pk)


# ============================================================================
# 16.2  Report fields / filters (inline on detail)
# ============================================================================

class ReportFieldCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, report_pk):
        report = get_object_or_404(models.ReportDefinition, pk=report_pk, tenant=request.tenant)
        post = request.POST.copy()
        post['report'] = report.pk
        form = forms.ReportFieldForm(post, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.report = report
            obj.save()
            messages.success(request, 'Field added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('bi:report_detail', pk=report.pk)

    def get(self, request, report_pk):
        return redirect('bi:report_detail', pk=report_pk)


class ReportFieldDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(models.ReportField, pk=pk, tenant=request.tenant)
        report_pk = f.report_id
        f.delete()
        messages.success(request, 'Field removed.')
        return redirect('bi:report_detail', pk=report_pk)

    def get(self, request, pk):
        return self.post(request, pk)


class ReportFilterCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, report_pk):
        report = get_object_or_404(models.ReportDefinition, pk=report_pk, tenant=request.tenant)
        post = request.POST.copy()
        post['report'] = report.pk
        form = forms.ReportFilterForm(post, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.report = report
            obj.save()
            messages.success(request, 'Filter added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('bi:report_detail', pk=report.pk)

    def get(self, request, report_pk):
        return redirect('bi:report_detail', pk=report_pk)


class ReportFilterDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(models.ReportFilter, pk=pk, tenant=request.tenant)
        report_pk = f.report_id
        f.delete()
        messages.success(request, 'Filter removed.')
        return redirect('bi:report_detail', pk=report_pk)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 16.2  Report runs
# ============================================================================

class ReportRunListView(_TenantListBase):
    model = models.ReportRun
    template_name = 'bi/reports/run_list.html'
    context_qs_name = 'runs'
    select_related = ('report',)

    def filter_qs(self, qs, request):
        report_id = request.GET.get('report', '')
        status = request.GET.get('status', '')
        if report_id:
            qs = qs.filter(report_id=report_id)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-run_at')

    def extra_context(self, request):
        return {
            'status_choices': models.ReportRun.STATUS_CHOICES,
            'reports': models.ReportDefinition.objects.filter(tenant=request.tenant),
        }


class ReportRunDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(
            models.ReportRun.objects.select_related('report', 'run_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'bi/reports/run_detail.html', {'run': run})


# ============================================================================
# 16.3  Predictive models
# ============================================================================

class PredictiveModelListView(_TenantListBase):
    model = models.PredictiveModel
    template_name = 'bi/predictive/models_list.html'
    context_qs_name = 'predictive_models'
    search_fields = ('code', 'name')

    def filter_qs(self, qs, request):
        code = request.GET.get('code', '')
        active = request.GET.get('active', '')
        if code:
            qs = qs.filter(code=code)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('code', 'name')

    def extra_context(self, request):
        return {'code_choices': models.PredictiveModel.CODE_CHOICES}


class PredictiveModelDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        pm = get_object_or_404(models.PredictiveModel, pk=pk, tenant=request.tenant)
        recent_runs = pm.runs.order_by('-started_at')[:10]
        return render(request, 'bi/predictive/model_detail.html', {
            'pm': pm, 'recent_runs': recent_runs,
        })


class PredictiveModelCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.PredictiveModelForm(tenant=request.tenant)
        return render(request, 'bi/predictive/model_form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.PredictiveModelForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Predictive model "{obj.code}" created.')
            return redirect('bi:predictive_model_detail', pk=obj.pk)
        return render(request, 'bi/predictive/model_form.html', {'form': form, 'mode': 'create'})


class PredictiveModelEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.PredictiveModel, pk=pk, tenant=request.tenant)
        form = forms.PredictiveModelForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/predictive/model_form.html', {
            'form': form, 'mode': 'edit', 'pm': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.PredictiveModel, pk=pk, tenant=request.tenant)
        form = forms.PredictiveModelForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Predictive model updated.')
            return redirect('bi:predictive_model_detail', pk=obj.pk)
        return render(request, 'bi/predictive/model_form.html', {
            'form': form, 'mode': 'edit', 'pm': obj,
        })


class PredictiveModelDeleteView(_TenantDeleteBase):
    model = models.PredictiveModel
    redirect_url_name = 'bi:predictive_model_list'
    success_message = 'Predictive model deleted.'


class PredictionRunNowView(TenantAdminRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        pm = get_object_or_404(models.PredictiveModel, pk=pk, tenant=request.tenant)
        run = models.PredictionRun(
            tenant=request.tenant, predictive_model=pm,
            run_by=request.user, started_at=timezone.now(),
            status='running',
        )
        run.save()
        try:
            count, rows = predictions_svc.run_prediction(pm)
            for row in rows:
                models.PredictionResult.objects.create(
                    tenant=request.tenant, run=run, **row,
                )
            run.result_count = count
            run.status = 'completed'
            run.finished_at = timezone.now()
            run.save(update_fields=['result_count', 'status', 'finished_at'])
            messages.success(request, f'Prediction run {run.run_number}: {count} result(s).')
        except Exception as exc:  # noqa: BLE001
            run.status = 'failed'
            run.error_message = str(exc)[:2000]
            run.finished_at = timezone.now()
            run.save(update_fields=['status', 'error_message', 'finished_at'])
            messages.error(request, f'Prediction failed: {exc}')
        return redirect('bi:prediction_run_detail', pk=run.pk)


class PredictionRunListView(_TenantListBase):
    model = models.PredictionRun
    template_name = 'bi/predictive/run_list.html'
    context_qs_name = 'runs'
    select_related = ('predictive_model',)

    def filter_qs(self, qs, request):
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-started_at')

    def extra_context(self, request):
        return {'status_choices': models.PredictionRun.STATUS_CHOICES}


class PredictionRunDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(
            models.PredictionRun.objects.select_related('predictive_model'),
            pk=pk, tenant=request.tenant,
        )
        results = run.results.order_by('period_date', 'target_pk')
        return render(request, 'bi/predictive/run_detail.html', {
            'run': run, 'results': results,
        })


class PredictionRunCancelView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(models.PredictionRun, pk=pk, tenant=request.tenant)
        if not run.is_cancelable():
            messages.error(request, 'Run is not cancelable.')
            return redirect('bi:prediction_run_detail', pk=pk)
        form = forms.PredictionRunCancelForm()
        return render(request, 'bi/predictive/run_cancel.html', {'form': form, 'run': run})

    def post(self, request, pk):
        run = get_object_or_404(models.PredictionRun, pk=pk, tenant=request.tenant)
        form = forms.PredictionRunCancelForm(request.POST)
        if not run.is_cancelable():
            messages.error(request, 'Run is not cancelable.')
            return redirect('bi:prediction_run_detail', pk=pk)
        if form.is_valid():
            run.status = 'cancelled'
            run.cancellation_reason = form.cleaned_data['cancellation_reason']
            run.finished_at = timezone.now()
            run.save(update_fields=['status', 'cancellation_reason', 'finished_at'])
            messages.success(request, 'Run cancelled.')
            return redirect('bi:prediction_run_detail', pk=pk)
        return render(request, 'bi/predictive/run_cancel.html', {'form': form, 'run': run})


# ============================================================================
# 16.3  Trends
# ============================================================================

class TrendAnalysisListView(_TenantListBase):
    model = models.TrendAnalysis
    template_name = 'bi/predictive/trend_list.html'
    context_qs_name = 'trends'
    search_fields = ('trend_number', 'name')

    def filter_qs(self, qs, request):
        source = request.GET.get('source_metric', '')
        direction = request.GET.get('direction', '')
        if source:
            qs = qs.filter(source_metric=source)
        if direction:
            qs = qs.filter(direction=direction)
        return qs.order_by('-computed_at')

    def extra_context(self, request):
        return {
            'source_choices': models.TrendAnalysis.SOURCE_CHOICES,
            'direction_choices': models.TrendAnalysis.DIRECTION_CHOICES,
        }


# ============================================================================
# 16.4  Data marts
# ============================================================================

class DataMartListView(_TenantListBase):
    model = models.DataMart
    template_name = 'bi/datamarts/list.html'
    context_qs_name = 'marts'
    search_fields = ('mart_number', 'code', 'name')

    def filter_qs(self, qs, request):
        freq = request.GET.get('refresh_frequency', '')
        active = request.GET.get('active', '')
        if freq:
            qs = qs.filter(refresh_frequency=freq)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('code')

    def extra_context(self, request):
        return {'frequency_choices': models.DataMart.FREQUENCY_CHOICES}


class DataMartDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        mart = get_object_or_404(models.DataMart, pk=pk, tenant=request.tenant)
        columns = mart.columns.order_by('position', 'id')
        snapshots = mart.snapshots.order_by('-snapshot_at')[:10]
        latest_snap = snapshots.first()
        rows = []
        if latest_snap:
            rows = (
                models.DataMartRow.objects.filter(
                    tenant=request.tenant, data_mart=mart, snapshot=latest_snap,
                ).order_by('-measure_total')[:50]
            )
        return render(request, 'bi/datamarts/detail.html', {
            'mart': mart, 'columns': columns, 'snapshots': snapshots,
            'rows': rows, 'latest_snap': latest_snap,
        })


class DataMartCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.DataMartForm(tenant=request.tenant)
        return render(request, 'bi/datamarts/form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.DataMartForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Data mart "{obj.code}" created.')
            return redirect('bi:mart_detail', pk=obj.pk)
        return render(request, 'bi/datamarts/form.html', {'form': form, 'mode': 'create'})


class DataMartEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.DataMart, pk=pk, tenant=request.tenant)
        form = forms.DataMartForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/datamarts/form.html', {
            'form': form, 'mode': 'edit', 'mart': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.DataMart, pk=pk, tenant=request.tenant)
        form = forms.DataMartForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Data mart updated.')
            return redirect('bi:mart_detail', pk=obj.pk)
        return render(request, 'bi/datamarts/form.html', {
            'form': form, 'mode': 'edit', 'mart': obj,
        })


class DataMartDeleteView(_TenantDeleteBase):
    model = models.DataMart
    redirect_url_name = 'bi:mart_list'
    success_message = 'Data mart deleted.'


class DataMartRefreshView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        mart = get_object_or_404(models.DataMart, pk=pk, tenant=request.tenant)
        try:
            snap, count, duration = datamart_svc.refresh_mart(
                mart, triggered_by='manual', triggered_by_user=request.user,
            )
            messages.success(request, f'Refreshed: {count} row(s) in {duration} ms.')
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Refresh failed: {exc}')
        return redirect('bi:mart_detail', pk=pk)


class DataMartColumnCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, mart_pk):
        mart = get_object_or_404(models.DataMart, pk=mart_pk, tenant=request.tenant)
        post = request.POST.copy()
        post['data_mart'] = mart.pk
        form = forms.DataMartColumnForm(post, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.data_mart = mart
            obj.save()
            messages.success(request, 'Column added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('bi:mart_detail', pk=mart.pk)

    def get(self, request, mart_pk):
        return redirect('bi:mart_detail', pk=mart_pk)


class DataMartColumnDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        col = get_object_or_404(models.DataMartColumn, pk=pk, tenant=request.tenant)
        mart_pk = col.data_mart_id
        col.delete()
        messages.success(request, 'Column removed.')
        return redirect('bi:mart_detail', pk=mart_pk)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 16.5  Schedules / distribution
# ============================================================================

class ReportScheduleListView(_TenantListBase):
    model = models.ReportSchedule
    template_name = 'bi/distribution/schedule_list.html'
    context_qs_name = 'schedules'
    select_related = ('report', 'dashboard')
    search_fields = ('schedule_number', 'name')

    def filter_qs(self, qs, request):
        status = request.GET.get('status', '')
        freq = request.GET.get('frequency', '')
        if status:
            qs = qs.filter(status=status)
        if freq:
            qs = qs.filter(frequency=freq)
        return qs.order_by('next_run_at')

    def extra_context(self, request):
        return {
            'status_choices': models.ReportSchedule.STATUS_CHOICES,
            'frequency_choices': models.ReportSchedule.FREQUENCY_CHOICES,
        }


class ReportScheduleDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        schedule = get_object_or_404(
            models.ReportSchedule.objects.select_related('report', 'dashboard'),
            pk=pk, tenant=request.tenant,
        )
        recipients = schedule.recipients.order_by('email')
        recent_deliveries = schedule.deliveries.select_related('recipient', 'export').order_by('-attempted_at')[:20]
        return render(request, 'bi/distribution/schedule_detail.html', {
            'schedule': schedule, 'recipients': recipients,
            'recent_deliveries': recent_deliveries,
        })


class ReportScheduleCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        form = forms.ReportScheduleForm(tenant=request.tenant)
        return render(request, 'bi/distribution/schedule_form.html', {'form': form, 'mode': 'create'})

    def post(self, request):
        form = forms.ReportScheduleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'Schedule "{obj.schedule_number}" created.')
            return redirect('bi:schedule_detail', pk=obj.pk)
        return render(request, 'bi/distribution/schedule_form.html', {'form': form, 'mode': 'create'})


class ReportScheduleEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        form = forms.ReportScheduleForm(instance=obj, tenant=request.tenant)
        return render(request, 'bi/distribution/schedule_form.html', {
            'form': form, 'mode': 'edit', 'schedule': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        form = forms.ReportScheduleForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Schedule updated.')
            return redirect('bi:schedule_detail', pk=obj.pk)
        return render(request, 'bi/distribution/schedule_form.html', {
            'form': form, 'mode': 'edit', 'schedule': obj,
        })


class ReportScheduleDeleteView(_TenantDeleteBase):
    model = models.ReportSchedule
    redirect_url_name = 'bi:schedule_list'
    success_message = 'Schedule deleted.'


class ReportScheduleRunNowView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        # Force-run regardless of next_run_at by stamping it to now.
        schedule.next_run_at = timezone.now()
        schedule.save(update_fields=['next_run_at'])
        try:
            deliveries = scheduler_svc.run_schedule(schedule)
            messages.success(request, f'Schedule executed. {len(deliveries)} delivery(s) created.')
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Execution failed: {exc}')
        return redirect('bi:schedule_detail', pk=pk)


class ReportScheduleDisableView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        form = forms.ReportScheduleDisableForm()
        return render(request, 'bi/distribution/schedule_disable.html', {
            'form': form, 'schedule': schedule,
        })

    def post(self, request, pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        form = forms.ReportScheduleDisableForm(request.POST)
        if form.is_valid():
            schedule.status = 'disabled'
            schedule.disabled_reason = form.cleaned_data['disabled_reason']
            schedule.save(update_fields=['status', 'disabled_reason'])
            messages.success(request, 'Schedule disabled.')
            return redirect('bi:schedule_detail', pk=pk)
        return render(request, 'bi/distribution/schedule_disable.html', {
            'form': form, 'schedule': schedule,
        })


class ReportSchedulePauseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        if schedule.is_pausable():
            schedule.status = 'paused'
            schedule.save(update_fields=['status'])
            messages.success(request, 'Schedule paused.')
        else:
            messages.error(request, 'Schedule cannot be paused from its current status.')
        return redirect('bi:schedule_detail', pk=pk)

    def get(self, request, pk):
        return self.post(request, pk)


class ReportScheduleResumeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=pk, tenant=request.tenant)
        if schedule.is_resumable():
            schedule.status = 'active'
            schedule.save(update_fields=['status'])
            messages.success(request, 'Schedule resumed.')
        else:
            messages.error(request, 'Schedule cannot be resumed from its current status.')
        return redirect('bi:schedule_detail', pk=pk)

    def get(self, request, pk):
        return self.post(request, pk)


# Recipients (inline on schedule detail)

class ReportRecipientCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, schedule_pk):
        schedule = get_object_or_404(models.ReportSchedule, pk=schedule_pk, tenant=request.tenant)
        post = request.POST.copy()
        post['schedule'] = schedule.pk
        form = forms.ReportRecipientForm(post, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.schedule = schedule
            obj.save()
            messages.success(request, 'Recipient added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('bi:schedule_detail', pk=schedule.pk)

    def get(self, request, schedule_pk):
        return redirect('bi:schedule_detail', pk=schedule_pk)


class ReportRecipientDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rec = get_object_or_404(models.ReportRecipient, pk=pk, tenant=request.tenant)
        schedule_pk = rec.schedule_id
        rec.delete()
        messages.success(request, 'Recipient removed.')
        return redirect('bi:schedule_detail', pk=schedule_pk)

    def get(self, request, pk):
        return self.post(request, pk)


# Deliveries (read-only)

class ReportDeliveryListView(_TenantListBase):
    model = models.ReportDelivery
    template_name = 'bi/distribution/delivery_list.html'
    context_qs_name = 'deliveries'
    select_related = ('schedule', 'recipient', 'export')

    def filter_qs(self, qs, request):
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-attempted_at')

    def extra_context(self, request):
        return {'status_choices': models.ReportDelivery.STATUS_CHOICES}


class ReportDeliveryDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        delivery = get_object_or_404(
            models.ReportDelivery.objects.select_related('schedule', 'recipient', 'export'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'bi/distribution/delivery_detail.html', {'delivery': delivery})


# Exports

class ReportExportListView(_TenantListBase):
    model = models.ReportExport
    template_name = 'bi/distribution/export_list.html'
    context_qs_name = 'exports'
    select_related = ('report', 'dashboard')

    def filter_qs(self, qs, request):
        fmt = request.GET.get('format', '')
        status = request.GET.get('status', '')
        if fmt:
            qs = qs.filter(format=fmt)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-generated_at')

    def extra_context(self, request):
        return {
            'format_choices': models.ReportExport.FORMAT_CHOICES,
            'status_choices': models.ReportExport.STATUS_CHOICES,
        }


class ReportExportDownloadView(TenantRequiredMixin, View):
    """Auth-gated file download.

    Mirrors apps/plm/views.py — verifies tenant ownership before streaming
    the file, so a guessed /media/bi/exports/... path would still hit the
    static mount in DEBUG but never be produced by the application.
    """

    def get(self, request, pk):
        export = get_object_or_404(models.ReportExport, pk=pk, tenant=request.tenant)
        if not export.file:
            raise Http404('No file attached to this export.')
        return FileResponse(export.file.open('rb'), as_attachment=True, filename=export.file.name.split('/')[-1])
