"""Quality Management views - full CRUD + workflow + SPC + CoA + Calibration.

Every view filters by ``request.tenant``. Workflow transitions use a
conditional UPDATE so concurrent reviewers cannot double-action. The heavy
work (AQL plan lookup, SPC limit math, CoA payload) lives in
``apps/qms/services/``.

Production hardening:
    Auth-gated download views (NCRAttachmentDownloadView,
    CalibrationCertificateDownloadView) verify tenant ownership via
    ``get_object_or_404(..., tenant=request.tenant)`` then stream via
    ``FileResponse``. Templates link to these via ``{% url %}`` rather than
    ``.file.url``, so a guessed ``/media/qms/...`` path would still hit the
    static mount in DEBUG but is never produced by the application.

    For production deploys, remove the ``static(MEDIA_URL, ...)`` mount
    in config/urls.py when DEBUG=False and configure the web server
    (Nginx ``internal;`` + ``X-Accel-Redirect``, or Apache ``mod_xsendfile``)
    to serve ``MEDIA_ROOT/qms/*`` ONLY via the auth-gated views.
"""
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin
from apps.mes.models import MESWorkOrder
from apps.plm.models import Product
from apps.pps.models import RoutingOperation, WorkCenter

from .forms import (
    CalibrationRecordForm, CalibrationStandardForm,
    CertificateOfAnalysisForm, CorrectiveActionForm, FinalInspectionForm,
    FinalInspectionPlanForm, FinalTestResultForm, FinalTestSpecForm,
    IncomingInspectionForm, IncomingInspectionPlanForm,
    InspectionCharacteristicForm, InspectionMeasurementForm,
    MeasurementEquipmentForm, NCRAttachmentForm, NCRCloseForm,
    NonConformanceReportForm, PreventiveActionForm, ProcessInspectionForm,
    ProcessInspectionPlanForm, RootCauseAnalysisForm, ToleranceVerificationForm,
)
from .models import (
    CalibrationRecord, CalibrationStandard, CertificateOfAnalysis,
    ControlChartPoint, CorrectiveAction, FinalInspection, FinalInspectionPlan,
    FinalTestResult, FinalTestSpec, IncomingInspection,
    IncomingInspectionPlan, InspectionCharacteristic, InspectionMeasurement,
    MeasurementEquipment, NCRAttachment, NonConformanceReport,
    PreventiveAction, ProcessInspection, ProcessInspectionPlan,
    RootCauseAnalysis, SPCChart, ToleranceVerification,
)
from .services import aql as aql_service
from .services import coa as coa_service
from .services import spc as spc_service


# ============================================================================
# Helpers (mirror the MES / MRP pattern)
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

class QMSIndexView(TenantRequiredMixin, View):
    template_name = 'qms/index.html'

    def get(self, request):
        t = request.tenant
        now = timezone.now()
        soon_cutoff = now + timedelta(days=7)
        ctx = {
            'open_ncrs': NonConformanceReport.objects.filter(
                tenant=t, status__in=('open', 'investigating', 'awaiting_capa'),
            ).count(),
            'critical_ncrs': NonConformanceReport.objects.filter(
                tenant=t, severity='critical',
                status__in=('open', 'investigating', 'awaiting_capa'),
            ).count(),
            'iqc_pending': IncomingInspection.objects.filter(
                tenant=t, status__in=('pending', 'in_inspection'),
            ).count(),
            'fqc_pending': FinalInspection.objects.filter(
                tenant=t, status__in=('pending', 'in_inspection'),
            ).count(),
            'equipment_due_soon': MeasurementEquipment.objects.filter(
                tenant=t, is_active=True, status='active',
                next_due_at__lte=soon_cutoff,
            ).count(),
            'equipment_overdue': MeasurementEquipment.objects.filter(
                tenant=t, is_active=True, status='active',
                next_due_at__lt=now,
            ).count(),
            'open_capas': CorrectiveAction.objects.filter(
                tenant=t, status__in=('open', 'in_progress'),
            ).count(),
            'recent_ncrs': NonConformanceReport.objects.filter(
                tenant=t,
            ).select_related('product').order_by('-reported_at')[:6],
            'open_capa_rows': CorrectiveAction.objects.filter(
                tenant=t, status__in=('open', 'in_progress'),
            ).select_related('ncr', 'owner').order_by('due_date')[:8],
            'due_equipment': MeasurementEquipment.objects.filter(
                tenant=t, is_active=True, status='active',
            ).order_by('next_due_at')[:8],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 7.1  IQC PLANS
# ============================================================================

class IQCPlanListView(TenantRequiredMixin, ListView):
    model = IncomingInspectionPlan
    template_name = 'qms/iqc/plans/list.html'
    context_object_name = 'plans'
    paginate_by = 20

    def get_queryset(self):
        qs = IncomingInspectionPlan.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q)
                | Q(product__name__icontains=q)
                | Q(version__icontains=q)
            )
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('product__sku', 'version')


class IQCPlanCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/iqc/plans/form.html', {
            'form': IncomingInspectionPlanForm(tenant=request.tenant),
        })

    def post(self, request):
        form = IncomingInspectionPlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'IQC plan created.')
            return redirect('qms:iqc_plan_detail', pk=obj.pk)
        return render(request, 'qms/iqc/plans/form.html', {'form': form})


class IQCPlanDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(
            IncomingInspectionPlan.objects.select_related('product'),
            pk=pk, tenant=request.tenant,
        )
        chars = plan.characteristics.order_by('sequence')
        recent_inspections = plan.inspections.select_related(
            'product',
        ).order_by('-created_at')[:10]
        return render(request, 'qms/iqc/plans/detail.html', {
            'plan': plan,
            'characteristics': chars,
            'recent_inspections': recent_inspections,
            'characteristic_form': InspectionCharacteristicForm(),
        })


class IQCPlanEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(IncomingInspectionPlan, pk=pk, tenant=request.tenant)
        return render(request, 'qms/iqc/plans/form.html', {
            'form': IncomingInspectionPlanForm(instance=plan, tenant=request.tenant),
            'plan': plan,
        })

    def post(self, request, pk):
        plan = get_object_or_404(IncomingInspectionPlan, pk=pk, tenant=request.tenant)
        form = IncomingInspectionPlanForm(request.POST, instance=plan, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'IQC plan updated.')
            return redirect('qms:iqc_plan_detail', pk=plan.pk)
        return render(request, 'qms/iqc/plans/form.html', {'form': form, 'plan': plan})


class IQCPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(IncomingInspectionPlan, pk=pk, tenant=request.tenant)
        try:
            plan.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - plan is referenced by inspections.')
            return redirect('qms:iqc_plan_detail', pk=pk)
        messages.success(request, 'IQC plan deleted.')
        return redirect('qms:iqc_plan_list')


class IQCCharacteristicCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, plan_id):
        plan = get_object_or_404(IncomingInspectionPlan, pk=plan_id, tenant=request.tenant)
        form = InspectionCharacteristicForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.plan = plan
            obj.save()
            messages.success(request, 'Characteristic added.')
        else:
            messages.error(request, 'Could not add characteristic - check the form.')
        return redirect('qms:iqc_plan_detail', pk=plan.pk)


class IQCCharacteristicDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        c = get_object_or_404(InspectionCharacteristic, pk=pk, tenant=request.tenant)
        plan_pk = c.plan_id
        c.delete()
        messages.success(request, 'Characteristic removed.')
        return redirect('qms:iqc_plan_detail', pk=plan_pk)


# ============================================================================
# 7.1  IQC INSPECTIONS
# ============================================================================

class IQCInspectionListView(TenantRequiredMixin, ListView):
    model = IncomingInspection
    template_name = 'qms/iqc/inspections/list.html'
    context_object_name = 'inspections'
    paginate_by = 25

    def get_queryset(self):
        qs = IncomingInspection.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'plan')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(inspection_number__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(supplier_name__icontains=q)
                | Q(po_reference__icontains=q)
                | Q(lot_number__icontains=q)
            )
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = IncomingInspection.STATUS_CHOICES
        return ctx


class IQCInspectionCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/iqc/inspections/form.html', {
            'form': IncomingInspectionForm(tenant=request.tenant),
        })

    def post(self, request):
        form = IncomingInspectionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.inspection_number = _next_sequence_number(
                    IncomingInspection.objects.filter(tenant=request.tenant),
                    'inspection_number', 'IQC',
                )
                # Apply AQL plan if linked
                if obj.plan and obj.received_qty:
                    plan_obj = obj.plan
                    try:
                        a = aql_service.lookup_plan(
                            int(obj.received_qty),
                            float(plan_obj.aql_value),
                            plan_obj.aql_level,
                        )
                        obj.sample_size = a.sample_size
                        obj.accept_number = a.accept_number
                        obj.reject_number = a.reject_number
                    except (ValueError, KeyError):
                        pass
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(
                request,
                f'IQC inspection {obj.inspection_number} created '
                f'(sample size {obj.sample_size}, accept up to {obj.accept_number}).',
            )
            return redirect('qms:iqc_inspection_detail', pk=obj.pk)
        return render(request, 'qms/iqc/inspections/form.html', {'form': form})


class IQCInspectionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        inspection = get_object_or_404(
            IncomingInspection.objects.select_related('product', 'plan'),
            pk=pk, tenant=request.tenant,
        )
        characteristics = []
        if inspection.plan_id:
            characteristics = list(
                inspection.plan.characteristics.order_by('sequence')
            )
        existing_measurements = {
            m.characteristic_id: m
            for m in inspection.measurements.all()
        }
        rows = []
        for c in characteristics:
            rows.append({
                'characteristic': c,
                'measurement': existing_measurements.get(c.pk),
            })
        ncrs = inspection.ncrs.order_by('-reported_at')
        return render(request, 'qms/iqc/inspections/detail.html', {
            'inspection': inspection,
            'rows': rows,
            'measurement_form': InspectionMeasurementForm(),
            'ncrs': ncrs,
        })


class IQCInspectionEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        i = get_object_or_404(IncomingInspection, pk=pk, tenant=request.tenant)
        if not i.is_editable():
            messages.warning(request, 'Inspection is no longer editable in this status.')
            return redirect('qms:iqc_inspection_detail', pk=pk)
        return render(request, 'qms/iqc/inspections/form.html', {
            'form': IncomingInspectionForm(instance=i, tenant=request.tenant),
            'inspection': i,
        })

    def post(self, request, pk):
        i = get_object_or_404(IncomingInspection, pk=pk, tenant=request.tenant)
        if not i.is_editable():
            messages.warning(request, 'Inspection is no longer editable in this status.')
            return redirect('qms:iqc_inspection_detail', pk=pk)
        form = IncomingInspectionForm(request.POST, instance=i, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Inspection updated.')
            return redirect('qms:iqc_inspection_detail', pk=i.pk)
        return render(request, 'qms/iqc/inspections/form.html', {
            'form': form, 'inspection': i,
        })


class IQCInspectionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        i = get_object_or_404(IncomingInspection, pk=pk, tenant=request.tenant)
        if i.status not in ('pending', 'in_inspection'):
            messages.error(request, 'Cannot delete a completed IQC inspection.')
            return redirect('qms:iqc_inspection_detail', pk=pk)
        i.delete()
        messages.success(request, 'IQC inspection deleted.')
        return redirect('qms:iqc_inspection_list')


class IQCInspectionStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            IncomingInspection, pk, request.tenant,
            ['pending'], 'in_inspection',
            extra_fields={'inspected_at': timezone.now()},
        )
        if ok:
            IncomingInspection.objects.filter(pk=pk).update(inspected_by=request.user)
            messages.success(request, 'Inspection started.')
        else:
            messages.warning(request, 'Only pending inspections can be started.')
        return redirect('qms:iqc_inspection_detail', pk=pk)


class IQCInspectionAcceptView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            IncomingInspection, pk, request.tenant,
            ['in_inspection'], 'accepted',
        )
        msg = 'Inspection accepted.' if ok else 'Only in-inspection records can be accepted.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:iqc_inspection_detail', pk=pk)


class IQCInspectionRejectView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            IncomingInspection, pk, request.tenant,
            ['in_inspection'], 'rejected',
        )
        msg = 'Inspection rejected.' if ok else 'Only in-inspection records can be rejected.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:iqc_inspection_detail', pk=pk)


class IQCInspectionDeviationView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            IncomingInspection, pk, request.tenant,
            ['in_inspection'], 'accepted_with_deviation',
        )
        msg = 'Inspection released with deviation.' if ok else 'Cannot release - wrong status.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:iqc_inspection_detail', pk=pk)


class IQCMeasurementCreateView(TenantRequiredMixin, View):
    def post(self, request, inspection_id):
        inspection = get_object_or_404(IncomingInspection, pk=inspection_id, tenant=request.tenant)
        form = InspectionMeasurementForm(request.POST)
        if form.is_valid():
            char = form.cleaned_data['characteristic']
            try:
                with transaction.atomic():
                    InspectionMeasurement.objects.update_or_create(
                        tenant=request.tenant,
                        inspection=inspection,
                        characteristic=char,
                        defaults={
                            'measured_value': form.cleaned_data.get('measured_value'),
                            'is_pass': form.cleaned_data.get('is_pass', True),
                            'notes': form.cleaned_data.get('notes', ''),
                        },
                    )
                messages.success(request, 'Measurement saved.')
            except IntegrityError:
                messages.error(request, 'Could not save measurement.')
        else:
            messages.error(request, 'Invalid measurement.')
        return redirect('qms:iqc_inspection_detail', pk=inspection.pk)


# ============================================================================
# 7.2  IPQC PLANS
# ============================================================================

class IPQCPlanListView(TenantRequiredMixin, ListView):
    model = ProcessInspectionPlan
    template_name = 'qms/ipqc/plans/list.html'
    context_object_name = 'plans'
    paginate_by = 20

    def get_queryset(self):
        qs = ProcessInspectionPlan.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'routing_operation__routing')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(routing_operation__operation_name__icontains=q)
            )
        for field in ('chart_type', 'frequency'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('product__sku', 'routing_operation__sequence')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['chart_choices'] = ProcessInspectionPlan.CHART_CHOICES
        ctx['frequency_choices'] = ProcessInspectionPlan.FREQUENCY_CHOICES
        return ctx


class IPQCPlanCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/ipqc/plans/form.html', {
            'form': ProcessInspectionPlanForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProcessInspectionPlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            # Auto-create the chart shell so the detail page has it.
            if obj.chart_type != 'none':
                SPCChart.objects.get_or_create(
                    tenant=request.tenant, plan=obj,
                    defaults={'chart_type': obj.chart_type,
                              'subgroup_size': obj.subgroup_size},
                )
            messages.success(request, 'IPQC plan created.')
            return redirect('qms:ipqc_plan_detail', pk=obj.pk)
        return render(request, 'qms/ipqc/plans/form.html', {'form': form})


class IPQCPlanDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(
            ProcessInspectionPlan.objects.select_related(
                'product', 'routing_operation__routing',
            ),
            pk=pk, tenant=request.tenant,
        )
        chart = getattr(plan, 'spc_chart', None)
        recent_inspections = plan.inspections.select_related(
            'work_order_operation__work_order',
        ).order_by('-inspected_at')[:10]
        return render(request, 'qms/ipqc/plans/detail.html', {
            'plan': plan, 'chart': chart,
            'recent_inspections': recent_inspections,
        })


class IPQCPlanEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(ProcessInspectionPlan, pk=pk, tenant=request.tenant)
        return render(request, 'qms/ipqc/plans/form.html', {
            'form': ProcessInspectionPlanForm(instance=plan, tenant=request.tenant),
            'plan': plan,
        })

    def post(self, request, pk):
        plan = get_object_or_404(ProcessInspectionPlan, pk=pk, tenant=request.tenant)
        form = ProcessInspectionPlanForm(request.POST, instance=plan, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'IPQC plan updated.')
            return redirect('qms:ipqc_plan_detail', pk=plan.pk)
        return render(request, 'qms/ipqc/plans/form.html', {'form': form, 'plan': plan})


class IPQCPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(ProcessInspectionPlan, pk=pk, tenant=request.tenant)
        try:
            plan.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - plan has inspection history.')
            return redirect('qms:ipqc_plan_detail', pk=pk)
        messages.success(request, 'IPQC plan deleted.')
        return redirect('qms:ipqc_plan_list')


# ============================================================================
# 7.2  IPQC INSPECTIONS
# ============================================================================

class IPQCInspectionListView(TenantRequiredMixin, ListView):
    model = ProcessInspection
    template_name = 'qms/ipqc/inspections/list.html'
    context_object_name = 'inspections'
    paginate_by = 25

    def get_queryset(self):
        qs = ProcessInspection.objects.filter(
            tenant=self.request.tenant,
        ).select_related(
            'plan__product', 'work_order_operation__work_order', 'inspector',
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(inspection_number__icontains=q)
                | Q(plan__name__icontains=q)
                | Q(plan__product__sku__icontains=q)
            )
        result = self.request.GET.get('result', '')
        if result:
            qs = qs.filter(result=result)
        return qs.order_by('-inspected_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['result_choices'] = ProcessInspection.RESULT_CHOICES
        return ctx


class IPQCInspectionCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/ipqc/inspections/form.html', {
            'form': ProcessInspectionForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProcessInspectionForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.inspector = request.user
                obj.inspection_number = _next_sequence_number(
                    ProcessInspection.objects.filter(tenant=request.tenant),
                    'inspection_number', 'IPQC',
                )
                obj.save()
                # If the plan has a chart, push a control-chart point too.
                chart = SPCChart.objects.filter(plan=obj.plan).first()
                if chart and obj.measured_value is not None:
                    violations = []
                    is_ooc = False
                    if chart.cl is not None and chart.ucl is not None and chart.lcl is not None:
                        v = spc_service.check_western_electric(
                            [obj.measured_value], cl=chart.cl,
                            ucl=chart.ucl, lcl=chart.lcl,
                        )
                        violations = v[0] if v else []
                        is_ooc = spc_service.is_out_of_control(violations)
                    ControlChartPoint.objects.create(
                        tenant=request.tenant,
                        chart=chart,
                        inspection=obj,
                        subgroup_index=obj.subgroup_index,
                        value=obj.measured_value,
                        is_out_of_control=is_ooc,
                        rule_violations=violations,
                        recorded_at=obj.inspected_at,
                    )
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'IPQC inspection {obj.inspection_number} recorded.')
            return redirect('qms:ipqc_inspection_detail', pk=obj.pk)
        return render(request, 'qms/ipqc/inspections/form.html', {'form': form})


class IPQCInspectionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        i = get_object_or_404(
            ProcessInspection.objects.select_related(
                'plan__product', 'work_order_operation__work_order', 'inspector',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'qms/ipqc/inspections/detail.html', {
            'inspection': i,
            'ncrs': i.ncrs.order_by('-reported_at'),
        })


class IPQCInspectionEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        i = get_object_or_404(ProcessInspection, pk=pk, tenant=request.tenant)
        return render(request, 'qms/ipqc/inspections/form.html', {
            'form': ProcessInspectionForm(instance=i, tenant=request.tenant),
            'inspection': i,
        })

    def post(self, request, pk):
        i = get_object_or_404(ProcessInspection, pk=pk, tenant=request.tenant)
        form = ProcessInspectionForm(request.POST, request.FILES, instance=i, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'IPQC inspection updated.')
            return redirect('qms:ipqc_inspection_detail', pk=i.pk)
        return render(request, 'qms/ipqc/inspections/form.html', {
            'form': form, 'inspection': i,
        })


class IPQCInspectionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        i = get_object_or_404(ProcessInspection, pk=pk, tenant=request.tenant)
        i.delete()
        messages.success(request, 'IPQC inspection deleted.')
        return redirect('qms:ipqc_inspection_list')


# ============================================================================
# 7.2  SPC CHARTS
# ============================================================================

class SPCChartListView(TenantRequiredMixin, ListView):
    model = SPCChart
    template_name = 'qms/ipqc/charts/list.html'
    context_object_name = 'charts'
    paginate_by = 20

    def get_queryset(self):
        qs = SPCChart.objects.filter(
            tenant=self.request.tenant,
        ).select_related('plan__product', 'plan__routing_operation')
        return qs.order_by('plan__product__sku')


class SPCChartDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        chart = get_object_or_404(
            SPCChart.objects.select_related(
                'plan__product', 'plan__routing_operation',
            ),
            pk=pk, tenant=request.tenant,
        )
        points = list(chart.points.order_by('subgroup_index'))
        # Build series data for ApexCharts via json_script (Lesson L-07).
        series = [{
            'x': p.subgroup_index,
            'y': float(p.value),
            'is_ooc': p.is_out_of_control,
        } for p in points]
        return render(request, 'qms/ipqc/charts/detail.html', {
            'chart': chart, 'points': points, 'series': series,
        })


class SPCChartRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        chart = get_object_or_404(
            SPCChart.objects.select_related('plan'),
            pk=pk, tenant=request.tenant,
        )
        # Pull last 25 inspections for this plan with measured values.
        recent = list(
            chart.plan.inspections.filter(
                measured_value__isnull=False,
            ).order_by('-inspected_at')[:25 * chart.subgroup_size]
        )
        recent.reverse()
        # Bin into subgroups of size chart.subgroup_size.
        subgroups = []
        cur = []
        for ins in recent:
            cur.append(ins.measured_value)
            if len(cur) == chart.subgroup_size:
                subgroups.append(cur)
                cur = []
        if not subgroups:
            messages.warning(
                request,
                f'Need at least {chart.subgroup_size} measurements to compute limits.',
            )
            return redirect('qms:spc_chart_detail', pk=pk)
        try:
            limits = spc_service.compute_xbar_r(subgroups)
        except ValueError as exc:
            messages.error(request, f'Could not compute limits: {exc}')
            return redirect('qms:spc_chart_detail', pk=pk)
        chart.cl = limits.cl
        chart.ucl = limits.ucl
        chart.lcl = limits.lcl
        chart.cl_r = limits.cl_r
        chart.ucl_r = limits.ucl_r
        chart.lcl_r = limits.lcl_r
        chart.sample_size_used = limits.sample_size_used
        chart.recomputed_at = timezone.now()
        chart.save()
        messages.success(
            request,
            f'Recomputed limits from {limits.sample_size_used} subgroups.',
        )
        return redirect('qms:spc_chart_detail', pk=pk)


# ============================================================================
# 7.3  FQC PLANS
# ============================================================================

class FQCPlanListView(TenantRequiredMixin, ListView):
    model = FinalInspectionPlan
    template_name = 'qms/fqc/plans/list.html'
    context_object_name = 'plans'
    paginate_by = 20

    def get_queryset(self):
        qs = FinalInspectionPlan.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(product__sku__icontains=q))
        return qs.order_by('product__sku', 'version')


class FQCPlanCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/fqc/plans/form.html', {
            'form': FinalInspectionPlanForm(tenant=request.tenant),
        })

    def post(self, request):
        form = FinalInspectionPlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Final inspection plan created.')
            return redirect('qms:fqc_plan_detail', pk=obj.pk)
        return render(request, 'qms/fqc/plans/form.html', {'form': form})


class FQCPlanDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(
            FinalInspectionPlan.objects.select_related('product'),
            pk=pk, tenant=request.tenant,
        )
        specs = plan.specs.order_by('sequence')
        recent_inspections = plan.inspections.order_by('-created_at')[:10]
        return render(request, 'qms/fqc/plans/detail.html', {
            'plan': plan, 'specs': specs,
            'recent_inspections': recent_inspections,
            'spec_form': FinalTestSpecForm(),
        })


class FQCPlanEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        plan = get_object_or_404(FinalInspectionPlan, pk=pk, tenant=request.tenant)
        return render(request, 'qms/fqc/plans/form.html', {
            'form': FinalInspectionPlanForm(instance=plan, tenant=request.tenant),
            'plan': plan,
        })

    def post(self, request, pk):
        plan = get_object_or_404(FinalInspectionPlan, pk=pk, tenant=request.tenant)
        form = FinalInspectionPlanForm(request.POST, instance=plan, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Final inspection plan updated.')
            return redirect('qms:fqc_plan_detail', pk=plan.pk)
        return render(request, 'qms/fqc/plans/form.html', {'form': form, 'plan': plan})


class FQCPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(FinalInspectionPlan, pk=pk, tenant=request.tenant)
        try:
            plan.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - plan has inspection history.')
            return redirect('qms:fqc_plan_detail', pk=pk)
        messages.success(request, 'Plan deleted.')
        return redirect('qms:fqc_plan_list')


class FQCSpecCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, plan_id):
        plan = get_object_or_404(FinalInspectionPlan, pk=plan_id, tenant=request.tenant)
        form = FinalTestSpecForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.plan = plan
            obj.save()
            messages.success(request, 'Test spec added.')
        else:
            messages.error(request, 'Could not add spec - check the form.')
        return redirect('qms:fqc_plan_detail', pk=plan.pk)


class FQCSpecDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        s = get_object_or_404(FinalTestSpec, pk=pk, tenant=request.tenant)
        plan_pk = s.plan_id
        s.delete()
        messages.success(request, 'Spec removed.')
        return redirect('qms:fqc_plan_detail', pk=plan_pk)


# ============================================================================
# 7.3  FQC INSPECTIONS
# ============================================================================

class FQCInspectionListView(TenantRequiredMixin, ListView):
    model = FinalInspection
    template_name = 'qms/fqc/inspections/list.html'
    context_object_name = 'inspections'
    paginate_by = 25

    def get_queryset(self):
        qs = FinalInspection.objects.filter(
            tenant=self.request.tenant,
        ).select_related('plan__product', 'work_order')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(inspection_number__icontains=q)
                | Q(lot_number__icontains=q)
                | Q(plan__product__sku__icontains=q)
                | Q(work_order__wo_number__icontains=q)
            )
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = FinalInspection.STATUS_CHOICES
        return ctx


class FQCInspectionCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/fqc/inspections/form.html', {
            'form': FinalInspectionForm(tenant=request.tenant),
        })

    def post(self, request):
        form = FinalInspectionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.inspection_number = _next_sequence_number(
                    FinalInspection.objects.filter(tenant=request.tenant),
                    'inspection_number', 'FQC',
                )
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'Final inspection {obj.inspection_number} created.')
            return redirect('qms:fqc_inspection_detail', pk=obj.pk)
        return render(request, 'qms/fqc/inspections/form.html', {'form': form})


class FQCInspectionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        i = get_object_or_404(
            FinalInspection.objects.select_related(
                'plan__product', 'work_order__product', 'inspected_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        specs = list(i.plan.specs.order_by('sequence'))
        existing = {r.spec_id: r for r in i.results.all()}
        rows = [{'spec': s, 'result': existing.get(s.pk)} for s in specs]
        coa = getattr(i, 'coa', None)
        return render(request, 'qms/fqc/inspections/detail.html', {
            'inspection': i, 'rows': rows, 'coa': coa,
            'result_form': FinalTestResultForm(),
            'ncrs': i.ncrs.order_by('-reported_at'),
        })


class FQCInspectionEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        i = get_object_or_404(FinalInspection, pk=pk, tenant=request.tenant)
        if not i.is_editable():
            messages.warning(request, 'Inspection is no longer editable.')
            return redirect('qms:fqc_inspection_detail', pk=pk)
        return render(request, 'qms/fqc/inspections/form.html', {
            'form': FinalInspectionForm(instance=i, tenant=request.tenant),
            'inspection': i,
        })

    def post(self, request, pk):
        i = get_object_or_404(FinalInspection, pk=pk, tenant=request.tenant)
        if not i.is_editable():
            messages.warning(request, 'Inspection is no longer editable.')
            return redirect('qms:fqc_inspection_detail', pk=pk)
        form = FinalInspectionForm(request.POST, instance=i, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Inspection updated.')
            return redirect('qms:fqc_inspection_detail', pk=i.pk)
        return render(request, 'qms/fqc/inspections/form.html', {
            'form': form, 'inspection': i,
        })


class FQCInspectionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        i = get_object_or_404(FinalInspection, pk=pk, tenant=request.tenant)
        if i.status not in ('pending', 'in_inspection'):
            messages.error(request, 'Cannot delete a completed FQC inspection.')
            return redirect('qms:fqc_inspection_detail', pk=pk)
        i.delete()
        messages.success(request, 'Final inspection deleted.')
        return redirect('qms:fqc_inspection_list')


class FQCInspectionStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            FinalInspection, pk, request.tenant,
            ['pending'], 'in_inspection',
            extra_fields={'inspected_at': timezone.now()},
        )
        if ok:
            FinalInspection.objects.filter(pk=pk).update(inspected_by=request.user)
            messages.success(request, 'Inspection started.')
        else:
            messages.warning(request, 'Only pending inspections can be started.')
        return redirect('qms:fqc_inspection_detail', pk=pk)


class FQCInspectionPassView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            FinalInspection, pk, request.tenant,
            ['in_inspection'], 'passed',
        )
        msg = 'Inspection passed.' if ok else 'Cannot pass - wrong status.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:fqc_inspection_detail', pk=pk)


class FQCInspectionFailView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            FinalInspection, pk, request.tenant,
            ['in_inspection'], 'failed',
        )
        msg = 'Inspection failed.' if ok else 'Cannot fail - wrong status.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:fqc_inspection_detail', pk=pk)


class FQCInspectionDeviationView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            FinalInspection, pk, request.tenant,
            ['in_inspection'], 'released_with_deviation',
        )
        msg = 'Released with deviation.' if ok else 'Cannot release - wrong status.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:fqc_inspection_detail', pk=pk)


class FQCResultCreateView(TenantRequiredMixin, View):
    def post(self, request, inspection_id):
        inspection = get_object_or_404(FinalInspection, pk=inspection_id, tenant=request.tenant)
        form = FinalTestResultForm(request.POST)
        if form.is_valid():
            spec = form.cleaned_data['spec']
            try:
                with transaction.atomic():
                    FinalTestResult.objects.update_or_create(
                        tenant=request.tenant,
                        inspection=inspection,
                        spec=spec,
                        defaults={
                            'measured_value': form.cleaned_data.get('measured_value'),
                            'measured_text': form.cleaned_data.get('measured_text', ''),
                            'is_pass': form.cleaned_data.get('is_pass', True),
                            'notes': form.cleaned_data.get('notes', ''),
                        },
                    )
                messages.success(request, 'Test result saved.')
            except IntegrityError:
                messages.error(request, 'Could not save test result.')
        else:
            messages.error(request, 'Invalid result.')
        return redirect('qms:fqc_inspection_detail', pk=inspection.pk)


# ============================================================================
# 7.3  CERTIFICATE OF ANALYSIS
# ============================================================================

class CoAGenerateView(TenantRequiredMixin, View):
    """Generate (or display) the CoA for a passed FQC inspection."""

    def get(self, request, pk):
        inspection = get_object_or_404(
            FinalInspection.objects.select_related('plan__product', 'work_order'),
            pk=pk, tenant=request.tenant,
        )
        if not inspection.can_generate_coa():
            messages.warning(
                request,
                'CoA can only be generated for passed or release-with-deviation inspections.',
            )
            return redirect('qms:fqc_inspection_detail', pk=pk)

        coa, created = CertificateOfAnalysis.objects.get_or_create(
            tenant=request.tenant,
            inspection=inspection,
            defaults={
                'coa_number': _next_sequence_number(
                    CertificateOfAnalysis.objects.filter(tenant=request.tenant),
                    'coa_number', 'COA',
                ),
                'issued_at': timezone.now(),
                'issued_by': request.user,
            },
        )
        payload = coa_service.build_coa_payload(
            inspection,
            issued_at=coa.issued_at,
            issued_by=coa.issued_by,
            customer_name=coa.customer_name,
            customer_reference=coa.customer_reference,
            coa_number=coa.coa_number,
        )
        return render(request, 'qms/fqc/coa/render.html', {
            'inspection': inspection, 'coa': coa, 'payload': payload,
        })

    def post(self, request, pk):
        # Update customer details on the CoA.
        inspection = get_object_or_404(FinalInspection, pk=pk, tenant=request.tenant)
        coa = getattr(inspection, 'coa', None)
        if coa is None:
            messages.error(request, 'CoA not generated yet.')
            return redirect('qms:fqc_inspection_detail', pk=pk)
        form = CertificateOfAnalysisForm(request.POST, instance=coa)
        if form.is_valid():
            form.save()
            messages.success(request, 'CoA updated.')
        else:
            messages.error(request, 'Invalid CoA form.')
        return redirect('qms:coa_render', pk=pk)


class CoAReleaseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        inspection = get_object_or_404(FinalInspection, pk=pk, tenant=request.tenant)
        coa = getattr(inspection, 'coa', None)
        if coa is None:
            messages.error(request, 'CoA not generated yet.')
            return redirect('qms:fqc_inspection_detail', pk=pk)
        coa.released_to_customer = True
        coa.released_at = timezone.now()
        coa.released_by = request.user
        coa.save()
        messages.success(request, 'CoA released to customer.')
        return redirect('qms:coa_render', pk=pk)


# ============================================================================
# 7.4  NCR & CAPA
# ============================================================================

class NCRListView(TenantRequiredMixin, ListView):
    model = NonConformanceReport
    template_name = 'qms/ncr/list.html'
    context_object_name = 'ncrs'
    paginate_by = 25

    def get_queryset(self):
        qs = NonConformanceReport.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'reported_by', 'assigned_to')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(ncr_number__icontains=q)
                | Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(lot_number__icontains=q)
            )
        for field in ('source', 'severity', 'status'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('-reported_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['source_choices'] = NonConformanceReport.SOURCE_CHOICES
        ctx['severity_choices'] = NonConformanceReport.SEVERITY_CHOICES
        ctx['status_choices'] = NonConformanceReport.STATUS_CHOICES
        return ctx


class NCRCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/ncr/form.html', {
            'form': NonConformanceReportForm(tenant=request.tenant),
        })

    def post(self, request):
        form = NonConformanceReportForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.reported_by = request.user
                obj.reported_at = timezone.now()
                obj.ncr_number = _next_sequence_number(
                    NonConformanceReport.objects.filter(tenant=request.tenant),
                    'ncr_number', 'NCR',
                )
                obj.save()
                # Create the empty RCA shell so the detail page can render it.
                RootCauseAnalysis.objects.get_or_create(
                    tenant=request.tenant, ncr=obj,
                )
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'NCR {obj.ncr_number} raised.')
            return redirect('qms:ncr_detail', pk=obj.pk)
        return render(request, 'qms/ncr/form.html', {'form': form})


class NCRDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        ncr = get_object_or_404(
            NonConformanceReport.objects.select_related(
                'product', 'reported_by', 'assigned_to', 'closed_by',
                'iqc_inspection', 'ipqc_inspection', 'fqc_inspection',
            ),
            pk=pk, tenant=request.tenant,
        )
        rca = getattr(ncr, 'rca', None)
        cas = ncr.corrective_actions.select_related('owner').order_by('sequence')
        pas = ncr.preventive_actions.select_related('owner').order_by('sequence')
        attachments = ncr.attachments.order_by('-created_at')
        return render(request, 'qms/ncr/detail.html', {
            'ncr': ncr, 'rca': rca, 'cas': cas, 'pas': pas,
            'attachments': attachments,
            'rca_form': RootCauseAnalysisForm(instance=rca),
            'ca_form': CorrectiveActionForm(tenant=request.tenant),
            'pa_form': PreventiveActionForm(tenant=request.tenant),
            'attachment_form': NCRAttachmentForm(),
            'close_form': NCRCloseForm(instance=ncr),
        })


class NCREditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        ncr = get_object_or_404(NonConformanceReport, pk=pk, tenant=request.tenant)
        if not ncr.is_editable():
            messages.warning(request, 'NCR is no longer editable.')
            return redirect('qms:ncr_detail', pk=pk)
        return render(request, 'qms/ncr/form.html', {
            'form': NonConformanceReportForm(instance=ncr, tenant=request.tenant),
            'ncr': ncr,
        })

    def post(self, request, pk):
        ncr = get_object_or_404(NonConformanceReport, pk=pk, tenant=request.tenant)
        if not ncr.is_editable():
            messages.warning(request, 'NCR is no longer editable.')
            return redirect('qms:ncr_detail', pk=pk)
        form = NonConformanceReportForm(request.POST, instance=ncr, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'NCR updated.')
            return redirect('qms:ncr_detail', pk=ncr.pk)
        return render(request, 'qms/ncr/form.html', {'form': form, 'ncr': ncr})


class NCRDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ncr = get_object_or_404(NonConformanceReport, pk=pk, tenant=request.tenant)
        if ncr.status not in ('open', 'cancelled'):
            messages.error(request, 'Only open or cancelled NCRs can be deleted - cancel first.')
            return redirect('qms:ncr_detail', pk=pk)
        ncr.delete()
        messages.success(request, 'NCR deleted.')
        return redirect('qms:ncr_list')


class NCRInvestigateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            NonConformanceReport, pk, request.tenant,
            ['open'], 'investigating',
        )
        msg = 'NCR moved to investigating.' if ok else 'Wrong status for transition.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:ncr_detail', pk=pk)


class NCRAwaitCAPAView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            NonConformanceReport, pk, request.tenant,
            ['investigating'], 'awaiting_capa',
        )
        msg = 'Awaiting CAPA.' if ok else 'Wrong status for transition.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:ncr_detail', pk=pk)


class NCRResolveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            NonConformanceReport, pk, request.tenant,
            ['investigating', 'awaiting_capa'], 'resolved',
        )
        msg = 'NCR resolved.' if ok else 'Wrong status for transition.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:ncr_detail', pk=pk)


class NCRCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ncr = get_object_or_404(NonConformanceReport, pk=pk, tenant=request.tenant)
        if ncr.status != 'resolved':
            messages.warning(request, 'Only resolved NCRs can be closed.')
            return redirect('qms:ncr_detail', pk=pk)
        form = NCRCloseForm(request.POST, instance=ncr)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.status = 'closed'
            obj.closed_by = request.user
            obj.closed_at = timezone.now()
            obj.save()
            messages.success(request, 'NCR closed.')
        else:
            messages.error(request, 'A resolution summary is required to close.')
        return redirect('qms:ncr_detail', pk=pk)


class NCRCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            NonConformanceReport, pk, request.tenant,
            ['open', 'investigating', 'awaiting_capa', 'resolved'], 'cancelled',
        )
        msg = 'NCR cancelled.' if ok else 'Cannot cancel a closed NCR.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:ncr_detail', pk=pk)


class NCRRCAEditView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ncr = get_object_or_404(NonConformanceReport, pk=pk, tenant=request.tenant)
        rca, _ = RootCauseAnalysis.objects.get_or_create(
            tenant=request.tenant, ncr=ncr,
        )
        form = RootCauseAnalysisForm(request.POST, instance=rca)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.analyzed_by = request.user
            obj.analyzed_at = timezone.now()
            obj.save()
            messages.success(request, 'Root cause analysis saved.')
        else:
            messages.error(request, 'Invalid RCA form.')
        return redirect('qms:ncr_detail', pk=ncr.pk)


# ---------------- Corrective / Preventive Actions ----------------

class CACreateView(TenantRequiredMixin, View):
    def post(self, request, ncr_id):
        ncr = get_object_or_404(NonConformanceReport, pk=ncr_id, tenant=request.tenant)
        form = CorrectiveActionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.ncr = ncr
            obj.save()
            messages.success(request, 'Corrective action added.')
        else:
            messages.error(request, 'Could not add corrective action.')
        return redirect('qms:ncr_detail', pk=ncr.pk)


class CAEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        ca = get_object_or_404(CorrectiveAction, pk=pk, tenant=request.tenant)
        return render(request, 'qms/ncr/ca_form.html', {
            'form': CorrectiveActionForm(instance=ca, tenant=request.tenant),
            'ca': ca, 'ncr': ca.ncr,
        })

    def post(self, request, pk):
        ca = get_object_or_404(CorrectiveAction, pk=pk, tenant=request.tenant)
        form = CorrectiveActionForm(request.POST, instance=ca, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Corrective action updated.')
            return redirect('qms:ncr_detail', pk=ca.ncr_id)
        return render(request, 'qms/ncr/ca_form.html', {
            'form': form, 'ca': ca, 'ncr': ca.ncr,
        })


class CADeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ca = get_object_or_404(CorrectiveAction, pk=pk, tenant=request.tenant)
        ncr_pk = ca.ncr_id
        ca.delete()
        messages.success(request, 'Corrective action deleted.')
        return redirect('qms:ncr_detail', pk=ncr_pk)


class CACompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ca = get_object_or_404(CorrectiveAction, pk=pk, tenant=request.tenant)
        if not ca.can_complete():
            messages.warning(request, 'Action already completed or cancelled.')
            return redirect('qms:ncr_detail', pk=ca.ncr_id)
        ca.status = 'completed'
        ca.completed_at = timezone.now()
        ca.completed_by = request.user
        ca.save()
        messages.success(request, 'Corrective action marked complete.')
        return redirect('qms:ncr_detail', pk=ca.ncr_id)


class PACreateView(TenantRequiredMixin, View):
    def post(self, request, ncr_id):
        ncr = get_object_or_404(NonConformanceReport, pk=ncr_id, tenant=request.tenant)
        form = PreventiveActionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.ncr = ncr
            obj.save()
            messages.success(request, 'Preventive action added.')
        else:
            messages.error(request, 'Could not add preventive action.')
        return redirect('qms:ncr_detail', pk=ncr.pk)


class PAEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        pa = get_object_or_404(PreventiveAction, pk=pk, tenant=request.tenant)
        return render(request, 'qms/ncr/pa_form.html', {
            'form': PreventiveActionForm(instance=pa, tenant=request.tenant),
            'pa': pa, 'ncr': pa.ncr,
        })

    def post(self, request, pk):
        pa = get_object_or_404(PreventiveAction, pk=pk, tenant=request.tenant)
        form = PreventiveActionForm(request.POST, instance=pa, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Preventive action updated.')
            return redirect('qms:ncr_detail', pk=pa.ncr_id)
        return render(request, 'qms/ncr/pa_form.html', {
            'form': form, 'pa': pa, 'ncr': pa.ncr,
        })


class PADeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        pa = get_object_or_404(PreventiveAction, pk=pk, tenant=request.tenant)
        ncr_pk = pa.ncr_id
        pa.delete()
        messages.success(request, 'Preventive action deleted.')
        return redirect('qms:ncr_detail', pk=ncr_pk)


class PACompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        pa = get_object_or_404(PreventiveAction, pk=pk, tenant=request.tenant)
        if not pa.can_complete():
            messages.warning(request, 'Action already completed or cancelled.')
            return redirect('qms:ncr_detail', pk=pa.ncr_id)
        pa.status = 'completed'
        pa.completed_at = timezone.now()
        pa.completed_by = request.user
        pa.save()
        messages.success(request, 'Preventive action marked complete.')
        return redirect('qms:ncr_detail', pk=pa.ncr_id)


# ---------------- NCR Attachments ----------------

class NCRAttachmentCreateView(TenantRequiredMixin, View):
    def post(self, request, ncr_id):
        ncr = get_object_or_404(NonConformanceReport, pk=ncr_id, tenant=request.tenant)
        form = NCRAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.ncr = ncr
            obj.uploaded_by = request.user
            obj.save()
            messages.success(request, 'Attachment added.')
        else:
            messages.error(request, 'Could not add attachment - check the file.')
        return redirect('qms:ncr_detail', pk=ncr.pk)


class NCRAttachmentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        a = get_object_or_404(NCRAttachment, pk=pk, tenant=request.tenant)
        ncr_pk = a.ncr_id
        a.delete()
        messages.success(request, 'Attachment removed.')
        return redirect('qms:ncr_detail', pk=ncr_pk)


class NCRAttachmentDownloadView(TenantRequiredMixin, View):
    def get(self, request, pk):
        a = get_object_or_404(NCRAttachment, pk=pk, tenant=request.tenant)
        if not a.file:
            raise Http404
        try:
            handle = a.file.open('rb')
        except FileNotFoundError as exc:
            raise Http404 from exc
        filename = os.path.basename(a.file.name)
        return FileResponse(handle, as_attachment=True, filename=filename)


# ============================================================================
# 7.5  CALIBRATION - EQUIPMENT
# ============================================================================

class EquipmentListView(TenantRequiredMixin, ListView):
    model = MeasurementEquipment
    template_name = 'qms/equipment/list.html'
    context_object_name = 'equipment'
    paginate_by = 25

    def get_queryset(self):
        qs = MeasurementEquipment.objects.filter(
            tenant=self.request.tenant,
        ).select_related('assigned_work_center')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(equipment_number__icontains=q)
                | Q(name__icontains=q)
                | Q(serial_number__icontains=q)
                | Q(manufacturer__icontains=q)
            )
        for field in ('equipment_type', 'status'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        due = self.request.GET.get('due', '')
        if due == 'soon':
            qs = qs.filter(next_due_at__lte=timezone.now() + timedelta(days=7))
        elif due == 'overdue':
            qs = qs.filter(next_due_at__lt=timezone.now())
        return qs.order_by('next_due_at', 'equipment_number')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['type_choices'] = MeasurementEquipment.EQUIPMENT_TYPE_CHOICES
        ctx['status_choices'] = MeasurementEquipment.STATUS_CHOICES
        ctx['now'] = timezone.now()
        ctx['soon_cutoff'] = timezone.now() + timedelta(days=7)
        return ctx


class EquipmentCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/equipment/form.html', {
            'form': MeasurementEquipmentForm(tenant=request.tenant),
        })

    def post(self, request):
        form = MeasurementEquipmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.equipment_number = _next_sequence_number(
                    MeasurementEquipment.objects.filter(tenant=request.tenant),
                    'equipment_number', 'EQP',
                )
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'Equipment {obj.equipment_number} added.')
            return redirect('qms:equipment_detail', pk=obj.pk)
        return render(request, 'qms/equipment/form.html', {'form': form})


class EquipmentDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        eq = get_object_or_404(
            MeasurementEquipment.objects.select_related('assigned_work_center'),
            pk=pk, tenant=request.tenant,
        )
        records = eq.calibration_records.order_by('-calibrated_at')[:25]
        return render(request, 'qms/equipment/detail.html', {
            'equipment': eq, 'records': records,
        })


class EquipmentEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        eq = get_object_or_404(MeasurementEquipment, pk=pk, tenant=request.tenant)
        return render(request, 'qms/equipment/form.html', {
            'form': MeasurementEquipmentForm(instance=eq, tenant=request.tenant),
            'equipment': eq,
        })

    def post(self, request, pk):
        eq = get_object_or_404(MeasurementEquipment, pk=pk, tenant=request.tenant)
        form = MeasurementEquipmentForm(request.POST, instance=eq, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment updated.')
            return redirect('qms:equipment_detail', pk=eq.pk)
        return render(request, 'qms/equipment/form.html', {'form': form, 'equipment': eq})


class EquipmentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        eq = get_object_or_404(MeasurementEquipment, pk=pk, tenant=request.tenant)
        try:
            eq.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - equipment has calibration history.')
            return redirect('qms:equipment_detail', pk=pk)
        messages.success(request, 'Equipment deleted.')
        return redirect('qms:equipment_list')


class EquipmentRetireView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MeasurementEquipment, pk, request.tenant,
            ['active', 'out_of_service'], 'retired',
            extra_fields={'is_active': False},
        )
        msg = 'Equipment retired.' if ok else 'Equipment is already retired.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('qms:equipment_detail', pk=pk)


# ============================================================================
# 7.5  CALIBRATION - RECORDS
# ============================================================================

class CalibrationListView(TenantRequiredMixin, ListView):
    model = CalibrationRecord
    template_name = 'qms/calibrations/list.html'
    context_object_name = 'records'
    paginate_by = 25

    def get_queryset(self):
        qs = CalibrationRecord.objects.filter(
            tenant=self.request.tenant,
        ).select_related('equipment', 'standard', 'calibrated_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(record_number__icontains=q)
                | Q(equipment__equipment_number__icontains=q)
                | Q(equipment__name__icontains=q)
                | Q(external_lab_name__icontains=q)
            )
        result = self.request.GET.get('result', '')
        if result:
            qs = qs.filter(result=result)
        return qs.order_by('-calibrated_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['result_choices'] = CalibrationRecord.RESULT_CHOICES
        return ctx


class CalibrationCreateView(TenantRequiredMixin, View):
    def get(self, request):
        equipment_id = request.GET.get('equipment')
        equipment = None
        if equipment_id:
            equipment = MeasurementEquipment.objects.filter(
                tenant=request.tenant, pk=equipment_id,
            ).first()
        equipments = MeasurementEquipment.objects.filter(
            tenant=request.tenant, is_active=True,
        ).order_by('equipment_number')
        return render(request, 'qms/calibrations/form.html', {
            'form': CalibrationRecordForm(tenant=request.tenant),
            'equipment': equipment, 'equipments': equipments,
        })

    def post(self, request):
        equipment_id = request.POST.get('equipment')
        equipment = get_object_or_404(
            MeasurementEquipment, pk=equipment_id, tenant=request.tenant,
        )
        form = CalibrationRecordForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            def _make():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.equipment = equipment
                obj.record_number = _next_sequence_number(
                    CalibrationRecord.objects.filter(tenant=request.tenant),
                    'record_number', 'CAL',
                )
                if not obj.next_due_at and obj.calibrated_at:
                    obj.next_due_at = obj.calibrated_at + timedelta(
                        days=equipment.calibration_interval_days,
                    )
                obj.save()
                return obj
            obj = _save_with_unique_number(_make)
            messages.success(request, f'Calibration {obj.record_number} recorded.')
            return redirect('qms:calibration_detail', pk=obj.pk)
        equipments = MeasurementEquipment.objects.filter(
            tenant=request.tenant, is_active=True,
        ).order_by('equipment_number')
        return render(request, 'qms/calibrations/form.html', {
            'form': form, 'equipment': equipment, 'equipments': equipments,
        })


class CalibrationDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(
            CalibrationRecord.objects.select_related('equipment', 'standard', 'calibrated_by'),
            pk=pk, tenant=request.tenant,
        )
        checks = rec.tolerance_checks.order_by('sequence')
        return render(request, 'qms/calibrations/detail.html', {
            'record': rec, 'checks': checks,
            'check_form': ToleranceVerificationForm(),
        })


class CalibrationEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(CalibrationRecord, pk=pk, tenant=request.tenant)
        return render(request, 'qms/calibrations/form.html', {
            'form': CalibrationRecordForm(instance=rec, tenant=request.tenant),
            'record': rec, 'equipment': rec.equipment,
        })

    def post(self, request, pk):
        rec = get_object_or_404(CalibrationRecord, pk=pk, tenant=request.tenant)
        form = CalibrationRecordForm(request.POST, request.FILES, instance=rec, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Calibration record updated.')
            return redirect('qms:calibration_detail', pk=rec.pk)
        return render(request, 'qms/calibrations/form.html', {
            'form': form, 'record': rec, 'equipment': rec.equipment,
        })


class CalibrationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rec = get_object_or_404(CalibrationRecord, pk=pk, tenant=request.tenant)
        rec.delete()
        messages.success(request, 'Calibration record deleted.')
        return redirect('qms:calibration_list')


class CalibrationCertificateDownloadView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(CalibrationRecord, pk=pk, tenant=request.tenant)
        if not rec.certificate_file:
            raise Http404
        try:
            handle = rec.certificate_file.open('rb')
        except FileNotFoundError as exc:
            raise Http404 from exc
        filename = os.path.basename(rec.certificate_file.name)
        return FileResponse(handle, as_attachment=True, filename=filename)


class ToleranceCheckCreateView(TenantRequiredMixin, View):
    def post(self, request, record_id):
        rec = get_object_or_404(CalibrationRecord, pk=record_id, tenant=request.tenant)
        form = ToleranceVerificationForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.record = rec
            obj.save()
            messages.success(request, 'Tolerance check added.')
        else:
            messages.error(request, 'Could not add tolerance check.')
        return redirect('qms:calibration_detail', pk=rec.pk)


# ============================================================================
# 7.5  CALIBRATION - STANDARDS
# ============================================================================

class CalibrationStandardListView(TenantRequiredMixin, ListView):
    model = CalibrationStandard
    template_name = 'qms/calibrations/standards_list.html'
    context_object_name = 'standards'
    paginate_by = 20

    def get_queryset(self):
        qs = CalibrationStandard.objects.filter(tenant=self.request.tenant)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(standard_number__icontains=q)
            )
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('standard_number')


class CalibrationStandardCreateView(TenantAdminRequiredMixin, View):
    def get(self, request):
        return render(request, 'qms/calibrations/standard_form.html', {
            'form': CalibrationStandardForm(tenant=request.tenant),
        })

    def post(self, request):
        form = CalibrationStandardForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Calibration standard added.')
            return redirect('qms:standard_list')
        return render(request, 'qms/calibrations/standard_form.html', {'form': form})


class CalibrationStandardEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        s = get_object_or_404(CalibrationStandard, pk=pk, tenant=request.tenant)
        return render(request, 'qms/calibrations/standard_form.html', {
            'form': CalibrationStandardForm(instance=s, tenant=request.tenant),
            'standard': s,
        })

    def post(self, request, pk):
        s = get_object_or_404(CalibrationStandard, pk=pk, tenant=request.tenant)
        form = CalibrationStandardForm(request.POST, instance=s, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Standard updated.')
            return redirect('qms:standard_list')
        return render(request, 'qms/calibrations/standard_form.html', {
            'form': form, 'standard': s,
        })


class CalibrationStandardDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        s = get_object_or_404(CalibrationStandard, pk=pk, tenant=request.tenant)
        try:
            s.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete - standard is referenced.')
            return redirect('qms:standard_list')
        messages.success(request, 'Standard removed.')
        return redirect('qms:standard_list')
