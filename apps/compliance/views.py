"""Module 13 - Compliance & Regulatory Management views.

Mirrors the cost / utility module shape:
    <Resource>ListView / CreateView / DetailView / EditView / DeleteView
    plus per-workflow POST views.

RBAC (L-10):
    - Read surfaces inherit ``TenantRequiredMixin``.
    - Mutating surfaces inherit ``TenantAdminRequiredMixin``.

Lessons honored:
    - L-03 status gates use the model's ``is_*()`` helpers.
    - L-04 any operation that drops/skips records surfaces a
      ``messages.warning(...)`` with explicit counts.
    - L-13 workflow status mutations use ``QuerySet.update()`` inside a
      ``transaction.atomic()`` block.
    - L-14 workflow POST views (cancel / supersede / sign / ack) validate
      via per-workflow form classes.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    audit as audit_svc,
    document as doc_svc,
    incident as incident_svc,
    recall as recall_svc,
)

PAGE_SIZE = 25


# ============================================================================
# Helpers
# ============================================================================

def _paginate(qs, request, size=PAGE_SIZE):
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    """Race-safe status transition (mirrors apps/cost / apps/utility)."""
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'compliance/index.html'

    def get(self, request):
        tenant = request.tenant
        if tenant is None:
            return render(request, self.template_name, {'kpi': {}})
        today = timezone.now().date()
        kpi = {
            'open_incidents': models.IncidentReport.objects.filter(
                tenant=tenant, status__in=('reported', 'investigating', 'corrective_action'),
            ).count(),
            'critical_incidents': models.IncidentReport.objects.filter(
                tenant=tenant, severity='critical', status__in=('reported', 'investigating', 'corrective_action'),
            ).count(),
            'open_risks': models.RiskAssessment.objects.filter(
                tenant=tenant, status__in=('draft', 'in_review'),
            ).count(),
            'high_risk_count': models.RiskAssessment.objects.filter(
                tenant=tenant, risk_score__gte=9,
            ).count(),
            'effective_docs': models.ComplianceDocument.objects.filter(
                tenant=tenant, status='effective',
            ).count(),
            'pending_reviews': models.ComplianceDocument.objects.filter(
                tenant=tenant, status='in_review',
            ).count(),
            'open_manifests': models.WasteManifest.objects.filter(
                tenant=tenant, status__in=('draft', 'in_transit'),
            ).count(),
            'active_recalls': models.ProductRecall.objects.filter(
                tenant=tenant, status__in=('initiated', 'in_progress'),
            ).count(),
        }
        recent_incidents = list(
            models.IncidentReport.objects.filter(tenant=tenant)
            .select_related('incident_type', 'reporter')
            .order_by('-occurred_at')[:6]
        )
        recent_recalls = list(
            models.ProductRecall.objects.filter(tenant=tenant)
            .select_related('product')
            .order_by('-initiated_at')[:6]
        )
        # Severity histogram for the dashboard chart (L-07).
        sev_rows = (
            models.IncidentReport.objects.filter(tenant=tenant)
            .values('severity').annotate(n=Count('id')).order_by('severity')
        )
        severity_chart = [{'severity': r['severity'], 'count': r['n']} for r in sev_rows]
        return render(request, self.template_name, {
            'kpi': kpi,
            'recent_incidents': recent_incidents,
            'recent_recalls': recent_recalls,
            'severity_chart': severity_chart,
        })


# ============================================================================
# 13.1  Incident Types
# ============================================================================

class IncidentTypeListView(TenantRequiredMixin, View):
    template_name = 'compliance/types/list.html'

    def get(self, request):
        qs = models.IncidentType.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        category = request.GET.get('category', '')
        if category:
            qs = qs.filter(category=category)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('code'), request),
            'category_choices': models.IncidentType.CATEGORY_CHOICES,
        })


class IncidentTypeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/types/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IncidentTypeForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.IncidentTypeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Incident type "{obj.code}" created.')
            return redirect('compliance:incident_type_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class IncidentTypeEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/types/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.IncidentType, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.IncidentTypeForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentType, pk=pk, tenant=request.tenant)
        form = forms.IncidentTypeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Incident type updated.')
            return redirect('compliance:incident_type_list')
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class IncidentTypeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentType, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Incident type deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('compliance:incident_type_list')

    def get(self, request, pk):
        return redirect('compliance:incident_type_list')


# ============================================================================
# 13.1  Incident Reports
# ============================================================================

class IncidentListView(TenantRequiredMixin, View):
    template_name = 'compliance/incidents/list.html'

    def get(self, request):
        qs = models.IncidentReport.objects.filter(tenant=request.tenant).select_related(
            'incident_type', 'reporter', 'location',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(incident_number__icontains=q) | Q(title__icontains=q)
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        severity = request.GET.get('severity', '')
        if severity:
            qs = qs.filter(severity=severity)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-occurred_at'), request),
            'status_choices': models.IncidentReport.STATUS_CHOICES,
            'severity_choices': models.IncidentReport.SEVERITY_CHOICES,
        })


class IncidentCreateView(TenantRequiredMixin, View):
    """Note: incident reporting is allowed for any logged-in tenant user
    (not admin-only) — anyone on the floor should be able to file an
    incident. Admin-only actions are gated below.
    """
    template_name = 'compliance/incidents/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IncidentReportForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.IncidentReportForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.reporter = request.user
            obj.save()
            messages.success(request, f'Incident {obj.incident_number} reported.')
            return redirect('compliance:incident_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class IncidentDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/incidents/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.IncidentReport.objects.select_related(
                'incident_type', 'reporter', 'location', 'closed_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj,
            'investigation_form': forms.IncidentInvestigationForm(),
            'action_form': forms.IncidentActionForm(),
            'cancel_form': forms.IncidentCancelForm(),
        })


class IncidentEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/incidents/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Closed / cancelled incidents cannot be edited.')
            return redirect('compliance:incident_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.IncidentReportForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Closed / cancelled incidents cannot be edited.')
            return redirect('compliance:incident_detail', pk=pk)
        form = forms.IncidentReportForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Incident updated.')
            return redirect('compliance:incident_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class IncidentInvestigateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_investigatable():
            messages.error(request, 'Only reported incidents can be investigated.')
            return redirect('compliance:incident_detail', pk=pk)
        form = forms.IncidentInvestigationForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Root-cause analysis is required.')
            return redirect('compliance:incident_detail', pk=pk)
        incident_svc.record_investigation(
            obj, root_cause=form.cleaned_data['root_cause'], by=request.user,
        )
        messages.success(request, 'Investigation recorded.')
        return redirect('compliance:incident_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:incident_detail', pk=pk)


class IncidentActionView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_actionable():
            messages.error(request, 'Only investigating incidents can transition to corrective action.')
            return redirect('compliance:incident_detail', pk=pk)
        form = forms.IncidentActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Corrective actions are required.')
            return redirect('compliance:incident_detail', pk=pk)
        incident_svc.record_corrective_action(
            obj, corrective_actions=form.cleaned_data['corrective_actions'],
            by=request.user,
        )
        messages.success(request, 'Corrective action recorded.')
        return redirect('compliance:incident_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:incident_detail', pk=pk)


class IncidentCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_closeable():
            messages.error(request, 'Only corrective-action incidents can be closed.')
            return redirect('compliance:incident_detail', pk=pk)
        incident_svc.close_incident(obj, by=request.user)
        messages.success(request, 'Incident closed.')
        return redirect('compliance:incident_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:incident_detail', pk=pk)


class IncidentCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(request, 'Incident cannot be cancelled from current state.')
            return redirect('compliance:incident_detail', pk=pk)
        form = forms.IncidentCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('compliance:incident_detail', pk=pk)
        incident_svc.cancel_incident(
            obj, reason=form.cleaned_data['cancellation_reason'], by=request.user,
        )
        messages.success(request, 'Incident cancelled.')
        return redirect('compliance:incident_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:incident_detail', pk=pk)


class IncidentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncidentReport, pk=pk, tenant=request.tenant)
        # L-03: only freshly-reported incidents are deletable.
        if obj.status != 'reported':
            messages.error(request, 'Only reported (un-actioned) incidents can be deleted.')
            return redirect('compliance:incident_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Incident deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('compliance:incident_detail', pk=pk)
        return redirect('compliance:incident_list')

    def get(self, request, pk):
        return redirect('compliance:incident_detail', pk=pk)


# ============================================================================
# 13.1  Risk Assessments
# ============================================================================

class RiskListView(TenantRequiredMixin, View):
    template_name = 'compliance/risks/list.html'

    def get(self, request):
        qs = models.RiskAssessment.objects.filter(tenant=request.tenant).select_related('location')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(assessment_number__icontains=q) | Q(title__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        band = request.GET.get('band', '')
        if band:
            ranges = {'low': (1, 3), 'medium': (4, 8), 'high': (9, 15), 'critical': (16, 25)}
            if band in ranges:
                lo, hi = ranges[band]
                qs = qs.filter(risk_score__gte=lo, risk_score__lte=hi)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-risk_score', 'assessment_number'), request),
            'status_choices': models.RiskAssessment.STATUS_CHOICES,
        })


class RiskCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/risks/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.RiskAssessmentForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.RiskAssessmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Risk assessment {obj.assessment_number} created.')
            return redirect('compliance:risk_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class RiskDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/risks/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.RiskAssessment.objects.select_related('location', 'approved_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class RiskEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/risks/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Approved / archived assessments cannot be edited.')
            return redirect('compliance:risk_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.RiskAssessmentForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Approved / archived assessments cannot be edited.')
            return redirect('compliance:risk_detail', pk=pk)
        form = forms.RiskAssessmentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Risk assessment updated.')
            return redirect('compliance:risk_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class RiskSubmitView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if not obj.is_submittable():
            messages.error(request, 'Only draft assessments can be submitted.')
            return redirect('compliance:risk_detail', pk=pk)
        ok = _atomic_status_transition(
            models.RiskAssessment, pk, request.tenant,
            from_states=['draft'], to_state='in_review',
        )
        if ok:
            messages.success(request, 'Submitted for review.')
        else:
            messages.error(request, 'Submit failed (concurrent change?).')
        return redirect('compliance:risk_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:risk_detail', pk=pk)


class RiskApproveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if not obj.is_approvable():
            messages.error(request, 'Only in-review assessments can be approved.')
            return redirect('compliance:risk_detail', pk=pk)
        ok = _atomic_status_transition(
            models.RiskAssessment, pk, request.tenant,
            from_states=['in_review'], to_state='approved',
            extra_fields={
                'approved_by_id': request.user.pk,
                'approved_at': timezone.now(),
            },
        )
        if ok:
            messages.success(request, 'Risk assessment approved.')
        else:
            messages.error(request, 'Approve failed.')
        return redirect('compliance:risk_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:risk_detail', pk=pk)


class RiskArchiveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if not obj.is_archivable():
            messages.error(request, 'Only approved assessments can be archived.')
            return redirect('compliance:risk_detail', pk=pk)
        _atomic_status_transition(
            models.RiskAssessment, pk, request.tenant,
            from_states=['approved'], to_state='archived',
        )
        messages.success(request, 'Risk assessment archived.')
        return redirect('compliance:risk_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:risk_detail', pk=pk)


class RiskDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RiskAssessment, pk=pk, tenant=request.tenant)
        if obj.status not in ('draft',):
            messages.error(request, 'Only draft assessments can be deleted.')
            return redirect('compliance:risk_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Risk assessment deleted.')
        return redirect('compliance:risk_list')

    def get(self, request, pk):
        return redirect('compliance:risk_detail', pk=pk)


# ============================================================================
# 13.1  Safety Audit Checklists + Audits
# ============================================================================

class ChecklistListView(TenantRequiredMixin, View):
    template_name = 'compliance/checklists/list.html'

    def get(self, request):
        qs = models.SafetyAuditChecklist.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('code'), request),
        })


class ChecklistCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/checklists/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SafetyChecklistForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.SafetyChecklistForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.items = []
            obj.save()
            messages.success(request, f'Checklist "{obj.code}" created.')
            return redirect('compliance:checklist_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class ChecklistDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/checklists/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.SafetyAuditChecklist, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'obj': obj,
            'item_form': forms.SafetyChecklistItemForm(),
        })

    def post(self, request, pk):
        """Inline append-an-item POST (admin-only)."""
        if not request.user.is_tenant_admin:
            return redirect('compliance:checklist_detail', pk=pk)
        obj = get_object_or_404(models.SafetyAuditChecklist, pk=pk, tenant=request.tenant)
        form = forms.SafetyChecklistItemForm(request.POST)
        if form.is_valid():
            items = list(obj.items or [])
            order = max((i.get('order', 0) for i in items), default=0) + 1
            items.append({'order': order, 'question': form.cleaned_data['question']})
            obj.items = items
            obj.save(update_fields=['items', 'updated_at'])
            messages.success(request, 'Item added.')
        return redirect('compliance:checklist_detail', pk=pk)


class ChecklistEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/checklists/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.SafetyAuditChecklist, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.SafetyChecklistForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAuditChecklist, pk=pk, tenant=request.tenant)
        form = forms.SafetyChecklistForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Checklist updated.')
            return redirect('compliance:checklist_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class ChecklistDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAuditChecklist, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Checklist deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('compliance:checklist_list')

    def get(self, request, pk):
        return redirect('compliance:checklist_list')


class AuditListView(TenantRequiredMixin, View):
    template_name = 'compliance/audits/list.html'

    def get(self, request):
        qs = models.SafetyAudit.objects.filter(tenant=request.tenant).select_related(
            'checklist', 'auditor', 'location',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(audit_number__icontains=q) | Q(checklist__name__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-scheduled_for'), request),
            'status_choices': models.SafetyAudit.STATUS_CHOICES,
        })


class AuditCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/audits/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SafetyAuditForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.SafetyAuditForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Audit {obj.audit_number} scheduled.')
            return redirect('compliance:audit_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class AuditDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/audits/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.SafetyAudit.objects.select_related(
                'checklist', 'auditor', 'location',
            ),
            pk=pk, tenant=request.tenant,
        )
        items = obj.item_results.all().order_by('item_order')
        # Available checklist questions not yet recorded.
        recorded_orders = {it.item_order for it in items}
        pending_items = [
            i for i in (obj.checklist.items or [])
            if i.get('order') not in recorded_orders
        ]
        return render(request, self.template_name, {
            'obj': obj, 'items': items, 'pending_items': pending_items,
            'record_form': forms.SafetyAuditItemRecordForm(),
            'cancel_form': forms.SafetyAuditCancelForm(),
        })


class AuditStartView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAudit, pk=pk, tenant=request.tenant)
        if not obj.is_startable():
            messages.error(request, 'Only scheduled audits can be started.')
            return redirect('compliance:audit_detail', pk=pk)
        ok = _atomic_status_transition(
            models.SafetyAudit, pk, request.tenant,
            from_states=['scheduled'], to_state='in_progress',
            extra_fields={'started_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Audit started.')
        return redirect('compliance:audit_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:audit_detail', pk=pk)


class AuditRecordItemView(TenantAdminRequiredMixin, View):
    """Inline POST on the audit detail page; appends a SafetyAuditItem row."""

    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAudit, pk=pk, tenant=request.tenant)
        if not obj.is_completable():
            messages.error(request, 'Audit must be in progress to record results.')
            return redirect('compliance:audit_detail', pk=pk)
        form = forms.SafetyAuditItemRecordForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid item record.')
            return redirect('compliance:audit_detail', pk=pk)
        data = form.cleaned_data
        item, created = models.SafetyAuditItem.objects.update_or_create(
            audit=obj, item_order=data['item_order'],
            defaults={
                'tenant': request.tenant,
                'question': data['question'],
                'result': data['result'],
                'finding': data.get('finding') or '',
            },
        )
        # Recompute pass/fail/na denorms.
        obj.pass_count = obj.item_results.filter(result='pass').count()
        obj.fail_count = obj.item_results.filter(result='fail').count()
        obj.na_count = obj.item_results.filter(result='na').count()
        obj.save(update_fields=['pass_count', 'fail_count', 'na_count', 'updated_at'])
        messages.success(request, 'Item recorded.')
        return redirect('compliance:audit_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:audit_detail', pk=pk)


class AuditCompleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAudit, pk=pk, tenant=request.tenant)
        if not obj.is_completable():
            messages.error(request, 'Only in-progress audits can be completed.')
            return redirect('compliance:audit_detail', pk=pk)
        ok = _atomic_status_transition(
            models.SafetyAudit, pk, request.tenant,
            from_states=['in_progress'], to_state='completed',
            extra_fields={'completed_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Audit completed.')
        return redirect('compliance:audit_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:audit_detail', pk=pk)


class AuditCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAudit, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(request, 'Audit cannot be cancelled from current state.')
            return redirect('compliance:audit_detail', pk=pk)
        form = forms.SafetyAuditCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('compliance:audit_detail', pk=pk)
        _atomic_status_transition(
            models.SafetyAudit, pk, request.tenant,
            from_states=['scheduled', 'in_progress'], to_state='cancelled',
            extra_fields={'notes': form.cleaned_data['cancellation_reason']},
        )
        messages.success(request, 'Audit cancelled.')
        return redirect('compliance:audit_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:audit_detail', pk=pk)


class AuditDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.SafetyAudit, pk=pk, tenant=request.tenant)
        if obj.status != 'scheduled':
            messages.error(request, 'Only scheduled audits can be deleted.')
            return redirect('compliance:audit_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Audit deleted.')
        return redirect('compliance:audit_list')

    def get(self, request, pk):
        return redirect('compliance:audit_detail', pk=pk)


# ============================================================================
# 13.2  Compliance Documents
# ============================================================================

class DocumentListView(TenantRequiredMixin, View):
    template_name = 'compliance/documents/list.html'

    def get(self, request):
        qs = models.ComplianceDocument.objects.filter(tenant=request.tenant).select_related('owner')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(doc_number__icontains=q) | Q(title__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        doc_type = request.GET.get('doc_type', '')
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('doc_number', '-version'), request),
            'status_choices': models.ComplianceDocument.STATUS_CHOICES,
            'doc_type_choices': models.ComplianceDocument.DOC_TYPE_CHOICES,
        })


class DocumentCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/documents/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ComplianceDocumentForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.ComplianceDocumentForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.owner = request.user
            obj.save()
            messages.success(request, f'Document {obj.doc_number} v{obj.version} created.')
            return redirect('compliance:document_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class DocumentDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/documents/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.ComplianceDocument.objects.select_related('owner', 'supersedes'),
            pk=pk, tenant=request.tenant,
        )
        approvals = obj.approvals.filter(tenant=request.tenant).order_by('-acted_at')
        signatures = obj.signatures.filter(tenant=request.tenant).order_by('-signed_at')
        return render(request, self.template_name, {
            'obj': obj,
            'approvals': approvals,
            'signatures': signatures,
            'comment_form': forms.DocumentApprovalCommentForm(),
            'sign_form': forms.ElectronicSignatureForm(),
        })


class DocumentEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/documents/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Approved / effective documents cannot be edited; supersede instead.')
            return redirect('compliance:document_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.ComplianceDocumentForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Approved / effective documents cannot be edited.')
            return redirect('compliance:document_detail', pk=pk)
        form = forms.ComplianceDocumentForm(
            request.POST, request.FILES, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Document updated.')
            return redirect('compliance:document_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class DocumentSubmitView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_submittable():
            messages.error(request, 'Only draft documents can be submitted.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.submit_for_review(obj, by=request.user, comment='Submitted')
        messages.success(request, 'Document submitted for review.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentApproveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_approvable():
            messages.error(request, 'Only in-review documents can be approved.')
            return redirect('compliance:document_detail', pk=pk)
        form = forms.DocumentApprovalCommentForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'A comment is required for approval.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.approve(obj, by=request.user, comment=form.cleaned_data['comment'])
        messages.success(request, 'Document approved.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentRejectView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_approvable():
            messages.error(request, 'Only in-review documents can be rejected.')
            return redirect('compliance:document_detail', pk=pk)
        form = forms.DocumentApprovalCommentForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'A comment is required for rejection.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.reject(obj, by=request.user, comment=form.cleaned_data['comment'])
        messages.success(request, 'Document rejected, returned to draft.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentPublishView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_publishable():
            messages.error(request, 'Only approved documents can be published.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.publish(obj, by=request.user, comment='Published')
        messages.success(request, 'Document published as effective.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentSignView(TenantAdminRequiredMixin, View):
    """21 CFR §11.50 e-signature — typed name + reason + password re-auth."""

    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        form = forms.ElectronicSignatureForm(request.POST)
        if not form.is_valid():
            err = next(iter(form.errors.values()))[0] if form.errors else 'Invalid signature.'
            messages.error(request, f'Sign failed: {err}')
            return redirect('compliance:document_detail', pk=pk)
        # Password re-auth — typed name alone is not enough.
        user = authenticate(
            username=request.user.username,
            password=form.cleaned_data['password'],
        )
        if user is None or user.pk != request.user.pk:
            messages.error(request, 'Password re-authentication failed.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.apply_signature(
            obj, signer=request.user,
            typed_name=form.cleaned_data['typed_name'],
            role=form.cleaned_data.get('role', ''),
            reason=form.cleaned_data['reason'],
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, 'Electronic signature recorded.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentSupersedeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if not obj.is_supersedable():
            messages.error(request, 'Only effective documents can be superseded.')
            return redirect('compliance:document_detail', pk=pk)
        doc_svc.supersede(obj, by=request.user, comment='Superseded')
        messages.success(request, 'Document superseded.')
        return redirect('compliance:document_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


class DocumentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ComplianceDocument, pk=pk, tenant=request.tenant)
        if obj.status != 'draft':
            messages.error(request, 'Only draft documents can be deleted; supersede otherwise.')
            return redirect('compliance:document_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Document deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('compliance:document_detail', pk=pk)
        return redirect('compliance:document_list')

    def get(self, request, pk):
        return redirect('compliance:document_detail', pk=pk)


# ============================================================================
# 13.3  Audit Trail viewer + archives
# ============================================================================

class AuditTrailListView(TenantRequiredMixin, View):
    template_name = 'compliance/audit_trail/list.html'

    def get(self, request):
        from apps.tenants.models import TenantAuditLog
        qs = TenantAuditLog.objects.filter(tenant=request.tenant).order_by('-timestamp')
        action = request.GET.get('action', '').strip()
        if action:
            qs = qs.filter(action__icontains=action)
        target = request.GET.get('target_type', '').strip()
        if target:
            qs = qs.filter(target_type__icontains=target)
        return render(request, self.template_name, {
            'page': _paginate(qs, request),
        })


class ArchiveListView(TenantRequiredMixin, View):
    template_name = 'compliance/audit_trail/archive_list.html'

    def get(self, request):
        qs = models.AuditLogArchive.objects.filter(tenant=request.tenant).order_by('-period_end')
        return render(request, self.template_name, {
            'page': _paginate(qs, request),
            'generate_form': forms.ArchiveGenerateForm(),
            'verification': audit_svc.verify_chain(request.tenant) if request.user.is_tenant_admin else None,
        })


class ArchiveGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.ArchiveGenerateForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Pick a valid period.')
            return redirect('compliance:archive_list')
        archive = audit_svc.archive_period(
            request.tenant,
            period_start=form.cleaned_data['period_start'],
            period_end=form.cleaned_data['period_end'],
            by=request.user,
        )
        messages.success(
            request,
            f'Archive {archive.archive_number} generated '
            f'({archive.record_count} records).',
        )
        return redirect('compliance:archive_list')

    def get(self, request):
        return redirect('compliance:archive_list')


class ArchiveDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/audit_trail/archive_detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AuditLogArchive, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {'obj': obj})


# ============================================================================
# 13.4  Waste Categories + Manifests + Disposal
# ============================================================================

class WasteCategoryListView(TenantRequiredMixin, View):
    template_name = 'compliance/waste_categories/list.html'

    def get(self, request):
        qs = models.WasteCategory.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        hazard = request.GET.get('hazard_class', '')
        if hazard:
            qs = qs.filter(hazard_class=hazard)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('code'), request),
            'hazard_choices': models.WasteCategory.HAZARD_CHOICES,
        })


class WasteCategoryCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/waste_categories/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.WasteCategoryForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.WasteCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Category "{obj.code}" created.')
            return redirect('compliance:waste_category_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class WasteCategoryEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/waste_categories/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.WasteCategory, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.WasteCategoryForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.WasteCategory, pk=pk, tenant=request.tenant)
        form = forms.WasteCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.')
            return redirect('compliance:waste_category_list')
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class WasteCategoryDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteCategory, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Category deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('compliance:waste_category_list')

    def get(self, request, pk):
        return redirect('compliance:waste_category_list')


class ManifestListView(TenantRequiredMixin, View):
    template_name = 'compliance/manifests/list.html'

    def get(self, request):
        qs = models.WasteManifest.objects.filter(tenant=request.tenant).select_related('category')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(manifest_number__icontains=q) | Q(generator__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-manifest_date'), request),
            'status_choices': models.WasteManifest.STATUS_CHOICES,
        })


class ManifestCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/manifests/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.WasteManifestForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.WasteManifestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Manifest {obj.manifest_number} created.')
            return redirect('compliance:manifest_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class ManifestDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/manifests/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.WasteManifest.objects.select_related('category'),
            pk=pk, tenant=request.tenant,
        )
        records = obj.disposal_records.all().order_by('line_number')
        return render(request, self.template_name, {
            'obj': obj, 'records': records,
            'record_form': forms.WasteDisposalRecordForm(),
            'cancel_form': forms.WasteManifestCancelForm(),
        })


class ManifestEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/manifests/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Only draft manifests can be edited.')
            return redirect('compliance:manifest_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.WasteManifestForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Only draft manifests can be edited.')
            return redirect('compliance:manifest_detail', pk=pk)
        form = forms.WasteManifestForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Manifest updated.')
            return redirect('compliance:manifest_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class ManifestDispatchView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_dispatchable():
            messages.error(request, 'Only draft manifests can be dispatched.')
            return redirect('compliance:manifest_detail', pk=pk)
        # Recompute total_quantity_kg before dispatch.
        from django.db.models import Sum
        total = obj.disposal_records.aggregate(t=Sum('quantity_kg')).get('t') or 0
        ok = _atomic_status_transition(
            models.WasteManifest, pk, request.tenant,
            from_states=['draft'], to_state='in_transit',
            extra_fields={'total_quantity_kg': total, 'pickup_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Manifest dispatched (in transit).')
        return redirect('compliance:manifest_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:manifest_detail', pk=pk)


class ManifestDisposeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_disposable():
            messages.error(request, 'Only in-transit manifests can be marked disposed.')
            return redirect('compliance:manifest_detail', pk=pk)
        ok = _atomic_status_transition(
            models.WasteManifest, pk, request.tenant,
            from_states=['in_transit'], to_state='disposed',
            extra_fields={'delivered_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Manifest marked disposed.')
        return redirect('compliance:manifest_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:manifest_detail', pk=pk)


class ManifestReconcileView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_reconcilable():
            messages.error(request, 'Only disposed manifests can be reconciled.')
            return redirect('compliance:manifest_detail', pk=pk)
        ok = _atomic_status_transition(
            models.WasteManifest, pk, request.tenant,
            from_states=['disposed'], to_state='reconciled',
        )
        if ok:
            messages.success(request, 'Manifest reconciled.')
        return redirect('compliance:manifest_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:manifest_detail', pk=pk)


class ManifestCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(request, 'Manifest cannot be cancelled from current state.')
            return redirect('compliance:manifest_detail', pk=pk)
        form = forms.WasteManifestCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('compliance:manifest_detail', pk=pk)
        _atomic_status_transition(
            models.WasteManifest, pk, request.tenant,
            from_states=['draft', 'in_transit'], to_state='cancelled',
            extra_fields={
                'cancellation_reason': form.cleaned_data['cancellation_reason'],
            },
        )
        messages.success(request, 'Manifest cancelled.')
        return redirect('compliance:manifest_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:manifest_detail', pk=pk)


class ManifestDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WasteManifest, pk=pk, tenant=request.tenant)
        if obj.status != 'draft':
            messages.error(request, 'Only draft manifests can be deleted.')
            return redirect('compliance:manifest_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Manifest deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('compliance:manifest_detail', pk=pk)
        return redirect('compliance:manifest_list')

    def get(self, request, pk):
        return redirect('compliance:manifest_detail', pk=pk)


class DisposalRecordCreateView(TenantAdminRequiredMixin, View):
    """Inline POST on manifest detail; appends a WasteDisposalRecord row."""

    def post(self, request, manifest_pk):
        manifest = get_object_or_404(
            models.WasteManifest, pk=manifest_pk, tenant=request.tenant,
        )
        if not manifest.is_editable():
            messages.error(request, 'Only draft manifests accept new disposal lines.')
            return redirect('compliance:manifest_detail', pk=manifest_pk)
        form = forms.WasteDisposalRecordForm(request.POST)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.manifest = manifest
            rec.tenant = manifest.tenant
            try:
                rec.save()
                messages.success(request, 'Disposal line added.')
            except Exception as exc:
                messages.error(request, f'Could not add line: {exc}')
        else:
            err = next(iter(form.errors.values()))[0] if form.errors else 'Invalid input.'
            messages.error(request, f'Could not add line: {err}')
        return redirect('compliance:manifest_detail', pk=manifest_pk)

    def get(self, request, manifest_pk):
        return redirect('compliance:manifest_detail', pk=manifest_pk)


class DisposalRecordDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rec = get_object_or_404(
            models.WasteDisposalRecord, pk=pk, manifest__tenant=request.tenant,
        )
        manifest_pk = rec.manifest_id
        if not rec.manifest.is_editable():
            messages.error(request, 'Only draft manifests allow line removal.')
            return redirect('compliance:manifest_detail', pk=manifest_pk)
        rec.delete()
        messages.success(request, 'Line removed.')
        return redirect('compliance:manifest_detail', pk=manifest_pk)

    def get(self, request, pk):
        rec = get_object_or_404(
            models.WasteDisposalRecord, pk=pk, manifest__tenant=request.tenant,
        )
        return redirect('compliance:manifest_detail', pk=rec.manifest_id)


# ============================================================================
# 13.5  Recalls
# ============================================================================

class RecallListView(TenantRequiredMixin, View):
    template_name = 'compliance/recalls/list.html'

    def get(self, request):
        qs = models.ProductRecall.objects.filter(tenant=request.tenant).select_related('product')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(recall_number__icontains=q) | Q(title__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        severity = request.GET.get('severity', '')
        if severity:
            qs = qs.filter(severity=severity)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-initiated_at'), request),
            'status_choices': models.ProductRecall.STATUS_CHOICES,
            'severity_choices': models.ProductRecall.SEVERITY_CHOICES,
        })


class RecallCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/recalls/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ProductRecallForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.ProductRecallForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.initiated_by = request.user
            obj.save()
            messages.success(request, f'Recall {obj.recall_number} initiated.')
            return redirect('compliance:recall_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class RecallDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/recalls/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.ProductRecall.objects.select_related('product', 'initiated_by'),
            pk=pk, tenant=request.tenant,
        )
        affected = obj.affected_lots.select_related('lot').order_by('lot__lot_number')
        notices = obj.notices.order_by('-sent_at', 'notice_number')
        return render(request, self.template_name, {
            'obj': obj,
            'affected_lots': affected,
            'notices': notices,
            'lot_form': forms.AffectedLotForm(tenant=request.tenant, recall=obj),
            'cancel_form': forms.RecallCancelForm(),
        })


class RecallEditView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/recalls/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Closed / cancelled recalls cannot be edited.')
            return redirect('compliance:recall_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.ProductRecallForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Closed / cancelled recalls cannot be edited.')
            return redirect('compliance:recall_detail', pk=pk)
        form = forms.ProductRecallForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Recall updated.')
            return redirect('compliance:recall_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class RecallProgressView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_progressable():
            messages.error(request, 'Only initiated recalls can move to in_progress.')
            return redirect('compliance:recall_detail', pk=pk)
        recall_svc.progress_recall(obj, by=request.user)
        messages.success(request, 'Recall in progress.')
        return redirect('compliance:recall_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:recall_detail', pk=pk)


class RecallCompleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_completable():
            messages.error(request, 'Only in-progress recalls can be completed.')
            return redirect('compliance:recall_detail', pk=pk)
        recall_svc.complete_recall(obj, by=request.user)
        messages.success(request, 'Recall completed.')
        return redirect('compliance:recall_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:recall_detail', pk=pk)


class RecallCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_closeable():
            messages.error(request, 'Only completed recalls can be closed.')
            return redirect('compliance:recall_detail', pk=pk)
        recall_svc.close_recall(obj, by=request.user)
        messages.success(request, 'Recall closed.')
        return redirect('compliance:recall_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:recall_detail', pk=pk)


class RecallCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(request, 'Recall cannot be cancelled from current state.')
            return redirect('compliance:recall_detail', pk=pk)
        form = forms.RecallCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('compliance:recall_detail', pk=pk)
        recall_svc.cancel_recall(
            obj, reason=form.cleaned_data['cancellation_reason'], by=request.user,
        )
        messages.success(request, 'Recall cancelled.')
        return redirect('compliance:recall_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:recall_detail', pk=pk)


class RecallDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ProductRecall, pk=pk, tenant=request.tenant)
        if obj.status != 'initiated':
            messages.error(request, 'Only initiated recalls can be deleted.')
            return redirect('compliance:recall_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Recall deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('compliance:recall_detail', pk=pk)
        return redirect('compliance:recall_list')

    def get(self, request, pk):
        return redirect('compliance:recall_detail', pk=pk)


class AffectedLotAddView(TenantAdminRequiredMixin, View):
    def post(self, request, recall_pk):
        recall = get_object_or_404(
            models.ProductRecall, pk=recall_pk, tenant=request.tenant,
        )
        if not recall.is_editable():
            messages.error(request, 'Closed / cancelled recalls cannot accept new lots.')
            return redirect('compliance:recall_detail', pk=recall_pk)
        form = forms.AffectedLotForm(
            request.POST, tenant=request.tenant, recall=recall,
        )
        if form.is_valid():
            recall_svc.add_affected_lot(
                recall,
                lot=form.cleaned_data['lot'],
                affected_quantity=form.cleaned_data['affected_quantity'],
            )
            messages.success(request, 'Lot linked.')
        else:
            err = next(iter(form.errors.values()))[0] if form.errors else 'Invalid input.'
            messages.error(request, f'Could not link lot: {err}')
        return redirect('compliance:recall_detail', pk=recall_pk)

    def get(self, request, recall_pk):
        return redirect('compliance:recall_detail', pk=recall_pk)


class AffectedLotRemoveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        link = get_object_or_404(
            models.RecallAffectedLot, pk=pk, recall__tenant=request.tenant,
        )
        recall_pk = link.recall_id
        if not link.recall.is_editable():
            messages.error(request, 'Closed / cancelled recalls cannot drop lots.')
            return redirect('compliance:recall_detail', pk=recall_pk)
        recall_svc.remove_affected_lot(link)
        messages.success(request, 'Lot unlinked.')
        return redirect('compliance:recall_detail', pk=recall_pk)

    def get(self, request, pk):
        link = get_object_or_404(
            models.RecallAffectedLot, pk=pk, recall__tenant=request.tenant,
        )
        return redirect('compliance:recall_detail', pk=link.recall_id)


class NoticeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'compliance/recalls/notice_form.html'

    def get(self, request, recall_pk):
        recall = get_object_or_404(
            models.ProductRecall, pk=recall_pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'recall': recall,
            'form': forms.RecallNoticeForm(tenant=request.tenant),
        })

    def post(self, request, recall_pk):
        recall = get_object_or_404(
            models.ProductRecall, pk=recall_pk, tenant=request.tenant,
        )
        form = forms.RecallNoticeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.recall = recall
            obj.save()
            messages.success(request, f'Notice {obj.notice_number} drafted.')
            return redirect('compliance:notice_detail', pk=obj.pk)
        return render(request, self.template_name, {'recall': recall, 'form': form})


class NoticeDetailView(TenantRequiredMixin, View):
    template_name = 'compliance/recalls/notice_detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.RecallNotice.objects.select_related('recall'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class NoticeSendView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RecallNotice, pk=pk, tenant=request.tenant)
        if not obj.is_sendable():
            messages.error(request, 'Only draft notices can be sent.')
            return redirect('compliance:notice_detail', pk=pk)
        recall_svc.send_notice(obj, by=request.user)
        messages.success(request, 'Notice sent.')
        return redirect('compliance:notice_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:notice_detail', pk=pk)


class NoticeAcknowledgeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RecallNotice, pk=pk, tenant=request.tenant)
        if not obj.is_acknowledgable():
            messages.error(request, 'Only sent notices can be acknowledged.')
            return redirect('compliance:notice_detail', pk=pk)
        recall_svc.acknowledge_notice(obj, by=request.user)
        messages.success(request, 'Notice acknowledged.')
        return redirect('compliance:notice_detail', pk=pk)

    def get(self, request, pk):
        return redirect('compliance:notice_detail', pk=pk)


class NoticeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.RecallNotice, pk=pk, tenant=request.tenant)
        if obj.status != 'draft':
            messages.error(request, 'Only draft notices can be deleted.')
            return redirect('compliance:notice_detail', pk=pk)
        recall_pk = obj.recall_id
        obj.delete()
        messages.success(request, 'Notice deleted.')
        return redirect('compliance:recall_detail', pk=recall_pk)

    def get(self, request, pk):
        return redirect('compliance:notice_detail', pk=pk)
