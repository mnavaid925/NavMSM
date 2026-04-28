"""Shop Floor Control views - full CRUD + workflow + operator terminal.

Every view filters by ``request.tenant``. Workflow transitions use a
conditional UPDATE so concurrent reviewers cannot double-action. The heavy
work (dispatch fan-out, time-log accounting, production rollup) lives in
``apps/mes/services/``.
"""
import os
import re

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin
from apps.plm.models import Product
from apps.pps.models import ProductionOrder, RoutingOperation, WorkCenter

from .forms import (
    AndonAlertForm, AndonResolveForm, MESWorkOrderForm, ProductionReportForm,
    ShopFloorOperatorForm, WorkInstructionAcknowledgementForm,
    WorkInstructionForm, WorkInstructionVersionForm,
)
from .models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog,
    ProductionReport, ShopFloorOperator, WorkInstruction,
    WorkInstructionAcknowledgement, WorkInstructionVersion,
)
from .services import dispatcher, reporting, time_logging


# ============================================================================
# Helpers (mirror the MRP pattern)
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


# ============================================================================
# Index / dashboard
# ============================================================================

class MESIndexView(TenantRequiredMixin, View):
    template_name = 'mes/index.html'

    def get(self, request):
        t = request.tenant
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ctx = {
            'open_work_orders': MESWorkOrder.objects.filter(
                tenant=t, status__in=('dispatched', 'in_progress', 'on_hold'),
            ).count(),
            'in_progress_ops': MESWorkOrderOperation.objects.filter(
                tenant=t, status__in=('running', 'paused', 'setup'),
            ).count(),
            'completed_today': MESWorkOrder.objects.filter(
                tenant=t, status='completed', completed_at__gte=today_start,
            ).count(),
            'open_andon': AndonAlert.objects.filter(tenant=t, status='open').count(),
            'critical_andon': AndonAlert.objects.filter(
                tenant=t, status='open', severity='critical',
            ).count(),
            'today_good_qty': ProductionReport.objects.filter(
                tenant=t, reported_at__gte=today_start,
            ).aggregate(s=Sum('good_qty'))['s'] or 0,
            'today_scrap_qty': ProductionReport.objects.filter(
                tenant=t, reported_at__gte=today_start,
            ).aggregate(s=Sum('scrap_qty'))['s'] or 0,
            'recent_work_orders': MESWorkOrder.objects.filter(
                tenant=t,
            ).select_related('product').order_by('-created_at')[:6],
            'recent_andon': AndonAlert.objects.filter(
                tenant=t, status__in=('open', 'acknowledged'),
            ).select_related('work_center').order_by('-severity', '-raised_at')[:8],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 6.1  WORK ORDERS
# ============================================================================

class WorkOrderListView(TenantRequiredMixin, ListView):
    model = MESWorkOrder
    template_name = 'mes/work_orders/list.html'
    context_object_name = 'work_orders'
    paginate_by = 20

    def get_queryset(self):
        qs = MESWorkOrder.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'production_order')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(wo_number__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product__name__icontains=q)
                | Q(production_order__order_number__icontains=q)
            )
        for field in ('status', 'priority'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = MESWorkOrder.STATUS_CHOICES
        ctx['priority_choices'] = MESWorkOrder.PRIORITY_CHOICES
        return ctx


class WorkOrderDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        wo = get_object_or_404(
            MESWorkOrder.objects.select_related('product', 'production_order'),
            pk=pk, tenant=request.tenant,
        )
        ops = wo.operations.select_related('work_center', 'current_operator').order_by('sequence')
        rollup = reporting.rollup_work_order(wo)
        recent_reports = ProductionReport.objects.filter(
            tenant=request.tenant, work_order_operation__work_order=wo,
        ).select_related('work_order_operation', 'reported_by').order_by('-reported_at')[:10]
        andon_alerts = AndonAlert.objects.filter(
            tenant=request.tenant, work_order=wo,
        ).order_by('-severity', '-raised_at')
        return render(request, 'mes/work_orders/detail.html', {
            'wo': wo, 'ops': ops, 'rollup': rollup,
            'recent_reports': recent_reports, 'andon_alerts': andon_alerts,
        })


class WorkOrderEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        wo = get_object_or_404(MESWorkOrder, pk=pk, tenant=request.tenant)
        if not wo.is_editable():
            messages.warning(request, 'Work order is no longer editable in this status.')
            return redirect('mes:work_order_detail', pk=pk)
        return render(request, 'mes/work_orders/form.html', {
            'form': MESWorkOrderForm(instance=wo), 'wo': wo,
        })

    def post(self, request, pk):
        wo = get_object_or_404(MESWorkOrder, pk=pk, tenant=request.tenant)
        if not wo.is_editable():
            messages.warning(request, 'Work order is no longer editable in this status.')
            return redirect('mes:work_order_detail', pk=pk)
        form = MESWorkOrderForm(request.POST, instance=wo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Work order updated.')
            return redirect('mes:work_order_detail', pk=wo.pk)
        return render(request, 'mes/work_orders/form.html', {'form': form, 'wo': wo})


class WorkOrderDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        wo = get_object_or_404(MESWorkOrder, pk=pk, tenant=request.tenant)
        if wo.status == 'in_progress':
            messages.error(request, 'In-progress work orders cannot be deleted - cancel first.')
            return redirect('mes:work_order_detail', pk=pk)
        try:
            wo.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - work order is referenced by other records.')
            return redirect('mes:work_order_detail', pk=pk)
        messages.success(request, 'Work order deleted.')
        return redirect('mes:work_order_list')


class WorkOrderStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        wo = get_object_or_404(MESWorkOrder, pk=pk, tenant=request.tenant)
        if not wo.can_start():
            messages.warning(request, 'Work order cannot be started in its current state.')
            return redirect('mes:work_order_detail', pk=pk)
        ok = _atomic_status_transition(
            MESWorkOrder, pk, request.tenant,
            ['dispatched', 'on_hold'], 'in_progress',
        )
        msg = 'Work order started.' if ok else 'Could not transition work order.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mes:work_order_detail', pk=pk)


class WorkOrderHoldView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MESWorkOrder, pk, request.tenant, ['in_progress'], 'on_hold',
        )
        msg = 'Work order placed on hold.' if ok else 'Only in-progress orders can be held.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mes:work_order_detail', pk=pk)


class WorkOrderCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MESWorkOrder, pk, request.tenant, ['in_progress'], 'completed',
            extra_fields={'completed_at': timezone.now()},
        )
        if ok:
            MESWorkOrder.objects.filter(pk=pk).update(completed_by=request.user)
            messages.success(request, 'Work order completed.')
        else:
            messages.warning(request, 'Only in-progress orders can be completed.')
        return redirect('mes:work_order_detail', pk=pk)


class WorkOrderCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MESWorkOrder, pk, request.tenant,
            ['dispatched', 'in_progress', 'on_hold'], 'cancelled',
        )
        msg = 'Work order cancelled.' if ok else 'Work order cannot be cancelled now.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mes:work_order_detail', pk=pk)


class DispatchView(TenantAdminRequiredMixin, View):
    """POST-only dispatch endpoint - usually invoked from the PPS order detail page."""
    def post(self, request, production_order_pk):
        po = get_object_or_404(
            ProductionOrder, pk=production_order_pk, tenant=request.tenant,
        )
        try:
            wo = dispatcher.dispatch_production_order(po, dispatched_by=request.user)
        except dispatcher.DispatchError as exc:
            messages.error(request, f'Dispatch failed: {exc}')
            return redirect('pps:order_detail', pk=po.pk)
        messages.success(request, f'Production order {po.order_number} dispatched as {wo.wo_number}.')
        return redirect('mes:work_order_detail', pk=wo.pk)


# ============================================================================
# 6.1  WORK ORDER OPERATIONS
# ============================================================================

class OperationDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        op = get_object_or_404(
            MESWorkOrderOperation.objects.select_related(
                'work_order__product', 'work_center', 'current_operator',
            ),
            pk=pk, tenant=request.tenant,
        )
        time_logs = op.time_logs.select_related('operator__user').order_by('-recorded_at')[:30]
        reports = op.production_reports.select_related('reported_by').order_by('-reported_at')
        return render(request, 'mes/work_orders/operation_detail.html', {
            'op': op, 'time_logs': time_logs, 'reports': reports,
        })


def _get_operator(request):
    """Return the request.user's ShopFloorOperator profile, or None."""
    return ShopFloorOperator.objects.filter(
        tenant=request.tenant, user=request.user, is_active=True,
    ).first()


class OperationStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(MESWorkOrderOperation, pk=pk, tenant=request.tenant)
        if not op.can_start():
            messages.warning(request, 'Operation cannot be started from its current state.')
            return redirect('mes:operation_detail', pk=pk)
        operator = _get_operator(request)
        if operator is None:
            messages.error(request, 'You need a shop-floor operator profile to start jobs.')
            return redirect('mes:operation_detail', pk=pk)
        time_logging.record_event(operator, 'start_job', work_order_operation=op)
        messages.success(request, 'Job started.')
        return redirect('mes:operation_detail', pk=pk)


class OperationPauseView(TenantRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(MESWorkOrderOperation, pk=pk, tenant=request.tenant)
        operator = _get_operator(request)
        if operator is None:
            messages.error(request, 'You need a shop-floor operator profile to pause jobs.')
            return redirect('mes:operation_detail', pk=pk)
        if not op.can_pause():
            messages.warning(request, 'Operation cannot be paused now.')
            return redirect('mes:operation_detail', pk=pk)
        time_logging.record_event(operator, 'pause_job', work_order_operation=op)
        messages.success(request, 'Job paused.')
        return redirect('mes:operation_detail', pk=pk)


class OperationResumeView(TenantRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(MESWorkOrderOperation, pk=pk, tenant=request.tenant)
        operator = _get_operator(request)
        if operator is None:
            messages.error(request, 'You need a shop-floor operator profile to resume jobs.')
            return redirect('mes:operation_detail', pk=pk)
        if not op.can_resume():
            messages.warning(request, 'Operation cannot be resumed now.')
            return redirect('mes:operation_detail', pk=pk)
        time_logging.record_event(operator, 'resume_job', work_order_operation=op)
        messages.success(request, 'Job resumed.')
        return redirect('mes:operation_detail', pk=pk)


class OperationStopView(TenantRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(MESWorkOrderOperation, pk=pk, tenant=request.tenant)
        operator = _get_operator(request)
        if operator is None:
            messages.error(request, 'You need a shop-floor operator profile to stop jobs.')
            return redirect('mes:operation_detail', pk=pk)
        if not op.can_stop():
            messages.warning(request, 'Operation cannot be stopped now.')
            return redirect('mes:operation_detail', pk=pk)
        time_logging.record_event(operator, 'stop_job', work_order_operation=op)
        messages.success(request, 'Job stopped.')
        return redirect('mes:operation_detail', pk=pk)


# ============================================================================
# 6.2  TERMINAL & OPERATORS
# ============================================================================

class TerminalView(TenantRequiredMixin, View):
    """Touchscreen kiosk landing page for the current operator."""
    def get(self, request):
        operator = _get_operator(request)
        if operator is None:
            messages.warning(
                request,
                'No shop-floor operator profile is linked to your account. '
                'Ask a tenant admin to create one.'
            )
            return redirect('mes:index')
        my_open_ops = MESWorkOrderOperation.objects.filter(
            tenant=request.tenant,
            status__in=('pending', 'setup', 'running', 'paused'),
            work_order__status__in=('dispatched', 'in_progress', 'on_hold'),
        ).select_related('work_order__product', 'work_center').order_by(
            'work_order__priority', 'work_order__wo_number', 'sequence',
        )
        clock_state = (
            OperatorTimeLog.objects.filter(
                tenant=request.tenant, operator=operator,
                action__in=('clock_in', 'clock_out'),
            ).order_by('-recorded_at').values_list('action', flat=True).first()
        )
        is_clocked_in = clock_state == 'clock_in'
        return render(request, 'mes/terminal/index.html', {
            'operator': operator, 'open_ops': my_open_ops,
            'is_clocked_in': is_clocked_in,
        })


class OperatorClockInView(TenantRequiredMixin, View):
    def post(self, request, pk):
        operator = get_object_or_404(ShopFloorOperator, pk=pk, tenant=request.tenant)
        if request.user != operator.user and not request.user.is_tenant_admin:
            messages.error(request, 'You can only clock in / out yourself.')
            return redirect('mes:terminal')
        time_logging.record_event(operator, 'clock_in')
        messages.success(request, f'{operator.badge_number} clocked in.')
        return redirect('mes:terminal')


class OperatorClockOutView(TenantRequiredMixin, View):
    def post(self, request, pk):
        operator = get_object_or_404(ShopFloorOperator, pk=pk, tenant=request.tenant)
        if request.user != operator.user and not request.user.is_tenant_admin:
            messages.error(request, 'You can only clock in / out yourself.')
            return redirect('mes:terminal')
        time_logging.record_event(operator, 'clock_out')
        messages.success(request, f'{operator.badge_number} clocked out.')
        return redirect('mes:terminal')


class OperatorListView(TenantRequiredMixin, ListView):
    model = ShopFloorOperator
    template_name = 'mes/operators/list.html'
    context_object_name = 'operators'
    paginate_by = 25

    def get_queryset(self):
        qs = ShopFloorOperator.objects.filter(
            tenant=self.request.tenant,
        ).select_related('user', 'default_work_center')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(badge_number__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('badge_number')


class OperatorCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'mes/operators/form.html', {
            'form': ShopFloorOperatorForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ShopFloorOperatorForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Operator profile created.')
            return redirect('mes:operator_list')
        return render(request, 'mes/operators/form.html', {'form': form})


class OperatorDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        op = get_object_or_404(
            ShopFloorOperator.objects.select_related('user', 'default_work_center'),
            pk=pk, tenant=request.tenant,
        )
        recent_logs = op.time_logs.select_related('work_order_operation__work_order').order_by('-recorded_at')[:25]
        return render(request, 'mes/operators/detail.html', {
            'operator': op, 'recent_logs': recent_logs,
        })


class OperatorEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        op = get_object_or_404(ShopFloorOperator, pk=pk, tenant=request.tenant)
        return render(request, 'mes/operators/form.html', {
            'form': ShopFloorOperatorForm(instance=op, tenant=request.tenant),
            'operator': op,
        })

    def post(self, request, pk):
        op = get_object_or_404(ShopFloorOperator, pk=pk, tenant=request.tenant)
        form = ShopFloorOperatorForm(request.POST, instance=op, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Operator profile updated.')
            return redirect('mes:operator_detail', pk=op.pk)
        return render(request, 'mes/operators/form.html', {'form': form, 'operator': op})


class OperatorDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(ShopFloorOperator, pk=pk, tenant=request.tenant)
        try:
            op.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - operator has time-log history.')
            return redirect('mes:operator_detail', pk=pk)
        messages.success(request, 'Operator deleted.')
        return redirect('mes:operator_list')


# ============================================================================
# 6.2  TIME LOGS (read-only list)
# ============================================================================

class TimeLogListView(TenantRequiredMixin, ListView):
    model = OperatorTimeLog
    template_name = 'mes/time_logs/list.html'
    context_object_name = 'time_logs'
    paginate_by = 30

    def get_queryset(self):
        qs = OperatorTimeLog.objects.filter(
            tenant=self.request.tenant,
        ).select_related(
            'operator__user', 'work_order_operation__work_order',
        )
        for field in ('operator', 'action'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{f'{field}_id' if field == 'operator' else field: v})
        return qs.order_by('-recorded_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action_choices'] = OperatorTimeLog.ACTION_CHOICES
        ctx['operators'] = ShopFloorOperator.objects.filter(
            tenant=self.request.tenant,
        ).select_related('user').order_by('badge_number')
        return ctx


# ============================================================================
# 6.3  PRODUCTION REPORTS
# ============================================================================

class ReportListView(TenantRequiredMixin, ListView):
    model = ProductionReport
    template_name = 'mes/reports/list.html'
    context_object_name = 'reports'
    paginate_by = 25

    def get_queryset(self):
        qs = ProductionReport.objects.filter(
            tenant=self.request.tenant,
        ).select_related(
            'work_order_operation__work_order__product', 'reported_by',
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(work_order_operation__work_order__wo_number__icontains=q)
                | Q(work_order_operation__work_order__product__sku__icontains=q)
                | Q(notes__icontains=q)
            )
        reason = self.request.GET.get('scrap_reason', '')
        if reason:
            qs = qs.filter(scrap_reason=reason)
        return qs.order_by('-reported_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['scrap_reason_choices'] = ProductionReport.SCRAP_REASON_CHOICES
        return ctx


class ReportCreateView(TenantRequiredMixin, View):
    """Operators (any tenant user) can file reports against any open op of their tenant."""
    def get(self, request):
        op_id = request.GET.get('op')
        op = None
        if op_id:
            op = MESWorkOrderOperation.objects.filter(
                tenant=request.tenant, pk=op_id,
            ).select_related('work_order__product').first()
        ops = MESWorkOrderOperation.objects.filter(
            tenant=request.tenant,
            status__in=('running', 'paused', 'setup', 'pending', 'completed'),
        ).select_related('work_order__product').order_by(
            '-work_order__created_at', 'sequence',
        )[:200]
        return render(request, 'mes/reports/form.html', {
            'form': ProductionReportForm(),
            'preselected_op': op, 'ops': ops,
        })

    def post(self, request):
        op_id = request.POST.get('work_order_operation')
        op = get_object_or_404(MESWorkOrderOperation, pk=op_id, tenant=request.tenant)
        form = ProductionReportForm(request.POST)
        if form.is_valid():
            try:
                reporting.record_production(
                    op,
                    good=form.cleaned_data['good_qty'],
                    scrap=form.cleaned_data['scrap_qty'],
                    rework=form.cleaned_data['rework_qty'],
                    scrap_reason=form.cleaned_data.get('scrap_reason') or '',
                    reported_by=request.user,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('mes:report_create')
            messages.success(request, 'Production report filed.')
            return redirect('mes:operation_detail', pk=op.pk)
        ops = MESWorkOrderOperation.objects.filter(
            tenant=request.tenant,
        ).select_related('work_order__product')[:200]
        return render(request, 'mes/reports/form.html', {
            'form': form, 'preselected_op': op, 'ops': ops,
        })


class ReportDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rpt = get_object_or_404(
            ProductionReport.objects.select_related(
                'work_order_operation__work_order__product', 'reported_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'mes/reports/detail.html', {'rpt': rpt})


class ReportDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rpt = get_object_or_404(ProductionReport, pk=pk, tenant=request.tenant)
        op = rpt.work_order_operation
        # Adjust the parent op denorms by subtracting the deleted report's qtys
        op.total_good_qty = max(op.total_good_qty - rpt.good_qty, 0)
        op.total_scrap_qty = max(op.total_scrap_qty - rpt.scrap_qty, 0)
        op.total_rework_qty = max(op.total_rework_qty - rpt.rework_qty, 0)
        op.save()
        rpt.delete()
        # Recompute the work order rollup
        wo = op.work_order
        agg = MESWorkOrderOperation.objects.filter(work_order=wo).aggregate(
            good=Sum('total_good_qty'), scrap=Sum('total_scrap_qty'),
        )
        wo.quantity_completed = agg['good'] or 0
        wo.quantity_scrapped = agg['scrap'] or 0
        wo.save()
        messages.success(request, 'Production report deleted.')
        return redirect('mes:report_list')


# ============================================================================
# 6.4  ANDON ALERTS
# ============================================================================

class AndonListView(TenantRequiredMixin, ListView):
    model = AndonAlert
    template_name = 'mes/andon/list.html'
    context_object_name = 'alerts'
    paginate_by = 25

    def get_queryset(self):
        qs = AndonAlert.objects.filter(
            tenant=self.request.tenant,
        ).select_related('work_center', 'work_order', 'raised_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(alert_number__icontains=q)
                | Q(title__icontains=q)
                | Q(message__icontains=q)
            )
        for field in ('alert_type', 'severity', 'status'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('-severity', '-raised_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['type_choices'] = AndonAlert.ALERT_TYPE_CHOICES
        ctx['severity_choices'] = AndonAlert.SEVERITY_CHOICES
        ctx['status_choices'] = AndonAlert.STATUS_CHOICES
        return ctx


class AndonCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'mes/andon/form.html', {
            'form': AndonAlertForm(tenant=request.tenant),
        })

    def post(self, request):
        form = AndonAlertForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.alert_number = _next_sequence_number(
                    AndonAlert.objects.filter(tenant=request.tenant),
                    'alert_number', 'AND',
                )
                obj.raised_by = request.user
                obj.raised_at = timezone.now()
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'Andon alert {obj.alert_number} raised.')
            return redirect('mes:andon_detail', pk=obj.pk)
        return render(request, 'mes/andon/form.html', {'form': form})


class AndonDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        a = get_object_or_404(
            AndonAlert.objects.select_related(
                'work_center', 'work_order', 'work_order_operation',
                'raised_by', 'acknowledged_by', 'resolved_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'mes/andon/detail.html', {
            'alert': a, 'resolve_form': AndonResolveForm(instance=a),
        })


class AndonEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        a = get_object_or_404(AndonAlert, pk=pk, tenant=request.tenant)
        if a.status not in ('open', 'acknowledged'):
            messages.warning(request, 'Andon alert can only be edited while open.')
            return redirect('mes:andon_detail', pk=pk)
        return render(request, 'mes/andon/form.html', {
            'form': AndonAlertForm(instance=a, tenant=request.tenant), 'alert': a,
        })

    def post(self, request, pk):
        a = get_object_or_404(AndonAlert, pk=pk, tenant=request.tenant)
        if a.status not in ('open', 'acknowledged'):
            messages.warning(request, 'Andon alert can only be edited while open.')
            return redirect('mes:andon_detail', pk=pk)
        form = AndonAlertForm(request.POST, instance=a, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Andon alert updated.')
            return redirect('mes:andon_detail', pk=a.pk)
        return render(request, 'mes/andon/form.html', {'form': form, 'alert': a})


class AndonAcknowledgeView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            AndonAlert, pk, request.tenant, ['open'], 'acknowledged',
            extra_fields={'acknowledged_at': timezone.now()},
        )
        if ok:
            AndonAlert.objects.filter(pk=pk).update(acknowledged_by=request.user)
            messages.success(request, 'Alert acknowledged.')
        else:
            messages.warning(request, 'Only open alerts can be acknowledged.')
        return redirect('mes:andon_detail', pk=pk)


class AndonResolveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        a = get_object_or_404(AndonAlert, pk=pk, tenant=request.tenant)
        if not a.can_resolve():
            messages.warning(request, 'Alert is already resolved or cancelled.')
            return redirect('mes:andon_detail', pk=pk)
        form = AndonResolveForm(request.POST, instance=a)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.status = 'resolved'
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
            obj.save()
            messages.success(request, 'Alert resolved.')
        else:
            messages.error(request, 'Please add a resolution note.')
        return redirect('mes:andon_detail', pk=pk)


class AndonCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            AndonAlert, pk, request.tenant,
            ['open', 'acknowledged'], 'cancelled',
        )
        msg = 'Alert cancelled.' if ok else 'Alert cannot be cancelled now.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mes:andon_detail', pk=pk)


class AndonDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        a = get_object_or_404(AndonAlert, pk=pk, tenant=request.tenant)
        a.delete()
        messages.success(request, 'Andon alert deleted.')
        return redirect('mes:andon_list')


# ============================================================================
# 6.5  WORK INSTRUCTIONS
# ============================================================================

class InstructionListView(TenantRequiredMixin, ListView):
    model = WorkInstruction
    template_name = 'mes/instructions/list.html'
    context_object_name = 'instructions'
    paginate_by = 20

    def get_queryset(self):
        qs = WorkInstruction.objects.filter(
            tenant=self.request.tenant,
        ).select_related(
            'routing_operation__routing__product', 'product', 'current_version',
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(instruction_number__icontains=q)
                | Q(title__icontains=q)
            )
        for field in ('doc_type', 'status'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.order_by('instruction_number')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doc_type_choices'] = WorkInstruction.DOC_TYPE_CHOICES
        ctx['status_choices'] = WorkInstruction.STATUS_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class InstructionCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'mes/instructions/form.html', {
            'form': WorkInstructionForm(tenant=request.tenant),
        })

    def post(self, request):
        form = WorkInstructionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.created_by = request.user
                obj.instruction_number = _next_sequence_number(
                    WorkInstruction.objects.filter(tenant=request.tenant),
                    'instruction_number', 'SOP',
                )
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(
                request,
                f'Instruction {obj.instruction_number} created. Add a version to release it.',
            )
            return redirect('mes:instruction_detail', pk=obj.pk)
        return render(request, 'mes/instructions/form.html', {'form': form})


class InstructionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        wi = get_object_or_404(
            WorkInstruction.objects.select_related(
                'routing_operation__routing', 'product', 'current_version',
                'created_by', 'released_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        versions = wi.versions.order_by('-created_at')
        my_ack = WorkInstructionAcknowledgement.objects.filter(
            tenant=request.tenant, instruction=wi, user=request.user,
            instruction_version=(wi.current_version.version if wi.current_version else ''),
        ).first()
        return render(request, 'mes/instructions/detail.html', {
            'instruction': wi, 'versions': versions, 'my_ack': my_ack,
            'ack_form': WorkInstructionAcknowledgementForm(),
        })


class InstructionEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        wi = get_object_or_404(WorkInstruction, pk=pk, tenant=request.tenant)
        return render(request, 'mes/instructions/form.html', {
            'form': WorkInstructionForm(instance=wi, tenant=request.tenant),
            'instruction': wi,
        })

    def post(self, request, pk):
        wi = get_object_or_404(WorkInstruction, pk=pk, tenant=request.tenant)
        form = WorkInstructionForm(request.POST, instance=wi, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Instruction updated.')
            return redirect('mes:instruction_detail', pk=wi.pk)
        return render(request, 'mes/instructions/form.html', {
            'form': form, 'instruction': wi,
        })


class InstructionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        wi = get_object_or_404(WorkInstruction, pk=pk, tenant=request.tenant)
        try:
            wi.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - instruction is referenced.')
            return redirect('mes:instruction_detail', pk=pk)
        messages.success(request, 'Instruction deleted.')
        return redirect('mes:instruction_list')


class InstructionVersionCreateView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        wi = get_object_or_404(WorkInstruction, pk=pk, tenant=request.tenant)
        return render(request, 'mes/instructions/version_form.html', {
            'form': WorkInstructionVersionForm(tenant=request.tenant, instruction=wi),
            'instruction': wi,
        })

    def post(self, request, pk):
        wi = get_object_or_404(WorkInstruction, pk=pk, tenant=request.tenant)
        form = WorkInstructionVersionForm(
            request.POST, request.FILES,
            tenant=request.tenant, instruction=wi,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.instruction = wi
            obj.uploaded_by = request.user
            obj.save()
            messages.success(request, f'Version {obj.version} added (draft). Release it to publish.')
            return redirect('mes:instruction_detail', pk=wi.pk)
        return render(request, 'mes/instructions/version_form.html', {
            'form': form, 'instruction': wi,
        })


class InstructionVersionReleaseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        v = get_object_or_404(
            WorkInstructionVersion.objects.select_related('instruction'),
            pk=pk, tenant=request.tenant,
        )
        wi = v.instruction
        with transaction.atomic():
            # Obsolete prior released versions
            WorkInstructionVersion.objects.filter(
                instruction=wi, status='released',
            ).exclude(pk=v.pk).update(status='obsolete')
            v.status = 'released'
            v.save()
            wi.current_version = v
            wi.status = 'released'
            wi.released_by = request.user
            wi.released_at = timezone.now()
            wi.save()
        messages.success(request, f'Version {v.version} released.')
        return redirect('mes:instruction_detail', pk=wi.pk)


class InstructionVersionObsoleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        v = get_object_or_404(
            WorkInstructionVersion.objects.select_related('instruction'),
            pk=pk, tenant=request.tenant,
        )
        wi = v.instruction
        v.status = 'obsolete'
        v.save()
        if wi.current_version_id == v.pk:
            wi.current_version = None
            wi.status = 'obsolete'
            wi.save()
        messages.success(request, f'Version {v.version} marked obsolete.')
        return redirect('mes:instruction_detail', pk=wi.pk)


class InstructionVersionDownloadView(TenantRequiredMixin, View):
    """Auth-gated download. Mirrors apps/plm/views.py CADVersionDownloadView."""
    def get(self, request, pk):
        v = get_object_or_404(
            WorkInstructionVersion.objects.select_related('instruction'),
            pk=pk, tenant=request.tenant,
        )
        if not v.attachment:
            raise Http404
        try:
            handle = v.attachment.open('rb')
        except FileNotFoundError as exc:
            raise Http404 from exc
        filename = os.path.basename(v.attachment.name)
        response = FileResponse(handle, as_attachment=True, filename=filename)
        return response


class InstructionAcknowledgeView(TenantRequiredMixin, View):
    def post(self, request, pk):
        wi = get_object_or_404(
            WorkInstruction.objects.select_related('current_version'),
            pk=pk, tenant=request.tenant,
        )
        if wi.current_version is None:
            messages.error(request, 'Cannot acknowledge - no released version.')
            return redirect('mes:instruction_detail', pk=pk)
        form = WorkInstructionAcknowledgementForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Type your name to confirm acknowledgement.')
            return redirect('mes:instruction_detail', pk=pk)
        try:
            WorkInstructionAcknowledgement.objects.create(
                tenant=request.tenant,
                instruction=wi,
                instruction_version=wi.current_version.version,
                user=request.user,
                signature_text=form.cleaned_data['signature_text'],
            )
            messages.success(request, 'Acknowledgement recorded.')
        except IntegrityError:
            messages.info(request, 'You have already acknowledged this version.')
        return redirect('mes:instruction_detail', pk=pk)
