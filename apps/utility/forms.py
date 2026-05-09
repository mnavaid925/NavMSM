"""Module 14 - Energy & Utility Management ModelForms.

Honors:
    - Lesson L-01: tenant-scoped forms enforce their own (tenant, ...) clean().
    - Lesson L-02: every Decimal field carries explicit MinValueValidator
      (declared on the model; ModelForm picks them up).
    - Lesson L-14: per-workflow forms enforce per-transition required fields.
    - L-19 (this module): file uploads validate extension + content_type +
      size cap so the importer can't be abused as a file-storage primitive.
"""
import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from . import models


_CSV_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB cap on bulk CSV imports.
_CSV_ALLOWED_CONTENT_TYPES = {
    'text/csv',
    'application/csv',
    'application/vnd.ms-excel',
    'text/plain',  # some browsers send this for .csv
    'application/octet-stream',  # fallback some browsers send
}
_CURRENCY_RE = re.compile(r'^[A-Z]{3}$')


class TenantForm(forms.ModelForm):
    """Stash request.tenant on self._tenant for clean() use (Lesson L-01)."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 14.1  Utility Meter Integration
# ============================================================================

class UtilityTypeForm(TenantForm):
    class Meta:
        model = models.UtilityType
        fields = ['code', 'name', 'unit_of_measure', 'cost_driver', 'description', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.cost.models import CostDriver
            self.fields['cost_driver'].queryset = (
                CostDriver.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.UtilityType.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A utility type with this code already exists.')
        return data


class UtilityMeterForm(TenantForm):
    class Meta:
        model = models.UtilityMeter
        fields = [
            'utility_type', 'name', 'location', 'parent_meter', 'cost_center',
            'asset', 'installed_at', 'last_calibrated_at', 'multiplier',
            'is_active', 'notes',
        ]
        widgets = {
            'installed_at': forms.DateInput(attrs={'type': 'date'}),
            'last_calibrated_at': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.inventory.models import Warehouse
            from apps.labor.models import CostCenter
            from apps.eam.models import Asset
            self.fields['utility_type'].queryset = (
                models.UtilityType.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            self.fields['parent_meter'].queryset = (
                models.UtilityMeter.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            if self.instance.pk:
                self.fields['parent_meter'].queryset = (
                    self.fields['parent_meter'].queryset.exclude(pk=self.instance.pk)
                )
            self.fields['location'].queryset = Warehouse.all_objects.filter(tenant=self._tenant)
            self.fields['cost_center'].queryset = CostCenter.all_objects.filter(tenant=self._tenant)
            self.fields['asset'].queryset = Asset.all_objects.filter(tenant=self._tenant)

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        utility_type = data.get('utility_type')
        name = data.get('name')
        if utility_type and name:
            qs = models.UtilityMeter.all_objects.filter(
                tenant=self._tenant, utility_type=utility_type, name=name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A meter with this name already exists for this utility type.')
        return data


class UtilityConsumptionForm(TenantForm):
    class Meta:
        model = models.UtilityConsumption
        fields = [
            'meter', 'period_start', 'period_end',
            'start_reading', 'end_reading', 'unit_cost', 'source', 'notes',
        ]
        widgets = {
            'period_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'period_end': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['meter'].queryset = (
                models.UtilityMeter.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        ps, pe = data.get('period_start'), data.get('period_end')
        if ps and pe and pe <= ps:
            self.add_error('period_end', 'Must be after period start.')
        sr, er = data.get('start_reading'), data.get('end_reading')
        if sr is not None and er is not None and er < sr:
            self.add_error('end_reading', 'End reading must be greater than or equal to start reading.')
        return data


class UtilityConsumptionImportForm(forms.Form):
    """CSV bulk import (admin-only).

    D-03 hardening:
        * Extension allow-list (.csv) via FileExtensionValidator.
        * 5 MiB hard size cap (independent of Django's
          DATA_UPLOAD_MAX_MEMORY_SIZE which only governs in-memory parse).
        * Content-type sniff against a small allow-list — browsers send a
          handful of legal types for CSV; we reject everything else.
        * First-line shape check: reject obvious non-CSV (PE / ELF / ZIP
          magic bytes) before handing the file to ``csv.DictReader``.
    """

    meter = forms.ModelChoiceField(queryset=models.UtilityMeter.all_objects.none())
    csv_file = forms.FileField(
        help_text='CSV columns: period_start,period_end,start_reading,end_reading,unit_cost (max 5 MB)',
        validators=[FileExtensionValidator(allowed_extensions=['csv'])],
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['meter'].queryset = (
                models.UtilityMeter.all_objects.filter(tenant=tenant, is_active=True)
            )

    def clean_csv_file(self):
        f = self.cleaned_data.get('csv_file')
        if f is None:
            return f
        if f.size > _CSV_MAX_BYTES:
            raise ValidationError(
                f'File too large: {f.size} bytes > {_CSV_MAX_BYTES} bytes (5 MiB cap).',
            )
        ctype = (getattr(f, 'content_type', '') or '').lower()
        if ctype and ctype not in _CSV_ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f'Unsupported content-type: {ctype}. Expected text/csv.',
            )
        # Magic-byte / binary sniff: read the first chunk, peek for known
        # binary signatures, then rewind. csv.DictReader needs the cursor
        # at the beginning.
        f.seek(0)
        head = f.read(8)
        f.seek(0)
        bad_signatures = (
            b'MZ',          # PE / DOS executable
            b'\x7fELF',     # Linux ELF
            b'PK\x03\x04',  # ZIP / Office Open XML
            b'\x89PNG',     # PNG image
            b'%PDF',        # PDF
            b'\xff\xd8\xff',  # JPEG
        )
        for sig in bad_signatures:
            if head.startswith(sig):
                raise ValidationError(
                    'File contents do not look like a CSV (binary signature '
                    'detected).',
                )
        return f


# ============================================================================
# 14.2  Energy Cost Allocation
# ============================================================================

class UtilityTariffForm(TenantForm):
    class Meta:
        model = models.UtilityTariff
        fields = [
            'utility_type', 'name', 'effective_from', 'effective_to',
            'flat_rate', 'currency', 'is_active', 'notes',
        ]
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['utility_type'].queryset = (
                models.UtilityType.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        eff_from, eff_to = data.get('effective_from'), data.get('effective_to')
        if eff_from and eff_to and eff_to < eff_from:
            self.add_error('effective_to', 'Must be on or after Effective From.')
        # D-05: ISO-4217 shape (3 upper-case letters). Length-only check
        # let strings like "ZZZ" / "999" / lower-case pass through.
        currency = data.get('currency', '')
        if currency and not _CURRENCY_RE.match(currency):
            self.add_error(
                'currency',
                'Must be a 3-letter upper-case ISO 4217 code (e.g. USD, EUR).',
            )
        return data


class TOURateBandForm(forms.ModelForm):
    """No tenant scoping — band is owned by tariff (which is tenant-scoped).

    The view passes ``tariff=<UtilityTariff>`` via the form ``initial`` so
    ``clean()`` can pre-check the (tariff, band_type, day_of_week, start_time)
    unique_together (D-04) — duplicate POST otherwise reaches the DB and the
    raw IntegrityError text is surfaced to the user.
    """

    class Meta:
        model = models.TOURateBand
        fields = ['band_type', 'day_of_week', 'start_time', 'end_time', 'rate', 'notes']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, tariff=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tariff = tariff

    def clean(self):
        data = super().clean()
        st, et = data.get('start_time'), data.get('end_time')
        if st and et and et <= st:
            self.add_error('end_time', 'Must be after start time.')
        # D-04: pre-check the unique_together so we don't echo a raw
        # IntegrityError. The view passes the parent tariff into __init__.
        if self._tariff is not None:
            band_type = data.get('band_type')
            day_of_week = data.get('day_of_week')
            if band_type and day_of_week and st:
                qs = models.TOURateBand.all_objects.filter(
                    tariff=self._tariff,
                    band_type=band_type,
                    day_of_week=day_of_week,
                    start_time=st,
                )
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    self.add_error(
                        'start_time',
                        'A band of this type already exists for this day at '
                        'this start time.',
                    )
        return data


class UtilityAllocationForm(TenantForm):
    class Meta:
        model = models.UtilityAllocation
        fields = [
            'period', 'meter', 'target_cost_center', 'target_product',
            'target_production_order', 'allocation_method', 'share_pct',
            'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.cost.models import AccountingPeriod
            from apps.labor.models import CostCenter
            from apps.plm.models import Product
            from apps.pps.models import ProductionOrder
            self.fields['period'].queryset = AccountingPeriod.all_objects.filter(tenant=self._tenant)
            self.fields['meter'].queryset = (
                models.UtilityMeter.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            self.fields['target_cost_center'].queryset = CostCenter.all_objects.filter(tenant=self._tenant)
            self.fields['target_product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['target_production_order'].queryset = (
                ProductionOrder.all_objects.filter(tenant=self._tenant)
            )

    def clean(self):
        data = super().clean()
        cc = data.get('target_cost_center')
        prod = data.get('target_product')
        po = data.get('target_production_order')
        targets = [t for t in (cc, prod, po) if t is not None]
        if not targets:
            raise ValidationError(
                'Pick at least one target: cost center, product, or production order.'
            )
        share = data.get('share_pct') or Decimal('0')
        if share <= 0 or share > 100:
            self.add_error('share_pct', 'Share must be greater than 0 and at most 100.')
        return data


class UtilityAllocationReverseForm(forms.Form):
    """L-14: reversal requires a non-empty reason."""

    reversal_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )

    def clean_reversal_reason(self):
        v = self.cleaned_data.get('reversal_reason', '').strip()
        if not v:
            raise ValidationError('Reversal reason is required.')
        return v


class UtilityAllocationPostForm(forms.Form):
    """Form for the POST /allocations/post/ orchestrator action."""

    period = forms.ModelChoiceField(queryset=None)
    meter = forms.ModelChoiceField(queryset=None)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            from apps.cost.models import AccountingPeriod
            self.fields['period'].queryset = (
                AccountingPeriod.all_objects.filter(tenant=tenant, status='open')
            )
            self.fields['meter'].queryset = (
                models.UtilityMeter.all_objects.filter(tenant=tenant, is_active=True)
            )


# ============================================================================
# 14.3  Peak Demand Management
# ============================================================================

class DemandResponseEventForm(TenantForm):
    class Meta:
        model = models.DemandResponseEvent
        fields = [
            'utility_type', 'event_type', 'start_at', 'end_at',
            'target_reduction_pct', 'incentive_amount', 'source', 'notes',
        ]
        widgets = {
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['utility_type'].queryset = (
                models.UtilityType.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        sa, ea = data.get('start_at'), data.get('end_at')
        if sa and ea and ea <= sa:
            self.add_error('end_at', 'End must be after start.')
        return data


class DemandResponseEventCancelForm(forms.Form):
    """L-14: cancellation requires a reason."""

    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )

    def clean_cancellation_reason(self):
        v = self.cleaned_data.get('cancellation_reason', '').strip()
        if not v:
            raise ValidationError('Cancellation reason is required.')
        return v


class PeakShavingScanForm(forms.Form):
    horizon_days = forms.IntegerField(min_value=1, max_value=90, initial=14)


class PeakShavingDismissForm(forms.Form):
    """L-14: dismiss requires a reason."""

    dismiss_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )

    def clean_dismiss_reason(self):
        v = self.cleaned_data.get('dismiss_reason', '').strip()
        if not v:
            raise ValidationError('Dismiss reason is required.')
        return v


# ============================================================================
# 14.4  Carbon & Sustainability Reporting
# ============================================================================

class CarbonEmissionReverseForm(forms.Form):
    """L-14: a reversal needs a typed reason.

    Mirrors ``UtilityAllocationReverseForm``. D-08: gives admins a UI path to
    null-out a manual or mis-emitted CarbonEmission row without dropping to
    ``manage.py shell``.
    """

    reversal_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )

    def clean_reversal_reason(self):
        v = self.cleaned_data.get('reversal_reason', '').strip()
        if not v:
            raise ValidationError('Reversal reason is required.')
        return v


class EmissionFactorForm(TenantForm):
    class Meta:
        model = models.EmissionFactor
        fields = [
            'source_type', 'scope', 'region', 'factor', 'unit_of_measure',
            'effective_from', 'effective_to', 'source_reference',
            'is_active', 'notes',
        ]
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        source_type = data.get('source_type')
        scope = data.get('scope')
        region = data.get('region', '')
        eff_from = data.get('effective_from')
        if source_type and scope and eff_from:
            qs = models.EmissionFactor.all_objects.filter(
                tenant=self._tenant, source_type=source_type,
                scope=scope, region=region, effective_from=eff_from,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('source_type', 'A factor with this source/scope/region/effective_from already exists.')
        eff_to = data.get('effective_to')
        if eff_from and eff_to and eff_to < eff_from:
            self.add_error('effective_to', 'Must be on or after Effective From.')
        return data


# ============================================================================
# 14.5  Utility Benchmarking
# ============================================================================

class BenchmarkSnapshotGenerateForm(forms.Form):
    period = forms.ModelChoiceField(queryset=None)
    plant_label = forms.CharField(max_length=60, initial='main_factory')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            from apps.cost.models import AccountingPeriod
            self.fields['period'].queryset = AccountingPeriod.all_objects.filter(tenant=tenant)


class BenchmarkComparisonForm(TenantForm):
    class Meta:
        model = models.BenchmarkComparison
        fields = ['comparison_type', 'from_snapshot', 'to_snapshot', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            qs = (
                models.BenchmarkSnapshot.all_objects
                .filter(tenant=self._tenant)
                .order_by('-period__start_date', 'plant_label')
            )
            self.fields['from_snapshot'].queryset = qs
            self.fields['to_snapshot'].queryset = qs

    def clean(self):
        data = super().clean()
        f, t = data.get('from_snapshot'), data.get('to_snapshot')
        if f and t and f.pk == t.pk:
            self.add_error('to_snapshot', 'From and To snapshots must differ.')
        return data
