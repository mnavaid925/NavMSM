"""Module 10 - Equipment & Asset Management views.

Read-only surfaces use ``TenantRequiredMixin`` (Lesson L-10).
State-changing surfaces (workflow transitions, deletes, admin CRUD) use
``TenantAdminRequiredMixin``.

Workflow transitions use a conditional ``UPDATE ... WHERE status IN (...)``
for race safety (Lessons L-03, L-12).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services.downtime import refresh_mwo_downtime
from .services.pm_scheduler import generate_upcoming_pm
from .services.prediction import check_reading
from .services.tool_life import consume_usage_log

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
    template_name = 'eam/index.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        ctx = {
            'asset_count': models.Asset.objects.filter(tenant=t, is_active=True).count(),
            'critical_assets': models.Asset.objects.filter(
                tenant=t, criticality='critical', is_active=True,
            ).count(),
            'down_assets': models.Asset.objects.filter(tenant=t, status='down').count(),
            'open_mwos': models.MaintenanceWorkOrder.objects.filter(
                tenant=t, status__in=('draft', 'scheduled', 'in_progress', 'on_hold'),
            ).count(),
            'overdue_pm': models.PMSchedule.objects.filter(
                tenant=t, status='scheduled', scheduled_date__lt=today,
            ).count(),
            'open_predictions': models.FailurePrediction.objects.filter(
                tenant=t, status__in=('open', 'investigating'),
            ).count(),
            'tool_count': models.Tool.objects.filter(tenant=t, is_active=True).count(),
            'recent_mwos': models.MaintenanceWorkOrder.objects.filter(tenant=t).select_related(
                'asset', 'reported_by',
            ).order_by('-id')[:8],
            'upcoming_pm': models.PMSchedule.objects.filter(
                tenant=t, status='scheduled', scheduled_date__gte=today,
            ).select_related('plan', 'plan__asset').order_by('scheduled_date')[:8],
            'critical_predictions': models.FailurePrediction.objects.filter(
                tenant=t, status__in=('open', 'investigating'),
            ).select_related('asset').order_by('-created_at')[:5],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 10.1  Asset Categories
# ============================================================================

class AssetCategoryListView(TenantRequiredMixin, View):
    template_name = 'eam/categories/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.AssetCategory.objects.filter(tenant=t).select_related('parent')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(name__icontains=q)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        page = _paginate(qs.order_by('name'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'active_filter': active,
        })


class AssetCategoryCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/categories/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.AssetCategoryForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.AssetCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Category "{obj.name}" created.')
            return redirect('eam:category_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class AssetCategoryEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/categories/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AssetCategory, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.AssetCategoryForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'is_create': False,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.AssetCategory, pk=pk, tenant=request.tenant)
        form = forms.AssetCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.')
            return redirect('eam:category_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'is_create': False})


class AssetCategoryDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AssetCategory, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                obj.delete()
            messages.success(request, 'Category deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete category: {e}')
        return redirect('eam:category_list')

    def get(self, request, pk):
        return redirect('eam:category_list')


# ============================================================================
# 10.1  Assets
# ============================================================================

class AssetListView(TenantRequiredMixin, View):
    template_name = 'eam/assets/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.Asset.objects.filter(tenant=t).select_related('category', 'parent', 'warehouse')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(tag__icontains=q) | Q(name__icontains=q)
                | Q(serial_number__icontains=q) | Q(model_number__icontains=q)
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        criticality = request.GET.get('criticality', '')
        if criticality:
            qs = qs.filter(criticality=criticality)
        category_pk = request.GET.get('category', '')
        if category_pk:
            qs = qs.filter(category_id=category_pk)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        page = _paginate(qs.order_by('tag'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'criticality_filter': criticality,
            'category_filter': category_pk, 'active_filter': active,
            'status_choices': models.Asset.STATUS_CHOICES,
            'criticality_choices': models.Asset.CRITICALITY_CHOICES,
            'categories': models.AssetCategory.objects.filter(tenant=t, is_active=True),
        })


class AssetCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/assets/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.AssetForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.AssetForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            for _ in range(5):
                try:
                    with transaction.atomic():
                        obj = form.save(commit=False)
                        obj.tenant = request.tenant
                        obj.save()
                    messages.success(request, f'Asset {obj.tag} created.')
                    return redirect('eam:asset_detail', pk=obj.pk)
                except IntegrityError:
                    obj.tag = ''  # retry sequence
                    continue
            messages.error(request, 'Could not assign a unique asset tag, please retry.')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class AssetDetailView(TenantRequiredMixin, View):
    template_name = 'eam/assets/detail.html'

    def get(self, request, pk):
        asset = get_object_or_404(
            models.Asset.objects.select_related('category', 'parent', 'warehouse'),
            pk=pk, tenant=request.tenant,
        )
        spare_parts = asset.spare_parts.select_related('product')
        readings = asset.meter_readings.order_by('-recorded_at')[:10]
        documents = asset.documents.order_by('-created_at')
        children = asset.children.all()
        plans = asset.maintenance_plans.filter(is_active=True)
        open_mwos = asset.work_orders.filter(
            status__in=('draft', 'scheduled', 'in_progress', 'on_hold'),
        ).order_by('-reported_at')[:5]
        recent_downtime = asset.downtime_events.order_by('-started_at')[:5]
        monitoring_points = asset.monitoring_points.filter(is_active=True)
        return render(request, self.template_name, {
            'asset': asset,
            'spare_parts': spare_parts,
            'readings': readings,
            'documents': documents,
            'children': children,
            'plans': plans,
            'open_mwos': open_mwos,
            'recent_downtime': recent_downtime,
            'monitoring_points': monitoring_points,
            'spare_form': forms.AssetSparePartForm(tenant=request.tenant, asset=asset),
            'reading_form': forms.AssetMeterReadingForm(tenant=request.tenant),
            'document_form': forms.AssetDocumentForm(tenant=request.tenant),
        })


class AssetEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/assets/form.html'

    def get(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.AssetForm(instance=asset, tenant=request.tenant),
            'asset': asset, 'is_create': False,
        })

    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        form = forms.AssetForm(request.POST, instance=asset, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Asset updated.')
            return redirect('eam:asset_detail', pk=asset.pk)
        return render(request, self.template_name, {'form': form, 'asset': asset, 'is_create': False})


class AssetDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                asset.delete()
            messages.success(request, 'Asset deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete asset: {e}')
            return redirect('eam:asset_detail', pk=pk)
        return redirect('eam:asset_list')

    def get(self, request, pk):
        return redirect('eam:asset_detail', pk=pk)


class AssetRetireView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        if asset.status == 'retired':
            messages.info(request, 'Asset is already retired.')
            return redirect('eam:asset_detail', pk=pk)
        models.Asset.all_objects.filter(pk=pk).update(status='retired', is_active=False)
        messages.success(request, 'Asset retired.')
        return redirect('eam:asset_detail', pk=pk)


class AssetReactivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        models.Asset.all_objects.filter(pk=pk).update(status='operational', is_active=True)
        messages.success(request, 'Asset reactivated.')
        return redirect('eam:asset_detail', pk=pk)


# Spare parts (inline on asset detail)

class AssetSparePartCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        form = forms.AssetSparePartForm(request.POST, tenant=request.tenant, asset=asset)
        if form.is_valid():
            sp = form.save(commit=False)
            sp.tenant = request.tenant
            sp.asset = asset
            sp.save()
            messages.success(request, 'Spare part linked.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:asset_detail', pk=pk)


class AssetSparePartDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        sp = get_object_or_404(models.AssetSparePart, pk=pk, tenant=request.tenant)
        asset_pk = sp.asset_id
        sp.delete()
        messages.success(request, 'Spare part link removed.')
        return redirect('eam:asset_detail', pk=asset_pk)


class AssetMeterReadingCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        form = forms.AssetMeterReadingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.asset = asset
            r.recorded_by = request.user
            r.save()
            messages.success(request, 'Meter reading recorded.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:asset_detail', pk=pk)


class AssetMeterReadingListView(TenantRequiredMixin, View):
    template_name = 'eam/meter_readings/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.AssetMeterReading.objects.filter(tenant=t).select_related('asset')
        asset_pk = request.GET.get('asset', '')
        if asset_pk:
            qs = qs.filter(asset_id=asset_pk)
        meter = request.GET.get('meter_type', '')
        if meter:
            qs = qs.filter(meter_type=meter)
        page = _paginate(qs.order_by('-recorded_at'), request)
        return render(request, self.template_name, {
            'page_obj': page,
            'asset_filter': asset_pk, 'meter_filter': meter,
            'assets': models.Asset.objects.filter(tenant=t),
            'meter_choices': models.AssetMeterReading.METER_CHOICES,
        })


class AssetDocumentCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        asset = get_object_or_404(models.Asset, pk=pk, tenant=request.tenant)
        form = forms.AssetDocumentForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            d = form.save(commit=False)
            d.tenant = request.tenant
            d.asset = asset
            d.uploaded_by = request.user
            d.save()
            messages.success(request, 'Document uploaded.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:asset_detail', pk=pk)


class AssetDocumentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        d = get_object_or_404(models.AssetDocument, pk=pk, tenant=request.tenant)
        asset_pk = d.asset_id
        d.delete()
        messages.success(request, 'Document removed.')
        return redirect('eam:asset_detail', pk=asset_pk)


# ============================================================================
# 10.2  Maintenance Plans + Tasks + Schedules
# ============================================================================

class PMPlanListView(TenantRequiredMixin, View):
    template_name = 'eam/pm_plans/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.MaintenancePlan.objects.filter(tenant=t).select_related('asset')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(asset__tag__icontains=q))
        trigger = request.GET.get('trigger', '')
        if trigger:
            qs = qs.filter(trigger_type=trigger)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        asset_pk = request.GET.get('asset', '')
        if asset_pk:
            qs = qs.filter(asset_id=asset_pk)
        page = _paginate(qs.order_by('asset__tag', 'name'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'trigger_filter': trigger, 'active_filter': active,
            'asset_filter': asset_pk,
            'trigger_choices': models.MaintenancePlan.TRIGGER_CHOICES,
            'assets': models.Asset.objects.filter(tenant=t, is_active=True),
        })


class PMPlanCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/pm_plans/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.MaintenancePlanForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.MaintenancePlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            p = form.save(commit=False)
            p.tenant = request.tenant
            p.created_by = request.user
            p.save()
            messages.success(request, f'PM plan "{p.name}" created. Add tasks next.')
            return redirect('eam:pmplan_detail', pk=p.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class PMPlanDetailView(TenantRequiredMixin, View):
    template_name = 'eam/pm_plans/detail.html'

    def get(self, request, pk):
        plan = get_object_or_404(
            models.MaintenancePlan.objects.select_related('asset'),
            pk=pk, tenant=request.tenant,
        )
        tasks = plan.tasks.order_by('sequence')
        upcoming = plan.schedules.order_by('-scheduled_date')[:10]
        return render(request, self.template_name, {
            'plan': plan, 'tasks': tasks, 'upcoming': upcoming,
            'task_form': forms.MaintenanceTaskForm(tenant=request.tenant),
        })


class PMPlanEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/pm_plans/form.html'

    def get(self, request, pk):
        plan = get_object_or_404(models.MaintenancePlan, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.MaintenancePlanForm(instance=plan, tenant=request.tenant),
            'plan': plan, 'is_create': False,
        })

    def post(self, request, pk):
        plan = get_object_or_404(models.MaintenancePlan, pk=pk, tenant=request.tenant)
        form = forms.MaintenancePlanForm(request.POST, instance=plan, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'PM plan updated.')
            return redirect('eam:pmplan_detail', pk=plan.pk)
        return render(request, self.template_name, {'form': form, 'plan': plan, 'is_create': False})


class PMPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(models.MaintenancePlan, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                plan.delete()
            messages.success(request, 'PM plan deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete PM plan: {e}')
            return redirect('eam:pmplan_detail', pk=pk)
        return redirect('eam:pmplan_list')

    def get(self, request, pk):
        return redirect('eam:pmplan_detail', pk=pk)


class PMTaskCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(models.MaintenancePlan, pk=pk, tenant=request.tenant)
        form = forms.MaintenanceTaskForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            t = form.save(commit=False)
            t.tenant = request.tenant
            t.plan = plan
            try:
                with transaction.atomic():
                    t.save()
                messages.success(request, 'Task added.')
            except IntegrityError:
                messages.error(request, 'Sequence number already exists for this plan.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:pmplan_detail', pk=pk)


class PMTaskDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(models.MaintenanceTask, pk=pk, tenant=request.tenant)
        plan_pk = task.plan_id
        task.delete()
        messages.success(request, 'Task removed.')
        return redirect('eam:pmplan_detail', pk=plan_pk)


class PMPlanGenerateView(TenantAdminRequiredMixin, View):
    """Generate the next batch of PMSchedule rows for a plan."""

    def post(self, request, pk):
        plan = get_object_or_404(models.MaintenancePlan, pk=pk, tenant=request.tenant)
        if not plan.is_active:
            messages.error(request, 'Plan is inactive - reactivate before generating.')
            return redirect('eam:pmplan_detail', pk=pk)
        upcoming = generate_upcoming_pm(plan, horizon_days=180, max_count=4)
        created = 0
        for sched_date, sched_meter in upcoming:
            if sched_date is None:
                continue
            exists = models.PMSchedule.all_objects.filter(
                tenant=request.tenant, plan=plan, scheduled_date=sched_date,
            ).exists()
            if exists:
                continue
            for _ in range(5):
                try:
                    with transaction.atomic():
                        models.PMSchedule.all_objects.create(
                            tenant=request.tenant,
                            plan=plan,
                            scheduled_date=sched_date,
                            scheduled_meter=sched_meter,
                        )
                    created += 1
                    break
                except IntegrityError:
                    continue
        if created:
            messages.success(request, f'Generated {created} upcoming PM schedule(s).')
        else:
            messages.info(request, 'No new schedules to generate (already covered).')
        return redirect('eam:pmplan_detail', pk=pk)


# ----- PM Schedules -----

class PMScheduleListView(TenantRequiredMixin, View):
    template_name = 'eam/pm_schedules/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.PMSchedule.objects.filter(tenant=t).select_related(
            'plan', 'plan__asset', 'assignee',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(schedule_number__icontains=q) | Q(plan__name__icontains=q)
                | Q(plan__asset__tag__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('scheduled_date'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.PMSchedule.STATUS_CHOICES,
        })


class PMScheduleCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/pm_schedules/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.PMScheduleForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.PMScheduleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            for _ in range(5):
                try:
                    with transaction.atomic():
                        s = form.save(commit=False)
                        s.tenant = request.tenant
                        s.save()
                    messages.success(request, f'PM schedule {s.schedule_number} created.')
                    return redirect('eam:pmschedule_detail', pk=s.pk)
                except IntegrityError:
                    continue
            messages.error(request, 'Could not assign a unique schedule number, please retry.')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class PMScheduleDetailView(TenantRequiredMixin, View):
    template_name = 'eam/pm_schedules/detail.html'

    def get(self, request, pk):
        s = get_object_or_404(
            models.PMSchedule.objects.select_related('plan', 'plan__asset', 'assignee'),
            pk=pk, tenant=request.tenant,
        )
        tasks = s.plan.tasks.order_by('sequence')
        completions = {c.task_id: c for c in s.task_completions.all()}
        # Attach the completion (if any) to each task so the template doesn't
        # need a dict-by-variable lookup.
        task_rows = [(t, completions.get(t.pk)) for t in tasks]
        return render(request, self.template_name, {
            's': s, 'task_rows': task_rows,
            'completion_form': forms.PMTaskCompletionForm(tenant=request.tenant, schedule=s),
            'complete_form': forms.PMScheduleCompleteForm(schedule=s),
        })


class PMScheduleStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.PMSchedule, pk, request.tenant,
            from_states=('scheduled', 'overdue'), to_state='in_progress',
            extra_fields={'started_at': timezone.now()},
        )
        if not ok:
            messages.error(request, 'PM schedule is not in a startable state.')
        else:
            messages.success(request, 'PM started.')
        return redirect('eam:pmschedule_detail', pk=pk)


class PMScheduleCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        s = get_object_or_404(models.PMSchedule, pk=pk, tenant=request.tenant)
        form = forms.PMScheduleCompleteForm(request.POST, schedule=s)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
            return redirect('eam:pmschedule_detail', pk=pk)
        ok = _atomic_status_transition(
            models.PMSchedule, pk, request.tenant,
            from_states=('scheduled', 'in_progress', 'overdue'),
            to_state='completed',
            extra_fields={
                'completed_at': timezone.now(), 'completed_by': request.user,
                'notes': form.cleaned_data.get('notes', ''),
            },
        )
        if not ok:
            messages.error(request, 'PM cannot be completed from current state.')
            return redirect('eam:pmschedule_detail', pk=pk)
        # Roll plan denorms forward.
        models.MaintenancePlan.all_objects.filter(pk=s.plan_id).update(
            last_done_at=s.scheduled_date,
        )
        messages.success(request, f'PM {s.schedule_number} completed.')
        return redirect('eam:pmschedule_detail', pk=pk)


class PMScheduleSkipView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.PMSchedule, pk, request.tenant,
            from_states=('scheduled', 'overdue'), to_state='skipped',
        )
        if not ok:
            messages.error(request, 'PM cannot be skipped from current state.')
        else:
            messages.success(request, 'PM skipped.')
        return redirect('eam:pmschedule_detail', pk=pk)


class PMTaskCompletionCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        s = get_object_or_404(models.PMSchedule, pk=pk, tenant=request.tenant)
        form = forms.PMTaskCompletionForm(request.POST, tenant=request.tenant, schedule=s)
        if form.is_valid():
            tc = form.save(commit=False)
            tc.tenant = request.tenant
            tc.pm_schedule = s
            tc.completed_by = request.user
            try:
                with transaction.atomic():
                    tc.save()
                messages.success(request, 'Task result recorded.')
            except IntegrityError:
                messages.info(request, 'A result for this task already exists.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:pmschedule_detail', pk=pk)


# ============================================================================
# 10.3  Predictive Maintenance
# ============================================================================

class ConditionPointListView(TenantRequiredMixin, View):
    template_name = 'eam/condition_points/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.ConditionMonitoringPoint.objects.filter(tenant=t).select_related('asset')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(asset__tag__icontains=q))
        param = request.GET.get('parameter', '')
        if param:
            qs = qs.filter(parameter=param)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        page = _paginate(qs.order_by('asset__tag', 'name'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'parameter_filter': param, 'active_filter': active,
            'parameter_choices': models.ConditionMonitoringPoint.PARAMETER_CHOICES,
        })


class ConditionPointCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/condition_points/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ConditionMonitoringPointForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.ConditionMonitoringPointForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Monitoring point created.')
            return redirect('eam:condition_point_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class ConditionPointDetailView(TenantRequiredMixin, View):
    template_name = 'eam/condition_points/detail.html'

    def get(self, request, pk):
        point = get_object_or_404(
            models.ConditionMonitoringPoint.objects.select_related('asset'),
            pk=pk, tenant=request.tenant,
        )
        readings = point.readings.order_by('-recorded_at')[:50]
        return render(request, self.template_name, {
            'point': point, 'readings': readings,
            'reading_form': forms.ConditionReadingForm(tenant=request.tenant),
        })


class ConditionPointEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/condition_points/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.ConditionMonitoringPoint, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.ConditionMonitoringPointForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'is_create': False,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ConditionMonitoringPoint, pk=pk, tenant=request.tenant)
        form = forms.ConditionMonitoringPointForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Monitoring point updated.')
            return redirect('eam:condition_point_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'is_create': False})


class ConditionPointDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ConditionMonitoringPoint, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                obj.delete()
            messages.success(request, 'Monitoring point deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
            return redirect('eam:condition_point_detail', pk=pk)
        return redirect('eam:condition_point_list')

    def get(self, request, pk):
        return redirect('eam:condition_point_detail', pk=pk)


class ConditionReadingCreateView(TenantRequiredMixin, View):
    """Any tenant user can record a reading."""

    def post(self, request, pk=None):
        form = forms.ConditionReadingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.recorded_by = request.user
            with transaction.atomic():
                r.save()  # signal will classify + spawn prediction if critical
            messages.success(request, 'Reading recorded.')
            return redirect('eam:condition_point_detail', pk=r.point_id)
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        if pk:
            return redirect('eam:condition_point_detail', pk=pk)
        return redirect('eam:condition_point_list')


class ConditionReadingListView(TenantRequiredMixin, View):
    template_name = 'eam/condition_readings/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.ConditionReading.objects.filter(tenant=t).select_related(
            'point', 'point__asset',
        )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        point_pk = request.GET.get('point', '')
        if point_pk:
            qs = qs.filter(point_id=point_pk)
        page = _paginate(qs.order_by('-recorded_at'), request)
        return render(request, self.template_name, {
            'page_obj': page,
            'status_filter': status, 'point_filter': point_pk,
            'status_choices': models.ConditionReading.STATUS_CHOICES,
            'points': models.ConditionMonitoringPoint.objects.filter(tenant=t),
        })


# ----- Failure Predictions -----

class FailurePredictionListView(TenantRequiredMixin, View):
    template_name = 'eam/failure_predictions/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.FailurePrediction.objects.filter(tenant=t).select_related('asset')
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        asset_pk = request.GET.get('asset', '')
        if asset_pk:
            qs = qs.filter(asset_id=asset_pk)
        page = _paginate(qs.order_by('-created_at'), request)
        return render(request, self.template_name, {
            'page_obj': page,
            'status_filter': status, 'asset_filter': asset_pk,
            'status_choices': models.FailurePrediction.STATUS_CHOICES,
            'assets': models.Asset.objects.filter(tenant=t),
        })


class FailurePredictionDetailView(TenantRequiredMixin, View):
    template_name = 'eam/failure_predictions/detail.html'

    def get(self, request, pk):
        p = get_object_or_404(
            models.FailurePrediction.objects.select_related(
                'asset', 'triggered_by_reading', 'triggered_by_reading__point',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'p': p,
            'resolve_form': forms.FailurePredictionResolveForm(),
        })


class FailurePredictionInvestigateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.FailurePrediction, pk, request.tenant,
            from_states=('open',), to_state='investigating',
        )
        if not ok:
            messages.error(request, 'Prediction is not in open state.')
        else:
            messages.success(request, 'Investigation started.')
        return redirect('eam:prediction_detail', pk=pk)


class FailurePredictionResolveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        p = get_object_or_404(models.FailurePrediction, pk=pk, tenant=request.tenant)
        form = forms.FailurePredictionResolveForm(request.POST)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
            return redirect('eam:prediction_detail', pk=pk)
        outcome = form.cleaned_data['outcome']
        ok = _atomic_status_transition(
            models.FailurePrediction, pk, request.tenant,
            from_states=('open', 'investigating'), to_state=outcome,
            extra_fields={
                'resolved_at': timezone.now(),
                'resolved_by': request.user,
                'resolution_notes': form.cleaned_data['resolution_notes'],
            },
        )
        if not ok:
            messages.error(request, 'Prediction cannot be resolved from current state.')
        else:
            messages.success(request, f'Prediction marked {outcome}.')
        return redirect('eam:prediction_detail', pk=pk)


# ============================================================================
# 10.4  Maintenance Work Orders
# ============================================================================

class MWOListView(TenantRequiredMixin, View):
    template_name = 'eam/mwo/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.MaintenanceWorkOrder.objects.filter(tenant=t).select_related('asset')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(mwo_number__icontains=q) | Q(title__icontains=q)
                | Q(asset__tag__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        wo_type = request.GET.get('wo_type', '')
        if wo_type:
            qs = qs.filter(wo_type=wo_type)
        priority = request.GET.get('priority', '')
        if priority:
            qs = qs.filter(priority=priority)
        asset_pk = request.GET.get('asset', '')
        if asset_pk:
            qs = qs.filter(asset_id=asset_pk)
        page = _paginate(qs.order_by('-reported_at'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'wo_type_filter': wo_type,
            'priority_filter': priority, 'asset_filter': asset_pk,
            'status_choices': models.MaintenanceWorkOrder.STATUS_CHOICES,
            'wo_type_choices': models.MaintenanceWorkOrder.WO_TYPE_CHOICES,
            'priority_choices': models.MaintenanceWorkOrder.PRIORITY_CHOICES,
            'assets': models.Asset.objects.filter(tenant=t),
        })


class MWOCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/mwo/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.MaintenanceWorkOrderForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.MaintenanceWorkOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            for _ in range(5):
                try:
                    with transaction.atomic():
                        m = form.save(commit=False)
                        m.tenant = request.tenant
                        m.reported_by = request.user
                        m.save()
                    messages.success(request, f'Work order {m.mwo_number} created.')
                    return redirect('eam:mwo_detail', pk=m.pk)
                except IntegrityError:
                    continue
            messages.error(request, 'Could not assign a unique work-order number, please retry.')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class MWODetailView(TenantRequiredMixin, View):
    template_name = 'eam/mwo/detail.html'

    def get(self, request, pk):
        m = get_object_or_404(
            models.MaintenanceWorkOrder.objects.select_related(
                'asset', 'reported_by', 'assigned_to', 'completed_by',
                'source_pm_schedule', 'source_failure_prediction', 'source_andon',
            ),
            pk=pk, tenant=request.tenant,
        )
        labor_logs = m.labor_logs.select_related('technician').order_by('-started_at')
        material_logs = m.material_logs.select_related('product').order_by('-used_at')
        downtime_events = m.downtime_events.order_by('-started_at')
        return render(request, self.template_name, {
            'm': m,
            'labor_logs': labor_logs,
            'material_logs': material_logs,
            'downtime_events': downtime_events,
            'labor_form': forms.MWOLaborLogForm(tenant=request.tenant),
            'material_form': forms.MWOMaterialLogForm(tenant=request.tenant),
            'downtime_form': forms.DowntimeEventForm(tenant=request.tenant),
            'complete_form': forms.MWOCompleteForm(),
        })


class MWOEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/mwo/form.html'

    def get(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        if not m.is_editable():
            messages.error(request, 'Only draft / scheduled / on-hold MWOs can be edited.')
            return redirect('eam:mwo_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.MaintenanceWorkOrderForm(instance=m, tenant=request.tenant),
            'm': m, 'is_create': False,
        })

    def post(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        if not m.is_editable():
            messages.error(request, 'Only draft / scheduled / on-hold MWOs can be edited.')
            return redirect('eam:mwo_detail', pk=pk)
        form = forms.MaintenanceWorkOrderForm(request.POST, instance=m, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Work order updated.')
            return redirect('eam:mwo_detail', pk=m.pk)
        return render(request, self.template_name, {'form': form, 'm': m, 'is_create': False})


class MWODeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        if m.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft / cancelled MWOs can be deleted.')
            return redirect('eam:mwo_detail', pk=pk)
        try:
            with transaction.atomic():
                m.delete()
            messages.success(request, 'Work order deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
            return redirect('eam:mwo_detail', pk=pk)
        return redirect('eam:mwo_list')

    def get(self, request, pk):
        return redirect('eam:mwo_detail', pk=pk)


class MWOScheduleView(TenantAdminRequiredMixin, View):
    """draft -> scheduled."""
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('draft',), to_state='scheduled',
        )
        if not ok:
            messages.error(request, 'Only draft MWOs can be scheduled.')
        else:
            messages.success(request, 'Work order scheduled.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('draft', 'scheduled', 'on_hold'), to_state='in_progress',
            extra_fields={'started_at': timezone.now()},
        )
        if not ok:
            messages.error(request, 'Work order cannot be started from current state.')
        else:
            messages.success(request, 'Work started.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOHoldView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('in_progress',), to_state='on_hold',
        )
        if not ok:
            messages.error(request, 'Work order is not in progress.')
        else:
            messages.success(request, 'Work order placed on hold.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOResumeView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('on_hold',), to_state='in_progress',
        )
        if not ok:
            messages.error(request, 'Only on-hold work orders can be resumed.')
        else:
            messages.success(request, 'Work resumed.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        form = forms.MWOCompleteForm(request.POST)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
            return redirect('eam:mwo_detail', pk=pk)
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('in_progress',), to_state='completed',
            extra_fields={
                'completed_at': timezone.now(),
                'completed_by': request.user,
                'resolution_notes': form.cleaned_data['resolution_notes'],
                'root_cause': form.cleaned_data.get('root_cause', ''),
            },
        )
        if not ok:
            messages.error(request, 'Work order is not in progress.')
            return redirect('eam:mwo_detail', pk=pk)
        # Refresh downtime denorm.
        refresh_mwo_downtime(m)
        messages.success(request, f'Work order {m.mwo_number} completed.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.MaintenanceWorkOrder, pk, request.tenant,
            from_states=('draft', 'scheduled', 'in_progress', 'on_hold'),
            to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'Work order cannot be cancelled.')
        else:
            messages.success(request, 'Work order cancelled.')
        return redirect('eam:mwo_detail', pk=pk)


class MWOLaborLogCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        form = forms.MWOLaborLogForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            log = form.save(commit=False)
            log.tenant = request.tenant
            log.mwo = m
            log.save()
            messages.success(request, 'Labor log added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:mwo_detail', pk=pk)


class MWOMaterialLogCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        m = get_object_or_404(models.MaintenanceWorkOrder, pk=pk, tenant=request.tenant)
        form = forms.MWOMaterialLogForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            log = form.save(commit=False)
            log.tenant = request.tenant
            log.mwo = m
            log.save()
            messages.success(request, 'Material log added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:mwo_detail', pk=pk)


# ----- Downtime events -----

class DowntimeListView(TenantRequiredMixin, View):
    template_name = 'eam/downtime/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.DowntimeEvent.objects.filter(tenant=t).select_related('asset', 'mwo')
        asset_pk = request.GET.get('asset', '')
        if asset_pk:
            qs = qs.filter(asset_id=asset_pk)
        downtime_type = request.GET.get('downtime_type', '')
        if downtime_type:
            qs = qs.filter(downtime_type=downtime_type)
        page = _paginate(qs.order_by('-started_at'), request)
        return render(request, self.template_name, {
            'page_obj': page,
            'asset_filter': asset_pk, 'downtime_type_filter': downtime_type,
            'downtime_type_choices': models.DowntimeEvent.DOWNTIME_TYPE_CHOICES,
            'assets': models.Asset.objects.filter(tenant=t),
        })


class DowntimeCreateView(TenantRequiredMixin, View):
    """Inline create from MWO detail or asset detail."""

    def post(self, request, pk=None):
        form = forms.DowntimeEventForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            d = form.save(commit=False)
            d.tenant = request.tenant
            d.save()
            messages.success(request, 'Downtime event recorded.')
            if d.mwo_id:
                return redirect('eam:mwo_detail', pk=d.mwo_id)
            return redirect('eam:asset_detail', pk=d.asset_id)
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        return redirect('eam:downtime_list')


class DowntimeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        d = get_object_or_404(models.DowntimeEvent, pk=pk, tenant=request.tenant)
        mwo_pk = d.mwo_id
        d.delete()
        if mwo_pk:
            from .models import MaintenanceWorkOrder
            try:
                refresh_mwo_downtime(MaintenanceWorkOrder.all_objects.get(pk=mwo_pk))
            except MaintenanceWorkOrder.DoesNotExist:
                pass
        messages.success(request, 'Downtime event removed.')
        return redirect('eam:downtime_list')


# ============================================================================
# 10.5  Tools
# ============================================================================

class ToolListView(TenantRequiredMixin, View):
    template_name = 'eam/tools/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.Tool.objects.filter(tenant=t)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(tool_id__icontains=q) | Q(name__icontains=q))
        tool_type = request.GET.get('tool_type', '')
        if tool_type:
            qs = qs.filter(tool_type=tool_type)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        page = _paginate(qs.order_by('tool_id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'tool_type_filter': tool_type, 'status_filter': status,
            'active_filter': active,
            'tool_type_choices': models.Tool.TOOL_TYPE_CHOICES,
            'status_choices': models.Tool.STATUS_CHOICES,
        })


class ToolCreateView(TenantAdminRequiredMixin, View):
    template_name = 'eam/tools/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ToolForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.ToolForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            for _ in range(5):
                try:
                    with transaction.atomic():
                        t = form.save(commit=False)
                        t.tenant = request.tenant
                        t.save()
                    messages.success(request, f'Tool {t.tool_id} created.')
                    return redirect('eam:tool_detail', pk=t.pk)
                except IntegrityError:
                    continue
            messages.error(request, 'Could not assign a unique tool ID, please retry.')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class ToolDetailView(TenantRequiredMixin, View):
    template_name = 'eam/tools/detail.html'

    def get(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        usage_logs = tool.usage_logs.order_by('-used_at')[:20]
        maintenance_records = tool.maintenance_records.order_by('-performed_at')[:20]
        cavities = tool.cavity_histories.order_by('cavity_number') if tool.tool_type == 'mold' else None
        return render(request, self.template_name, {
            'tool': tool,
            'usage_logs': usage_logs,
            'maintenance_records': maintenance_records,
            'cavities': cavities,
            'usage_form': forms.ToolUsageLogForm(tenant=request.tenant),
            'maintenance_form': forms.ToolMaintenanceRecordForm(tenant=request.tenant),
            'cavity_form': forms.MoldCavityHistoryForm(tenant=request.tenant, tool=tool),
        })


class ToolEditView(TenantAdminRequiredMixin, View):
    template_name = 'eam/tools/form.html'

    def get(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.ToolForm(instance=tool, tenant=request.tenant),
            'tool': tool, 'is_create': False,
        })

    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        form = forms.ToolForm(request.POST, instance=tool, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tool updated.')
            return redirect('eam:tool_detail', pk=tool.pk)
        return render(request, self.template_name, {'form': form, 'tool': tool, 'is_create': False})


class ToolDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                tool.delete()
            messages.success(request, 'Tool deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete tool: {e}')
            return redirect('eam:tool_detail', pk=pk)
        return redirect('eam:tool_list')

    def get(self, request, pk):
        return redirect('eam:tool_detail', pk=pk)


class ToolRetireView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        models.Tool.all_objects.filter(pk=pk).update(status='retired', is_active=False)
        messages.success(request, 'Tool retired.')
        return redirect('eam:tool_detail', pk=pk)


class ToolReactivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        models.Tool.all_objects.filter(pk=pk).update(status='available', is_active=True)
        messages.success(request, 'Tool reactivated.')
        return redirect('eam:tool_detail', pk=pk)


class ToolUsageLogCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        form = forms.ToolUsageLogForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            consume_usage_log(
                tool,
                mes_work_order=form.cleaned_data.get('mes_work_order'),
                cycles_added=form.cleaned_data.get('cycles_added') or 0,
                hours_added=form.cleaned_data.get('hours_added') or Decimal('0'),
                operator=request.user,
                notes=form.cleaned_data.get('notes', ''),
            )
            messages.success(request, 'Usage logged.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:tool_detail', pk=pk)


class ToolMaintenanceRecordCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        form = forms.ToolMaintenanceRecordForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.tool = tool
            r.performed_by = request.user
            r.save()
            if r.record_type == 'sharpening':
                models.Tool.all_objects.filter(pk=tool.pk).update(
                    last_sharpened_at=r.performed_at,
                )
            messages.success(request, 'Maintenance record added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:tool_detail', pk=pk)


class ToolMaintenanceListView(TenantRequiredMixin, View):
    template_name = 'eam/tool_maintenance/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.ToolMaintenanceRecord.objects.filter(tenant=t).select_related('tool')
        record_type = request.GET.get('record_type', '')
        if record_type:
            qs = qs.filter(record_type=record_type)
        tool_pk = request.GET.get('tool', '')
        if tool_pk:
            qs = qs.filter(tool_id=tool_pk)
        page = _paginate(qs.order_by('-performed_at'), request)
        return render(request, self.template_name, {
            'page_obj': page,
            'record_type_filter': record_type, 'tool_filter': tool_pk,
            'record_type_choices': models.ToolMaintenanceRecord.RECORD_TYPE_CHOICES,
            'tools': models.Tool.objects.filter(tenant=t),
        })


class MoldCavityCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        tool = get_object_or_404(models.Tool, pk=pk, tenant=request.tenant)
        form = forms.MoldCavityHistoryForm(request.POST, tenant=request.tenant, tool=tool)
        if form.is_valid():
            c = form.save(commit=False)
            c.tenant = request.tenant
            c.tool = tool
            try:
                with transaction.atomic():
                    c.save()
                messages.success(request, 'Cavity history added.')
            except IntegrityError:
                messages.error(request, 'A history entry already exists for this cavity.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('eam:tool_detail', pk=pk)
