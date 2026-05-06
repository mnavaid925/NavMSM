"""Module 12 - Cost Management & Accounting views.

Read-only surfaces use ``TenantRequiredMixin`` (Lesson L-10).
State-changing surfaces use ``TenantAdminRequiredMixin``.

Workflow transitions use a conditional ``UPDATE ... WHERE status IN (...)``
for race safety (Lessons L-03, L-12).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    actual_costing as actual_svc,
    overhead as oh_svc,
    reporting as report_svc,
    standard_costing as std_svc,
    wip as wip_svc,
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
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'cost/index.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)

        # KPI cards
        active_version = models.StandardCostVersion.objects.filter(
            tenant=t, status='active',
        ).order_by('-effective_from').first()

        open_jobs = models.JobCost.objects.filter(tenant=t, status='open').count()
        closed_jobs_month = models.JobCost.objects.filter(
            tenant=t, status='closed', closed_at__gte=month_start,
        ).count()
        open_period = models.AccountingPeriod.objects.filter(
            tenant=t, status='open',
        ).count()
        wip_total = (
            models.JobCost.objects.filter(tenant=t, status='open')
            .aggregate(t=Sum('wip_balance'))['t']
        ) or Decimal('0')
        recent_allocations = models.OverheadAllocation.objects.filter(
            tenant=t, is_reversed=False,
        ).select_related('pool', 'period').order_by('-posted_at')[:6]
        recent_variances = models.CostVariance.objects.filter(
            tenant=t,
        ).select_related('production_order', 'version').order_by('-analyzed_at')[:6]
        recent_cogm = models.COGMReport.objects.filter(
            tenant=t,
        ).select_related('period').order_by('-period__start_date')[:6]

        # Chart 1: COGM trend (last 6 periods)
        cogm_rows = list(
            models.COGMReport.objects.filter(tenant=t)
            .select_related('period').order_by('period__start_date')[:12]
        )
        cogm_chart = {
            'labels': [r.period.name for r in cogm_rows],
            'materials': [float(r.direct_materials or 0) for r in cogm_rows],
            'labor': [float(r.direct_labor or 0) for r in cogm_rows],
            'overhead': [float(r.overhead_applied or 0) for r in cogm_rows],
        }

        # Chart 2: Variance breakdown (current period)
        var_rows = list(
            models.CostVariance.objects.filter(tenant=t).order_by('-analyzed_at')[:10]
        )
        var_chart = {
            'labels': [v.production_order.order_number if hasattr(v.production_order, 'order_number') else str(v.production_order) for v in var_rows],
            'totals': [float(v.total_variance or 0) for v in var_rows],
        }

        ctx = {
            'active_version': active_version,
            'open_jobs': open_jobs,
            'closed_jobs_month': closed_jobs_month,
            'open_periods': open_period,
            'wip_total': wip_total,
            'recent_allocations': recent_allocations,
            'recent_variances': recent_variances,
            'recent_cogm': recent_cogm,
            'cogm_chart': cogm_chart,
            'variance_chart': var_chart,
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 12.1 Standard Cost Versions
# ============================================================================

class StandardCostVersionListView(TenantRequiredMixin, View):
    template_name = 'cost/standard_versions/list.html'

    def get(self, request):
        qs = models.StandardCostVersion.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(version_number__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-effective_from'), request),
            'status_choices': models.StandardCostVersion.STATUS_CHOICES,
        })


class StandardCostVersionCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/standard_versions/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.StandardCostVersionForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.StandardCostVersionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'Version "{obj.version_number}" created.')
            return redirect('cost:version_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class StandardCostVersionEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/standard_versions/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.warning(request, 'Only draft versions can be edited.')
            return redirect('cost:version_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.StandardCostVersionForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Only draft versions can be edited.')
            return redirect('cost:version_detail', pk=pk)
        form = forms.StandardCostVersionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Version updated.')
            return redirect('cost:version_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'mode': 'edit', 'obj': obj,
        })


class StandardCostVersionDetailView(TenantRequiredMixin, View):
    template_name = 'cost/standard_versions/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        costs = obj.costs.select_related('product').order_by('product__sku')
        return render(request, self.template_name, {
            'obj': obj, 'costs': costs,
            'approve_form': forms.StandardCostVersionApproveForm(),
        })


class StandardCostVersionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if not obj.is_editable():
            messages.error(request, 'Only draft versions can be deleted.')
            return redirect('cost:version_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Version deleted.')
        return redirect('cost:version_list')

    def get(self, request, pk):
        return redirect('cost:version_list')


class StandardCostVersionApproveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if not obj.is_approvable():
            messages.error(request, 'Version cannot be approved from its current state.')
            return redirect('cost:version_detail', pk=pk)
        form = forms.StandardCostVersionApproveForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Approval notes are required.')
            return redirect('cost:version_detail', pk=pk)
        ok = _atomic_status_transition(
            models.StandardCostVersion, pk, request.tenant,
            from_states=['draft'], to_state='approved',
            extra_fields={
                'approved_by': request.user,
                'approved_at': timezone.now(),
                'notes': form.cleaned_data['notes'],
            },
        )
        if ok:
            messages.success(request, 'Version approved.')
        else:
            messages.error(request, 'Approval failed (concurrent change?).')
        return redirect('cost:version_detail', pk=pk)


class StandardCostVersionActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if not obj.is_activatable():
            messages.error(request, 'Version cannot be activated.')
            return redirect('cost:version_detail', pk=pk)
        with transaction.atomic():
            # Auto-archive overlapping active versions.
            models.StandardCostVersion.objects.filter(
                tenant=request.tenant, status='active',
            ).update(status='archived')
            ok = _atomic_status_transition(
                models.StandardCostVersion, pk, request.tenant,
                from_states=['approved'], to_state='active',
            )
        if ok:
            messages.success(request, 'Version activated.')
        else:
            messages.error(request, 'Activation failed.')
        return redirect('cost:version_detail', pk=pk)


class StandardCostVersionArchiveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.StandardCostVersion, pk, request.tenant,
            from_states=['active'], to_state='archived',
        )
        if ok:
            messages.success(request, 'Version archived.')
        else:
            messages.error(request, 'Archive failed.')
        return redirect('cost:version_detail', pk=pk)


class StandardCostVersionRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCostVersion, pk=pk, tenant=request.tenant)
        if obj.status == 'archived':
            messages.error(request, 'Cannot recompute an archived version.')
            return redirect('cost:version_detail', pk=pk)
        result = std_svc.recompute_from_bom(obj)
        messages.success(
            request,
            f'Recompute: {result["created"]} created, {result["updated"]} updated, '
            f'{result["skipped"]} skipped (no BOM rollup).'
        )
        return redirect('cost:version_detail', pk=pk)


class StandardCostCompareView(TenantRequiredMixin, View):
    template_name = 'cost/standard_versions/compare.html'

    def get(self, request):
        v1_pk = request.GET.get('v1')
        v2_pk = request.GET.get('v2')
        rows = []
        v1 = v2 = None
        if v1_pk and v2_pk:
            v1 = get_object_or_404(models.StandardCostVersion, pk=v1_pk, tenant=request.tenant)
            v2 = get_object_or_404(models.StandardCostVersion, pk=v2_pk, tenant=request.tenant)
            rows = std_svc.compare_versions(v1, v2)
        versions = models.StandardCostVersion.objects.filter(tenant=request.tenant).order_by('-effective_from')
        return render(request, self.template_name, {
            'versions': versions, 'v1': v1, 'v2': v2, 'rows': rows,
        })


# ============================================================================
# 12.1 Standard Cost rows
# ============================================================================

class StandardCostListView(TenantRequiredMixin, View):
    template_name = 'cost/standard_costs/list.html'

    def get(self, request):
        qs = models.StandardCost.objects.filter(tenant=request.tenant).select_related(
            'version', 'product',
        )
        version_pk = request.GET.get('version', '')
        if version_pk:
            qs = qs.filter(version_id=version_pk)
        product_pk = request.GET.get('product', '')
        if product_pk:
            qs = qs.filter(product_id=product_pk)
        from apps.plm.models import Product
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-version__effective_from', 'product__sku'), request),
            'versions': models.StandardCostVersion.objects.filter(tenant=request.tenant),
            'products': Product.objects.filter(tenant=request.tenant),
        })


class StandardCostCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/standard_costs/form.html'

    def get(self, request, version_pk):
        version = get_object_or_404(models.StandardCostVersion, pk=version_pk, tenant=request.tenant)
        if not version.is_editable():
            messages.warning(request, 'Costs can only be added to draft versions.')
            return redirect('cost:version_detail', pk=version_pk)
        return render(request, self.template_name, {
            'form': forms.StandardCostForm(tenant=request.tenant, version=version),
            'version': version, 'mode': 'create',
        })

    def post(self, request, version_pk):
        version = get_object_or_404(models.StandardCostVersion, pk=version_pk, tenant=request.tenant)
        if not version.is_editable():
            messages.error(request, 'Costs can only be added to draft versions.')
            return redirect('cost:version_detail', pk=version_pk)
        form = forms.StandardCostForm(request.POST, tenant=request.tenant, version=version)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.version = version
            obj.save()
            messages.success(request, 'Standard cost row added.')
            return redirect('cost:version_detail', pk=version_pk)
        return render(request, self.template_name, {
            'form': form, 'version': version, 'mode': 'create',
        })


class StandardCostEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/standard_costs/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.StandardCost, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.StandardCostForm(instance=obj, tenant=request.tenant, version=obj.version),
            'version': obj.version, 'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCost, pk=pk, tenant=request.tenant)
        form = forms.StandardCostForm(request.POST, instance=obj, tenant=request.tenant, version=obj.version)
        if form.is_valid():
            form.save()
            messages.success(request, 'Standard cost updated.')
            return redirect('cost:version_detail', pk=obj.version_id)
        return render(request, self.template_name, {
            'form': form, 'version': obj.version, 'mode': 'edit', 'obj': obj,
        })


class StandardCostDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.StandardCost, pk=pk, tenant=request.tenant)
        if not obj.version.is_editable():
            messages.error(request, 'Cannot delete - version is not in draft.')
            return redirect('cost:version_detail', pk=obj.version_id)
        version_pk = obj.version_id
        obj.delete()
        messages.success(request, 'Standard cost deleted.')
        return redirect('cost:version_detail', pk=version_pk)


# ============================================================================
# 12.2 Actual Costs & Variances
# ============================================================================

class ActualCostListView(TenantRequiredMixin, View):
    template_name = 'cost/actual_costs/list.html'

    def get(self, request):
        qs = models.ActualCost.objects.filter(tenant=request.tenant).select_related(
            'production_order', 'production_order__product',
        ).order_by('-as_of_date')
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class ActualCostDetailView(TenantRequiredMixin, View):
    template_name = 'cost/actual_costs/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.ActualCost, pk=pk, tenant=request.tenant)
        # Compute variance live for display.
        variances = actual_svc.compute_variances(obj.production_order)
        return render(request, self.template_name, {'obj': obj, 'variances': variances})


class ActualCostRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, po_pk):
        from apps.pps.models import ProductionOrder
        po = get_object_or_404(ProductionOrder, pk=po_pk, tenant=request.tenant)
        ac = actual_svc.compute_actual(po)
        messages.success(request, f'Actual cost recomputed: {ac.total_cost}.')
        return redirect('cost:actual_cost_detail', pk=ac.pk)


class CostVarianceListView(TenantRequiredMixin, View):
    template_name = 'cost/variances/list.html'

    def get(self, request):
        qs = models.CostVariance.objects.filter(tenant=request.tenant).select_related(
            'production_order', 'version',
        ).order_by('-analyzed_at')
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class CostVarianceCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/variances/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CostVarianceForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.CostVarianceForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.analyzed_by = request.user
            # Compute initial values from service
            v = actual_svc.compute_variances(obj.production_order, version=obj.version)
            if v:
                for k, val in v.items():
                    setattr(obj, k, val)
            obj.save()
            messages.success(request, f'Variance {obj.variance_number} created.')
            return redirect('cost:variance_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class CostVarianceDetailView(TenantRequiredMixin, View):
    template_name = 'cost/variances/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.CostVariance, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {'obj': obj})


class CostVarianceEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/variances/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.CostVariance, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CostVarianceForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.CostVariance, pk=pk, tenant=request.tenant)
        form = forms.CostVarianceForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Variance updated.')
            return redirect('cost:variance_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class CostVarianceDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CostVariance, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Variance deleted.')
        return redirect('cost:variance_list')


class CostVarianceRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CostVariance, pk=pk, tenant=request.tenant)
        v = actual_svc.compute_variances(obj.production_order, version=obj.version)
        if v:
            for k, val in v.items():
                setattr(obj, k, val)
            obj.analyzed_at = timezone.now()
            obj.analyzed_by = request.user
            obj.save()
            messages.success(request, 'Variance recomputed.')
        else:
            messages.warning(request, 'No standard cost row for this product/version - skipped.')
        return redirect('cost:variance_detail', pk=pk)


# ============================================================================
# 12.3 Job Cost & WIP
# ============================================================================

class JobCostListView(TenantRequiredMixin, View):
    template_name = 'cost/jobs/list.html'

    def get(self, request):
        qs = models.JobCost.objects.filter(tenant=request.tenant).select_related(
            'production_order', 'production_order__product',
        )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-opened_at'), request),
            'status_choices': models.JobCost.STATUS_CHOICES,
        })


class JobCostCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/jobs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.JobCostForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.JobCostForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            try:
                obj.save()
            except Exception as exc:
                messages.error(request, f'Could not create job: {exc}')
                return render(request, self.template_name, {'form': form, 'mode': 'create'})
            messages.success(request, f'Job {obj.job_number} created.')
            return redirect('cost:job_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class JobCostDetailView(TenantRequiredMixin, View):
    template_name = 'cost/jobs/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.JobCost, pk=pk, tenant=request.tenant)
        entries = obj.wip_entries.select_related(
            'cost_center', 'routing_operation',
        ).order_by('-entry_date')[:50]
        op_rollup = wip_svc.compute_operation_rollup(obj)
        return render(request, self.template_name, {
            'obj': obj, 'entries': entries, 'op_rollup': op_rollup,
            'close_form': forms.JobCloseForm(),
        })


class JobCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.JobCost, pk=pk, tenant=request.tenant)
        form = forms.JobCloseForm(request.POST)
        force = False
        if form.is_valid():
            force = form.cleaned_data.get('force') or False
        ok, msg = wip_svc.close_job(obj, closed_by=request.user, force=force)
        if ok:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect('cost:job_detail', pk=pk)


class JobCostDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.JobCost, pk=pk, tenant=request.tenant)
        if obj.wip_entries.exists():
            messages.error(request, 'Cannot delete a job with WIP entries.')
            return redirect('cost:job_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Job deleted.')
        return redirect('cost:job_list')


class WIPEntryListView(TenantRequiredMixin, View):
    template_name = 'cost/wip_entries/list.html'

    def get(self, request):
        qs = models.WIPEntry.objects.filter(tenant=request.tenant).select_related(
            'job', 'job__production_order', 'cost_center', 'routing_operation',
        )
        entry_type = request.GET.get('entry_type', '')
        if entry_type:
            qs = qs.filter(entry_type=entry_type)
        job_pk = request.GET.get('job', '')
        if job_pk:
            qs = qs.filter(job_id=job_pk)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-entry_date'), request),
            'entry_type_choices': models.WIPEntry.ENTRY_TYPE_CHOICES,
            'jobs': models.JobCost.objects.filter(tenant=request.tenant),
        })


class WIPEntryCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/wip_entries/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.WIPEntryForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.WIPEntryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            data = form.cleaned_data
            try:
                entry = wip_svc.post_wip_entry(
                    tenant=request.tenant,
                    job=data['job'],
                    entry_type=data['entry_type'],
                    amount=data['amount'],
                    quantity=data.get('quantity') or Decimal('0'),
                    unit_of_measure=data.get('unit_of_measure', ''),
                    cost_center=data.get('cost_center'),
                    routing_operation=data.get('routing_operation'),
                    posted_by=request.user,
                    notes=data.get('notes', ''),
                )
                messages.success(request, f'WIP entry {entry.entry_number} posted.')
                return redirect('cost:job_detail', pk=data['job'].pk)
            except Exception as exc:
                messages.error(request, f'Posting failed: {exc}')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class WIPEntryDetailView(TenantRequiredMixin, View):
    template_name = 'cost/wip_entries/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.WIPEntry, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {'obj': obj})


class WIPEntryDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.WIPEntry, pk=pk, tenant=request.tenant)
        if obj.job.status == 'closed':
            messages.error(request, 'Cannot delete an entry on a closed job.')
            return redirect('cost:wip_detail', pk=pk)
        job_pk = obj.job_id
        obj.delete()
        messages.success(request, 'WIP entry deleted.')
        return redirect('cost:job_detail', pk=job_pk)


# ============================================================================
# 12.4 Cost Drivers / Pools / Rates / Actuals / Allocations
# ============================================================================

# --- Cost Drivers ---

class CostDriverListView(TenantRequiredMixin, View):
    template_name = 'cost/cost_drivers/list.html'

    def get(self, request):
        qs = models.CostDriver.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {'page': _paginate(qs.order_by('code'), request)})


class CostDriverCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/cost_drivers/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CostDriverForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.CostDriverForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Driver created.')
            return redirect('cost:driver_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class CostDriverEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/cost_drivers/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.CostDriver, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CostDriverForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.CostDriver, pk=pk, tenant=request.tenant)
        form = forms.CostDriverForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Driver updated.')
            return redirect('cost:driver_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class CostDriverDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CostDriver, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Driver deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('cost:driver_list')


# --- Pools ---

class OverheadPoolListView(TenantRequiredMixin, View):
    template_name = 'cost/overhead_pools/list.html'

    def get(self, request):
        qs = models.OverheadPool.objects.filter(tenant=request.tenant).select_related('default_driver')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        pool_type = request.GET.get('pool_type', '')
        if pool_type:
            qs = qs.filter(pool_type=pool_type)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('code'), request),
            'pool_type_choices': models.OverheadPool.POOL_TYPE_CHOICES,
        })


class OverheadPoolCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/overhead_pools/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.OverheadPoolForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.OverheadPoolForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Pool created.')
            return redirect('cost:pool_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class OverheadPoolEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/overhead_pools/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.OverheadPool, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.OverheadPoolForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.OverheadPool, pk=pk, tenant=request.tenant)
        form = forms.OverheadPoolForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pool updated.')
            return redirect('cost:pool_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class OverheadPoolDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.OverheadPool, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Pool deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('cost:pool_list')


# --- Rates ---

class OverheadRateListView(TenantRequiredMixin, View):
    template_name = 'cost/overhead_rates/list.html'

    def get(self, request):
        qs = models.OverheadRate.objects.filter(tenant=request.tenant).select_related(
            'pool', 'period', 'driver',
        ).order_by('-period__start_date', 'pool__code')
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class OverheadRateCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/overhead_rates/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.OverheadRateForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.OverheadRateForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Rate created.')
            return redirect('cost:rate_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class OverheadRateEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/overhead_rates/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.OverheadRate, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.OverheadRateForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.OverheadRate, pk=pk, tenant=request.tenant)
        form = forms.OverheadRateForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rate updated.')
            return redirect('cost:rate_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class OverheadRateDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.OverheadRate, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Rate deleted.')
        return redirect('cost:rate_list')


# --- Driver Actuals ---

class DriverActualsListView(TenantRequiredMixin, View):
    template_name = 'cost/driver_actuals/list.html'

    def get(self, request):
        qs = models.DriverActuals.objects.filter(tenant=request.tenant).select_related(
            'driver', 'period', 'cost_center', 'production_order',
        ).order_by('-recorded_at')
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class DriverActualsCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/driver_actuals/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.DriverActualsForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.DriverActualsForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.recorded_by = request.user
            obj.save()
            messages.success(request, 'Driver actuals recorded.')
            return redirect('cost:driver_actuals_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class DriverActualsEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/driver_actuals/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.DriverActuals, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.DriverActualsForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.DriverActuals, pk=pk, tenant=request.tenant)
        form = forms.DriverActualsForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Driver actuals updated.')
            return redirect('cost:driver_actuals_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class DriverActualsDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DriverActuals, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Driver actuals deleted.')
        return redirect('cost:driver_actuals_list')


# --- Allocations ---

class OverheadAllocationListView(TenantRequiredMixin, View):
    template_name = 'cost/overhead_allocations/list.html'

    def get(self, request):
        qs = models.OverheadAllocation.objects.filter(tenant=request.tenant).select_related(
            'pool', 'period', 'target_cost_center', 'target_production_order',
        ).order_by('-posted_at')
        return render(request, self.template_name, {
            'page': _paginate(qs, request),
            'apply_form': forms.OverheadApplyForm(tenant=request.tenant),
        })


class OverheadAllocationDetailView(TenantRequiredMixin, View):
    template_name = 'cost/overhead_allocations/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.OverheadAllocation, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'obj': obj,
            'reverse_form': forms.OverheadReverseForm(),
        })


class OverheadApplyView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.OverheadApplyForm(request.POST, tenant=request.tenant)
        if not form.is_valid():
            messages.error(request, 'Pick an open period to apply overhead to.')
            return redirect('cost:allocation_list')
        period = form.cleaned_data['period']
        try:
            counts = oh_svc.apply_overhead(period, posted_by=request.user)
            messages.success(
                request,
                f'Overhead applied: {counts["allocations"]} allocations, '
                f'{counts["wip_entries"]} WIP entries.'
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('cost:allocation_list')


class OverheadReverseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.OverheadAllocation, pk=pk, tenant=request.tenant)
        form = forms.OverheadReverseForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Reversal reason is required.')
            return redirect('cost:allocation_detail', pk=pk)
        if obj.is_reversed:
            messages.warning(request, 'Allocation already reversed.')
            return redirect('cost:allocation_detail', pk=pk)
        if obj.period.status == 'closed':
            messages.error(request, 'Cannot reverse on a closed period.')
            return redirect('cost:allocation_detail', pk=pk)
        # Reverse just this single allocation (vs reverse_overhead which does all).
        from .services import wip as wip_svc2
        wip = models.WIPEntry.all_objects.filter(
            source_overhead_allocation=obj, is_reversal=False,
        ).first()
        if wip is not None:
            wip_svc2.reverse_wip_entry(
                wip, posted_by=request.user,
                reason=form.cleaned_data['reversal_reason'],
            )
        obj.is_reversed = True
        obj.reversal_reason = form.cleaned_data['reversal_reason']
        obj.save(update_fields=['is_reversed', 'reversal_reason', 'updated_at'])
        messages.success(request, 'Allocation reversed.')
        return redirect('cost:allocation_detail', pk=pk)


# ============================================================================
# 12.5 Periods / COGM / Margin / P&L
# ============================================================================

class PeriodListView(TenantRequiredMixin, View):
    template_name = 'cost/periods/list.html'

    def get(self, request):
        qs = models.AccountingPeriod.objects.filter(tenant=request.tenant)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-start_date'), request),
            'status_choices': models.AccountingPeriod.STATUS_CHOICES,
        })


class PeriodCreateView(TenantAdminRequiredMixin, View):
    template_name = 'cost/periods/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.AccountingPeriodForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.AccountingPeriodForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Period {obj.period_number} created.')
            return redirect('cost:period_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class PeriodDetailView(TenantRequiredMixin, View):
    template_name = 'cost/periods/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        cogm = models.COGMReport.objects.filter(tenant=request.tenant, period=obj).first()
        margins = models.GrossMarginReport.objects.filter(
            tenant=request.tenant, period=obj,
        ).select_related('product').order_by('-gross_margin')
        pnl = models.PlantPnLReport.objects.filter(tenant=request.tenant, period=obj).first()
        return render(request, self.template_name, {
            'obj': obj, 'cogm': cogm, 'margins': margins, 'pnl': pnl,
            'lock_form': forms.AccountingPeriodLockForm(),
        })


class PeriodEditView(TenantAdminRequiredMixin, View):
    template_name = 'cost/periods/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        if obj.status == 'closed':
            messages.warning(request, 'Closed periods cannot be edited.')
            return redirect('cost:period_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.AccountingPeriodForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        if obj.status == 'closed':
            messages.error(request, 'Closed periods cannot be edited.')
            return redirect('cost:period_detail', pk=pk)
        form = forms.AccountingPeriodForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Period updated.')
            return redirect('cost:period_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class PeriodDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        if obj.status != 'open':
            messages.error(request, 'Only open periods can be deleted.')
            return redirect('cost:period_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Period deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('cost:period_detail', pk=pk)
        return redirect('cost:period_list')


class PeriodLockView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        if not obj.is_lockable():
            messages.error(request, 'Only open periods can be locked.')
            return redirect('cost:period_detail', pk=pk)
        form = forms.AccountingPeriodLockForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Confirmation is required to lock.')
            return redirect('cost:period_detail', pk=pk)
        ok = _atomic_status_transition(
            models.AccountingPeriod, pk, request.tenant,
            from_states=['open'], to_state='locked',
            extra_fields={
                'locked_by': request.user, 'locked_at': timezone.now(),
                'notes': form.cleaned_data.get('notes', '') or obj.notes,
            },
        )
        if ok:
            messages.success(request, 'Period locked.')
        else:
            messages.error(request, 'Lock failed.')
        return redirect('cost:period_detail', pk=pk)


class PeriodCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AccountingPeriod, pk=pk, tenant=request.tenant)
        if not obj.is_closable():
            messages.error(request, 'Only locked periods can be closed.')
            return redirect('cost:period_detail', pk=pk)
        ok = _atomic_status_transition(
            models.AccountingPeriod, pk, request.tenant,
            from_states=['locked'], to_state='closed',
            extra_fields={
                'closed_by': request.user, 'closed_at': timezone.now(),
            },
        )
        if ok:
            # Generate final reports.
            try:
                report_svc.generate_cogm(obj, generated_by=request.user)
                report_svc.generate_gross_margin(obj)
                report_svc.generate_plant_pnl(obj, generated_by=request.user)
            except Exception:
                pass
            messages.success(request, 'Period closed and reports generated.')
        else:
            messages.error(request, 'Close failed.')
        return redirect('cost:period_detail', pk=pk)


# --- COGM ---

class COGMReportListView(TenantRequiredMixin, View):
    template_name = 'cost/cogm/list.html'

    def get(self, request):
        qs = models.COGMReport.objects.filter(tenant=request.tenant).select_related('period')
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-period__start_date'), request),
        })


class COGMReportDetailView(TenantRequiredMixin, View):
    template_name = 'cost/cogm/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.COGMReport, pk=pk, tenant=request.tenant)
        chart = {
            'labels': ['Opening WIP', 'DM', 'DL', 'OH Applied', 'Closing WIP'],
            'values': [
                float(obj.opening_wip or 0),
                float(obj.direct_materials or 0),
                float(obj.direct_labor or 0),
                float(obj.overhead_applied or 0),
                -float(obj.closing_wip or 0),
            ],
        }
        return render(request, self.template_name, {'obj': obj, 'chart': chart})


class COGMGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        period = get_object_or_404(models.AccountingPeriod, pk=period_pk, tenant=request.tenant)
        report = report_svc.generate_cogm(period, generated_by=request.user)
        messages.success(request, f'COGM generated: {report.cogm}.')
        return redirect('cost:cogm_detail', pk=report.pk)


# --- Gross Margin ---

class GrossMarginListView(TenantRequiredMixin, View):
    template_name = 'cost/gross_margin/list.html'

    def get(self, request):
        qs = models.GrossMarginReport.objects.filter(tenant=request.tenant).select_related(
            'period', 'product',
        )
        period_pk = request.GET.get('period', '')
        if period_pk:
            qs = qs.filter(period_id=period_pk)
        product_pk = request.GET.get('product', '')
        if product_pk:
            qs = qs.filter(product_id=product_pk)
        from apps.plm.models import Product
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-period__start_date', '-gross_margin'), request),
            'periods': models.AccountingPeriod.objects.filter(tenant=request.tenant),
            'products': Product.objects.filter(tenant=request.tenant),
        })


class GrossMarginDetailView(TenantRequiredMixin, View):
    template_name = 'cost/gross_margin/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.GrossMarginReport, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {'obj': obj})


class GrossMarginGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        period = get_object_or_404(models.AccountingPeriod, pk=period_pk, tenant=request.tenant)
        result = report_svc.generate_gross_margin(period)
        messages.success(
            request,
            f'Margin rows: {result["created"]} created, {result["updated"]} updated.'
        )
        return redirect('cost:margin_list')


# --- Plant P&L ---

class PlantPnLListView(TenantRequiredMixin, View):
    template_name = 'cost/plant_pnl/list.html'

    def get(self, request):
        qs = models.PlantPnLReport.objects.filter(tenant=request.tenant).select_related('period')
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-period__start_date'), request),
            'generate_form': forms.PlantPnLForm(tenant=request.tenant),
        })


class PlantPnLDetailView(TenantRequiredMixin, View):
    template_name = 'cost/plant_pnl/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.PlantPnLReport, pk=pk, tenant=request.tenant)
        chart = {
            'labels': ['Revenue', 'COGM', 'Selling', 'G&A', 'Unallocated', 'OI'],
            'values': [
                float(obj.revenue or 0),
                -float(obj.cogm or 0),
                -float(obj.selling_expense or 0),
                -float(obj.general_admin_expense or 0),
                -float(obj.unallocated_overhead or 0),
                float(obj.operating_income or 0),
            ],
        }
        return render(request, self.template_name, {'obj': obj, 'chart': chart})


class PlantPnLGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.PlantPnLForm(request.POST, tenant=request.tenant)
        if not form.is_valid():
            messages.error(request, 'Invalid input.')
            return redirect('cost:pnl_list')
        period = form.cleaned_data['period']
        report = report_svc.generate_plant_pnl(
            period,
            selling_expense=form.cleaned_data['selling_expense'],
            ga_expense=form.cleaned_data['general_admin_expense'],
            unallocated_overhead=form.cleaned_data['unallocated_overhead'],
            generated_by=request.user,
        )
        messages.success(request, f'P&L generated for {period.name}.')
        return redirect('cost:pnl_detail', pk=report.pk)
