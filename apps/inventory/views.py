"""Module 8 — Inventory & Warehouse Management views.

Full CRUD across the 5 sub-modules + workflow actions:
    - GRN: receive (draft -> received), generate putaway tasks, complete putaway, cancel
    - Transfer: send (draft -> in_transit), receive (in_transit -> received), cancel
    - Adjustment: post (draft -> posted)
    - Cycle count: start (draft -> counting), reconcile (counting -> reconciled), cancel

Every view filters by ``request.tenant``. Workflow transitions use a
conditional UPDATE for race safety. Heavy lifting lives in ``services/``.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin
from apps.plm.models import Product

from . import forms, models
from .services import grn as grn_service
from .services.cycle_count import compute_variance
from .services.movements import post_movement


PAGE_SIZE = 25


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


def _paginate(qs, request, size=PAGE_SIZE):
    from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'inventory/index.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        soon = today + timedelta(days=30)

        ctx = {
            'warehouse_count': models.Warehouse.objects.filter(tenant=t, is_active=True).count(),
            'bin_count': models.StorageBin.objects.filter(tenant=t).count(),
            'sku_count': (
                models.StockItem.objects.filter(tenant=t)
                .values('product').distinct().count()
            ),
            'open_grn': models.GoodsReceiptNote.objects.filter(
                tenant=t, status__in=('draft', 'received', 'putaway_pending'),
            ).count(),
            'open_transfers': models.StockTransfer.objects.filter(
                tenant=t, status__in=('draft', 'in_transit'),
            ).count(),
            'open_cycle_counts': models.CycleCountSheet.objects.filter(
                tenant=t, status__in=('draft', 'counting'),
            ).count(),
            'expiring_lots': models.Lot.objects.filter(
                tenant=t, status='active',
                expiry_date__isnull=False,
                expiry_date__lte=soon,
                expiry_date__gte=today,
            ).count(),
            'expired_lots': models.Lot.objects.filter(
                tenant=t,
                expiry_date__isnull=False,
                expiry_date__lt=today,
            ).exclude(status__in=('expired', 'consumed')).count(),
            'recent_movements': models.StockMovement.objects.filter(
                tenant=t,
            ).select_related('product', 'from_bin', 'to_bin').order_by('-posted_at')[:8],
            'expiring_lot_list': models.Lot.objects.filter(
                tenant=t, status='active',
                expiry_date__isnull=False,
                expiry_date__lte=soon,
            ).select_related('product').order_by('expiry_date')[:8],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 8.1  WAREHOUSE / ZONE / BIN CRUD
# ============================================================================

class WarehouseListView(TenantRequiredMixin, View):
    template_name = 'inventory/warehouses/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.Warehouse.objects.filter(tenant=t).select_related('manager')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        page = _paginate(qs.order_by('code'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'active_filter': active,
        })


class WarehouseCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/warehouses/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.WarehouseForm(tenant=request.tenant),
            'is_create': True,
        })

    def post(self, request):
        form = forms.WarehouseForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Warehouse {obj.code} created.')
            return redirect('inventory:warehouse_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class WarehouseDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/warehouses/detail.html'

    def get(self, request, pk):
        wh = get_object_or_404(models.Warehouse, pk=pk, tenant=request.tenant)
        zones = wh.zones.prefetch_related('bins').order_by('zone_type', 'code')
        return render(request, self.template_name, {'wh': wh, 'zones': zones})


class WarehouseEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/warehouses/form.html'

    def get(self, request, pk):
        wh = get_object_or_404(models.Warehouse, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.WarehouseForm(instance=wh, tenant=request.tenant),
            'wh': wh, 'is_create': False,
        })

    def post(self, request, pk):
        wh = get_object_or_404(models.Warehouse, pk=pk, tenant=request.tenant)
        form = forms.WarehouseForm(request.POST, instance=wh, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse updated.')
            return redirect('inventory:warehouse_detail', pk=wh.pk)
        return render(request, self.template_name, {'form': form, 'wh': wh, 'is_create': False})


class WarehouseDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        wh = get_object_or_404(models.Warehouse, pk=pk, tenant=request.tenant)
        try:
            wh.delete()
            messages.success(request, 'Warehouse deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete warehouse: {e}')
        return redirect('inventory:warehouse_list')

    def get(self, request, pk):
        return redirect('inventory:warehouse_list')


# Zones
class WarehouseZoneListView(TenantRequiredMixin, View):
    template_name = 'inventory/zones/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.WarehouseZone.objects.filter(tenant=t).select_related('warehouse')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        zone_type = request.GET.get('zone_type', '')
        if zone_type:
            qs = qs.filter(zone_type=zone_type)
        warehouse = request.GET.get('warehouse', '')
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)
        page = _paginate(qs.order_by('warehouse__code', 'code'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'zone_type_filter': zone_type, 'warehouse_filter': warehouse,
            'zone_type_choices': models.WarehouseZone.ZONE_TYPE_CHOICES,
            'warehouses': models.Warehouse.objects.filter(tenant=t),
        })


class WarehouseZoneCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/zones/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.WarehouseZoneForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.WarehouseZoneForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Zone {obj.code} created.')
            return redirect('inventory:zone_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class WarehouseZoneEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/zones/form.html'

    def get(self, request, pk):
        zone = get_object_or_404(models.WarehouseZone, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.WarehouseZoneForm(instance=zone, tenant=request.tenant),
            'zone': zone, 'is_create': False,
        })

    def post(self, request, pk):
        zone = get_object_or_404(models.WarehouseZone, pk=pk, tenant=request.tenant)
        form = forms.WarehouseZoneForm(request.POST, instance=zone, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Zone updated.')
            return redirect('inventory:zone_list')
        return render(request, self.template_name, {'form': form, 'zone': zone, 'is_create': False})


class WarehouseZoneDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        zone = get_object_or_404(models.WarehouseZone, pk=pk, tenant=request.tenant)
        try:
            zone.delete()
            messages.success(request, 'Zone deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete zone: {e}')
        return redirect('inventory:zone_list')

    def get(self, request, pk):
        return redirect('inventory:zone_list')


# Bins
class StorageBinListView(TenantRequiredMixin, View):
    template_name = 'inventory/bins/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.StorageBin.objects.filter(tenant=t).select_related('zone__warehouse')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(code__icontains=q)
        bin_type = request.GET.get('bin_type', '')
        if bin_type:
            qs = qs.filter(bin_type=bin_type)
        abc = request.GET.get('abc_class', '')
        if abc:
            qs = qs.filter(abc_class=abc)
        blocked = request.GET.get('blocked', '')
        if blocked == 'yes':
            qs = qs.filter(is_blocked=True)
        elif blocked == 'no':
            qs = qs.filter(is_blocked=False)
        page = _paginate(qs.order_by('zone__warehouse__code', 'zone__code', 'code'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'bin_type_filter': bin_type, 'abc_filter': abc, 'blocked_filter': blocked,
            'bin_type_choices': models.StorageBin.BIN_TYPE_CHOICES,
        })


class StorageBinCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/bins/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.StorageBinForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.StorageBinForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Bin {obj.code} created.')
            return redirect('inventory:bin_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class StorageBinEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/bins/form.html'

    def get(self, request, pk):
        bin = get_object_or_404(models.StorageBin, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.StorageBinForm(instance=bin, tenant=request.tenant),
            'bin': bin, 'is_create': False,
        })

    def post(self, request, pk):
        bin = get_object_or_404(models.StorageBin, pk=pk, tenant=request.tenant)
        form = forms.StorageBinForm(request.POST, instance=bin, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Bin updated.')
            return redirect('inventory:bin_list')
        return render(request, self.template_name, {'form': form, 'bin': bin, 'is_create': False})


class StorageBinDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        bin = get_object_or_404(models.StorageBin, pk=pk, tenant=request.tenant)
        try:
            bin.delete()
            messages.success(request, 'Bin deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete bin: {e}')
        return redirect('inventory:bin_list')

    def get(self, request, pk):
        return redirect('inventory:bin_list')


# StockItem (read-only — auto-maintained by movements)
class StockItemListView(TenantRequiredMixin, View):
    template_name = 'inventory/stock_items/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.StockItem.objects.filter(tenant=t).select_related(
            'product', 'bin__zone__warehouse', 'lot', 'serial',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q))
        warehouse = request.GET.get('warehouse', '')
        if warehouse:
            qs = qs.filter(bin__zone__warehouse_id=warehouse)
        only_in_stock = request.GET.get('in_stock', '')
        if only_in_stock == 'yes':
            qs = qs.filter(qty_on_hand__gt=0)
        page = _paginate(qs.order_by('product__sku', 'bin__code'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'warehouse_filter': warehouse, 'in_stock_filter': only_in_stock,
            'warehouses': models.Warehouse.objects.filter(tenant=t),
        })


# ============================================================================
# 8.2  GOODS RECEIPT & PUTAWAY
# ============================================================================

class GRNListView(TenantRequiredMixin, View):
    template_name = 'inventory/grn/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.GoodsReceiptNote.objects.filter(tenant=t).select_related('warehouse')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(grn_number__icontains=q)
                | Q(supplier_name__icontains=q)
                | Q(po_reference__icontains=q)
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        warehouse = request.GET.get('warehouse', '')
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)
        page = _paginate(qs.order_by('-received_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'warehouse_filter': warehouse,
            'status_choices': models.GoodsReceiptNote.STATUS_CHOICES,
            'warehouses': models.Warehouse.objects.filter(tenant=t),
        })


class GRNCreateView(TenantRequiredMixin, View):
    template_name = 'inventory/grn/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.GoodsReceiptNoteForm(tenant=request.tenant),
            'is_create': True,
        })

    def post(self, request):
        form = forms.GoodsReceiptNoteForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            grn = form.save(commit=False)
            grn.tenant = request.tenant
            grn.received_by = request.user
            grn.save()
            messages.success(request, f'GRN {grn.grn_number} created. Add lines next.')
            return redirect('inventory:grn_detail', pk=grn.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class GRNDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/grn/detail.html'

    def get(self, request, pk):
        grn = get_object_or_404(
            models.GoodsReceiptNote, pk=pk, tenant=request.tenant,
        )
        line_form = forms.GRNLineForm(tenant=request.tenant)
        lines = grn.lines.select_related('product', 'receiving_zone').all()
        putaway_tasks = models.PutawayTask.objects.filter(
            tenant=request.tenant, grn_line__grn=grn,
        ).select_related('grn_line__product', 'suggested_bin', 'actual_bin')
        return render(request, self.template_name, {
            'grn': grn, 'lines': lines, 'line_form': line_form,
            'putaway_tasks': putaway_tasks,
        })


class GRNEditView(TenantRequiredMixin, View):
    template_name = 'inventory/grn/form.html'

    def get(self, request, pk):
        grn = get_object_or_404(models.GoodsReceiptNote, pk=pk, tenant=request.tenant)
        if grn.status != 'draft':
            messages.error(request, 'Only draft GRNs can be edited.')
            return redirect('inventory:grn_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.GoodsReceiptNoteForm(instance=grn, tenant=request.tenant),
            'grn': grn, 'is_create': False,
        })

    def post(self, request, pk):
        grn = get_object_or_404(models.GoodsReceiptNote, pk=pk, tenant=request.tenant)
        if grn.status != 'draft':
            messages.error(request, 'Only draft GRNs can be edited.')
            return redirect('inventory:grn_detail', pk=pk)
        form = forms.GoodsReceiptNoteForm(request.POST, instance=grn, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'GRN updated.')
            return redirect('inventory:grn_detail', pk=grn.pk)
        return render(request, self.template_name, {'form': form, 'grn': grn, 'is_create': False})


class GRNDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        grn = get_object_or_404(models.GoodsReceiptNote, pk=pk, tenant=request.tenant)
        if grn.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft or cancelled GRNs can be deleted.')
            return redirect('inventory:grn_detail', pk=pk)
        grn.delete()
        messages.success(request, 'GRN deleted.')
        return redirect('inventory:grn_list')

    def get(self, request, pk):
        return redirect('inventory:grn_detail', pk=pk)


class GRNLineCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        grn = get_object_or_404(models.GoodsReceiptNote, pk=pk, tenant=request.tenant)
        if grn.status != 'draft':
            messages.error(request, 'Lines can only be added to draft GRNs.')
            return redirect('inventory:grn_detail', pk=pk)
        form = forms.GRNLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.grn = grn
            line.save()
            messages.success(request, 'GRN line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('inventory:grn_detail', pk=pk)


class GRNLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.GRNLine, pk=pk, tenant=request.tenant)
        if line.grn.status != 'draft':
            messages.error(request, 'Only draft GRNs can be modified.')
            return redirect('inventory:grn_detail', pk=line.grn_id)
        grn_pk = line.grn_id
        line.delete()
        messages.success(request, 'GRN line removed.')
        return redirect('inventory:grn_detail', pk=grn_pk)

    def get(self, request, pk):
        line = get_object_or_404(models.GRNLine, pk=pk, tenant=request.tenant)
        return redirect('inventory:grn_detail', pk=line.grn_id)


class GRNReceiveView(TenantRequiredMixin, View):
    """draft -> received: generate putaway tasks for each line."""

    def post(self, request, pk):
        grn = get_object_or_404(models.GoodsReceiptNote, pk=pk, tenant=request.tenant)
        if not grn.lines.exists():
            messages.error(request, 'GRN has no lines — add at least one before receiving.')
            return redirect('inventory:grn_detail', pk=pk)
        ok = _atomic_status_transition(
            models.GoodsReceiptNote, pk, request.tenant,
            from_states=('draft',), to_state='putaway_pending',
        )
        if not ok:
            messages.error(request, 'GRN is not in draft status.')
            return redirect('inventory:grn_detail', pk=pk)
        grn.refresh_from_db()
        strategy = request.POST.get('strategy', 'nearest_empty')
        grn_service.generate_putaway_tasks(grn, strategy=strategy)
        messages.success(request, 'GRN received. Putaway tasks generated.')
        return redirect('inventory:grn_detail', pk=pk)


class GRNCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.GoodsReceiptNote, pk, request.tenant,
            from_states=('draft', 'received', 'putaway_pending'), to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'GRN cannot be cancelled in its current state.')
        else:
            messages.success(request, 'GRN cancelled.')
        return redirect('inventory:grn_detail', pk=pk)


class PutawayCompleteView(TenantRequiredMixin, View):
    """Mark a putaway task complete and post the receipt movement."""

    def post(self, request, pk):
        task = get_object_or_404(
            models.PutawayTask, pk=pk, tenant=request.tenant,
        )
        if task.status == 'completed':
            messages.info(request, 'Task already completed.')
            return redirect('inventory:grn_detail', pk=task.grn_line.grn_id)

        actual_bin_id = request.POST.get('actual_bin')
        if not actual_bin_id:
            messages.error(request, 'Pick an actual bin to complete putaway.')
            return redirect('inventory:grn_detail', pk=task.grn_line.grn_id)
        actual_bin = get_object_or_404(
            models.StorageBin, pk=actual_bin_id, tenant=request.tenant,
        )

        line = task.grn_line
        # Resolve or create the lot if the GRN line carries a lot_number.
        lot = None
        if line.lot_number:
            lot, _ = models.Lot.all_objects.get_or_create(
                tenant=request.tenant,
                product=line.product,
                lot_number=line.lot_number,
                defaults={'status': 'active'},
            )

        with transaction.atomic():
            task.actual_bin = actual_bin
            task.status = 'completed'
            task.completed_by = request.user
            task.completed_at = timezone.now()
            task.save()
            post_movement(
                tenant=request.tenant,
                movement_type='receipt',
                product=line.product,
                qty=task.qty,
                to_bin=actual_bin,
                lot=lot,
                reason='GRN putaway',
                reference=line.grn.grn_number,
                grn_line=line,
                posted_by=request.user,
            )
        # If every task on the GRN is completed, flip GRN -> completed.
        all_done = not models.PutawayTask.objects.filter(
            tenant=request.tenant, grn_line__grn=line.grn,
        ).exclude(status__in=('completed', 'cancelled')).exists()
        if all_done:
            line.grn.status = 'completed'
            line.grn.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Putaway complete.')
        return redirect('inventory:grn_detail', pk=line.grn_id)


# ============================================================================
# 8.3  MOVEMENTS / TRANSFERS / ADJUSTMENTS
# ============================================================================

class StockMovementListView(TenantRequiredMixin, View):
    template_name = 'inventory/movements/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.StockMovement.objects.filter(tenant=t).select_related(
            'product', 'from_bin', 'to_bin', 'lot',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q) | Q(reference__icontains=q),
            )
        mtype = request.GET.get('movement_type', '')
        if mtype:
            qs = qs.filter(movement_type=mtype)
        page = _paginate(qs.order_by('-posted_at', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'movement_type_filter': mtype,
            'movement_type_choices': models.StockMovement.MOVEMENT_TYPE_CHOICES,
        })


class StockMovementCreateView(TenantRequiredMixin, View):
    template_name = 'inventory/movements/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.StockMovementForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.StockMovementForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                post_movement(
                    tenant=request.tenant,
                    movement_type=form.cleaned_data['movement_type'],
                    product=form.cleaned_data['product'],
                    qty=form.cleaned_data['qty'],
                    from_bin=form.cleaned_data.get('from_bin'),
                    to_bin=form.cleaned_data.get('to_bin'),
                    lot=form.cleaned_data.get('lot'),
                    serial=form.cleaned_data.get('serial'),
                    reason=form.cleaned_data.get('reason', ''),
                    reference=form.cleaned_data.get('reference', ''),
                    notes=form.cleaned_data.get('notes', ''),
                    posted_by=request.user,
                )
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, self.template_name, {'form': form, 'is_create': True})
            messages.success(request, 'Movement posted.')
            return redirect('inventory:movement_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class StockMovementDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/movements/detail.html'

    def get(self, request, pk):
        mv = get_object_or_404(
            models.StockMovement, pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'mv': mv})


# Transfers
class TransferListView(TenantRequiredMixin, View):
    template_name = 'inventory/transfers/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.StockTransfer.objects.filter(tenant=t).select_related(
            'source_warehouse', 'destination_warehouse',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(transfer_number__icontains=q)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-requested_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.StockTransfer.STATUS_CHOICES,
        })


class TransferCreateView(TenantRequiredMixin, View):
    template_name = 'inventory/transfers/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.StockTransferForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.StockTransferForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.requested_by = request.user
            obj.save()
            messages.success(request, f'Transfer {obj.transfer_number} created.')
            return redirect('inventory:transfer_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class TransferDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/transfers/detail.html'

    def get(self, request, pk):
        tr = get_object_or_404(models.StockTransfer, pk=pk, tenant=request.tenant)
        lines = tr.lines.select_related('product', 'source_bin', 'destination_bin', 'lot')
        line_form = forms.StockTransferLineForm(tenant=request.tenant)
        return render(request, self.template_name, {
            'tr': tr, 'lines': lines, 'line_form': line_form,
        })


class TransferLineCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        tr = get_object_or_404(models.StockTransfer, pk=pk, tenant=request.tenant)
        if tr.status != 'draft':
            messages.error(request, 'Only draft transfers can be modified.')
            return redirect('inventory:transfer_detail', pk=pk)
        form = forms.StockTransferLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.transfer = tr
            line.save()
            messages.success(request, 'Transfer line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('inventory:transfer_detail', pk=pk)


class TransferLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.StockTransferLine, pk=pk, tenant=request.tenant)
        if line.transfer.status != 'draft':
            messages.error(request, 'Only draft transfers can be modified.')
            return redirect('inventory:transfer_detail', pk=line.transfer_id)
        tr_pk = line.transfer_id
        line.delete()
        messages.success(request, 'Transfer line removed.')
        return redirect('inventory:transfer_detail', pk=tr_pk)

    def get(self, request, pk):
        line = get_object_or_404(models.StockTransferLine, pk=pk, tenant=request.tenant)
        return redirect('inventory:transfer_detail', pk=line.transfer_id)


class TransferShipView(TenantRequiredMixin, View):
    """draft -> in_transit: post production_out from source_bin per line."""

    def post(self, request, pk):
        tr = get_object_or_404(models.StockTransfer, pk=pk, tenant=request.tenant)
        if tr.status != 'draft':
            messages.error(request, 'Transfer is not in draft state.')
            return redirect('inventory:transfer_detail', pk=pk)
        if not tr.lines.exists():
            messages.error(request, 'Add at least one line before shipping.')
            return redirect('inventory:transfer_detail', pk=pk)
        try:
            with transaction.atomic():
                ok = _atomic_status_transition(
                    models.StockTransfer, pk, request.tenant,
                    from_states=('draft',), to_state='in_transit',
                )
                if not ok:
                    raise ValueError('Transfer is not in draft state.')
                for line in tr.lines.all():
                    post_movement(
                        tenant=request.tenant,
                        movement_type='issue',
                        product=line.product,
                        qty=line.qty,
                        from_bin=line.source_bin,
                        lot=line.lot,
                        serial=line.serial,
                        reason='transfer ship',
                        reference=tr.transfer_number,
                        posted_by=request.user,
                    )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('inventory:transfer_detail', pk=pk)
        messages.success(request, 'Transfer shipped.')
        return redirect('inventory:transfer_detail', pk=pk)


class TransferReceiveView(TenantRequiredMixin, View):
    """in_transit -> received: post receipt at destination bin per line.

    A `destination_bin` POST param can override per-line dest; otherwise the
    line's `destination_bin` is used. If neither is set, we error out.
    """

    def post(self, request, pk):
        tr = get_object_or_404(models.StockTransfer, pk=pk, tenant=request.tenant)
        if tr.status != 'in_transit':
            messages.error(request, 'Transfer is not in transit.')
            return redirect('inventory:transfer_detail', pk=pk)
        try:
            with transaction.atomic():
                ok = _atomic_status_transition(
                    models.StockTransfer, pk, request.tenant,
                    from_states=('in_transit',), to_state='received',
                    extra_fields={
                        'received_at': timezone.now(),
                        'received_by': request.user,
                    },
                )
                if not ok:
                    raise ValueError('Transfer is not in transit.')
                for line in tr.lines.all():
                    dest = line.destination_bin
                    if not dest:
                        raise ValueError(
                            f'Line for {line.product.sku} has no destination bin set.'
                        )
                    post_movement(
                        tenant=request.tenant,
                        movement_type='receipt',
                        product=line.product,
                        qty=line.qty,
                        to_bin=dest,
                        lot=line.lot,
                        serial=line.serial,
                        reason='transfer receive',
                        reference=tr.transfer_number,
                        posted_by=request.user,
                    )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('inventory:transfer_detail', pk=pk)
        messages.success(request, 'Transfer received.')
        return redirect('inventory:transfer_detail', pk=pk)


class TransferCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.StockTransfer, pk, request.tenant,
            from_states=('draft',), to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'Only draft transfers can be cancelled.')
        else:
            messages.success(request, 'Transfer cancelled.')
        return redirect('inventory:transfer_detail', pk=pk)


class TransferDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        tr = get_object_or_404(models.StockTransfer, pk=pk, tenant=request.tenant)
        if tr.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft / cancelled transfers can be deleted.')
            return redirect('inventory:transfer_detail', pk=pk)
        tr.delete()
        messages.success(request, 'Transfer deleted.')
        return redirect('inventory:transfer_list')

    def get(self, request, pk):
        return redirect('inventory:transfer_detail', pk=pk)


# Adjustments
class AdjustmentListView(TenantRequiredMixin, View):
    template_name = 'inventory/adjustments/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.StockAdjustment.objects.filter(tenant=t).select_related('warehouse')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(adjustment_number__icontains=q)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        reason = request.GET.get('reason', '')
        if reason:
            qs = qs.filter(reason=reason)
        page = _paginate(qs.order_by('-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'reason_filter': reason,
            'status_choices': models.StockAdjustment.STATUS_CHOICES,
            'reason_choices': models.StockAdjustment.REASON_CHOICES,
        })


class AdjustmentCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/adjustments/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.StockAdjustmentForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.StockAdjustmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Adjustment {obj.adjustment_number} created.')
            return redirect('inventory:adjustment_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class AdjustmentDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/adjustments/detail.html'

    def get(self, request, pk):
        adj = get_object_or_404(models.StockAdjustment, pk=pk, tenant=request.tenant)
        lines = adj.lines.select_related('bin', 'product', 'lot')
        line_form = forms.StockAdjustmentLineForm(tenant=request.tenant)
        return render(request, self.template_name, {
            'adj': adj, 'lines': lines, 'line_form': line_form,
        })


class AdjustmentLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        adj = get_object_or_404(models.StockAdjustment, pk=pk, tenant=request.tenant)
        if adj.status != 'draft':
            messages.error(request, 'Only draft adjustments can be modified.')
            return redirect('inventory:adjustment_detail', pk=pk)
        form = forms.StockAdjustmentLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.adjustment = adj
            line.save()
            messages.success(request, 'Adjustment line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('inventory:adjustment_detail', pk=pk)


class AdjustmentLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.StockAdjustmentLine, pk=pk, tenant=request.tenant)
        if line.adjustment.status != 'draft':
            messages.error(request, 'Only draft adjustments can be modified.')
            return redirect('inventory:adjustment_detail', pk=line.adjustment_id)
        adj_pk = line.adjustment_id
        line.delete()
        messages.success(request, 'Adjustment line removed.')
        return redirect('inventory:adjustment_detail', pk=adj_pk)

    def get(self, request, pk):
        line = get_object_or_404(models.StockAdjustmentLine, pk=pk, tenant=request.tenant)
        return redirect('inventory:adjustment_detail', pk=line.adjustment_id)


class AdjustmentPostView(TenantAdminRequiredMixin, View):
    """draft -> posted: emit one StockMovement(adjustment) per line."""

    def post(self, request, pk):
        adj = get_object_or_404(models.StockAdjustment, pk=pk, tenant=request.tenant)
        if adj.status != 'draft':
            messages.error(request, 'Adjustment is not in draft state.')
            return redirect('inventory:adjustment_detail', pk=pk)
        if not adj.lines.exists():
            messages.error(request, 'Add at least one line before posting.')
            return redirect('inventory:adjustment_detail', pk=pk)
        try:
            with transaction.atomic():
                ok = _atomic_status_transition(
                    models.StockAdjustment, pk, request.tenant,
                    from_states=('draft',), to_state='posted',
                    extra_fields={
                        'posted_at': timezone.now(),
                        'posted_by': request.user,
                    },
                )
                if not ok:
                    raise ValueError('Adjustment is not in draft state.')
                for line in adj.lines.all():
                    variance = line.actual_qty - line.system_qty
                    if variance == 0:
                        continue
                    if variance > 0:
                        post_movement(
                            tenant=request.tenant,
                            movement_type='adjustment',
                            product=line.product, qty=variance, to_bin=line.bin,
                            lot=line.lot, serial=line.serial,
                            reason=f'adj:{adj.reason}', reference=adj.adjustment_number,
                            posted_by=request.user,
                        )
                    else:
                        post_movement(
                            tenant=request.tenant,
                            movement_type='adjustment',
                            product=line.product, qty=-variance, from_bin=line.bin,
                            lot=line.lot, serial=line.serial,
                            reason=f'adj:{adj.reason}', reference=adj.adjustment_number,
                            posted_by=request.user,
                        )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('inventory:adjustment_detail', pk=pk)
        messages.success(request, 'Adjustment posted.')
        return redirect('inventory:adjustment_detail', pk=pk)


class AdjustmentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        adj = get_object_or_404(models.StockAdjustment, pk=pk, tenant=request.tenant)
        if adj.status != 'draft':
            messages.error(request, 'Only draft adjustments can be deleted.')
            return redirect('inventory:adjustment_detail', pk=pk)
        adj.delete()
        messages.success(request, 'Adjustment deleted.')
        return redirect('inventory:adjustment_list')

    def get(self, request, pk):
        return redirect('inventory:adjustment_detail', pk=pk)


# ============================================================================
# 8.4  CYCLE COUNTING
# ============================================================================

class CycleCountPlanListView(TenantRequiredMixin, View):
    template_name = 'inventory/cycle_count_plans/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.CycleCountPlan.objects.filter(tenant=t).select_related('warehouse')
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
            'frequency_choices': models.CycleCountPlan.FREQUENCY_CHOICES,
        })


class CycleCountPlanCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/cycle_count_plans/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CycleCountPlanForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.CycleCountPlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Plan created.')
            return redirect('inventory:cc_plan_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class CycleCountPlanEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/cycle_count_plans/form.html'

    def get(self, request, pk):
        plan = get_object_or_404(models.CycleCountPlan, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CycleCountPlanForm(instance=plan, tenant=request.tenant),
            'plan': plan, 'is_create': False,
        })

    def post(self, request, pk):
        plan = get_object_or_404(models.CycleCountPlan, pk=pk, tenant=request.tenant)
        form = forms.CycleCountPlanForm(request.POST, instance=plan, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Plan updated.')
            return redirect('inventory:cc_plan_list')
        return render(request, self.template_name, {'form': form, 'plan': plan, 'is_create': False})


class CycleCountPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(models.CycleCountPlan, pk=pk, tenant=request.tenant)
        plan.delete()
        messages.success(request, 'Plan deleted.')
        return redirect('inventory:cc_plan_list')

    def get(self, request, pk):
        return redirect('inventory:cc_plan_list')


class CycleCountSheetListView(TenantRequiredMixin, View):
    template_name = 'inventory/cycle_count_sheets/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.CycleCountSheet.objects.filter(tenant=t).select_related('warehouse', 'plan')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(sheet_number__icontains=q)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-count_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.CycleCountSheet.STATUS_CHOICES,
        })


class CycleCountSheetCreateView(TenantRequiredMixin, View):
    template_name = 'inventory/cycle_count_sheets/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CycleCountSheetForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.CycleCountSheetForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.counted_by = obj.counted_by or request.user
            obj.save()
            messages.success(request, f'Sheet {obj.sheet_number} created.')
            return redirect('inventory:cc_sheet_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class CycleCountSheetDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/cycle_count_sheets/detail.html'

    def get(self, request, pk):
        sheet = get_object_or_404(models.CycleCountSheet, pk=pk, tenant=request.tenant)
        lines = sheet.lines.select_related('bin', 'product', 'lot')
        line_form = forms.CycleCountLineForm(tenant=request.tenant)
        return render(request, self.template_name, {
            'sheet': sheet, 'lines': lines, 'line_form': line_form,
        })


class CycleCountLineCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        sheet = get_object_or_404(models.CycleCountSheet, pk=pk, tenant=request.tenant)
        if sheet.status not in ('draft', 'counting'):
            messages.error(request, 'Lines can only be added while drafting or counting.')
            return redirect('inventory:cc_sheet_detail', pk=pk)
        form = forms.CycleCountLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.sheet = sheet
            if line.counted_qty is not None:
                _, _, recount = compute_variance(line.system_qty, line.counted_qty)
                line.recount_required = recount
            line.save()
            messages.success(request, 'Line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('inventory:cc_sheet_detail', pk=pk)


class CycleCountLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.CycleCountLine, pk=pk, tenant=request.tenant)
        if line.sheet.status not in ('draft', 'counting'):
            messages.error(request, 'Sheet is no longer editable.')
            return redirect('inventory:cc_sheet_detail', pk=line.sheet_id)
        sheet_pk = line.sheet_id
        line.delete()
        messages.success(request, 'Line removed.')
        return redirect('inventory:cc_sheet_detail', pk=sheet_pk)

    def get(self, request, pk):
        line = get_object_or_404(models.CycleCountLine, pk=pk, tenant=request.tenant)
        return redirect('inventory:cc_sheet_detail', pk=line.sheet_id)


class CycleCountStartView(TenantRequiredMixin, View):
    """draft -> counting."""

    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.CycleCountSheet, pk, request.tenant,
            from_states=('draft',), to_state='counting',
        )
        if not ok:
            messages.error(request, 'Sheet is not in draft state.')
        else:
            messages.success(request, 'Counting started.')
        return redirect('inventory:cc_sheet_detail', pk=pk)


class CycleCountReconcileView(TenantAdminRequiredMixin, View):
    """counting -> reconciled: post StockMovement(cycle_count) for variances."""

    def post(self, request, pk):
        sheet = get_object_or_404(models.CycleCountSheet, pk=pk, tenant=request.tenant)
        if sheet.status != 'counting':
            messages.error(request, 'Sheet is not in counting state.')
            return redirect('inventory:cc_sheet_detail', pk=pk)
        try:
            with transaction.atomic():
                ok = _atomic_status_transition(
                    models.CycleCountSheet, pk, request.tenant,
                    from_states=('counting',), to_state='reconciled',
                    extra_fields={
                        'reconciled_at': timezone.now(),
                        'reconciled_by': request.user,
                    },
                )
                if not ok:
                    raise ValueError('Sheet is not in counting state.')
                for line in sheet.lines.all():
                    if line.counted_qty is None:
                        continue
                    variance = line.counted_qty - line.system_qty
                    if variance == 0:
                        continue
                    if variance > 0:
                        post_movement(
                            tenant=request.tenant,
                            movement_type='cycle_count',
                            product=line.product, qty=variance, to_bin=line.bin,
                            lot=line.lot, serial=line.serial,
                            reason='cycle count variance',
                            reference=sheet.sheet_number,
                            posted_by=request.user,
                        )
                    else:
                        post_movement(
                            tenant=request.tenant,
                            movement_type='cycle_count',
                            product=line.product, qty=-variance, from_bin=line.bin,
                            lot=line.lot, serial=line.serial,
                            reason='cycle count variance',
                            reference=sheet.sheet_number,
                            posted_by=request.user,
                        )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('inventory:cc_sheet_detail', pk=pk)
        messages.success(request, 'Sheet reconciled.')
        return redirect('inventory:cc_sheet_detail', pk=pk)


class CycleCountSheetDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        sheet = get_object_or_404(models.CycleCountSheet, pk=pk, tenant=request.tenant)
        if sheet.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft / cancelled sheets can be deleted.')
            return redirect('inventory:cc_sheet_detail', pk=pk)
        sheet.delete()
        messages.success(request, 'Sheet deleted.')
        return redirect('inventory:cc_sheet_list')

    def get(self, request, pk):
        return redirect('inventory:cc_sheet_detail', pk=pk)


# ============================================================================
# 8.5  LOTS / SERIALS
# ============================================================================

class LotListView(TenantRequiredMixin, View):
    template_name = 'inventory/lots/list.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        qs = models.Lot.objects.filter(tenant=t).select_related('product')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(lot_number__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(supplier_name__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        expiring = request.GET.get('expiring', '')
        if expiring == 'soon':
            qs = qs.filter(
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=30),
                expiry_date__gte=today,
            )
        elif expiring == 'expired':
            qs = qs.filter(expiry_date__isnull=False, expiry_date__lt=today)
        page = _paginate(qs.order_by('expiry_date', 'lot_number'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'expiring_filter': expiring,
            'status_choices': models.Lot.STATUS_CHOICES,
            'today': today,
        })


class LotCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/lots/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.LotForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.LotForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Lot created.')
            return redirect('inventory:lot_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class LotDetailView(TenantRequiredMixin, View):
    template_name = 'inventory/lots/detail.html'

    def get(self, request, pk):
        lot = get_object_or_404(models.Lot, pk=pk, tenant=request.tenant)
        stock_items = lot.stock_items.select_related('bin__zone__warehouse')
        movements = lot.movements.select_related('product').order_by('-posted_at')[:20]
        return render(request, self.template_name, {
            'lot': lot, 'stock_items': stock_items, 'movements': movements,
        })


class LotEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/lots/form.html'

    def get(self, request, pk):
        lot = get_object_or_404(models.Lot, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.LotForm(instance=lot, tenant=request.tenant),
            'lot': lot, 'is_create': False,
        })

    def post(self, request, pk):
        lot = get_object_or_404(models.Lot, pk=pk, tenant=request.tenant)
        form = forms.LotForm(request.POST, instance=lot, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Lot updated.')
            return redirect('inventory:lot_detail', pk=lot.pk)
        return render(request, self.template_name, {'form': form, 'lot': lot, 'is_create': False})


class LotDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        lot = get_object_or_404(models.Lot, pk=pk, tenant=request.tenant)
        try:
            lot.delete()
            messages.success(request, 'Lot deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete lot: {e}')
        return redirect('inventory:lot_list')

    def get(self, request, pk):
        return redirect('inventory:lot_detail', pk=pk)


class SerialListView(TenantRequiredMixin, View):
    template_name = 'inventory/serials/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.SerialNumber.objects.filter(tenant=t).select_related('product', 'lot')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(serial_number__icontains=q) | Q(product__sku__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('product__sku', 'serial_number'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.SerialNumber.STATUS_CHOICES,
        })


class SerialCreateView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/serials/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SerialNumberForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.SerialNumberForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Serial number created.')
            return redirect('inventory:serial_list')
        return render(request, self.template_name, {'form': form, 'is_create': True})


class SerialEditView(TenantAdminRequiredMixin, View):
    template_name = 'inventory/serials/form.html'

    def get(self, request, pk):
        sn = get_object_or_404(models.SerialNumber, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.SerialNumberForm(instance=sn, tenant=request.tenant),
            'sn': sn, 'is_create': False,
        })

    def post(self, request, pk):
        sn = get_object_or_404(models.SerialNumber, pk=pk, tenant=request.tenant)
        form = forms.SerialNumberForm(request.POST, instance=sn, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Serial number updated.')
            return redirect('inventory:serial_list')
        return render(request, self.template_name, {'form': form, 'sn': sn, 'is_create': False})


class SerialDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        sn = get_object_or_404(models.SerialNumber, pk=pk, tenant=request.tenant)
        try:
            sn.delete()
            messages.success(request, 'Serial number deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete serial number: {e}')
        return redirect('inventory:serial_list')

    def get(self, request, pk):
        return redirect('inventory:serial_list')
