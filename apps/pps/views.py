"""Production Planning & Scheduling views — full CRUD across 5 sub-modules.

Every view filters by request.tenant. Workflow transitions use a conditional
UPDATE (atomic) so concurrent reviewers cannot double-action. Heavy work
(scheduling, simulation, optimization) lives in apps/pps/services/.
"""
import json
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import TenantRequiredMixin
from apps.bom.models import BillOfMaterials
from apps.plm.models import Product

from .forms import (
    CapacityCalendarForm, DemandForecastForm, MasterProductionScheduleForm,
    MPSLineForm, OptimizationObjectiveForm, OptimizationRunForm,
    ProductionOrderForm, RoutingForm, RoutingOperationForm, ScenarioChangeForm,
    ScenarioForm, WorkCenterForm,
)
from .models import (
    CapacityCalendar, CapacityLoad, DemandForecast, MasterProductionSchedule,
    MPSLine, OptimizationObjective, OptimizationResult, OptimizationRun,
    ProductionOrder, Routing, RoutingOperation, ScenarioChange,
    ScenarioResult, Scenario, ScheduledOperation, WorkCenter,
)
from .services import optimizer as optimizer_service
from .services import scheduler as scheduler_service
from .services import simulator as simulator_service


# ============================================================================
# Helpers
# ============================================================================

_SEQ_RE = re.compile(r'^[A-Z]+-(\d+)$')


def _next_sequence_number(qs, field, prefix, width=5):
    last = qs.aggregate(Max(field))[f'{field}__max']
    next_num = 1
    if last:
        m = _SEQ_RE.match(str(last))
        next_num = int(m.group(1)) + 1 if m else qs.count() + 1
    return f'{prefix}-{next_num:0{width}d}'


def _save_with_unique_number(make_obj, max_attempts=5):
    last_err = None
    for _ in range(max_attempts):
        try:
            with transaction.atomic():
                return make_obj()
        except IntegrityError as e:
            last_err = e
            continue
    raise last_err


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


def _calendars_by_work_center(tenant):
    """Return {wc_id: {weekday: [(shift_start, shift_end, is_working), ...]}}."""
    out: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for cal in CapacityCalendar.objects.filter(tenant=tenant).select_related('work_center'):
        out[cal.work_center_id][cal.day_of_week].append((cal.shift_start, cal.shift_end, cal.is_working))
    # Convert defaultdict to plain dict for predictability.
    return {wc: dict(days) for wc, days in out.items()}


def _ops_to_requests(operations):
    return [
        scheduler_service.OperationRequest(
            sequence=op.sequence,
            operation_name=op.operation_name,
            work_center_id=op.work_center_id,
            work_center_code=op.work_center.code,
            setup_minutes=Decimal(str(op.setup_minutes)),
            run_minutes_per_unit=Decimal(str(op.run_minutes_per_unit)),
            queue_minutes=Decimal(str(op.queue_minutes)),
            move_minutes=Decimal(str(op.move_minutes)),
        )
        for op in operations
    ]


# ============================================================================
# Index / dashboard
# ============================================================================

class PPSIndexView(TenantRequiredMixin, View):
    template_name = 'pps/index.html'

    def get(self, request):
        t = request.tenant
        latest_run = OptimizationRun.objects.filter(
            tenant=t, status='completed',
        ).select_related('result').order_by('-finished_at').first()
        latest_gain = (
            latest_run.result.improvement_pct
            if latest_run and hasattr(latest_run, 'result') else None
        )
        ctx = {
            'mps_open': MasterProductionSchedule.objects.filter(
                tenant=t, status__in=('draft', 'under_review', 'approved', 'released'),
            ).count(),
            'orders_planned': ProductionOrder.objects.filter(tenant=t, status='planned').count(),
            'orders_released': ProductionOrder.objects.filter(tenant=t, status='released').count(),
            'orders_in_progress': ProductionOrder.objects.filter(tenant=t, status='in_progress').count(),
            'orders_completed': ProductionOrder.objects.filter(tenant=t, status='completed').count(),
            'bottleneck_count': CapacityLoad.objects.filter(
                tenant=t, is_bottleneck=True,
                period_date__gte=date.today() - timedelta(days=14),
            ).count(),
            'last_optimization_gain': latest_gain,
            'work_centers': WorkCenter.objects.filter(tenant=t, is_active=True).count(),
            'recent_orders': ProductionOrder.objects.filter(
                tenant=t,
            ).select_related('product').order_by('-created_at')[:8],
            'recent_mps': MasterProductionSchedule.objects.filter(
                tenant=t,
            ).order_by('-created_at')[:5],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 4.1  DEMAND FORECASTS
# ============================================================================

class DemandForecastListView(TenantRequiredMixin, ListView):
    model = DemandForecast
    template_name = 'pps/forecasts/list.html'
    context_object_name = 'forecasts'
    paginate_by = 20

    def get_queryset(self):
        qs = DemandForecast.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q) | Q(product__name__icontains=q),
            )
        for field in ('source',):
            val = self.request.GET.get(field, '')
            if val:
                qs = qs.filter(**{field: val})
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['source_choices'] = DemandForecast.SOURCE_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class DemandForecastCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/forecasts/form.html', {
            'form': DemandForecastForm(tenant=request.tenant),
        })

    def post(self, request):
        form = DemandForecastForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Forecast added.')
            return redirect('pps:forecast_list')
        return render(request, 'pps/forecasts/form.html', {'form': form})


class DemandForecastDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        f = get_object_or_404(
            DemandForecast.objects.select_related('product'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'pps/forecasts/detail.html', {'forecast': f})


class DemandForecastEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        f = get_object_or_404(DemandForecast, pk=pk, tenant=request.tenant)
        return render(request, 'pps/forecasts/form.html', {
            'form': DemandForecastForm(instance=f, tenant=request.tenant),
            'forecast': f,
        })

    def post(self, request, pk):
        f = get_object_or_404(DemandForecast, pk=pk, tenant=request.tenant)
        form = DemandForecastForm(request.POST, instance=f, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Forecast updated.')
            return redirect('pps:forecast_list')
        return render(request, 'pps/forecasts/form.html', {'form': form, 'forecast': f})


class DemandForecastDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(DemandForecast, pk=pk, tenant=request.tenant)
        f.delete()
        messages.success(request, 'Forecast deleted.')
        return redirect('pps:forecast_list')


# ============================================================================
# 4.1  MASTER PRODUCTION SCHEDULE — CRUD + workflow
# ============================================================================

class MPSListView(TenantRequiredMixin, ListView):
    model = MasterProductionSchedule
    template_name = 'pps/mps/list.html'
    context_object_name = 'mps_list'
    paginate_by = 20

    def get_queryset(self):
        qs = MasterProductionSchedule.objects.filter(
            tenant=self.request.tenant,
        ).select_related('created_by', 'approved_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(mps_number__icontains=q) | Q(name__icontains=q))
        for field in ('status', 'time_bucket'):
            val = self.request.GET.get(field, '')
            if val:
                qs = qs.filter(**{field: val})
        return qs.annotate(line_count=Count('lines')).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = MasterProductionSchedule.STATUS_CHOICES
        ctx['bucket_choices'] = MasterProductionSchedule.BUCKET_CHOICES
        return ctx


class MPSCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/mps/form.html', {
            'form': MasterProductionScheduleForm(),
        })

    def post(self, request):
        form = MasterProductionScheduleForm(request.POST)
        if form.is_valid():
            def _make():
                m = form.save(commit=False)
                m.tenant = request.tenant
                m.created_by = request.user
                m.mps_number = _next_sequence_number(
                    MasterProductionSchedule.objects.filter(tenant=request.tenant),
                    'mps_number', 'MPS',
                )
                m.save()
                return m
            mps = _save_with_unique_number(_make)
            messages.success(request, f'MPS {mps.mps_number} created.')
            return redirect('pps:mps_detail', pk=mps.pk)
        return render(request, 'pps/mps/form.html', {'form': form})


class MPSDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        mps = get_object_or_404(
            MasterProductionSchedule.objects.select_related('created_by', 'approved_by'),
            pk=pk, tenant=request.tenant,
        )
        lines = mps.lines.select_related('product').order_by('period_start', 'product__sku')
        return render(request, 'pps/mps/detail.html', {
            'mps': mps,
            'lines': lines,
            'line_form': MPSLineForm(tenant=request.tenant),
        })


class MPSEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        mps = get_object_or_404(MasterProductionSchedule, pk=pk, tenant=request.tenant)
        if not mps.is_editable():
            messages.warning(request, 'MPS can only be edited in Draft or Under Review status.')
            return redirect('pps:mps_detail', pk=pk)
        return render(request, 'pps/mps/form.html', {
            'form': MasterProductionScheduleForm(instance=mps),
            'mps': mps,
        })

    def post(self, request, pk):
        mps = get_object_or_404(MasterProductionSchedule, pk=pk, tenant=request.tenant)
        if not mps.is_editable():
            messages.warning(request, 'MPS can only be edited in Draft or Under Review status.')
            return redirect('pps:mps_detail', pk=pk)
        form = MasterProductionScheduleForm(request.POST, instance=mps)
        if form.is_valid():
            form.save()
            messages.success(request, 'MPS updated.')
            return redirect('pps:mps_detail', pk=mps.pk)
        return render(request, 'pps/mps/form.html', {'form': form, 'mps': mps})


class MPSDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        mps = get_object_or_404(MasterProductionSchedule, pk=pk, tenant=request.tenant)
        if mps.status == 'released':
            messages.error(request, 'Released MPS cannot be deleted — mark Obsolete first.')
            return redirect('pps:mps_detail', pk=pk)
        try:
            mps.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — MPS is referenced by other records.')
            return redirect('pps:mps_detail', pk=pk)
        messages.success(request, 'MPS deleted.')
        return redirect('pps:mps_list')


class MPSSubmitView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MasterProductionSchedule, pk, request.tenant, ['draft'], 'under_review',
        )
        msg = 'MPS submitted for review.' if ok else 'Only Draft MPS can be submitted.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('pps:mps_detail', pk=pk)


class MPSApproveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MasterProductionSchedule, pk, request.tenant, ['under_review'], 'approved',
            extra_fields={'approved_at': timezone.now()},
        )
        if ok:
            MasterProductionSchedule.objects.filter(pk=pk).update(approved_by=request.user)
            messages.success(request, 'MPS approved.')
        else:
            messages.warning(request, 'MPS is not awaiting review.')
        return redirect('pps:mps_detail', pk=pk)


class MPSReleaseView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MasterProductionSchedule, pk, request.tenant, ['approved'], 'released',
            extra_fields={'released_at': timezone.now()},
        )
        msg = 'MPS released.' if ok else 'Only Approved MPS can be released.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('pps:mps_detail', pk=pk)


class MPSObsoleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MasterProductionSchedule, pk, request.tenant,
            ['released', 'approved', 'draft', 'under_review'], 'obsolete',
        )
        msg = 'MPS marked Obsolete.' if ok else 'Cannot mark Obsolete from current state.'
        (messages.info if ok else messages.warning)(request, msg)
        return redirect('pps:mps_detail', pk=pk)


# ---- MPS Lines (nested) ----

class MPSLineCreateView(TenantRequiredMixin, View):
    def post(self, request, mps_id):
        mps = get_object_or_404(MasterProductionSchedule, pk=mps_id, tenant=request.tenant)
        if not mps.is_editable():
            messages.warning(request, 'Lines can only be added while MPS is Draft or Under Review.')
            return redirect('pps:mps_detail', pk=mps_id)
        form = MPSLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.mps = mps
            try:
                line.save()
                messages.success(request, f'Line {line.product.sku} added.')
            except IntegrityError:
                messages.error(request, 'A line for that product/period already exists.')
        else:
            messages.error(
                request,
                'Could not add line: ' + '; '.join(
                    f'{k}: {v[0]}' for k, v in form.errors.items()
                ),
            )
        return redirect('pps:mps_detail', pk=mps_id)


class MPSLineEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        line = get_object_or_404(MPSLine, pk=pk, tenant=request.tenant)
        return render(request, 'pps/mps_lines/form.html', {
            'form': MPSLineForm(instance=line, tenant=request.tenant),
            'line': line,
        })

    def post(self, request, pk):
        line = get_object_or_404(MPSLine, pk=pk, tenant=request.tenant)
        if not line.mps.is_editable():
            messages.warning(request, 'Lines can only be edited while MPS is Draft or Under Review.')
            return redirect('pps:mps_detail', pk=line.mps_id)
        form = MPSLineForm(request.POST, instance=line, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Line updated.')
            return redirect('pps:mps_detail', pk=line.mps_id)
        return render(request, 'pps/mps_lines/form.html', {'form': form, 'line': line})


class MPSLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(MPSLine, pk=pk, tenant=request.tenant)
        if not line.mps.is_editable():
            messages.warning(request, 'Lines can only be deleted while MPS is Draft or Under Review.')
            return redirect('pps:mps_detail', pk=line.mps_id)
        mps_id = line.mps_id
        line.delete()
        messages.success(request, 'Line deleted.')
        return redirect('pps:mps_detail', pk=mps_id)


# ============================================================================
# 4.2  WORK CENTERS
# ============================================================================

class WorkCenterListView(TenantRequiredMixin, ListView):
    model = WorkCenter
    template_name = 'pps/work_centers/list.html'
    context_object_name = 'work_centers'
    paginate_by = 20

    def get_queryset(self):
        qs = WorkCenter.objects.filter(tenant=self.request.tenant)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        wc_type = self.request.GET.get('work_center_type', '')
        if wc_type:
            qs = qs.filter(work_center_type=wc_type)
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['type_choices'] = WorkCenter.TYPE_CHOICES
        return ctx


class WorkCenterCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/work_centers/form.html', {
            'form': WorkCenterForm(),
        })

    def post(self, request):
        form = WorkCenterForm(request.POST)
        if form.is_valid():
            wc = form.save(commit=False)
            wc.tenant = request.tenant
            try:
                wc.save()
            except IntegrityError:
                messages.error(request, f'A work center with code "{wc.code}" already exists.')
                return render(request, 'pps/work_centers/form.html', {'form': form})
            messages.success(request, f'Work center {wc.code} created.')
            return redirect('pps:work_center_detail', pk=wc.pk)
        return render(request, 'pps/work_centers/form.html', {'form': form})


class WorkCenterDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        wc = get_object_or_404(WorkCenter, pk=pk, tenant=request.tenant)
        calendars = wc.calendars.order_by('day_of_week', 'shift_start')
        recent_load = CapacityLoad.objects.filter(
            tenant=request.tenant, work_center=wc,
        ).order_by('-period_date')[:14]
        return render(request, 'pps/work_centers/detail.html', {
            'work_center': wc,
            'calendars': calendars,
            'recent_load': recent_load,
        })


class WorkCenterEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        wc = get_object_or_404(WorkCenter, pk=pk, tenant=request.tenant)
        return render(request, 'pps/work_centers/form.html', {
            'form': WorkCenterForm(instance=wc),
            'work_center': wc,
        })

    def post(self, request, pk):
        wc = get_object_or_404(WorkCenter, pk=pk, tenant=request.tenant)
        form = WorkCenterForm(request.POST, instance=wc)
        if form.is_valid():
            form.save()
            messages.success(request, 'Work center updated.')
            return redirect('pps:work_center_detail', pk=wc.pk)
        return render(request, 'pps/work_centers/form.html', {'form': form, 'work_center': wc})


class WorkCenterDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        wc = get_object_or_404(WorkCenter, pk=pk, tenant=request.tenant)
        try:
            wc.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — work center is used by routings or scheduled operations.')
            return redirect('pps:work_center_detail', pk=pk)
        messages.success(request, 'Work center deleted.')
        return redirect('pps:work_center_list')


# ---- Capacity calendar entries ----

class CapacityCalendarListView(TenantRequiredMixin, ListView):
    model = CapacityCalendar
    template_name = 'pps/calendars/list.html'
    context_object_name = 'calendars'
    paginate_by = 30

    def get_queryset(self):
        qs = CapacityCalendar.objects.filter(
            tenant=self.request.tenant,
        ).select_related('work_center')
        wc = self.request.GET.get('work_center', '')
        if wc:
            qs = qs.filter(work_center_id=wc)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['work_centers'] = WorkCenter.objects.filter(
            tenant=self.request.tenant,
        ).order_by('code')
        return ctx


class CapacityCalendarCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/calendars/form.html', {
            'form': CapacityCalendarForm(tenant=request.tenant),
        })

    def post(self, request):
        form = CapacityCalendarForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            cal = form.save(commit=False)
            cal.tenant = request.tenant
            try:
                cal.save()
            except IntegrityError:
                messages.error(request, 'A shift starting at that time already exists for this day.')
                return render(request, 'pps/calendars/form.html', {'form': form})
            messages.success(request, 'Calendar entry added.')
            return redirect('pps:calendar_list')
        return render(request, 'pps/calendars/form.html', {'form': form})


class CapacityCalendarEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        cal = get_object_or_404(CapacityCalendar, pk=pk, tenant=request.tenant)
        return render(request, 'pps/calendars/form.html', {
            'form': CapacityCalendarForm(instance=cal, tenant=request.tenant),
            'calendar': cal,
        })

    def post(self, request, pk):
        cal = get_object_or_404(CapacityCalendar, pk=pk, tenant=request.tenant)
        form = CapacityCalendarForm(request.POST, instance=cal, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Calendar entry updated.')
            return redirect('pps:calendar_list')
        return render(request, 'pps/calendars/form.html', {'form': form, 'calendar': cal})


class CapacityCalendarDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        cal = get_object_or_404(CapacityCalendar, pk=pk, tenant=request.tenant)
        cal.delete()
        messages.success(request, 'Calendar entry deleted.')
        return redirect('pps:calendar_list')


# ---- Capacity load dashboard ----

class CapacityDashboardView(TenantRequiredMixin, View):
    template_name = 'pps/capacity/dashboard.html'

    def get(self, request):
        t = request.tenant
        wc_filter = request.GET.get('work_center', '').strip()
        date_from = request.GET.get('date_from', '').strip()
        date_to = request.GET.get('date_to', '').strip()
        qs = CapacityLoad.objects.filter(tenant=t).select_related('work_center')
        if wc_filter:
            qs = qs.filter(work_center_id=wc_filter)
        if date_from:
            qs = qs.filter(period_date__gte=date_from)
        if date_to:
            qs = qs.filter(period_date__lte=date_to)
        loads = list(qs.order_by('period_date', 'work_center__code'))

        # Group for chart: per work center -> list of (date, util)
        chart_series: dict[str, list[dict]] = defaultdict(list)
        for ld in loads:
            chart_series[ld.work_center.code].append({
                'date': ld.period_date.isoformat(),
                'utilization': float(ld.utilization_pct),
                'planned': ld.planned_minutes,
                'available': ld.available_minutes,
            })
        return render(request, self.template_name, {
            'loads': loads,
            'work_centers': WorkCenter.objects.filter(tenant=t, is_active=True).order_by('code'),
            'chart_series_json': json.dumps([
                {'name': wc, 'data': [pt['utilization'] for pt in pts],
                 'categories': [pt['date'] for pt in pts]}
                for wc, pts in chart_series.items()
            ]),
            'bottleneck_count': sum(1 for ld in loads if ld.is_bottleneck),
        })


class CapacityRecomputeView(TenantRequiredMixin, View):
    """Recompute CapacityLoad for the next 14 days across every active work center."""

    def post(self, request):
        t = request.tenant
        today = date.today()
        horizon = [today + timedelta(days=i) for i in range(14)]
        cals = _calendars_by_work_center(t)
        # Pull all scheduled operations in horizon, grouped by (wc, date).
        sched_qs = ScheduledOperation.objects.filter(
            tenant=t,
            planned_start__date__gte=today,
            planned_start__date__lte=today + timedelta(days=13),
        )
        per_wc_per_date: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
        for s in sched_qs:
            d = s.planned_start.date()
            per_wc_per_date[s.work_center_id][d] += s.planned_minutes

        for wc in WorkCenter.objects.filter(tenant=t, is_active=True):
            available = {}
            for d in horizon:
                shifts = cals.get(wc.pk, {}).get(d.weekday(), [])
                mins = sum(
                    int((datetime.combine(d, e) - datetime.combine(d, s)).total_seconds() // 60)
                    for s, e, working in shifts if working
                )
                available[d] = mins
            scheduled = per_wc_per_date.get(wc.pk, {})
            summary = scheduler_service.compute_load(scheduled, available)
            for d, info in summary.items():
                CapacityLoad.objects.update_or_create(
                    tenant=t, work_center=wc, period_date=d,
                    defaults={
                        'planned_minutes': info['planned_minutes'],
                        'available_minutes': info['available_minutes'],
                        'utilization_pct': info['utilization_pct'],
                        'is_bottleneck': info['is_bottleneck'],
                        'computed_at': timezone.now(),
                    },
                )
        messages.success(request, 'Capacity load recomputed for the next 14 days.')
        return redirect('pps:capacity_dashboard')


# ============================================================================
# 4.3  ROUTINGS
# ============================================================================

class RoutingListView(TenantRequiredMixin, ListView):
    model = Routing
    template_name = 'pps/routings/list.html'
    context_object_name = 'routings'
    paginate_by = 20

    def get_queryset(self):
        qs = Routing.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(routing_number__icontains=q)
                | Q(name__icontains=q)
                | Q(product__sku__icontains=q),
            )
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.annotate(op_count=Count('operations')).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = Routing.STATUS_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class RoutingCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/routings/form.html', {
            'form': RoutingForm(tenant=request.tenant),
        })

    def post(self, request):
        form = RoutingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                r = form.save(commit=False)
                r.tenant = request.tenant
                r.created_by = request.user
                r.routing_number = _next_sequence_number(
                    Routing.objects.filter(tenant=request.tenant),
                    'routing_number', 'ROUT',
                )
                r.save()
                return r
            routing = _save_with_unique_number(_make)
            messages.success(request, f'Routing {routing.routing_number} created.')
            return redirect('pps:routing_detail', pk=routing.pk)
        return render(request, 'pps/routings/form.html', {'form': form})


class RoutingDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        routing = get_object_or_404(
            Routing.objects.select_related('product', 'created_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'pps/routings/detail.html', {
            'routing': routing,
            'operations': routing.operations.select_related('work_center').order_by('sequence'),
            'op_form': RoutingOperationForm(tenant=request.tenant),
        })


class RoutingEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        routing = get_object_or_404(Routing, pk=pk, tenant=request.tenant)
        return render(request, 'pps/routings/form.html', {
            'form': RoutingForm(instance=routing, tenant=request.tenant),
            'routing': routing,
        })

    def post(self, request, pk):
        routing = get_object_or_404(Routing, pk=pk, tenant=request.tenant)
        form = RoutingForm(request.POST, instance=routing, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Routing updated.')
            return redirect('pps:routing_detail', pk=routing.pk)
        return render(request, 'pps/routings/form.html', {'form': form, 'routing': routing})


class RoutingDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        routing = get_object_or_404(Routing, pk=pk, tenant=request.tenant)
        try:
            routing.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — routing is referenced by production orders.')
            return redirect('pps:routing_detail', pk=pk)
        messages.success(request, 'Routing deleted.')
        return redirect('pps:routing_list')


class RoutingOperationCreateView(TenantRequiredMixin, View):
    def post(self, request, routing_id):
        routing = get_object_or_404(Routing, pk=routing_id, tenant=request.tenant)
        form = RoutingOperationForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            op = form.save(commit=False)
            op.tenant = request.tenant
            op.routing = routing
            op.save()
            messages.success(request, f'Operation "{op.operation_name}" added.')
        else:
            messages.error(
                request,
                'Could not add operation: ' + '; '.join(
                    f'{k}: {v[0]}' for k, v in form.errors.items()
                ),
            )
        return redirect('pps:routing_detail', pk=routing_id)


class RoutingOperationEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        op = get_object_or_404(RoutingOperation, pk=pk, tenant=request.tenant)
        return render(request, 'pps/routing_operations/form.html', {
            'form': RoutingOperationForm(instance=op, tenant=request.tenant),
            'operation': op,
        })

    def post(self, request, pk):
        op = get_object_or_404(RoutingOperation, pk=pk, tenant=request.tenant)
        form = RoutingOperationForm(request.POST, instance=op, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Operation updated.')
            return redirect('pps:routing_detail', pk=op.routing_id)
        return render(request, 'pps/routing_operations/form.html', {'form': form, 'operation': op})


class RoutingOperationDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(RoutingOperation, pk=pk, tenant=request.tenant)
        rid = op.routing_id
        op.delete()
        messages.success(request, 'Operation deleted.')
        return redirect('pps:routing_detail', pk=rid)


# ============================================================================
# 4.3  PRODUCTION ORDERS
# ============================================================================

class ProductionOrderListView(TenantRequiredMixin, ListView):
    model = ProductionOrder
    template_name = 'pps/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductionOrder.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'routing', 'bom')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product__name__icontains=q),
            )
        for field in ('status', 'priority', 'scheduling_method'):
            val = self.request.GET.get(field, '')
            if val:
                qs = qs.filter(**{field: val})
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = ProductionOrder.STATUS_CHOICES
        ctx['priority_choices'] = ProductionOrder.PRIORITY_CHOICES
        ctx['method_choices'] = ProductionOrder.METHOD_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class ProductionOrderCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/orders/form.html', {
            'form': ProductionOrderForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProductionOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                o = form.save(commit=False)
                o.tenant = request.tenant
                o.created_by = request.user
                o.order_number = _next_sequence_number(
                    ProductionOrder.objects.filter(tenant=request.tenant),
                    'order_number', 'PO',
                )
                o.save()
                return o
            order = _save_with_unique_number(_make)
            messages.success(request, f'Production order {order.order_number} created.')
            return redirect('pps:order_detail', pk=order.pk)
        return render(request, 'pps/orders/form.html', {'form': form})


class ProductionOrderDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        order = get_object_or_404(
            ProductionOrder.objects.select_related(
                'product', 'routing', 'bom', 'mps_line', 'created_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'pps/orders/detail.html', {
            'order': order,
            'scheduled_ops': order.scheduled_operations.select_related('work_center').order_by('sequence'),
        })


class ProductionOrderEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, tenant=request.tenant)
        if not order.is_editable():
            messages.warning(request, 'Only Planned orders can be edited.')
            return redirect('pps:order_detail', pk=pk)
        return render(request, 'pps/orders/form.html', {
            'form': ProductionOrderForm(instance=order, tenant=request.tenant),
            'order': order,
        })

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, tenant=request.tenant)
        if not order.is_editable():
            messages.warning(request, 'Only Planned orders can be edited.')
            return redirect('pps:order_detail', pk=pk)
        form = ProductionOrderForm(request.POST, instance=order, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Order updated.')
            return redirect('pps:order_detail', pk=order.pk)
        return render(request, 'pps/orders/form.html', {'form': form, 'order': order})


class ProductionOrderDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, tenant=request.tenant)
        if order.status not in ('planned', 'cancelled'):
            messages.error(request, 'Only Planned or Cancelled orders can be deleted.')
            return redirect('pps:order_detail', pk=pk)
        order.delete()
        messages.success(request, 'Order deleted.')
        return redirect('pps:order_list')


class ProductionOrderReleaseView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            ProductionOrder, pk, request.tenant, ['planned'], 'released',
        )
        msg = 'Order released to the floor.' if ok else 'Only Planned orders can be released.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('pps:order_detail', pk=pk)


class ProductionOrderStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            ProductionOrder, pk, request.tenant, ['released'], 'in_progress',
            extra_fields={'actual_start': timezone.now()},
        )
        msg = 'Order started.' if ok else 'Only Released orders can be started.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('pps:order_detail', pk=pk)


class ProductionOrderCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            ProductionOrder, pk, request.tenant, ['in_progress'], 'completed',
            extra_fields={'actual_end': timezone.now()},
        )
        msg = 'Order completed.' if ok else 'Only In-Progress orders can be completed.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('pps:order_detail', pk=pk)


class ProductionOrderCancelView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            ProductionOrder, pk, request.tenant,
            ['planned', 'released', 'in_progress'], 'cancelled',
        )
        msg = 'Order cancelled.' if ok else 'Order cannot be cancelled from current state.'
        (messages.info if ok else messages.warning)(request, msg)
        return redirect('pps:order_detail', pk=pk)


class ProductionOrderScheduleView(TenantRequiredMixin, View):
    """Schedule an order (forward/backward/infinite). Replaces existing
    ScheduledOperation rows for the order."""

    def post(self, request, pk):
        order = get_object_or_404(
            ProductionOrder.objects.select_related('routing'),
            pk=pk, tenant=request.tenant,
        )
        if order.routing is None:
            messages.error(request, 'Cannot schedule — order has no routing.')
            return redirect('pps:order_detail', pk=pk)
        method = request.POST.get('method', order.scheduling_method)
        if method not in ('forward', 'backward', 'infinite'):
            method = 'forward'
        ops = list(order.routing.operations.select_related('work_center').order_by('sequence'))
        if not ops:
            messages.error(request, 'Cannot schedule — routing has no operations.')
            return redirect('pps:order_detail', pk=pk)
        cals = _calendars_by_work_center(request.tenant)
        requests_ = _ops_to_requests(ops)
        anchor_start = order.requested_start or timezone.now()
        anchor_end = order.requested_end or (anchor_start + timedelta(days=7))
        if method == 'backward':
            slots = scheduler_service.schedule_backward(
                requests_, end=anchor_end, quantity=order.quantity, calendars=cals,
            )
        elif method == 'infinite':
            slots = scheduler_service.schedule_infinite(
                requests_, start=anchor_start, quantity=order.quantity,
            )
        else:
            slots = scheduler_service.schedule_forward(
                requests_, start=anchor_start, quantity=order.quantity, calendars=cals,
            )
        op_by_seq = {op.sequence: op for op in ops}
        with transaction.atomic():
            order.scheduled_operations.all().delete()
            for slot in slots:
                ScheduledOperation.objects.create(
                    tenant=request.tenant,
                    production_order=order,
                    routing_operation=op_by_seq.get(slot.sequence),
                    work_center_id=slot.work_center_id,
                    sequence=slot.sequence,
                    operation_name=slot.operation_name,
                    planned_start=slot.planned_start,
                    planned_end=slot.planned_end,
                    planned_minutes=slot.planned_minutes,
                )
            if slots:
                ProductionOrder.objects.filter(pk=order.pk).update(
                    scheduling_method=method,
                    scheduled_start=slots[0].planned_start,
                    scheduled_end=slots[-1].planned_end,
                )
        messages.success(
            request,
            f'Order scheduled ({method}) — {len(slots)} operations laid down.',
        )
        return redirect('pps:order_detail', pk=pk)


class OrderGanttView(TenantRequiredMixin, View):
    template_name = 'pps/orders/gantt.html'

    def get(self, request):
        t = request.tenant
        days = int(request.GET.get('days', '14') or 14)
        wc_filter = request.GET.get('work_center', '').strip()
        start = timezone.now() - timedelta(days=2)
        end = timezone.now() + timedelta(days=days)
        qs = ScheduledOperation.objects.filter(
            tenant=t, planned_start__gte=start, planned_start__lte=end,
        ).select_related('production_order', 'production_order__product', 'work_center')
        if wc_filter:
            qs = qs.filter(work_center_id=wc_filter)
        qs = qs.order_by('work_center__code', 'planned_start')

        # ApexCharts rangeBar input: per work-center series, each data point
        # is {x: order_number, y: [start_ms, end_ms]}.
        series_map: dict[str, list[dict]] = defaultdict(list)
        for s in qs:
            series_map[s.work_center.code].append({
                'x': f'{s.production_order.order_number} · {s.production_order.product.sku}',
                'y': [int(s.planned_start.timestamp() * 1000),
                      int(s.planned_end.timestamp() * 1000)],
                'sequence': s.sequence,
                'operation_name': s.operation_name or (s.routing_operation.operation_name if s.routing_operation_id else ''),
                'order_id': s.production_order_id,
            })
        chart_series = [{'name': wc, 'data': data} for wc, data in series_map.items()]
        return render(request, self.template_name, {
            'chart_series_json': json.dumps(chart_series),
            'work_centers': WorkCenter.objects.filter(tenant=t).order_by('code'),
            'days': days,
            'scheduled_count': qs.count(),
        })


# ============================================================================
# 4.4  WHAT-IF SCENARIOS
# ============================================================================

class ScenarioListView(TenantRequiredMixin, ListView):
    model = Scenario
    template_name = 'pps/scenarios/list.html'
    context_object_name = 'scenarios'
    paginate_by = 20

    def get_queryset(self):
        qs = Scenario.objects.filter(
            tenant=self.request.tenant,
        ).select_related('base_mps', 'created_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(base_mps__mps_number__icontains=q))
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = Scenario.STATUS_CHOICES
        return ctx


class ScenarioCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/scenarios/form.html', {
            'form': ScenarioForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ScenarioForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            s = form.save(commit=False)
            s.tenant = request.tenant
            s.created_by = request.user
            s.save()
            messages.success(request, f'Scenario "{s.name}" created.')
            return redirect('pps:scenario_detail', pk=s.pk)
        return render(request, 'pps/scenarios/form.html', {'form': form})


class ScenarioDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        scenario = get_object_or_404(
            Scenario.objects.select_related('base_mps', 'created_by', 'applied_by'),
            pk=pk, tenant=request.tenant,
        )
        result = getattr(scenario, 'result', None)
        return render(request, 'pps/scenarios/detail.html', {
            'scenario': scenario,
            'changes': scenario.changes.order_by('sequence'),
            'change_form': ScenarioChangeForm(),
            'result': result,
        })


class ScenarioEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        s = get_object_or_404(Scenario, pk=pk, tenant=request.tenant)
        if not s.is_editable():
            messages.warning(request, 'Scenario can only be edited while Draft or Completed.')
            return redirect('pps:scenario_detail', pk=pk)
        return render(request, 'pps/scenarios/form.html', {
            'form': ScenarioForm(instance=s, tenant=request.tenant),
            'scenario': s,
        })

    def post(self, request, pk):
        s = get_object_or_404(Scenario, pk=pk, tenant=request.tenant)
        if not s.is_editable():
            messages.warning(request, 'Scenario can only be edited while Draft or Completed.')
            return redirect('pps:scenario_detail', pk=pk)
        form = ScenarioForm(request.POST, instance=s, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scenario updated.')
            return redirect('pps:scenario_detail', pk=s.pk)
        return render(request, 'pps/scenarios/form.html', {'form': form, 'scenario': s})


class ScenarioDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        s = get_object_or_404(Scenario, pk=pk, tenant=request.tenant)
        if s.status == 'applied':
            messages.error(request, 'Applied scenarios cannot be deleted.')
            return redirect('pps:scenario_detail', pk=pk)
        s.delete()
        messages.success(request, 'Scenario deleted.')
        return redirect('pps:scenario_list')


class ScenarioRunView(TenantRequiredMixin, View):
    def post(self, request, pk):
        scenario = get_object_or_404(
            Scenario.objects.select_related('base_mps'),
            pk=pk, tenant=request.tenant,
        )
        if scenario.status not in ('draft', 'completed'):
            messages.warning(request, 'Scenario cannot be re-run from current state.')
            return redirect('pps:scenario_detail', pk=pk)
        Scenario.objects.filter(pk=pk).update(status='running')
        try:
            payload = simulator_service.apply_scenario(scenario)
        except Exception as exc:  # pragma: no cover — simulator is deterministic
            Scenario.objects.filter(pk=pk).update(status='draft')
            messages.error(request, f'Simulation failed: {exc}')
            return redirect('pps:scenario_detail', pk=pk)
        ScenarioResult.objects.update_or_create(
            tenant=request.tenant, scenario=scenario,
            defaults={
                'on_time_pct': payload['on_time_pct'],
                'total_load_minutes': payload['total_load_minutes'],
                'total_idle_minutes': payload['total_idle_minutes'],
                'bottleneck_count': payload['bottleneck_count'],
                'summary_json': payload['summary_json'],
                'computed_at': timezone.now(),
            },
        )
        Scenario.objects.filter(pk=pk).update(status='completed', ran_at=timezone.now())
        messages.success(request, 'Scenario simulated. Check the result panel for KPI deltas.')
        return redirect('pps:scenario_detail', pk=pk)


class ScenarioApplyView(TenantRequiredMixin, View):
    """'Apply' is a soft action — records intent, does not mutate the base MPS.

    Real apply (push scenario lines into base_mps) is intentionally out of
    scope for v1; the audit trail makes it clear what would have changed.
    """

    def post(self, request, pk):
        ok = _atomic_status_transition(
            Scenario, pk, request.tenant, ['completed'], 'applied',
            extra_fields={'applied_at': timezone.now()},
        )
        if ok:
            Scenario.objects.filter(pk=pk).update(applied_by=request.user)
            messages.success(request, 'Scenario marked as Applied. Audit trail recorded.')
        else:
            messages.warning(request, 'Only Completed scenarios can be marked Applied.')
        return redirect('pps:scenario_detail', pk=pk)


class ScenarioDiscardView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            Scenario, pk, request.tenant,
            ['draft', 'completed', 'running'], 'discarded',
        )
        msg = 'Scenario discarded.' if ok else 'Scenario cannot be discarded from current state.'
        (messages.info if ok else messages.warning)(request, msg)
        return redirect('pps:scenario_detail', pk=pk)


class ScenarioChangeCreateView(TenantRequiredMixin, View):
    def post(self, request, scenario_id):
        scenario = get_object_or_404(Scenario, pk=scenario_id, tenant=request.tenant)
        if not scenario.is_editable():
            messages.warning(request, 'Changes can only be added while scenario is Draft or Completed.')
            return redirect('pps:scenario_detail', pk=scenario_id)
        form = ScenarioChangeForm(request.POST)
        if form.is_valid():
            ch = form.save(commit=False)
            ch.tenant = request.tenant
            ch.scenario = scenario
            # `payload` is rendered as a Textarea — accept JSON or empty.
            raw = (request.POST.get('payload') or '').strip()
            if raw:
                try:
                    ch.payload = json.loads(raw)
                except json.JSONDecodeError:
                    messages.error(request, 'Payload must be valid JSON.')
                    return redirect('pps:scenario_detail', pk=scenario_id)
            else:
                ch.payload = {}
            ch.save()
            messages.success(request, 'Change recorded.')
        else:
            messages.error(
                request,
                'Could not record change: ' + '; '.join(
                    f'{k}: {v[0]}' for k, v in form.errors.items()
                ),
            )
        return redirect('pps:scenario_detail', pk=scenario_id)


class ScenarioChangeEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        ch = get_object_or_404(ScenarioChange, pk=pk, tenant=request.tenant)
        return render(request, 'pps/scenario_changes/form.html', {
            'form': ScenarioChangeForm(instance=ch, initial={'payload': json.dumps(ch.payload or {})}),
            'change': ch,
        })

    def post(self, request, pk):
        ch = get_object_or_404(ScenarioChange, pk=pk, tenant=request.tenant)
        form = ScenarioChangeForm(request.POST, instance=ch)
        if form.is_valid():
            obj = form.save(commit=False)
            raw = (request.POST.get('payload') or '').strip()
            if raw:
                try:
                    obj.payload = json.loads(raw)
                except json.JSONDecodeError:
                    messages.error(request, 'Payload must be valid JSON.')
                    return render(request, 'pps/scenario_changes/form.html', {'form': form, 'change': ch})
            else:
                obj.payload = {}
            obj.save()
            messages.success(request, 'Change updated.')
            return redirect('pps:scenario_detail', pk=ch.scenario_id)
        return render(request, 'pps/scenario_changes/form.html', {'form': form, 'change': ch})


class ScenarioChangeDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ch = get_object_or_404(ScenarioChange, pk=pk, tenant=request.tenant)
        sid = ch.scenario_id
        ch.delete()
        messages.success(request, 'Change deleted.')
        return redirect('pps:scenario_detail', pk=sid)


# ============================================================================
# 4.5  OPTIMIZATION OBJECTIVES & RUNS
# ============================================================================

class OptimizationObjectiveListView(TenantRequiredMixin, ListView):
    model = OptimizationObjective
    template_name = 'pps/optimizer/objective_list.html'
    context_object_name = 'objectives'
    paginate_by = 20

    def get_queryset(self):
        qs = OptimizationObjective.objects.filter(tenant=self.request.tenant)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs


class OptimizationObjectiveCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/optimizer/objective_form.html', {
            'form': OptimizationObjectiveForm(),
        })

    def post(self, request):
        form = OptimizationObjectiveForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            try:
                obj.save()
            except IntegrityError:
                messages.error(request, f'An objective named "{obj.name}" already exists.')
                return render(request, 'pps/optimizer/objective_form.html', {'form': form})
            messages.success(request, 'Objective created.')
            return redirect('pps:objective_list')
        return render(request, 'pps/optimizer/objective_form.html', {'form': form})


class OptimizationObjectiveEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(OptimizationObjective, pk=pk, tenant=request.tenant)
        return render(request, 'pps/optimizer/objective_form.html', {
            'form': OptimizationObjectiveForm(instance=obj),
            'objective': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(OptimizationObjective, pk=pk, tenant=request.tenant)
        form = OptimizationObjectiveForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Objective updated.')
            return redirect('pps:objective_list')
        return render(request, 'pps/optimizer/objective_form.html', {'form': form, 'objective': obj})


class OptimizationObjectiveDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(OptimizationObjective, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — objective is referenced by a run.')
            return redirect('pps:objective_list')
        messages.success(request, 'Objective deleted.')
        return redirect('pps:objective_list')


class OptimizationRunListView(TenantRequiredMixin, ListView):
    model = OptimizationRun
    template_name = 'pps/optimizer/run_list.html'
    context_object_name = 'runs'
    paginate_by = 20

    def get_queryset(self):
        qs = OptimizationRun.objects.filter(
            tenant=self.request.tenant,
        ).select_related('mps', 'objective', 'started_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(mps__mps_number__icontains=q))
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = OptimizationRun.STATUS_CHOICES
        return ctx


class OptimizationRunCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'pps/optimizer/run_form.html', {
            'form': OptimizationRunForm(tenant=request.tenant),
        })

    def post(self, request):
        form = OptimizationRunForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            run = form.save(commit=False)
            run.tenant = request.tenant
            run.started_by = request.user
            run.save()
            messages.success(request, f'Run "{run.name}" queued.')
            return redirect('pps:run_detail', pk=run.pk)
        return render(request, 'pps/optimizer/run_form.html', {'form': form})


class OptimizationRunDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(
            OptimizationRun.objects.select_related('mps', 'objective', 'started_by'),
            pk=pk, tenant=request.tenant,
        )
        result = getattr(run, 'result', None)
        return render(request, 'pps/optimizer/run_detail.html', {
            'run': run,
            'result': result,
        })


class OptimizationRunDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(OptimizationRun, pk=pk, tenant=request.tenant)
        run.delete()
        messages.success(request, 'Run deleted.')
        return redirect('pps:run_list')


def _orders_for_run(run, tenant):
    """Project candidate production orders for the run's MPS into dicts."""
    orders = list(
        ProductionOrder.objects
        .filter(tenant=tenant, mps_line__mps=run.mps,
                status__in=('planned', 'released'))
        .select_related('product')
    )
    if not orders:
        # Fall back to all open orders if none are tied to MPS lines.
        orders = list(
            ProductionOrder.objects
            .filter(tenant=tenant, status__in=('planned', 'released'))
            .select_related('product')
        )
    payload = []
    for o in orders:
        # Estimate minutes: prefer routing total, else 60 min/qty default.
        if o.routing_id:
            ops = list(o.routing.operations.all())
            mins = sum(int(op.total_minutes(o.quantity)) for op in ops)
        else:
            mins = int(Decimal(str(o.quantity)) * Decimal('60'))
        payload.append({
            'id': o.pk,
            'product_id': o.product_id,
            'priority': o.priority,
            'requested_end': o.requested_end,
            'minutes': mins,
        })
    return payload


class OptimizationStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(
            OptimizationRun.objects.select_related('mps', 'objective'),
            pk=pk, tenant=request.tenant,
        )
        if run.status not in ('queued', 'failed'):
            messages.warning(request, 'Run is not in a startable state.')
            return redirect('pps:run_detail', pk=pk)
        OptimizationRun.objects.filter(pk=pk).update(
            status='running', started_at=timezone.now(),
        )
        try:
            orders = _orders_for_run(run, request.tenant)
            payload = optimizer_service.run_optimization(run, orders=orders)
        except Exception as exc:  # pragma: no cover — pure-python heuristic
            OptimizationRun.objects.filter(pk=pk).update(
                status='failed', error_message=str(exc), finished_at=timezone.now(),
            )
            messages.error(request, f'Optimization failed: {exc}')
            return redirect('pps:run_detail', pk=pk)
        OptimizationResult.objects.update_or_create(
            tenant=request.tenant, run=run,
            defaults={
                'before_total_minutes': payload['before_total_minutes'],
                'after_total_minutes': payload['after_total_minutes'],
                'before_changeovers': payload['before_changeovers'],
                'after_changeovers': payload['after_changeovers'],
                'before_lateness': payload['before_lateness'],
                'after_lateness': payload['after_lateness'],
                'improvement_pct': payload['improvement_pct'],
                'suggestion_json': payload['suggestion_json'],
            },
        )
        OptimizationRun.objects.filter(pk=pk).update(
            status='completed', finished_at=timezone.now(),
        )
        messages.success(
            request,
            f'Optimization complete — {payload["improvement_pct"]}% projected gain.',
        )
        return redirect('pps:run_detail', pk=pk)


class OptimizationApplyView(TenantRequiredMixin, View):
    """Marks the result as applied. v1 does not mutate orders — see scenario apply."""

    def post(self, request, pk):
        run = get_object_or_404(
            OptimizationRun.objects.select_related('result'),
            pk=pk, tenant=request.tenant,
        )
        if run.status != 'completed' or not hasattr(run, 'result'):
            messages.warning(request, 'Only completed runs with a result can be applied.')
            return redirect('pps:run_detail', pk=pk)
        OptimizationResult.objects.filter(run=run).update(
            applied_at=timezone.now(), applied_by=request.user,
        )
        messages.success(request, 'Result marked as applied. Audit trail recorded.')
        return redirect('pps:run_detail', pk=pk)


class OptimizationDiscardView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(OptimizationRun, pk=pk, tenant=request.tenant)
        if run.status == 'queued':
            run.delete()
            messages.info(request, 'Queued run discarded.')
            return redirect('pps:run_list')
        messages.info(request, 'Use Delete to remove a completed run.')
        return redirect('pps:run_detail', pk=pk)
