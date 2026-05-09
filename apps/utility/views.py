"""Module 14 - Energy & Utility Management views.

Read-only surfaces use ``TenantRequiredMixin`` (Lesson L-10).
State-changing surfaces use ``TenantAdminRequiredMixin``.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    allocation as alloc_svc,
    benchmark as bench_svc,
    carbon as carbon_svc,
    meters as meter_svc,
    peak as peak_svc,
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


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra=None):
    fields = {'status': to_state}
    if extra:
        fields.update(extra)
    with transaction.atomic():
        return model.objects.filter(pk=pk, tenant=tenant, status__in=from_states).update(**fields) > 0


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'utility/index.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)

        # KPI cards
        active_meters = models.UtilityMeter.objects.filter(tenant=t, is_active=True).count()
        active_dr = models.DemandResponseEvent.objects.filter(
            tenant=t, status__in=('scheduled', 'active'),
        ).count()
        new_suggestions = models.PeakShavingSuggestion.objects.filter(
            tenant=t, status='new',
        ).count()
        latest_kpi = (
            models.SustainabilityKPI.objects.filter(tenant=t)
            .select_related('period').order_by('-period__start_date').first()
        )
        kwh_mtd = (
            models.UtilityConsumption.objects.filter(
                tenant=t, period_start__gte=month_start, is_reversal=False,
                meter__utility_type__unit_of_measure='kwh',
            ).aggregate(t=Sum('consumption'))['t']
        ) or Decimal('0')
        co2e_mtd = (
            models.CarbonEmission.objects.filter(
                tenant=t, recorded_at__date__gte=month_start, is_reversal=False,
            ).aggregate(t=Sum('co2e_kg'))['t']
        ) or Decimal('0')
        cost_mtd = (
            models.UtilityConsumption.objects.filter(
                tenant=t, period_start__gte=month_start, is_reversal=False,
            ).aggregate(t=Sum('total_cost'))['t']
        ) or Decimal('0')

        recent_consumption = (
            models.UtilityConsumption.objects.filter(tenant=t, is_reversal=False)
            .select_related('meter', 'meter__utility_type').order_by('-period_start')[:8]
        )
        recent_emissions = (
            models.CarbonEmission.objects.filter(tenant=t, is_reversal=False)
            .select_related('factor').order_by('-recorded_at')[:8]
        )
        upcoming_dr = (
            models.DemandResponseEvent.objects.filter(
                tenant=t, status__in=('scheduled', 'active'), end_at__gte=timezone.now(),
            ).order_by('start_at')[:5]
        )

        # Chart 1: kWh consumption trend (last 14 days)
        days = [today - timedelta(days=i) for i in range(13, -1, -1)]
        kwh_per_day = []
        for d in days:
            v = models.UtilityConsumption.objects.filter(
                tenant=t, is_reversal=False,
                meter__utility_type__unit_of_measure='kwh',
                period_start__date=d,
            ).aggregate(t=Sum('consumption'))['t']
            kwh_per_day.append(float(v or 0))
        kwh_chart = {
            'labels': [d.strftime('%b %d') for d in days],
            'series': kwh_per_day,
        }

        # Chart 2: Scope 1/2/3 stacked totals (latest KPI)
        if latest_kpi:
            scope_chart = {
                'labels': ['Scope 1', 'Scope 2', 'Scope 3'],
                'series': [
                    float(latest_kpi.total_scope_1_kg),
                    float(latest_kpi.total_scope_2_kg),
                    float(latest_kpi.total_scope_3_kg),
                ],
            }
        else:
            scope_chart = {'labels': ['Scope 1', 'Scope 2', 'Scope 3'], 'series': [0, 0, 0]}

        return render(request, self.template_name, {
            'active_meters': active_meters,
            'active_dr': active_dr,
            'new_suggestions': new_suggestions,
            'latest_kpi': latest_kpi,
            'kwh_mtd': kwh_mtd,
            'co2e_mtd': co2e_mtd,
            'cost_mtd': cost_mtd,
            'recent_consumption': recent_consumption,
            'recent_emissions': recent_emissions,
            'upcoming_dr': upcoming_dr,
            'kwh_chart': kwh_chart,
            'scope_chart': scope_chart,
        })


# ============================================================================
# 14.1 Utility Type CRUD
# ============================================================================

class UtilityTypeListView(TenantRequiredMixin, View):
    template_name = 'utility/types/list.html'

    def get(self, request):
        qs = models.UtilityType.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        active = request.GET.get('active', '')
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {'page_obj': _paginate(qs, request)})


class UtilityTypeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/types/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityTypeForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityTypeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Utility type created.')
            return redirect('utility:type_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class UtilityTypeEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/types/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.UtilityType, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.UtilityTypeForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityType, pk=pk, tenant=request.tenant)
        form = forms.UtilityTypeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Utility type updated.')
            return redirect('utility:type_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class UtilityTypeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityType, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Utility type deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:type_list')


# ============================================================================
# 14.1 Utility Meter CRUD
# ============================================================================

class UtilityMeterListView(TenantRequiredMixin, View):
    template_name = 'utility/meters/list.html'

    def get(self, request):
        qs = models.UtilityMeter.objects.filter(tenant=request.tenant).select_related(
            'utility_type', 'location', 'cost_center', 'asset',
        )
        q = request.GET.get('q', '').strip()
        utype = request.GET.get('type', '')
        active = request.GET.get('active', '')
        if q:
            qs = qs.filter(Q(meter_number__icontains=q) | Q(name__icontains=q))
        if utype:
            qs = qs.filter(utility_type_id=utype)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        types = models.UtilityType.objects.filter(tenant=request.tenant)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'utility_types': types,
        })


class UtilityMeterCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/meters/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityMeterForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityMeterForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Meter {obj.meter_number} created.')
            return redirect('utility:meter_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class UtilityMeterDetailView(TenantRequiredMixin, View):
    template_name = 'utility/meters/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityMeter.objects.select_related('utility_type', 'location', 'cost_center', 'asset', 'parent_meter'),
            pk=pk, tenant=request.tenant,
        )
        recent = (
            models.UtilityConsumption.objects
            .filter(tenant=request.tenant, meter=obj)
            .order_by('-period_start')[:30]
        )
        sub_meters = models.UtilityMeter.objects.filter(tenant=request.tenant, parent_meter=obj)
        return render(request, self.template_name, {
            'obj': obj, 'recent': recent, 'sub_meters': sub_meters,
        })


class UtilityMeterEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/meters/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.UtilityMeter, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.UtilityMeterForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityMeter, pk=pk, tenant=request.tenant)
        form = forms.UtilityMeterForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Meter updated.')
            return redirect('utility:meter_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class UtilityMeterDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityMeter, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Meter deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:meter_list')


# ============================================================================
# 14.1 Utility Consumption CRUD + Import
# ============================================================================

class UtilityConsumptionListView(TenantRequiredMixin, View):
    template_name = 'utility/consumption/list.html'

    def get(self, request):
        qs = (
            models.UtilityConsumption.objects.filter(tenant=request.tenant)
            .select_related('meter', 'meter__utility_type', 'recorded_by')
        )
        q = request.GET.get('q', '').strip()
        meter = request.GET.get('meter', '')
        source = request.GET.get('source', '')
        if q:
            qs = qs.filter(Q(entry_number__icontains=q) | Q(meter__meter_number__icontains=q))
        if meter:
            qs = qs.filter(meter_id=meter)
        if source:
            qs = qs.filter(source=source)
        meters = models.UtilityMeter.objects.filter(tenant=request.tenant)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'meters': meters,
            'source_choices': models.UtilityConsumption.SOURCE_CHOICES,
        })


class UtilityConsumptionCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityConsumptionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.recorded_by = request.user
            obj.save()
            messages.success(request, f'Consumption {obj.entry_number} recorded.')
            return redirect('utility:consumption_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class UtilityConsumptionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/consumption/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityConsumption.objects.select_related(
                'meter', 'meter__utility_type', 'recorded_by', 'source_meter_reading',
            ),
            pk=pk, tenant=request.tenant,
        )
        emissions = models.CarbonEmission.objects.filter(
            tenant=request.tenant, source_consumption=obj,
        )
        return render(request, self.template_name, {'obj': obj, 'emissions': emissions})


class UtilityConsumptionEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.UtilityConsumption, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityConsumption, pk=pk, tenant=request.tenant)
        form = forms.UtilityConsumptionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Consumption updated.')
            return redirect('utility:consumption_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class UtilityConsumptionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityConsumption, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Consumption deleted (carbon row reversed).')
        return redirect('utility:consumption_list')


class UtilityConsumptionImportView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/import.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionImportForm(tenant=request.tenant),
        })

    def post(self, request):
        form = forms.UtilityConsumptionImportForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            try:
                result = meter_svc.bulk_import_billing(
                    form.cleaned_data['meter'],
                    form.cleaned_data['csv_file'],
                    recorded_by=request.user,
                )
                messages.success(
                    request,
                    f'Imported {result["created"]} rows. Skipped {result["skipped"]} duplicates.',
                )
                if result['skipped']:
                    messages.warning(
                        request,
                        f'{result["skipped"]} rows skipped because they already exist for this meter/period.',
                    )
                return redirect('utility:consumption_list')
            except Exception as e:
                messages.error(request, f'Import failed: {e}')
        return render(request, self.template_name, {'form': form})


# ============================================================================
# 14.2 Utility Tariff + TOU bands CRUD
# ============================================================================

class UtilityTariffListView(TenantRequiredMixin, View):
    template_name = 'utility/tariffs/list.html'

    def get(self, request):
        qs = models.UtilityTariff.objects.filter(tenant=request.tenant).select_related('utility_type')
        q = request.GET.get('q', '').strip()
        utype = request.GET.get('type', '')
        active = request.GET.get('active', '')
        if q:
            qs = qs.filter(Q(tariff_number__icontains=q) | Q(name__icontains=q))
        if utype:
            qs = qs.filter(utility_type_id=utype)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'utility_types': models.UtilityType.objects.filter(tenant=request.tenant),
        })


class UtilityTariffCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/tariffs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityTariffForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityTariffForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Tariff {obj.tariff_number} created.')
            return redirect('utility:tariff_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class UtilityTariffDetailView(TenantRequiredMixin, View):
    template_name = 'utility/tariffs/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityTariff.objects.select_related('utility_type'),
            pk=pk, tenant=request.tenant,
        )
        bands = models.TOURateBand.objects.filter(tariff=obj).order_by('day_of_week', 'start_time')
        return render(request, self.template_name, {'obj': obj, 'bands': bands, 'band_form': forms.TOURateBandForm()})


class UtilityTariffEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/tariffs/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.UtilityTariff, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.UtilityTariffForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityTariff, pk=pk, tenant=request.tenant)
        form = forms.UtilityTariffForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tariff updated.')
            return redirect('utility:tariff_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class UtilityTariffDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityTariff, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Tariff deleted (TOU bands cascade).')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:tariff_list')


class TOURateBandCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, tariff_pk):
        tariff = get_object_or_404(models.UtilityTariff, pk=tariff_pk, tenant=request.tenant)
        form = forms.TOURateBandForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tariff = tariff
            obj.tenant = request.tenant
            try:
                with transaction.atomic():
                    obj.save()
                messages.success(request, 'TOU band added.')
            except IntegrityError:
                messages.error(request, 'A band with the same type/day/start_time already exists.')
        else:
            messages.error(request, 'Invalid band: ' + str(form.errors))
        return redirect('utility:tariff_detail', pk=tariff.pk)


class TOURateBandDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        band = get_object_or_404(models.TOURateBand, pk=pk, tenant=request.tenant)
        tariff_pk = band.tariff_id
        band.delete()
        messages.success(request, 'TOU band removed.')
        return redirect('utility:tariff_detail', pk=tariff_pk)


# ============================================================================
# 14.2 Utility Allocation
# ============================================================================

class UtilityAllocationListView(TenantRequiredMixin, View):
    template_name = 'utility/allocations/list.html'

    def get(self, request):
        qs = (
            models.UtilityAllocation.objects.filter(tenant=request.tenant)
            .select_related('period', 'meter', 'target_cost_center', 'target_product', 'target_production_order')
        )
        period = request.GET.get('period', '')
        meter = request.GET.get('meter', '')
        if period:
            qs = qs.filter(period_id=period)
        if meter:
            qs = qs.filter(meter_id=meter)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'periods': _open_periods(request.tenant),
            'meters': models.UtilityMeter.objects.filter(tenant=request.tenant),
            'post_form': forms.UtilityAllocationPostForm(tenant=request.tenant),
        })


def _open_periods(tenant):
    from apps.cost.models import AccountingPeriod
    return AccountingPeriod.objects.filter(tenant=tenant)


class UtilityAllocationDetailView(TenantRequiredMixin, View):
    template_name = 'utility/allocations/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityAllocation.objects.select_related(
                'period', 'meter', 'meter__utility_type',
                'target_cost_center', 'target_product', 'target_production_order',
                'posted_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj, 'reverse_form': forms.UtilityAllocationReverseForm(),
        })


class UtilityAllocationPostView(TenantAdminRequiredMixin, View):
    """POST orchestrator that runs services.allocation.post_allocation()."""

    def post(self, request):
        form = forms.UtilityAllocationPostForm(request.POST, tenant=request.tenant)
        if not form.is_valid():
            messages.error(request, 'Invalid form: pick a period and a meter.')
            return redirect('utility:allocation_list')
        period = form.cleaned_data['period']
        meter = form.cleaned_data['meter']
        # v1: single-target (meter's cost center, 100%) for one-click posting.
        targets = []
        if meter.cost_center:
            targets.append({
                'cost_center': meter.cost_center,
                'product': None,
                'production_order': None,
                'share_pct': Decimal('100'),
            })
        if not targets:
            messages.warning(
                request,
                f'Meter {meter.meter_number} has no cost center assigned. Allocation skipped.',
            )
            return redirect('utility:allocation_list')
        result = alloc_svc.post_allocation(period, meter, targets, posted_by=request.user)
        messages.success(
            request,
            f'Posted {result["created"]} allocation rows (cleared {result["cleared_prior"]} prior).',
        )
        return redirect('utility:allocation_list')


class UtilityAllocationReverseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityAllocation, pk=pk, tenant=request.tenant)
        form = forms.UtilityAllocationReverseForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Reversal reason is required.')
            return redirect('utility:allocation_detail', pk=pk)
        alloc_svc.reverse_allocation(
            obj, reason=form.cleaned_data['reversal_reason'], reversed_by=request.user,
        )
        messages.success(request, f'Allocation {obj.allocation_number} reversed.')
        return redirect('utility:allocation_detail', pk=pk)


class UtilityAllocationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityAllocation, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Allocation deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:allocation_list')


# ============================================================================
# 14.3 Demand Response Events
# ============================================================================

class DemandResponseEventListView(TenantRequiredMixin, View):
    template_name = 'utility/dr_events/list.html'

    def get(self, request):
        qs = models.DemandResponseEvent.objects.filter(tenant=request.tenant).select_related('utility_type')
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'status_choices': models.DemandResponseEvent.STATUS_CHOICES,
        })


class DemandResponseEventCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/dr_events/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.DemandResponseEventForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.DemandResponseEventForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'DR event {obj.event_number} scheduled.')
            return redirect('utility:dr_event_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class DemandResponseEventDetailView(TenantRequiredMixin, View):
    template_name = 'utility/dr_events/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.DemandResponseEvent.objects.select_related('utility_type'),
            pk=pk, tenant=request.tenant,
        )
        suggestions = models.PeakShavingSuggestion.objects.filter(tenant=request.tenant, event=obj)
        return render(request, self.template_name, {
            'obj': obj, 'suggestions': suggestions,
            'cancel_form': forms.DemandResponseEventCancelForm(),
        })


class DemandResponseEventEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/dr_events/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.DemandResponseEventForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        form = forms.DemandResponseEventForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'DR event updated.')
            return redirect('utility:dr_event_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class DemandResponseEventActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.DemandResponseEvent, pk, request.tenant, ['scheduled'], 'active',
        )
        if ok:
            messages.success(request, 'DR event activated.')
        else:
            messages.error(request, 'DR event cannot be activated from its current state.')
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventCompleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.DemandResponseEvent, pk, request.tenant, ['active'], 'completed',
        )
        if ok:
            messages.success(request, 'DR event marked completed.')
        else:
            messages.error(request, 'DR event cannot be completed from its current state.')
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(request, 'DR event cannot be cancelled from its current state.')
            return redirect('utility:dr_event_detail', pk=pk)
        form = forms.DemandResponseEventCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('utility:dr_event_detail', pk=pk)
        with transaction.atomic():
            models.DemandResponseEvent.objects.filter(pk=obj.pk, tenant=request.tenant).update(
                status='cancelled',
                cancellation_reason=form.cleaned_data['cancellation_reason'],
            )
        messages.success(request, 'DR event cancelled.')
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'DR event deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:dr_event_list')


# ============================================================================
# 14.3 Peak Shaving Suggestions
# ============================================================================

class PeakShavingSuggestionListView(TenantRequiredMixin, View):
    template_name = 'utility/peak_suggestions/list.html'

    def get(self, request):
        qs = (
            models.PeakShavingSuggestion.objects.filter(tenant=request.tenant)
            .select_related('event', 'tou_band', 'production_order', 'scheduled_operation')
        )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'status_choices': models.PeakShavingSuggestion.STATUS_CHOICES,
            'scan_form': forms.PeakShavingScanForm(),
        })


class PeakShavingSuggestionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/peak_suggestions/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.PeakShavingSuggestion.objects.select_related(
                'event', 'tou_band', 'production_order', 'scheduled_operation', 'acknowledged_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj, 'dismiss_form': forms.PeakShavingDismissForm(),
        })


class PeakShavingSuggestionScanView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.PeakShavingScanForm(request.POST)
        horizon = 14
        if form.is_valid():
            horizon = form.cleaned_data['horizon_days']
        result = peak_svc.scan_for_peak_overlap(request.tenant, horizon_days=horizon)
        messages.success(
            request,
            f'Scan complete. {result["created"]} new suggestions over {result["horizon_days"]} days.',
        )
        return redirect('utility:peak_list')


class PeakShavingSuggestionAckView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.PeakShavingSuggestion, pk=pk, tenant=request.tenant)
        if not obj.is_acknowledgable():
            messages.error(request, 'Suggestion is no longer acknowledgable.')
            return redirect('utility:peak_detail', pk=pk)
        peak_svc.acknowledge(obj, by=request.user)
        messages.success(request, 'Suggestion acknowledged.')
        return redirect('utility:peak_detail', pk=pk)


class PeakShavingSuggestionDismissView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.PeakShavingSuggestion, pk=pk, tenant=request.tenant)
        if not obj.is_dismissable():
            messages.error(request, 'Suggestion is no longer dismissable.')
            return redirect('utility:peak_detail', pk=pk)
        form = forms.PeakShavingDismissForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Dismiss reason is required.')
            return redirect('utility:peak_detail', pk=pk)
        peak_svc.dismiss(obj, reason=form.cleaned_data['dismiss_reason'], by=request.user)
        messages.success(request, 'Suggestion dismissed.')
        return redirect('utility:peak_detail', pk=pk)


# ============================================================================
# 14.4 Emission Factors
# ============================================================================

class EmissionFactorListView(TenantRequiredMixin, View):
    template_name = 'utility/emission_factors/list.html'

    def get(self, request):
        qs = models.EmissionFactor.objects.filter(tenant=request.tenant)
        scope = request.GET.get('scope', '')
        source = request.GET.get('source', '')
        active = request.GET.get('active', '')
        if scope:
            qs = qs.filter(scope=scope)
        if source:
            qs = qs.filter(source_type=source)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'scope_choices': models.EmissionFactor.SCOPE_CHOICES,
            'source_choices': models.EmissionFactor.SOURCE_TYPE_CHOICES,
        })


class EmissionFactorCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/emission_factors/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.EmissionFactorForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.EmissionFactorForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Emission factor saved.')
            return redirect('utility:factor_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class EmissionFactorEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/emission_factors/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.EmissionFactorForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        form = forms.EmissionFactorForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Emission factor updated.')
            return redirect('utility:factor_list')
        return render(request, self.template_name, {'form': form, 'obj': obj, 'mode': 'edit'})


class EmissionFactorDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Emission factor deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
        return redirect('utility:factor_list')


# ============================================================================
# 14.4 Carbon Emissions ledger
# ============================================================================

class CarbonEmissionListView(TenantRequiredMixin, View):
    template_name = 'utility/emissions/list.html'

    def get(self, request):
        qs = (
            models.CarbonEmission.objects.filter(tenant=request.tenant)
            .select_related('period', 'factor', 'source_consumption')
        )
        scope = request.GET.get('scope', '')
        source = request.GET.get('source', '')
        period = request.GET.get('period', '')
        if scope:
            qs = qs.filter(scope=scope)
        if source:
            qs = qs.filter(source_type=source)
        if period:
            qs = qs.filter(period_id=period)
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'scope_choices': models.CarbonEmission.SCOPE_CHOICES,
            'source_choices': models.EmissionFactor.SOURCE_TYPE_CHOICES,
            'periods': _open_periods(request.tenant),
        })


class CarbonEmissionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/emissions/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.CarbonEmission.objects.select_related('period', 'factor', 'source_consumption', 'recorded_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class CarbonEmissionRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        from apps.cost.models import AccountingPeriod
        period = get_object_or_404(AccountingPeriod, pk=period_pk, tenant=request.tenant)
        result = carbon_svc.recompute_emissions(period)
        messages.success(
            request,
            f'Recomputed {result["emitted"]} emissions from {result["consumptions_scanned"]} consumption rows.',
        )
        return redirect('utility:emission_list')


# ============================================================================
# 14.4 Sustainability KPI
# ============================================================================

class SustainabilityKPIListView(TenantRequiredMixin, View):
    template_name = 'utility/sustainability/list.html'

    def get(self, request):
        qs = (
            models.SustainabilityKPI.objects.filter(tenant=request.tenant)
            .select_related('period')
        )
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'periods': _open_periods(request.tenant),
        })


class SustainabilityKPIDetailView(TenantRequiredMixin, View):
    template_name = 'utility/sustainability/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.SustainabilityKPI.objects.select_related('period', 'generated_by'),
            pk=pk, tenant=request.tenant,
        )
        scope_chart = {
            'labels': ['Scope 1', 'Scope 2', 'Scope 3'],
            'series': [
                float(obj.total_scope_1_kg),
                float(obj.total_scope_2_kg),
                float(obj.total_scope_3_kg),
            ],
        }
        return render(request, self.template_name, {'obj': obj, 'scope_chart': scope_chart})


class SustainabilityKPIGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        from apps.cost.models import AccountingPeriod
        period = get_object_or_404(AccountingPeriod, pk=period_pk, tenant=request.tenant)
        kpi = carbon_svc.generate_sustainability_kpi(period, generated_by=request.user)
        messages.success(request, f'KPI snapshot generated for {period.name}.')
        return redirect('utility:sustainability_detail', pk=kpi.pk)


# ============================================================================
# 14.5 Benchmarking
# ============================================================================

class BenchmarkSnapshotListView(TenantRequiredMixin, View):
    template_name = 'utility/benchmarks/list.html'

    def get(self, request):
        qs = (
            models.BenchmarkSnapshot.objects
            .filter(Q(tenant=request.tenant) | Q(tenant__isnull=True))
            .select_related('period')
        )
        return render(request, self.template_name, {
            'page_obj': _paginate(qs, request),
            'generate_form': forms.BenchmarkSnapshotGenerateForm(tenant=request.tenant),
        })


class BenchmarkSnapshotDetailView(TenantRequiredMixin, View):
    template_name = 'utility/benchmarks/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.BenchmarkSnapshot.objects.select_related('period', 'generated_by'),
            pk=pk,
        )
        # Multi-tenant guard: tenant FK may be None for industry_avg row,
        # but only the same-tenant or anonymous-aggregate row is shown.
        if obj.tenant_id is not None and obj.tenant_id != request.tenant.id:
            from django.http import Http404
            raise Http404
        return render(request, self.template_name, {'obj': obj})


class BenchmarkSnapshotGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.BenchmarkSnapshotGenerateForm(request.POST, tenant=request.tenant)
        if not form.is_valid():
            messages.error(request, 'Invalid form: pick a period and a label.')
            return redirect('utility:benchmark_list')
        snap = bench_svc.generate_snapshot(
            form.cleaned_data['period'],
            plant_label=form.cleaned_data['plant_label'],
            tenant=request.tenant,
            generated_by=request.user,
        )
        messages.success(request, f'Snapshot generated for {snap.period.name} / {snap.plant_label}.')
        return redirect('utility:benchmark_detail', pk=snap.pk)


class BenchmarkComparisonListView(TenantRequiredMixin, View):
    template_name = 'utility/benchmark_reports/list.html'

    def get(self, request):
        qs = (
            models.BenchmarkComparison.objects.filter(tenant=request.tenant)
            .select_related('from_snapshot', 'to_snapshot')
        )
        return render(request, self.template_name, {'page_obj': _paginate(qs, request)})


class BenchmarkComparisonCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/benchmark_reports/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.BenchmarkComparisonForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.BenchmarkComparisonForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = bench_svc.create_comparison(
                comparison_type=form.cleaned_data['comparison_type'],
                from_snapshot=form.cleaned_data['from_snapshot'],
                to_snapshot=form.cleaned_data['to_snapshot'],
                tenant=request.tenant,
                generated_by=request.user,
                notes=form.cleaned_data['notes'],
            )
            messages.success(request, f'Comparison {obj.report_number} generated.')
            return redirect('utility:benchmark_report_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class BenchmarkComparisonDetailView(TenantRequiredMixin, View):
    template_name = 'utility/benchmark_reports/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.BenchmarkComparison.objects.select_related(
                'from_snapshot', 'from_snapshot__period',
                'to_snapshot', 'to_snapshot__period',
                'generated_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class BenchmarkComparisonDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.BenchmarkComparison, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Comparison deleted.')
        return redirect('utility:benchmark_report_list')
