"""Module 14 - Energy & Utility Management views.

Class-based views mirroring the cost-module shape (apps/cost/views.py):
    <Resource>ListView / CreateView / DetailView / EditView / DeleteView
    plus per-workflow POST views.

RBAC (Lesson L-10):
    - Read surfaces inherit ``TenantRequiredMixin`` (logged-in + tenant attached).
    - Mutating surfaces inherit ``TenantAdminRequiredMixin`` so non-admin
      tenant users get a 302 redirect.

Lessons honored:
    - L-03: status gates use the model's ``is_*()`` helpers so view + template
      stay in lock-step (DemandResponseEvent.is_activatable() /
      is_completable() / is_cancellable(), PeakShavingSuggestion.is_*()).
    - L-04: any operation that drops/skips records surfaces a
      ``messages.warning(...)`` with explicit counts.
    - L-07: the dashboard view returns ApexCharts series as raw Python
      ``list[dict]`` so the template can serialize via ``json_script``.
    - L-12: auto-numbered model rows rely on the model's ``save()`` retry
      pattern; views call ``.save()`` (never bulk_create) and the model
      handles sequence collisions with the cost-style retry.
    - L-13: workflow status mutations use ``QuerySet.update()`` inside a
      ``transaction.atomic()`` block so an unhandled IntegrityError on the
      row never poisons the parent transaction.
    - L-14: workflow POST views (reverse / cancel / dismiss) validate via
      the per-workflow form classes (UtilityAllocationReverseForm,
      DemandResponseEventCancelForm, PeakShavingDismissForm) — never via
      raw ``request.POST``.
"""
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
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
    meters as meters_svc,
    peak as peak_svc,
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
    """Race-safe status transition (mirrors apps/cost/views.py helper)."""
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
    """Module 14 dashboard.

    L-07: chart series are returned as raw Python list[dict]; the template
    serializes via ``{{ data|json_script:"..." }}``.
    """
    template_name = 'utility/index.html'

    def get(self, request):
        tenant = request.tenant
        if tenant is None:
            return render(request, self.template_name, {
                'kpi': {},
                'recent_consumption': [],
                'recent_allocations': [],
                'recent_emissions': [],
                'open_dr_events': [],
                'open_suggestions': [],
                'consumption_chart': [],
                'co2e_chart': [],
            })

        today = timezone.now().date()
        month_start = today.replace(day=1)

        # KPI cards
        meter_count = models.UtilityMeter.objects.filter(
            tenant=tenant, is_active=True,
        ).count()
        open_dr_count = models.DemandResponseEvent.objects.filter(
            tenant=tenant, status__in=('scheduled', 'active'),
        ).count()
        open_suggestions_count = models.PeakShavingSuggestion.objects.filter(
            tenant=tenant, status='new',
        ).count()
        open_allocations_count = models.UtilityAllocation.objects.filter(
            tenant=tenant, is_reversed=False, is_posted_to_cost=False,
        ).count()
        posted_allocations_count = models.UtilityAllocation.objects.filter(
            tenant=tenant, is_reversed=False, is_posted_to_cost=True,
        ).count()
        period_kwh = models.UtilityConsumption.objects.filter(
            tenant=tenant,
            meter__utility_type__unit_of_measure='kwh',
            period_start__date__gte=month_start,
            is_reversal=False,
        ).aggregate(t=Sum('consumption'))['t'] or Decimal('0')
        period_co2e = models.CarbonEmission.objects.filter(
            tenant=tenant, recorded_at__date__gte=month_start, is_reversal=False,
        ).aggregate(t=Sum('co2e_kg'))['t'] or Decimal('0')

        kpi = {
            'meter_count': meter_count,
            'open_dr_events': open_dr_count,
            'open_suggestions': open_suggestions_count,
            'open_allocations': open_allocations_count,
            'posted_allocations': posted_allocations_count,
            'period_kwh': period_kwh,
            'period_co2e': period_co2e,
        }

        recent_consumption = list(
            models.UtilityConsumption.objects.filter(tenant=tenant)
            .select_related('meter', 'meter__utility_type')
            .order_by('-recorded_at')[:6]
        )
        recent_allocations = list(
            models.UtilityAllocation.objects.filter(tenant=tenant)
            .select_related(
                'period', 'meter', 'target_cost_center',
                'target_product', 'target_production_order',
            )
            .order_by('-posted_at', '-id')[:6]
        )
        recent_emissions = list(
            models.CarbonEmission.objects.filter(tenant=tenant)
            .select_related('period', 'factor')
            .order_by('-recorded_at')[:6]
        )
        open_dr_events = list(
            models.DemandResponseEvent.objects.filter(
                tenant=tenant, status__in=('scheduled', 'active'),
            )
            .select_related('utility_type')
            .order_by('start_at')[:6]
        )
        open_suggestions = list(
            models.PeakShavingSuggestion.objects.filter(tenant=tenant, status='new')
            .select_related(
                'production_order', 'scheduled_operation', 'event', 'tou_band',
            )
            .order_by('original_start')[:6]
        )

        # Charts (L-07: raw Python list[dict]; template wraps via json_script)
        kpi_rows = list(
            models.SustainabilityKPI.objects.filter(tenant=tenant)
            .select_related('period')
            .order_by('period__start_date')[:12]
        )
        consumption_chart = [
            {
                'period': r.period.name,
                'kwh': float(r.total_kwh or 0),
                'water': float(r.total_water_m3 or 0),
                'gas': float(r.total_gas_m3 or 0),
            }
            for r in kpi_rows
        ]
        co2e_chart = [
            {
                'period': r.period.name,
                'scope_1': float(r.total_scope_1_kg or 0),
                'scope_2': float(r.total_scope_2_kg or 0),
                'scope_3': float(r.total_scope_3_kg or 0),
            }
            for r in kpi_rows
        ]

        return render(request, self.template_name, {
            'kpi': kpi,
            'recent_consumption': recent_consumption,
            'recent_allocations': recent_allocations,
            'recent_emissions': recent_emissions,
            'open_dr_events': open_dr_events,
            'open_suggestions': open_suggestions,
            'consumption_chart': consumption_chart,
            'co2e_chart': co2e_chart,
        })


# ============================================================================
# 14.1 Utility Types
# ============================================================================

class UtilityTypeListView(TenantRequiredMixin, View):
    template_name = 'utility/types/list.html'

    def get(self, request):
        qs = models.UtilityType.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        unit = request.GET.get('unit_of_measure', '')
        if unit:
            qs = qs.filter(unit_of_measure=unit)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('code'), request),
            'unit_choices': models.UtilityType.UNIT_CHOICES,
        })


class UtilityTypeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/types/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityTypeForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityTypeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Utility type "{obj.code}" created.')
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
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class UtilityTypeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityType, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Utility type deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('utility:type_list')

    def get(self, request, pk):
        return redirect('utility:type_list')


# ============================================================================
# 14.1 Utility Meters
# ============================================================================

class UtilityMeterListView(TenantRequiredMixin, View):
    template_name = 'utility/meters/list.html'

    def get(self, request):
        qs = models.UtilityMeter.objects.filter(tenant=request.tenant).select_related(
            'utility_type', 'location', 'parent_meter', 'cost_center', 'asset',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(meter_number__icontains=q) | Q(name__icontains=q))
        utility_type = request.GET.get('utility_type', '')
        if utility_type:
            qs = qs.filter(utility_type_id=utility_type)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('meter_number'), request),
            'utility_types': models.UtilityType.objects.filter(tenant=request.tenant),
        })


class UtilityMeterCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/meters/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityMeterForm(tenant=request.tenant),
            'mode': 'create',
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
            models.UtilityMeter.objects.select_related(
                'utility_type', 'location', 'parent_meter', 'cost_center', 'asset',
            ),
            pk=pk, tenant=request.tenant,
        )
        consumption = obj.consumptions.filter(
            tenant=request.tenant,
        ).order_by('-period_start')[:25]
        sub_meters = obj.sub_meters.filter(tenant=request.tenant)[:25]
        return render(request, self.template_name, {
            'obj': obj, 'consumption': consumption, 'sub_meters': sub_meters,
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
            return redirect('utility:meter_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class UtilityMeterDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityMeter, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Meter deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:meter_detail', pk=pk)
        return redirect('utility:meter_list')

    def get(self, request, pk):
        return redirect('utility:meter_detail', pk=pk)


# ============================================================================
# 14.1 Utility Consumption (append-only ledger; edit/delete admin-only)
# ============================================================================

class UtilityConsumptionListView(TenantRequiredMixin, View):
    template_name = 'utility/consumption/list.html'

    def get(self, request):
        qs = models.UtilityConsumption.objects.filter(
            tenant=request.tenant,
        ).select_related('meter', 'meter__utility_type')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(entry_number__icontains=q) | Q(meter__meter_number__icontains=q)
            )
        meter_pk = request.GET.get('meter', '')
        if meter_pk:
            qs = qs.filter(meter_id=meter_pk)
        source = request.GET.get('source', '')
        if source:
            qs = qs.filter(source=source)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-period_start'), request),
            'meters': models.UtilityMeter.objects.filter(
                tenant=request.tenant, is_active=True,
            ),
            'source_choices': models.UtilityConsumption.SOURCE_CHOICES,
        })


class UtilityConsumptionCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.UtilityConsumptionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            data = form.cleaned_data
            try:
                obj = meters_svc.post_consumption(
                    data['meter'],
                    period_start=data['period_start'],
                    period_end=data['period_end'],
                    start_reading=data['start_reading'],
                    end_reading=data['end_reading'],
                    unit_cost=data.get('unit_cost'),
                    source=data.get('source') or 'manual',
                    recorded_by=request.user,
                    notes=data.get('notes', ''),
                )
                messages.success(
                    request,
                    f'Consumption entry {obj.entry_number} recorded.',
                )
                return redirect('utility:consumption_detail', pk=obj.pk)
            except Exception as exc:
                messages.error(request, f'Could not record consumption: {exc}')
        return render(request, self.template_name, {
            'form': form, 'mode': 'create',
        })


class UtilityConsumptionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/consumption/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityConsumption.objects.select_related(
                'meter', 'meter__utility_type', 'recorded_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        emissions = obj.carbon_emissions.filter(tenant=request.tenant)
        return render(request, self.template_name, {
            'obj': obj, 'emissions': emissions,
        })


class UtilityConsumptionEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityConsumption, pk=pk, tenant=request.tenant,
        )
        # L-03: reversal rows are immutable history.
        if obj.is_reversal:
            messages.warning(request, 'Reversal rows cannot be edited.')
            return redirect('utility:consumption_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionForm(
                instance=obj, tenant=request.tenant,
            ),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(
            models.UtilityConsumption, pk=pk, tenant=request.tenant,
        )
        if obj.is_reversal:
            messages.error(request, 'Reversal rows cannot be edited.')
            return redirect('utility:consumption_detail', pk=pk)
        form = forms.UtilityConsumptionForm(
            request.POST, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Consumption entry updated.')
            return redirect('utility:consumption_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class UtilityConsumptionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(
            models.UtilityConsumption, pk=pk, tenant=request.tenant,
        )
        try:
            obj.delete()
            messages.success(request, 'Consumption entry deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:consumption_detail', pk=pk)
        return redirect('utility:consumption_list')

    def get(self, request, pk):
        return redirect('utility:consumption_detail', pk=pk)


class UtilityConsumptionImportView(TenantAdminRequiredMixin, View):
    template_name = 'utility/consumption/import.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityConsumptionImportForm(tenant=request.tenant),
        })

    def post(self, request):
        form = forms.UtilityConsumptionImportForm(
            request.POST, request.FILES, tenant=request.tenant,
        )
        if form.is_valid():
            meter = form.cleaned_data['meter']
            csv_file = form.cleaned_data['csv_file']
            try:
                result = meters_svc.bulk_import_billing(
                    meter, csv_file, recorded_by=request.user,
                )
                messages.success(
                    request,
                    f'Import complete: {result["created"]} created.',
                )
                # L-04: surface skipped + invalid counts loudly when non-zero.
                if result.get('skipped', 0) > 0:
                    messages.warning(
                        request,
                        f'{result["skipped"]} row(s) skipped (already imported '
                        f'for that period).',
                    )
                if result.get('invalid', 0) > 0:
                    messages.warning(
                        request,
                        f'{result["invalid"]} row(s) skipped (unparseable '
                        f'period_start/period_end).',
                    )
                return redirect('utility:consumption_list')
            except Exception as exc:
                messages.error(request, f'Import failed: {exc}')
        return render(request, self.template_name, {'form': form})


# ============================================================================
# 14.2 Utility Tariffs
# ============================================================================

class UtilityTariffListView(TenantRequiredMixin, View):
    template_name = 'utility/tariffs/list.html'

    def get(self, request):
        qs = models.UtilityTariff.objects.filter(
            tenant=request.tenant,
        ).select_related('utility_type')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(tariff_number__icontains=q) | Q(name__icontains=q))
        utility_type = request.GET.get('utility_type', '')
        if utility_type:
            qs = qs.filter(utility_type_id=utility_type)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-effective_from', 'tariff_number'), request),
            'utility_types': models.UtilityType.objects.filter(tenant=request.tenant),
        })


class UtilityTariffCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/tariffs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.UtilityTariffForm(tenant=request.tenant),
            'mode': 'create',
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
        bands = obj.tou_bands.order_by('day_of_week', 'start_time')
        return render(request, self.template_name, {
            'obj': obj, 'bands': bands,
            'band_form': forms.TOURateBandForm(),
        })


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
        form = forms.UtilityTariffForm(
            request.POST, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Tariff updated.')
            return redirect('utility:tariff_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class UtilityTariffDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityTariff, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Tariff deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:tariff_detail', pk=pk)
        return redirect('utility:tariff_list')

    def get(self, request, pk):
        return redirect('utility:tariff_detail', pk=pk)


# ============================================================================
# 14.2 TOU Rate Bands (inline create/delete on tariff detail)
# ============================================================================

class TOURateBandCreateView(TenantAdminRequiredMixin, View):
    """Inline POST from the tariff detail page; redirects back to the tariff."""

    def post(self, request, tariff_pk):
        tariff = get_object_or_404(
            models.UtilityTariff, pk=tariff_pk, tenant=request.tenant,
        )
        # D-04: pass parent tariff so the form can pre-check the
        # unique_together and surface a friendly error rather than the raw
        # IntegrityError text.
        form = forms.TOURateBandForm(request.POST, tariff=tariff)
        if form.is_valid():
            band = form.save(commit=False)
            band.tariff = tariff
            band.tenant = request.tenant
            band.save()
            messages.success(request, 'TOU rate band added.')
        else:
            err = (
                next(iter(form.errors.values()))[0]
                if form.errors else 'Invalid input.'
            )
            messages.error(request, f'Could not add band: {err}')
        return redirect('utility:tariff_detail', pk=tariff_pk)

    def get(self, request, tariff_pk):
        return redirect('utility:tariff_detail', pk=tariff_pk)


class TOURateBandDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        band = get_object_or_404(
            models.TOURateBand, pk=pk, tariff__tenant=request.tenant,
        )
        tariff_pk = band.tariff_id
        band.delete()
        messages.success(request, 'TOU rate band deleted.')
        return redirect('utility:tariff_detail', pk=tariff_pk)

    def get(self, request, pk):
        band = get_object_or_404(
            models.TOURateBand, pk=pk, tariff__tenant=request.tenant,
        )
        return redirect('utility:tariff_detail', pk=band.tariff_id)


# ============================================================================
# 14.2 Utility Allocations
# ============================================================================

class UtilityAllocationListView(TenantRequiredMixin, View):
    template_name = 'utility/allocations/list.html'

    def get(self, request):
        qs = models.UtilityAllocation.objects.filter(
            tenant=request.tenant,
        ).select_related(
            'period', 'meter', 'meter__utility_type', 'target_cost_center',
            'target_product', 'target_production_order',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(allocation_number__icontains=q) |
                Q(meter__meter_number__icontains=q)
            )
        period_pk = request.GET.get('period', '')
        if period_pk:
            qs = qs.filter(period_id=period_pk)
        meter_pk = request.GET.get('meter', '')
        if meter_pk:
            qs = qs.filter(meter_id=meter_pk)
        method = request.GET.get('method', '')
        if method:
            qs = qs.filter(allocation_method=method)
        state = request.GET.get('state', '')
        if state == 'reversed':
            qs = qs.filter(is_reversed=True)
        elif state == 'posted':
            qs = qs.filter(is_reversed=False, is_posted_to_cost=True)
        elif state == 'open':
            qs = qs.filter(is_reversed=False, is_posted_to_cost=False)

        from apps.cost.models import AccountingPeriod
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-posted_at', 'allocation_number'), request),
            'periods': AccountingPeriod.objects.filter(tenant=request.tenant),
            'meters': models.UtilityMeter.objects.filter(
                tenant=request.tenant, is_active=True,
            ),
            'method_choices': models.UtilityAllocation.METHOD_CHOICES,
            'post_form': forms.UtilityAllocationPostForm(tenant=request.tenant),
        })


class UtilityAllocationDetailView(TenantRequiredMixin, View):
    template_name = 'utility/allocations/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.UtilityAllocation.objects.select_related(
                'period', 'meter', 'meter__utility_type', 'target_cost_center',
                'target_product', 'target_production_order', 'posted_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj,
            'reverse_form': forms.UtilityAllocationReverseForm(),
        })


class UtilityAllocationPostView(TenantAdminRequiredMixin, View):
    """POST-only orchestrator — re-emits allocations for a (period, meter).

    The allocation service is idempotent: prior un-reversed rows + matching
    cost.DriverActuals are wiped before re-emitting.
    """

    def post(self, request):
        form = forms.UtilityAllocationPostForm(request.POST, tenant=request.tenant)
        if not form.is_valid():
            messages.error(request, 'Pick an open period and an active meter.')
            return redirect('utility:allocation_list')
        period = form.cleaned_data['period']
        meter = form.cleaned_data['meter']
        # Re-collect prior allocation rows as targets so the orchestrator
        # re-emits the same shape after wiping.
        targets = []
        for a in models.UtilityAllocation.objects.filter(
            tenant=request.tenant, period=period, meter=meter, is_reversed=False,
        ):
            targets.append({
                'cost_center': a.target_cost_center,
                'product': a.target_product,
                'production_order': a.target_production_order,
                'share_pct': a.share_pct,
            })
        if not targets:
            # L-04: warn loudly when nothing happens.
            messages.warning(
                request,
                'No allocation targets defined for this (period, meter). '
                'Create at least one allocation row first, then post.',
            )
            return redirect('utility:allocation_list')
        try:
            result = alloc_svc.post_allocation(
                period, meter, targets, posted_by=request.user,
            )
            messages.success(
                request,
                f'Allocation posted: {result["created"]} row(s) emitted '
                f'({result["cleared_prior"]} prior cleared).',
            )
        except Exception as exc:
            messages.error(request, f'Posting failed: {exc}')
        return redirect('utility:allocation_list')

    def get(self, request):
        return redirect('utility:allocation_list')


class UtilityAllocationReverseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityAllocation, pk=pk, tenant=request.tenant)
        if obj.is_reversed:
            messages.warning(request, 'Allocation already reversed.')
            return redirect('utility:allocation_detail', pk=pk)
        # L-14: validate via the per-workflow form so reversal_reason is required.
        form = forms.UtilityAllocationReverseForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Reversal reason is required.')
            return redirect('utility:allocation_detail', pk=pk)
        try:
            alloc_svc.reverse_allocation(
                obj,
                reason=form.cleaned_data['reversal_reason'],
                reversed_by=request.user,
            )
            messages.success(request, 'Allocation reversed.')
        except Exception as exc:
            messages.error(request, f'Reverse failed: {exc}')
        return redirect('utility:allocation_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:allocation_detail', pk=pk)


class UtilityAllocationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.UtilityAllocation, pk=pk, tenant=request.tenant)
        # L-03: posted (not reversed) allocations cannot be deleted —
        # they must be reversed first to keep the cost ledger consistent.
        if obj.is_posted_to_cost and not obj.is_reversed:
            messages.error(
                request,
                'Cannot delete a posted allocation. Reverse it first.',
            )
            return redirect('utility:allocation_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Allocation deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:allocation_detail', pk=pk)
        return redirect('utility:allocation_list')

    def get(self, request, pk):
        return redirect('utility:allocation_detail', pk=pk)


# ============================================================================
# 14.3 Demand Response Events
# ============================================================================

class DemandResponseEventListView(TenantRequiredMixin, View):
    template_name = 'utility/dr_events/list.html'

    def get(self, request):
        qs = models.DemandResponseEvent.objects.filter(
            tenant=request.tenant,
        ).select_related('utility_type')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(event_number__icontains=q) | Q(utility_type__code__icontains=q)
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        event_type = request.GET.get('event_type', '')
        if event_type:
            qs = qs.filter(event_type=event_type)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-start_at'), request),
            'status_choices': models.DemandResponseEvent.STATUS_CHOICES,
            'event_type_choices': models.DemandResponseEvent.EVENT_TYPE_CHOICES,
            'utility_types': models.UtilityType.objects.filter(tenant=request.tenant),
        })


class DemandResponseEventCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/dr_events/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.DemandResponseEventForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.DemandResponseEventForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'DR event {obj.event_number} created.')
            return redirect('utility:dr_event_detail', pk=obj.pk)
        return render(request, self.template_name, {
            'form': form, 'mode': 'create',
        })


class DemandResponseEventDetailView(TenantRequiredMixin, View):
    template_name = 'utility/dr_events/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.DemandResponseEvent.objects.select_related(
                'utility_type', 'created_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        suggestions = obj.shaving_suggestions.filter(
            tenant=request.tenant,
        ).select_related('production_order', 'scheduled_operation')[:25]
        return render(request, self.template_name, {
            'obj': obj, 'suggestions': suggestions,
            'cancel_form': forms.DemandResponseEventCancelForm(),
        })


class DemandResponseEventEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/dr_events/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        # L-03: only scheduled events can be edited (matches template gate).
        if obj.status != 'scheduled':
            messages.warning(request, 'Only scheduled DR events can be edited.')
            return redirect('utility:dr_event_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.DemandResponseEventForm(
                instance=obj, tenant=request.tenant,
            ),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        if obj.status != 'scheduled':
            messages.error(request, 'Only scheduled DR events can be edited.')
            return redirect('utility:dr_event_detail', pk=pk)
        form = forms.DemandResponseEventForm(
            request.POST, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'DR event updated.')
            return redirect('utility:dr_event_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class DemandResponseEventActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        # L-03: parity with model is_activatable() helper.
        if not obj.is_activatable():
            messages.error(request, 'Only scheduled events can be activated.')
            return redirect('utility:dr_event_detail', pk=pk)
        ok = _atomic_status_transition(
            models.DemandResponseEvent, pk, request.tenant,
            from_states=['scheduled'], to_state='active',
        )
        if ok:
            messages.success(request, 'DR event activated.')
        else:
            messages.error(request, 'Activation failed (concurrent change?).')
        return redirect('utility:dr_event_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventCompleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        # L-03: parity with model is_completable() helper.
        if not obj.is_completable():
            messages.error(request, 'Only active events can be completed.')
            return redirect('utility:dr_event_detail', pk=pk)
        ok = _atomic_status_transition(
            models.DemandResponseEvent, pk, request.tenant,
            from_states=['active'], to_state='completed',
        )
        if ok:
            messages.success(request, 'DR event completed.')
        else:
            messages.error(request, 'Complete failed.')
        return redirect('utility:dr_event_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        if not obj.is_cancellable():
            messages.error(
                request,
                'Event cannot be cancelled from its current state.',
            )
            return redirect('utility:dr_event_detail', pk=pk)
        # L-14: validate via the per-workflow form (cancellation_reason required).
        form = forms.DemandResponseEventCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Cancellation reason is required.')
            return redirect('utility:dr_event_detail', pk=pk)
        ok = _atomic_status_transition(
            models.DemandResponseEvent, pk, request.tenant,
            from_states=['scheduled', 'active'], to_state='cancelled',
            extra_fields={
                'cancellation_reason': form.cleaned_data['cancellation_reason'],
            },
        )
        if ok:
            messages.success(request, 'DR event cancelled.')
        else:
            messages.error(request, 'Cancel failed.')
        return redirect('utility:dr_event_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:dr_event_detail', pk=pk)


class DemandResponseEventDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DemandResponseEvent, pk=pk, tenant=request.tenant)
        # L-03: only scheduled (un-activated) events deletable.
        if obj.status != 'scheduled':
            messages.error(request, 'Only scheduled DR events can be deleted.')
            return redirect('utility:dr_event_detail', pk=pk)
        try:
            obj.delete()
            messages.success(request, 'DR event deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:dr_event_detail', pk=pk)
        return redirect('utility:dr_event_list')

    def get(self, request, pk):
        return redirect('utility:dr_event_detail', pk=pk)


# ============================================================================
# 14.3 Peak Shaving Suggestions (read-only + ack/dismiss)
# ============================================================================

class PeakShavingSuggestionListView(TenantRequiredMixin, View):
    template_name = 'utility/peak/list.html'

    def get(self, request):
        qs = models.PeakShavingSuggestion.objects.filter(
            tenant=request.tenant,
        ).select_related(
            'event', 'tou_band', 'tou_band__tariff',
            'production_order', 'scheduled_operation',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(suggestion_number__icontains=q)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-original_start'), request),
            'status_choices': models.PeakShavingSuggestion.STATUS_CHOICES,
            'scan_form': forms.PeakShavingScanForm(),
        })


class PeakShavingSuggestionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/peak/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.PeakShavingSuggestion.objects.select_related(
                'event', 'tou_band', 'tou_band__tariff',
                'production_order', 'scheduled_operation', 'acknowledged_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj,
            'dismiss_form': forms.PeakShavingDismissForm(),
        })


class PeakShavingSuggestionScanView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.PeakShavingScanForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Horizon must be 1-90 days.')
            return redirect('utility:peak_list')
        horizon = form.cleaned_data['horizon_days']
        try:
            result = peak_svc.scan_for_peak_overlap(
                request.tenant, horizon_days=horizon,
            )
            if result['created'] == 0:
                messages.info(
                    request,
                    f'Scan complete (horizon {horizon} days): '
                    f'no new suggestions.',
                )
            else:
                messages.success(
                    request,
                    f'Scan complete: {result["created"]} new suggestion(s) created.',
                )
        except Exception as exc:
            messages.error(request, f'Scan failed: {exc}')
        return redirect('utility:peak_list')

    def get(self, request):
        return redirect('utility:peak_list')


class PeakShavingSuggestionAckView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.PeakShavingSuggestion, pk=pk, tenant=request.tenant)
        # L-03: parity with model is_acknowledgable() helper.
        if not obj.is_acknowledgable():
            messages.error(
                request,
                'Only suggestions in "new" state can be acknowledged.',
            )
            return redirect('utility:peak_detail', pk=pk)
        peak_svc.acknowledge(obj, by=request.user)
        messages.success(request, 'Suggestion acknowledged.')
        return redirect('utility:peak_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:peak_detail', pk=pk)


class PeakShavingSuggestionDismissView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.PeakShavingSuggestion, pk=pk, tenant=request.tenant)
        # L-03: parity with model is_dismissable() helper.
        if not obj.is_dismissable():
            messages.error(
                request,
                'Suggestion cannot be dismissed from its current state.',
            )
            return redirect('utility:peak_detail', pk=pk)
        # L-14: validate via the per-workflow form (dismiss_reason required).
        form = forms.PeakShavingDismissForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Dismiss reason is required.')
            return redirect('utility:peak_detail', pk=pk)
        peak_svc.dismiss(
            obj,
            reason=form.cleaned_data['dismiss_reason'],
            by=request.user,
        )
        messages.success(request, 'Suggestion dismissed.')
        return redirect('utility:peak_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:peak_detail', pk=pk)


# ============================================================================
# 14.4 Emission Factors
# ============================================================================

class EmissionFactorListView(TenantRequiredMixin, View):
    template_name = 'utility/factors/list.html'

    def get(self, request):
        qs = models.EmissionFactor.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(source_type__icontains=q) | Q(region__icontains=q)
            )
        scope = request.GET.get('scope', '')
        if scope:
            qs = qs.filter(scope=scope)
        source_type = request.GET.get('source_type', '')
        if source_type:
            qs = qs.filter(source_type=source_type)
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {
            'page': _paginate(
                qs.order_by('scope', 'source_type', '-effective_from'),
                request,
            ),
            'scope_choices': models.EmissionFactor.SCOPE_CHOICES,
            'source_type_choices': models.EmissionFactor.SOURCE_TYPE_CHOICES,
        })


class EmissionFactorCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/factors/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.EmissionFactorForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.EmissionFactorForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Emission factor created.')
            return redirect('utility:factor_list')
        return render(request, self.template_name, {
            'form': form, 'mode': 'create',
        })


class EmissionFactorEditView(TenantAdminRequiredMixin, View):
    template_name = 'utility/factors/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.EmissionFactorForm(instance=obj, tenant=request.tenant),
            'obj': obj, 'mode': 'edit',
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        form = forms.EmissionFactorForm(
            request.POST, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Emission factor updated.')
            return redirect('utility:factor_list')
        return render(request, self.template_name, {
            'form': form, 'obj': obj, 'mode': 'edit',
        })


class EmissionFactorDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.EmissionFactor, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Emission factor deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('utility:factor_list')

    def get(self, request, pk):
        return redirect('utility:factor_list')


# ============================================================================
# 14.4 Carbon Emissions (append-only ledger)
# ============================================================================

class CarbonEmissionListView(TenantRequiredMixin, View):
    template_name = 'utility/emissions/list.html'

    def get(self, request):
        qs = models.CarbonEmission.objects.filter(
            tenant=request.tenant,
        ).select_related('period', 'factor')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(entry_number__icontains=q) | Q(source_type__icontains=q)
            )
        scope = request.GET.get('scope', '')
        if scope:
            qs = qs.filter(scope=scope)
        period_pk = request.GET.get('period', '')
        if period_pk:
            qs = qs.filter(period_id=period_pk)
        from apps.cost.models import AccountingPeriod
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-recorded_at'), request),
            'scope_choices': models.CarbonEmission.SCOPE_CHOICES,
            'periods': AccountingPeriod.objects.filter(tenant=request.tenant),
        })


class CarbonEmissionDetailView(TenantRequiredMixin, View):
    template_name = 'utility/emissions/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.CarbonEmission.objects.select_related(
                'period', 'factor', 'source_consumption', 'source_allocation',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {
            'obj': obj,
            'reverse_form': forms.CarbonEmissionReverseForm(),
        })


class CarbonEmissionReverseView(TenantAdminRequiredMixin, View):
    """D-08: admin-only path to issue a typed-reason reversal of a manual or
    mis-emitted CarbonEmission row.

    Append-only ledger semantics — emits a NEW row with ``is_reversal=True``
    and negated ``co2e_kg``/``source_quantity`` rather than mutating or
    deleting the original. The audit signal on ``is_reversal`` flips records
    the action for compliance.
    """

    def post(self, request, pk):
        obj = get_object_or_404(
            models.CarbonEmission, pk=pk, tenant=request.tenant,
        )
        if obj.is_reversal:
            messages.warning(request, 'This is already a reversal row.')
            return redirect('utility:emission_detail', pk=pk)
        # Don't double-reverse: bail if a prior reversal of this row exists.
        already = models.CarbonEmission.all_objects.filter(
            tenant=obj.tenant,
            period=obj.period,
            is_reversal=True,
            notes__startswith=f'reversal-of:{obj.entry_number}',
        ).exists()
        if already:
            messages.warning(
                request,
                'A reversal already exists for this emission row.',
            )
            return redirect('utility:emission_detail', pk=pk)
        form = forms.CarbonEmissionReverseForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Reversal reason is required.')
            return redirect('utility:emission_detail', pk=pk)
        try:
            from decimal import Decimal as _D
            with transaction.atomic():
                reversal = models.CarbonEmission.all_objects.create(
                    tenant=obj.tenant,
                    period=obj.period,
                    scope=obj.scope,
                    source_type=obj.source_type,
                    source_quantity=_D('0'),
                    factor=obj.factor,
                    source_consumption=None,
                    source_allocation=obj.source_allocation,
                    recorded_by=request.user,
                    recorded_at=timezone.now(),
                    is_reversal=True,
                    notes=(
                        f'reversal-of:{obj.entry_number} | '
                        f'reason: {form.cleaned_data["reversal_reason"]}'
                    ),
                )
                # Override the persisted values with negated originals.
                models.CarbonEmission.all_objects.filter(pk=reversal.pk).update(
                    source_quantity=-(obj.source_quantity or _D('0')),
                    co2e_kg=-(obj.co2e_kg or _D('0')),
                )
            messages.success(request, 'Reversal row emitted.')
        except Exception as exc:
            messages.error(request, f'Reverse failed: {exc}')
        return redirect('utility:emission_detail', pk=pk)

    def get(self, request, pk):
        return redirect('utility:emission_detail', pk=pk)


class CarbonEmissionRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        from apps.cost.models import AccountingPeriod
        period = get_object_or_404(
            AccountingPeriod, pk=period_pk, tenant=request.tenant,
        )
        try:
            result = carbon_svc.recompute_emissions(period)
            emitted = result['emitted']
            scanned = result['consumptions_scanned']
            skipped = scanned - emitted
            messages.success(
                request,
                f'Recompute: {emitted} emission row(s) re-emitted from '
                f'{scanned} consumption row(s).',
            )
            # L-04: surface dropped count loudly.
            if skipped > 0:
                messages.warning(
                    request,
                    f'{skipped} consumption row(s) skipped — no active '
                    f'emission factor for that source/scope/period.',
                )
        except Exception as exc:
            messages.error(request, f'Recompute failed: {exc}')
        return redirect('utility:emission_list')

    def get(self, request, period_pk):
        return redirect('utility:emission_list')


# ============================================================================
# 14.4 Sustainability KPIs (generate-only)
# ============================================================================

class SustainabilityKPIListView(TenantRequiredMixin, View):
    template_name = 'utility/sustainability/list.html'

    def get(self, request):
        qs = models.SustainabilityKPI.objects.filter(
            tenant=request.tenant,
        ).select_related('period', 'generated_by')
        period_pk = request.GET.get('period', '')
        if period_pk:
            qs = qs.filter(period_id=period_pk)
        from apps.cost.models import AccountingPeriod
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-period__start_date'), request),
            'periods': AccountingPeriod.objects.filter(tenant=request.tenant),
        })


class SustainabilityKPIDetailView(TenantRequiredMixin, View):
    template_name = 'utility/sustainability/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.SustainabilityKPI.objects.select_related(
                'period', 'generated_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class SustainabilityKPIGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request, period_pk):
        from apps.cost.models import AccountingPeriod
        period = get_object_or_404(
            AccountingPeriod, pk=period_pk, tenant=request.tenant,
        )
        try:
            kpi = carbon_svc.generate_sustainability_kpi(
                period, generated_by=request.user,
            )
            messages.success(
                request,
                f'Sustainability KPI generated for {period.name}: '
                f'{kpi.total_co2e_kg} kgCO2e.',
            )
            return redirect('utility:sustainability_detail', pk=kpi.pk)
        except Exception as exc:
            messages.error(request, f'Generate failed: {exc}')
            return redirect('utility:sustainability_list')

    def get(self, request, period_pk):
        return redirect('utility:sustainability_list')


# ============================================================================
# 14.5 Benchmark Snapshots (generate-only)
# ============================================================================

class BenchmarkSnapshotListView(TenantRequiredMixin, View):
    template_name = 'utility/benchmarks/list.html'

    def get(self, request):
        qs = models.BenchmarkSnapshot.objects.filter(
            tenant=request.tenant,
        ).select_related('period', 'generated_by')
        period_pk = request.GET.get('period', '')
        if period_pk:
            qs = qs.filter(period_id=period_pk)
        plant = request.GET.get('plant_label', '').strip()
        if plant:
            qs = qs.filter(plant_label__icontains=plant)
        from apps.cost.models import AccountingPeriod
        return render(request, self.template_name, {
            'page': _paginate(
                qs.order_by('-period__start_date', 'plant_label'),
                request,
            ),
            'periods': AccountingPeriod.objects.filter(tenant=request.tenant),
            'generate_form': forms.BenchmarkSnapshotGenerateForm(tenant=request.tenant),
        })


class BenchmarkSnapshotDetailView(TenantRequiredMixin, View):
    template_name = 'utility/benchmarks/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.BenchmarkSnapshot.objects.select_related(
                'period', 'generated_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class BenchmarkSnapshotGenerateView(TenantAdminRequiredMixin, View):
    def post(self, request):
        form = forms.BenchmarkSnapshotGenerateForm(
            request.POST, tenant=request.tenant,
        )
        if not form.is_valid():
            messages.error(request, 'Pick a period and a plant label.')
            return redirect('utility:benchmark_list')
        period = form.cleaned_data['period']
        plant_label = form.cleaned_data['plant_label']
        try:
            snap = bench_svc.generate_snapshot(
                period, plant_label=plant_label,
                tenant=request.tenant, generated_by=request.user,
            )
            messages.success(
                request,
                f'Snapshot generated for {plant_label} / {period.name} '
                f'({snap.total_kwh} kWh).',
            )
            return redirect('utility:benchmark_detail', pk=snap.pk)
        except Exception as exc:
            messages.error(request, f'Generate failed: {exc}')
            return redirect('utility:benchmark_list')

    def get(self, request):
        return redirect('utility:benchmark_list')


# ============================================================================
# 14.5 Benchmark Comparison Reports
# ============================================================================

class BenchmarkComparisonListView(TenantRequiredMixin, View):
    template_name = 'utility/reports/list.html'

    def get(self, request):
        qs = models.BenchmarkComparison.objects.filter(
            tenant=request.tenant,
        ).select_related(
            'from_snapshot', 'from_snapshot__period',
            'to_snapshot', 'to_snapshot__period', 'generated_by',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(report_number__icontains=q) | Q(winner__icontains=q)
            )
        comp_type = request.GET.get('comparison_type', '')
        if comp_type:
            qs = qs.filter(comparison_type=comp_type)
        return render(request, self.template_name, {
            'page': _paginate(qs.order_by('-generated_at'), request),
            'comparison_choices': models.BenchmarkComparison.COMPARISON_CHOICES,
        })


class BenchmarkComparisonCreateView(TenantAdminRequiredMixin, View):
    template_name = 'utility/reports/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.BenchmarkComparisonForm(tenant=request.tenant),
            'mode': 'create',
        })

    def post(self, request):
        form = forms.BenchmarkComparisonForm(
            request.POST, tenant=request.tenant,
        )
        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form, 'mode': 'create',
            })
        data = form.cleaned_data
        try:
            report = bench_svc.create_comparison(
                comparison_type=data['comparison_type'],
                from_snapshot=data['from_snapshot'],
                to_snapshot=data['to_snapshot'],
                tenant=request.tenant,
                generated_by=request.user,
                notes=data.get('notes', ''),
            )
            messages.success(
                request,
                f'Comparison report {report.report_number} generated. '
                f'Winner: {report.winner}.',
            )
            return redirect('utility:benchmark_report_detail', pk=report.pk)
        except Exception as exc:
            messages.error(request, f'Compare failed: {exc}')
            return render(request, self.template_name, {
                'form': form, 'mode': 'create',
            })


class BenchmarkComparisonDetailView(TenantRequiredMixin, View):
    template_name = 'utility/reports/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.BenchmarkComparison.objects.select_related(
                'from_snapshot', 'from_snapshot__period',
                'to_snapshot', 'to_snapshot__period', 'generated_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        deltas = bench_svc.compare(obj.from_snapshot, obj.to_snapshot)
        return render(request, self.template_name, {
            'obj': obj, 'deltas': deltas,
        })


class BenchmarkComparisonDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(
            models.BenchmarkComparison, pk=pk, tenant=request.tenant,
        )
        try:
            obj.delete()
            messages.success(request, 'Benchmark comparison report deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
            return redirect('utility:benchmark_report_detail', pk=pk)
        return redirect('utility:benchmark_report_list')

    def get(self, request, pk):
        return redirect('utility:benchmark_report_detail', pk=pk)
