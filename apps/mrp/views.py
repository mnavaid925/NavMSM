"""Material Requirements Planning views — full CRUD + workflow + MRP run.

Every view filters by request.tenant. Workflow transitions use a conditional
UPDATE (atomic) so concurrent reviewers cannot double-action. The heavy work
(forecasting, lot sizing, gross-to-net + BOM explosion) lives in
apps/mrp/services/.
"""
import re
from datetime import date, timedelta
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
from apps.plm.models import Product

from .forms import (
    ForecastModelForm, ForecastRunForm, InventorySnapshotForm,
    MRPCalculationForm, MRPExceptionResolveForm, MRPPurchaseRequisitionForm,
    MRPRunForm, ScheduledReceiptForm, SeasonalityProfileForm,
)
from .models import (
    ForecastModel, ForecastResult, ForecastRun, InventorySnapshot,
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun, MRPRunResult,
    NetRequirement, ScheduledReceipt, SeasonalityProfile,
)
from .services import exceptions as exception_service
from .services import forecasting as forecast_service
from .services import mrp_engine

# ============================================================================
# Helpers (mirror the PPS pattern)
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

class MRPIndexView(TenantRequiredMixin, View):
    template_name = 'mrp/index.html'

    def get(self, request):
        t = request.tenant
        latest_run = (
            MRPRun.objects.filter(tenant=t, status='completed')
            .select_related('result').order_by('-finished_at').first()
        )
        latest_coverage = (
            latest_run.result.coverage_pct
            if latest_run and hasattr(latest_run, 'result') else None
        )
        ctx = {
            'open_runs': MRPRun.objects.filter(
                tenant=t, status__in=('queued', 'running'),
            ).count(),
            'completed_runs': MRPRun.objects.filter(tenant=t, status='completed').count(),
            'open_exceptions': MRPException.objects.filter(tenant=t, status='open').count(),
            'critical_exceptions': MRPException.objects.filter(
                tenant=t, status='open', severity='critical',
            ).count(),
            'late_orders': MRPException.objects.filter(
                tenant=t, status='open', exception_type='late_order',
            ).count(),
            'pending_prs': MRPPurchaseRequisition.objects.filter(
                tenant=t, status__in=('draft', 'approved'),
            ).count(),
            'forecast_models_active': ForecastModel.objects.filter(
                tenant=t, is_active=True,
            ).count(),
            'last_coverage': latest_coverage,
            'last_run': latest_run,
            'recent_runs': MRPRun.objects.filter(tenant=t).order_by('-created_at')[:6],
            'recent_exceptions': MRPException.objects.filter(
                tenant=t, status='open',
            ).select_related('product').order_by('-severity', '-created_at')[:8],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 5.1  FORECAST MODELS
# ============================================================================

class ForecastModelListView(TenantRequiredMixin, ListView):
    model = ForecastModel
    template_name = 'mrp/forecast_models/list.html'
    context_object_name = 'forecast_models'
    paginate_by = 20

    def get_queryset(self):
        qs = ForecastModel.objects.filter(tenant=self.request.tenant)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        for field in ('method', 'period_type'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['method_choices'] = ForecastModel.METHOD_CHOICES
        ctx['period_choices'] = ForecastModel.PERIOD_CHOICES
        return ctx


class ForecastModelCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'mrp/forecast_models/form.html', {
            'form': ForecastModelForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ForecastModelForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'Forecast model "{obj.name}" created.')
            return redirect('mrp:forecast_model_list')
        return render(request, 'mrp/forecast_models/form.html', {'form': form})


class ForecastModelDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        fm = get_object_or_404(ForecastModel, pk=pk, tenant=request.tenant)
        runs = fm.runs.order_by('-created_at')[:10]
        return render(request, 'mrp/forecast_models/detail.html', {
            'forecast_model': fm, 'runs': runs,
        })


class ForecastModelEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        fm = get_object_or_404(ForecastModel, pk=pk, tenant=request.tenant)
        return render(request, 'mrp/forecast_models/form.html', {
            'form': ForecastModelForm(instance=fm, tenant=request.tenant),
            'forecast_model': fm,
        })

    def post(self, request, pk):
        fm = get_object_or_404(ForecastModel, pk=pk, tenant=request.tenant)
        form = ForecastModelForm(request.POST, instance=fm, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Forecast model updated.')
            return redirect('mrp:forecast_model_detail', pk=fm.pk)
        return render(request, 'mrp/forecast_models/form.html', {
            'form': form, 'forecast_model': fm,
        })


class ForecastModelDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        fm = get_object_or_404(ForecastModel, pk=pk, tenant=request.tenant)
        try:
            fm.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — forecast model is referenced by past runs.')
            return redirect('mrp:forecast_model_detail', pk=pk)
        messages.success(request, 'Forecast model deleted.')
        return redirect('mrp:forecast_model_list')


class ForecastModelRunView(TenantRequiredMixin, View):
    """Execute a forecast against synthetic history. POST-only.

    For v1, history is pulled from existing ForecastResult rows OR a flat
    line of zeros if none exist. The seeder is responsible for populating
    a realistic baseline; production will eventually pull from sales-order
    history once Module 17 (Sales) is built.
    """
    def post(self, request, pk):
        fm = get_object_or_404(ForecastModel, pk=pk, tenant=request.tenant)

        def _make():
            n = _next_sequence_number(
                ForecastRun.objects.filter(tenant=request.tenant),
                'run_number', 'FRUN',
            )
            return ForecastRun.objects.create(
                tenant=request.tenant,
                run_number=n,
                forecast_model=fm,
                run_date=date.today(),
                status='running',
                started_by=request.user,
                started_at=timezone.now(),
            )
        run = _save_with_unique_number(_make)

        try:
            today = date.today()
            products = Product.objects.filter(
                tenant=request.tenant, status='active',
            )[:8]
            results = []
            params = fm.params or {}
            horizon = fm.horizon_periods
            step_days = 1 if fm.period_type == 'day' else (7 if fm.period_type == 'week' else 30)
            for product in products:
                # Synthetic history: last 12 periods at 100 ± noise from product pk.
                pseudo = [Decimal(str(80 + (product.pk * 7) % 40 + (i * 3))) for i in range(12)]
                if fm.method == 'naive_seasonal':
                    profiles = list(SeasonalityProfile.objects.filter(
                        tenant=request.tenant, product=product,
                    ).order_by('period_index')[:12])
                    indices = (
                        [p.seasonal_index for p in profiles]
                        if profiles else [Decimal('1')] * 12
                    )
                    forecast = forecast_service.naive_seasonal(pseudo, indices, horizon)
                else:
                    forecast = forecast_service.run_forecast(
                        fm.method, pseudo, params, horizon,
                    )
                for i, qty in enumerate(forecast):
                    ps = today + timedelta(days=step_days * i)
                    pe = ps + timedelta(days=step_days - 1)
                    results.append(ForecastResult(
                        tenant=request.tenant, run=run,
                        product=product, period_start=ps, period_end=pe,
                        forecasted_qty=qty,
                        lower_bound=qty * Decimal('0.85'),
                        upper_bound=qty * Decimal('1.15'),
                        confidence_pct=Decimal('80'),
                    ))
            ForecastResult.all_objects.bulk_create(results, batch_size=500)
            run.status = 'completed'
            run.finished_at = timezone.now()
            run.save()
            messages.success(
                request,
                f'Forecast {run.run_number} completed — produced {len(results)} forecast points.',
            )
        except Exception as exc:  # noqa: BLE001 — surface any unexpected error to the user
            run.status = 'failed'
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()
            messages.error(request, f'Forecast failed: {exc}')
        return redirect('mrp:forecast_run_detail', pk=run.pk)


# ============================================================================
# 5.1  SEASONALITY PROFILES
# ============================================================================

class SeasonalityListView(TenantRequiredMixin, ListView):
    model = SeasonalityProfile
    template_name = 'mrp/seasonality/list.html'
    context_object_name = 'profiles'
    paginate_by = 30

    def get_queryset(self):
        qs = SeasonalityProfile.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q))
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        period_type = self.request.GET.get('period_type', '')
        if period_type:
            qs = qs.filter(period_type=period_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        ctx['period_choices'] = SeasonalityProfile.PERIOD_CHOICES
        return ctx


class SeasonalityCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'mrp/seasonality/form.html', {
            'form': SeasonalityProfileForm(tenant=request.tenant),
        })

    def post(self, request):
        form = SeasonalityProfileForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Seasonality entry added.')
            return redirect('mrp:seasonality_list')
        return render(request, 'mrp/seasonality/form.html', {'form': form})


class SeasonalityEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        sp = get_object_or_404(SeasonalityProfile, pk=pk, tenant=request.tenant)
        return render(request, 'mrp/seasonality/form.html', {
            'form': SeasonalityProfileForm(instance=sp, tenant=request.tenant),
            'profile': sp,
        })

    def post(self, request, pk):
        sp = get_object_or_404(SeasonalityProfile, pk=pk, tenant=request.tenant)
        form = SeasonalityProfileForm(request.POST, instance=sp, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Seasonality entry updated.')
            return redirect('mrp:seasonality_list')
        return render(request, 'mrp/seasonality/form.html', {'form': form, 'profile': sp})


class SeasonalityDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        sp = get_object_or_404(SeasonalityProfile, pk=pk, tenant=request.tenant)
        sp.delete()
        messages.success(request, 'Seasonality entry deleted.')
        return redirect('mrp:seasonality_list')


# ============================================================================
# 5.1  FORECAST RUNS
# ============================================================================

class ForecastRunListView(TenantRequiredMixin, ListView):
    model = ForecastRun
    template_name = 'mrp/forecast_runs/list.html'
    context_object_name = 'runs'
    paginate_by = 20

    def get_queryset(self):
        qs = ForecastRun.objects.filter(
            tenant=self.request.tenant,
        ).select_related('forecast_model', 'started_by').annotate(result_count=Count('results'))
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(run_number__icontains=q) | Q(forecast_model__name__icontains=q))
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        forecast_model = self.request.GET.get('forecast_model', '')
        if forecast_model:
            qs = qs.filter(forecast_model_id=forecast_model)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = ForecastRun.STATUS_CHOICES
        ctx['forecast_models'] = ForecastModel.objects.filter(tenant=self.request.tenant).order_by('name')
        return ctx


class ForecastRunDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(
            ForecastRun.objects.select_related('forecast_model', 'started_by'),
            pk=pk, tenant=request.tenant,
        )
        results = run.results.select_related('product').order_by('product__sku', 'period_start')
        return render(request, 'mrp/forecast_runs/detail.html', {
            'run': run, 'results': results,
        })


class ForecastRunDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(ForecastRun, pk=pk, tenant=request.tenant)
        run.delete()
        messages.success(request, 'Forecast run deleted.')
        return redirect('mrp:forecast_run_list')


# ============================================================================
# 5.2  INVENTORY SNAPSHOTS
# ============================================================================

class InventoryListView(TenantRequiredMixin, ListView):
    model = InventorySnapshot
    template_name = 'mrp/inventory/list.html'
    context_object_name = 'snapshots'
    paginate_by = 20

    def get_queryset(self):
        qs = InventorySnapshot.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q))
        method = self.request.GET.get('lot_size_method', '')
        if method:
            qs = qs.filter(lot_size_method=method)
        return qs.order_by('product__sku')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lot_size_choices'] = InventorySnapshot.LOT_SIZE_CHOICES
        return ctx


class InventoryCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'mrp/inventory/form.html', {
            'form': InventorySnapshotForm(tenant=request.tenant),
        })

    def post(self, request):
        form = InventorySnapshotForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Inventory snapshot created.')
            return redirect('mrp:inventory_list')
        return render(request, 'mrp/inventory/form.html', {'form': form})


class InventoryDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        snap = get_object_or_404(
            InventorySnapshot.objects.select_related('product'),
            pk=pk, tenant=request.tenant,
        )
        upcoming_receipts = ScheduledReceipt.objects.filter(
            tenant=request.tenant, product=snap.product,
            expected_date__gte=date.today(),
        ).order_by('expected_date')[:10]
        return render(request, 'mrp/inventory/detail.html', {
            'snapshot': snap, 'upcoming_receipts': upcoming_receipts,
        })


class InventoryEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        snap = get_object_or_404(InventorySnapshot, pk=pk, tenant=request.tenant)
        return render(request, 'mrp/inventory/form.html', {
            'form': InventorySnapshotForm(instance=snap, tenant=request.tenant),
            'snapshot': snap,
        })

    def post(self, request, pk):
        snap = get_object_or_404(InventorySnapshot, pk=pk, tenant=request.tenant)
        form = InventorySnapshotForm(request.POST, instance=snap, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Inventory snapshot updated.')
            return redirect('mrp:inventory_detail', pk=snap.pk)
        return render(request, 'mrp/inventory/form.html', {'form': form, 'snapshot': snap})


class InventoryDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        snap = get_object_or_404(InventorySnapshot, pk=pk, tenant=request.tenant)
        snap.delete()
        messages.success(request, 'Inventory snapshot deleted.')
        return redirect('mrp:inventory_list')


# ============================================================================
# 5.2  SCHEDULED RECEIPTS
# ============================================================================

class ReceiptListView(TenantRequiredMixin, ListView):
    model = ScheduledReceipt
    template_name = 'mrp/receipts/list.html'
    context_object_name = 'receipts'
    paginate_by = 20

    def get_queryset(self):
        qs = ScheduledReceipt.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(reference__icontains=q))
        rtype = self.request.GET.get('receipt_type', '')
        if rtype:
            qs = qs.filter(receipt_type=rtype)
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.order_by('expected_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['receipt_type_choices'] = ScheduledReceipt.RECEIPT_TYPE_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class ReceiptCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'mrp/receipts/form.html', {
            'form': ScheduledReceiptForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ScheduledReceiptForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Scheduled receipt added.')
            return redirect('mrp:receipt_list')
        return render(request, 'mrp/receipts/form.html', {'form': form})


class ReceiptEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rcp = get_object_or_404(ScheduledReceipt, pk=pk, tenant=request.tenant)
        return render(request, 'mrp/receipts/form.html', {
            'form': ScheduledReceiptForm(instance=rcp, tenant=request.tenant),
            'receipt': rcp,
        })

    def post(self, request, pk):
        rcp = get_object_or_404(ScheduledReceipt, pk=pk, tenant=request.tenant)
        form = ScheduledReceiptForm(request.POST, instance=rcp, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Receipt updated.')
            return redirect('mrp:receipt_list')
        return render(request, 'mrp/receipts/form.html', {'form': form, 'receipt': rcp})


class ReceiptDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        rcp = get_object_or_404(ScheduledReceipt, pk=pk, tenant=request.tenant)
        rcp.delete()
        messages.success(request, 'Receipt deleted.')
        return redirect('mrp:receipt_list')


# ============================================================================
# 5.2  MRP CALCULATIONS
# ============================================================================

class CalculationListView(TenantRequiredMixin, ListView):
    model = MRPCalculation
    template_name = 'mrp/calculations/list.html'
    context_object_name = 'calculations'
    paginate_by = 20

    def get_queryset(self):
        qs = MRPCalculation.objects.filter(
            tenant=self.request.tenant,
        ).select_related('source_mps').annotate(
            net_count=Count('net_requirements', distinct=True),
            exc_count=Count('exceptions', distinct=True),
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(mrp_number__icontains=q) | Q(name__icontains=q))
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = MRPCalculation.STATUS_CHOICES
        return ctx


class CalculationDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        calc = get_object_or_404(
            MRPCalculation.objects.select_related('source_mps', 'started_by'),
            pk=pk, tenant=request.tenant,
        )
        nets = calc.net_requirements.select_related(
            'product', 'parent_product',
        ).order_by('bom_level', 'product__sku', 'period_start')
        prs = calc.purchase_requisitions.select_related('product').order_by('-created_at')
        excs = calc.exceptions.select_related('product').order_by('-severity', '-created_at')
        return render(request, 'mrp/calculations/detail.html', {
            'calc': calc, 'nets': nets, 'prs': prs, 'exceptions': excs,
        })


class CalculationDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        calc = get_object_or_404(MRPCalculation, pk=pk, tenant=request.tenant)
        if calc.status == 'committed':
            messages.error(request, 'Committed calculations cannot be deleted.')
            return redirect('mrp:calculation_detail', pk=pk)
        try:
            calc.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — calculation is referenced.')
            return redirect('mrp:calculation_detail', pk=pk)
        messages.success(request, 'MRP calculation deleted.')
        return redirect('mrp:calculation_list')


# ============================================================================
# 5.5  MRP RUNS
# ============================================================================

class RunListView(TenantRequiredMixin, ListView):
    model = MRPRun
    template_name = 'mrp/runs/list.html'
    context_object_name = 'runs'
    paginate_by = 20

    def get_queryset(self):
        qs = MRPRun.objects.filter(
            tenant=self.request.tenant,
        ).select_related('mrp_calculation', 'source_mps', 'started_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(run_number__icontains=q) | Q(name__icontains=q))
        for field in ('status', 'run_type'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = MRPRun.STATUS_CHOICES
        ctx['run_type_choices'] = MRPRun.RUN_TYPE_CHOICES
        return ctx


class RunCreateView(TenantRequiredMixin, View):
    """Creates an MRPRun + a fresh MRPCalculation pair queued for execution."""
    def get(self, request):
        return render(request, 'mrp/runs/form.html', {
            'run_form': MRPRunForm(tenant=request.tenant),
            'calc_form': MRPCalculationForm(tenant=request.tenant),
        })

    def post(self, request):
        run_form = MRPRunForm(request.POST, tenant=request.tenant)
        calc_form = MRPCalculationForm(request.POST, tenant=request.tenant)
        if run_form.is_valid() and calc_form.is_valid():
            def _make():
                with transaction.atomic():
                    calc = calc_form.save(commit=False)
                    calc.tenant = request.tenant
                    calc.started_by = request.user
                    calc.mrp_number = _next_sequence_number(
                        MRPCalculation.objects.filter(tenant=request.tenant),
                        'mrp_number', 'MRP',
                    )
                    calc.save()
                    run = run_form.save(commit=False)
                    run.tenant = request.tenant
                    run.mrp_calculation = calc
                    run.started_by = request.user
                    run.run_number = _next_sequence_number(
                        MRPRun.objects.filter(tenant=request.tenant),
                        'run_number', 'MRPRUN',
                    )
                    run.save()
                    return run
            run = _save_with_unique_number(_make)
            messages.success(request, f'MRP run {run.run_number} created. Click Start to execute.')
            return redirect('mrp:run_detail', pk=run.pk)
        return render(request, 'mrp/runs/form.html', {
            'run_form': run_form, 'calc_form': calc_form,
        })


class RunDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        run = get_object_or_404(
            MRPRun.objects.select_related('mrp_calculation', 'source_mps', 'started_by'),
            pk=pk, tenant=request.tenant,
        )
        result = MRPRunResult.objects.filter(run=run).first()
        return render(request, 'mrp/runs/detail.html', {
            'run': run, 'result': result, 'calc': run.mrp_calculation,
        })


class RunStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(
            MRPRun.objects.select_related('mrp_calculation', 'source_mps'),
            pk=pk, tenant=request.tenant,
        )
        if not run.can_start():
            messages.warning(request, 'Run is not in Queued state.')
            return redirect('mrp:run_detail', pk=pk)

        # Mark running
        run.status = 'running'
        run.started_at = timezone.now()
        run.save()
        run.mrp_calculation.status = 'running'
        run.mrp_calculation.started_at = timezone.now()
        run.mrp_calculation.save()

        try:
            calc = run.mrp_calculation
            if run.source_mps_id and not calc.source_mps_id:
                calc.source_mps = run.source_mps
                calc.save()
            summary = mrp_engine.run_mrp(calc, mode=run.run_type)
            exc_count = exception_service.generate_exceptions(
                calc, skipped_no_bom_skus=summary.skipped_no_bom,
            )

            # Coverage = 1 - (sum of net_requirement / sum of gross_requirement) as %.
            from django.db.models import Sum
            agg = NetRequirement.objects.filter(mrp_calculation=calc).aggregate(
                gross=Sum('gross_requirement'),
                net=Sum('net_requirement'),
            )
            gross = agg['gross'] or Decimal('0')
            net = agg['net'] or Decimal('0')
            coverage = Decimal('100')
            if gross > 0:
                coverage = ((gross - net) / gross) * Decimal('100')
                if coverage < 0:
                    coverage = Decimal('0')
            late_count = MRPException.objects.filter(
                mrp_calculation=calc, exception_type='late_order',
            ).count()
            MRPRunResult.objects.create(
                tenant=request.tenant, run=run,
                total_planned_orders=summary.total_planned_orders,
                total_pr_suggestions=summary.total_pr_suggestions,
                total_exceptions=exc_count,
                late_orders_count=late_count,
                coverage_pct=coverage.quantize(Decimal('0.01')),
                summary_json={
                    'skipped_no_bom': summary.skipped_no_bom,
                    'notes': summary.notes,
                },
                computed_at=timezone.now(),
            )
            run.status = 'completed'
            run.finished_at = timezone.now()
            run.save()
            calc.status = 'completed'
            calc.finished_at = timezone.now()
            calc.save()
            if summary.skipped_no_bom:
                messages.warning(
                    request,
                    'Some end items had no released BOM and were skipped: '
                    + ', '.join(summary.skipped_no_bom),
                )
            messages.success(
                request,
                f'MRP run completed — {summary.total_planned_orders} planned orders, '
                f'{summary.total_pr_suggestions} PR suggestions, {exc_count} exceptions.',
            )
        except Exception as exc:  # noqa: BLE001 — surface any failure for the user
            run.status = 'failed'
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()
            calc.status = 'failed'
            calc.finished_at = timezone.now()
            calc.error_message = str(exc)
            calc.save()
            messages.error(request, f'MRP run failed: {exc}')
        return redirect('mrp:run_detail', pk=run.pk)


class RunApplyView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(MRPRun, pk=pk, tenant=request.tenant)
        if not run.can_apply():
            messages.warning(
                request,
                'Only completed Regenerative or Net-Change runs can be applied. Simulations are read-only.',
            )
            return redirect('mrp:run_detail', pk=pk)
        ok = _atomic_status_transition(
            MRPRun, pk, request.tenant, ['completed'], 'applied',
            extra_fields={'applied_at': timezone.now()},
        )
        if ok:
            MRPRun.objects.filter(pk=pk).update(applied_by=request.user)
            MRPCalculation.objects.filter(pk=run.mrp_calculation_id).update(
                status='committed', committed_at=timezone.now(),
                committed_by=request.user,
            )
            messages.success(request, 'MRP run applied — calculation committed.')
        else:
            messages.warning(request, 'Run is not in Completed state.')
        return redirect('mrp:run_detail', pk=pk)


class RunDiscardView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(MRPRun, pk=pk, tenant=request.tenant)
        if not run.can_discard():
            messages.warning(request, 'Only Completed or Failed runs can be discarded.')
            return redirect('mrp:run_detail', pk=pk)
        ok = _atomic_status_transition(
            MRPRun, pk, request.tenant, ['completed', 'failed'], 'discarded',
        )
        if ok:
            MRPCalculation.objects.filter(pk=run.mrp_calculation_id).update(status='discarded')
            messages.success(request, 'MRP run discarded.')
        else:
            messages.warning(request, 'Run could not be discarded.')
        return redirect('mrp:run_detail', pk=pk)


class RunDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(MRPRun, pk=pk, tenant=request.tenant)
        if run.status == 'applied':
            messages.error(request, 'Applied runs cannot be deleted.')
            return redirect('mrp:run_detail', pk=pk)
        try:
            run.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — run is referenced.')
            return redirect('mrp:run_detail', pk=pk)
        messages.success(request, 'MRP run deleted.')
        return redirect('mrp:run_list')


# ============================================================================
# 5.3  PURCHASE REQUISITIONS
# ============================================================================

class PRListView(TenantRequiredMixin, ListView):
    model = MRPPurchaseRequisition
    template_name = 'mrp/requisitions/list.html'
    context_object_name = 'requisitions'
    paginate_by = 20

    def get_queryset(self):
        qs = MRPPurchaseRequisition.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'mrp_calculation')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(pr_number__icontains=q) | Q(product__sku__icontains=q))
        for field in ('status', 'priority'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = MRPPurchaseRequisition.STATUS_CHOICES
        ctx['priority_choices'] = MRPPurchaseRequisition.PRIORITY_CHOICES
        ctx['products'] = Product.objects.filter(tenant=self.request.tenant).order_by('sku')
        return ctx


class PRDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        pr = get_object_or_404(
            MRPPurchaseRequisition.objects.select_related('product', 'mrp_calculation', 'approved_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'mrp/requisitions/detail.html', {'pr': pr})


class PREditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        pr = get_object_or_404(MRPPurchaseRequisition, pk=pk, tenant=request.tenant)
        if not pr.is_editable():
            messages.warning(request, 'PR can only be edited in Draft status.')
            return redirect('mrp:pr_detail', pk=pk)
        return render(request, 'mrp/requisitions/form.html', {
            'form': MRPPurchaseRequisitionForm(instance=pr, tenant=request.tenant),
            'pr': pr,
        })

    def post(self, request, pk):
        pr = get_object_or_404(MRPPurchaseRequisition, pk=pk, tenant=request.tenant)
        if not pr.is_editable():
            messages.warning(request, 'PR can only be edited in Draft status.')
            return redirect('mrp:pr_detail', pk=pk)
        form = MRPPurchaseRequisitionForm(request.POST, instance=pr, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'PR updated.')
            return redirect('mrp:pr_detail', pk=pr.pk)
        return render(request, 'mrp/requisitions/form.html', {'form': form, 'pr': pr})


class PRApproveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MRPPurchaseRequisition, pk, request.tenant, ['draft'], 'approved',
            extra_fields={'approved_at': timezone.now()},
        )
        if ok:
            MRPPurchaseRequisition.objects.filter(pk=pk).update(approved_by=request.user)
            messages.success(request, 'PR approved.')
        else:
            messages.warning(request, 'Only Draft PRs can be approved.')
        return redirect('mrp:pr_detail', pk=pk)


class PRCancelView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MRPPurchaseRequisition, pk, request.tenant,
            ['draft', 'approved'], 'cancelled',
        )
        msg = 'PR cancelled.' if ok else 'PR cannot be cancelled in current state.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mrp:pr_detail', pk=pk)


class PRDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        pr = get_object_or_404(MRPPurchaseRequisition, pk=pk, tenant=request.tenant)
        if pr.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only Draft or Cancelled PRs can be deleted.')
            return redirect('mrp:pr_detail', pk=pk)
        pr.delete()
        messages.success(request, 'PR deleted.')
        return redirect('mrp:pr_list')


# ============================================================================
# 5.4  EXCEPTIONS
# ============================================================================

class ExceptionListView(TenantRequiredMixin, ListView):
    model = MRPException
    template_name = 'mrp/exceptions/list.html'
    context_object_name = 'exceptions'
    paginate_by = 25

    def get_queryset(self):
        qs = MRPException.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'mrp_calculation')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(message__icontains=q))
        for field in ('exception_type', 'severity', 'status'):
            v = self.request.GET.get(field, '')
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by('-severity', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['type_choices'] = MRPException.EXCEPTION_TYPE_CHOICES
        ctx['severity_choices'] = MRPException.SEVERITY_CHOICES
        ctx['status_choices'] = MRPException.STATUS_CHOICES
        return ctx


class ExceptionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        exc = get_object_or_404(
            MRPException.objects.select_related('product', 'mrp_calculation', 'resolved_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'mrp/exceptions/detail.html', {
            'exc': exc, 'resolve_form': MRPExceptionResolveForm(instance=exc),
        })


class ExceptionAckView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MRPException, pk, request.tenant, ['open'], 'acknowledged',
        )
        msg = 'Exception acknowledged.' if ok else 'Only open exceptions can be acknowledged.'
        (messages.success if ok else messages.warning)(request, msg)
        return redirect('mrp:exception_detail', pk=pk)


class ExceptionResolveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        exc = get_object_or_404(MRPException, pk=pk, tenant=request.tenant)
        if exc.status not in ('open', 'acknowledged'):
            messages.warning(request, 'Exception is already resolved/ignored.')
            return redirect('mrp:exception_detail', pk=pk)
        form = MRPExceptionResolveForm(request.POST, instance=exc)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.status = 'resolved'
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
            obj.save()
            messages.success(request, 'Exception marked resolved.')
        else:
            messages.error(request, 'Please add a resolution note.')
        return redirect('mrp:exception_detail', pk=pk)


class ExceptionIgnoreView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            MRPException, pk, request.tenant, ['open', 'acknowledged'], 'ignored',
            extra_fields={'resolved_at': timezone.now()},
        )
        if ok:
            MRPException.objects.filter(pk=pk).update(resolved_by=request.user)
            messages.success(request, 'Exception ignored.')
        else:
            messages.warning(request, 'Only open or acknowledged exceptions can be ignored.')
        return redirect('mrp:exception_detail', pk=pk)


class ExceptionDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        exc = get_object_or_404(MRPException, pk=pk, tenant=request.tenant)
        exc.delete()
        messages.success(request, 'Exception deleted.')
        return redirect('mrp:exception_list')
