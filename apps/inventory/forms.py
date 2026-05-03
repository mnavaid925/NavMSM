"""ModelForms for Module 8 — Inventory & Warehouse Management.

Per Lesson L-01, every form whose Meta.fields excludes ``tenant`` performs
its own duplicate check inside ``clean()`` — Django's default
``validate_unique`` cannot enforce a ``unique_together`` set that touches a
field the form does not expose.
"""
from decimal import Decimal

from django import forms

from apps.plm.models import Product

from . import models


class TenantScopedFormMixin:
    """Pull `tenant` out of kwargs and stash it on the instance."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ---------------- 8.1  Multi-Warehouse Inventory ----------------

class WarehouseForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.Warehouse
        fields = ('code', 'name', 'address', 'manager', 'is_default', 'is_active')
        widgets = {'address': forms.Textarea(attrs={'rows': 2})}

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get('code')
        if self._tenant and code:
            qs = models.Warehouse.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A warehouse with this code already exists.')
        return cleaned


class WarehouseZoneForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.WarehouseZone
        fields = ('warehouse', 'code', 'name', 'zone_type', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['warehouse'].queryset = models.Warehouse.all_objects.filter(
                tenant=self._tenant
            )

    def clean(self):
        cleaned = super().clean()
        warehouse = cleaned.get('warehouse')
        code = cleaned.get('code')
        if warehouse and code:
            qs = models.WarehouseZone.all_objects.filter(warehouse=warehouse, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A zone with this code already exists in this warehouse.')
        return cleaned


class StorageBinForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StorageBin
        fields = ('zone', 'code', 'bin_type', 'capacity', 'abc_class', 'is_blocked', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['zone'].queryset = models.WarehouseZone.all_objects.filter(
                tenant=self._tenant
            ).select_related('warehouse')

    def clean(self):
        cleaned = super().clean()
        zone = cleaned.get('zone')
        code = cleaned.get('code')
        if zone and code:
            qs = models.StorageBin.all_objects.filter(zone=zone, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A bin with this code already exists in this zone.')
        return cleaned


# ---------------- 8.2  GRN & Putaway ----------------

class GoodsReceiptNoteForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.GoodsReceiptNote
        fields = (
            'warehouse', 'supplier_name', 'po_reference', 'incoming_inspection',
            'received_date', 'notes',
        )
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['warehouse'].queryset = models.Warehouse.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            from apps.qms.models import IncomingInspection
            self.fields['incoming_inspection'].queryset = (
                IncomingInspection.all_objects.filter(tenant=self._tenant)
            )
            self.fields['incoming_inspection'].required = False


class GRNLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.GRNLine
        fields = (
            'product', 'expected_qty', 'received_qty',
            'lot_number', 'serial_numbers', 'receiving_zone', 'notes',
        )
        widgets = {
            'serial_numbers': forms.Textarea(attrs={'rows': 2, 'placeholder': 'SN001, SN002, ...'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')
            self.fields['receiving_zone'].queryset = models.WarehouseZone.all_objects.filter(
                tenant=self._tenant, zone_type__in=('receiving', 'storage'),
            ).select_related('warehouse')


# ---------------- 8.3  Movements / Transfers / Adjustments ----------------

class StockMovementForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StockMovement
        fields = (
            'movement_type', 'product', 'qty',
            'from_bin', 'to_bin', 'lot', 'serial',
            'reason', 'reference', 'notes',
        )
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['from_bin'].queryset = models.StorageBin.all_objects.filter(tenant=self._tenant)
            self.fields['to_bin'].queryset = models.StorageBin.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].queryset = models.Lot.all_objects.filter(tenant=self._tenant)
            self.fields['serial'].queryset = models.SerialNumber.all_objects.filter(tenant=self._tenant)
            self.fields['from_bin'].required = False
            self.fields['to_bin'].required = False
            self.fields['lot'].required = False
            self.fields['serial'].required = False

    def clean(self):
        cleaned = super().clean()
        movement_type = cleaned.get('movement_type')
        from_bin = cleaned.get('from_bin')
        to_bin = cleaned.get('to_bin')
        if movement_type in ('receipt', 'production_in') and not to_bin:
            self.add_error('to_bin', 'Required for receipts and production_in.')
        if movement_type in ('issue', 'production_out', 'scrap') and not from_bin:
            self.add_error('from_bin', 'Required for issues / production_out / scrap.')
        if movement_type == 'transfer' and (not from_bin or not to_bin):
            raise forms.ValidationError('Transfers require both from_bin and to_bin.')
        if movement_type in ('adjustment', 'cycle_count') and bool(from_bin) == bool(to_bin):
            raise forms.ValidationError(
                'Adjustment / cycle count requires exactly one of from_bin / to_bin.'
            )
        return cleaned


class StockTransferForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StockTransfer
        fields = (
            'source_warehouse', 'destination_warehouse',
            'requested_date', 'expected_arrival', 'notes',
        )
        widgets = {
            'requested_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_arrival': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            wh_qs = models.Warehouse.all_objects.filter(tenant=self._tenant, is_active=True)
            self.fields['source_warehouse'].queryset = wh_qs
            self.fields['destination_warehouse'].queryset = wh_qs

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get('source_warehouse')
        dst = cleaned.get('destination_warehouse')
        if src and dst and src.pk == dst.pk:
            raise forms.ValidationError('Source and destination warehouses must differ.')
        return cleaned


class StockTransferLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StockTransferLine
        fields = ('product', 'qty', 'source_bin', 'destination_bin', 'lot', 'serial')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            bins_qs = models.StorageBin.all_objects.filter(tenant=self._tenant)
            self.fields['source_bin'].queryset = bins_qs
            self.fields['destination_bin'].queryset = bins_qs
            self.fields['destination_bin'].required = False
            self.fields['lot'].queryset = models.Lot.all_objects.filter(tenant=self._tenant)
            self.fields['serial'].queryset = models.SerialNumber.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].required = False
            self.fields['serial'].required = False


class StockAdjustmentForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StockAdjustment
        fields = ('warehouse', 'reason', 'reason_notes')
        widgets = {'reason_notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['warehouse'].queryset = models.Warehouse.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean_reason_notes(self):
        notes = (self.cleaned_data.get('reason_notes') or '').strip()
        if not notes:
            raise forms.ValidationError('Reason notes are required for stock adjustments.')
        return notes


class StockAdjustmentLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.StockAdjustmentLine
        fields = ('bin', 'product', 'lot', 'serial', 'system_qty', 'actual_qty')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['bin'].queryset = models.StorageBin.all_objects.filter(tenant=self._tenant)
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].queryset = models.Lot.all_objects.filter(tenant=self._tenant)
            self.fields['serial'].queryset = models.SerialNumber.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].required = False
            self.fields['serial'].required = False


# ---------------- 8.4  Cycle Counting ----------------

class CycleCountPlanForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.CycleCountPlan
        fields = ('name', 'warehouse', 'frequency', 'abc_class_filter', 'is_active', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['warehouse'].queryset = models.Warehouse.all_objects.filter(
                tenant=self._tenant
            )

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        if self._tenant and name:
            qs = models.CycleCountPlan.all_objects.filter(tenant=self._tenant, name=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A plan with this name already exists.')
        return cleaned


class CycleCountSheetForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.CycleCountSheet
        fields = ('plan', 'warehouse', 'count_date', 'counted_by', 'notes')
        widgets = {
            'count_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['plan'].queryset = models.CycleCountPlan.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['warehouse'].queryset = models.Warehouse.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['plan'].required = False


class CycleCountLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.CycleCountLine
        fields = (
            'bin', 'product', 'lot', 'serial',
            'system_qty', 'counted_qty', 'recount_required', 'notes',
        )
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['bin'].queryset = models.StorageBin.all_objects.filter(tenant=self._tenant)
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].queryset = models.Lot.all_objects.filter(tenant=self._tenant)
            self.fields['serial'].queryset = models.SerialNumber.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].required = False
            self.fields['serial'].required = False


# ---------------- 8.5  Lot / Serial ----------------

class LotForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.Lot
        fields = (
            'product', 'lot_number', 'manufactured_date', 'expiry_date',
            'supplier_name', 'coa_reference', 'status', 'notes',
        )
        widgets = {
            'manufactured_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        lot_number = cleaned.get('lot_number')
        if self._tenant and product and lot_number:
            qs = models.Lot.all_objects.filter(
                tenant=self._tenant, product=product, lot_number=lot_number,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('lot_number', 'A lot with this number already exists for this product.')
        mfd = cleaned.get('manufactured_date')
        exp = cleaned.get('expiry_date')
        if mfd and exp and exp < mfd:
            self.add_error('expiry_date', 'Expiry date cannot be before manufactured date.')
        return cleaned


class SerialNumberForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.SerialNumber
        fields = ('product', 'serial_number', 'lot', 'status', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].queryset = models.Lot.all_objects.filter(tenant=self._tenant)
            self.fields['lot'].required = False

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        sn = cleaned.get('serial_number')
        if self._tenant and product and sn:
            qs = models.SerialNumber.all_objects.filter(
                tenant=self._tenant, product=product, serial_number=sn,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('serial_number', 'A serial number with this value already exists for this product.')
        return cleaned
