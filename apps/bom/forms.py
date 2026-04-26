"""ModelForms for BOM CRUD."""
from django import forms

from apps.plm.models import Product

from .models import (
    AlternateMaterial, BillOfMaterials, BOMCostRollup, BOMLine, BOMRevision,
    BOMSyncMap, CostElement, SubstitutionRule,
)


# ---------------- BOM header & lines ----------------

class BillOfMaterialsForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = (
            'name', 'product', 'bom_type', 'version', 'revision',
            'description', 'is_default', 'effective_from', 'effective_to',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')


class BOMLineForm(forms.ModelForm):
    class Meta:
        model = BOMLine
        fields = (
            'parent_line', 'sequence', 'component', 'quantity', 'unit_of_measure',
            'scrap_percent', 'is_phantom', 'reference_designator', 'notes',
        )
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, bom=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['component'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
        if bom is not None:
            qs = BOMLine.objects.filter(bom=bom)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['parent_line'].queryset = qs
            self.fields['parent_line'].required = False
        else:
            self.fields['parent_line'].queryset = BOMLine.objects.none()
            self.fields['parent_line'].required = False


class BOMRevisionForm(forms.ModelForm):
    class Meta:
        model = BOMRevision
        fields = ('version', 'revision', 'revision_type', 'change_summary', 'effective_from')
        widgets = {
            'change_summary': forms.Textarea(attrs={'rows': 3}),
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
        }


# ---------------- Alternates & substitution rules ----------------

class AlternateMaterialForm(forms.ModelForm):
    class Meta:
        model = AlternateMaterial
        fields = (
            'alternate_component', 'priority', 'substitution_type',
            'usage_rule', 'notes',
        )
        widgets = {
            'usage_rule': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, exclude_component=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Product.objects.none()
        if tenant is not None:
            qs = Product.objects.filter(tenant=tenant).exclude(status='obsolete')
            if exclude_component is not None:
                qs = qs.exclude(pk=exclude_component.pk)
        self.fields['alternate_component'].queryset = qs


class SubstitutionRuleForm(forms.ModelForm):
    class Meta:
        model = SubstitutionRule
        fields = (
            'name', 'description', 'original_component', 'substitute_component',
            'condition_text', 'requires_approval', 'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'condition_text': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            qs = Product.objects.filter(tenant=tenant).exclude(status='obsolete')
            self.fields['original_component'].queryset = qs
            self.fields['substitute_component'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        original = cleaned.get('original_component')
        sub = cleaned.get('substitute_component')
        if original and sub and original.pk == sub.pk:
            self.add_error('substitute_component', 'Substitute must differ from the original component.')
        return cleaned


# ---------------- Cost elements ----------------

class CostElementForm(forms.ModelForm):
    class Meta:
        model = CostElement
        fields = (
            'product', 'cost_type', 'unit_cost', 'currency',
            'effective_date', 'source', 'notes',
        )
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)


# ---------------- Sync map ----------------

class BOMSyncMapForm(forms.ModelForm):
    class Meta:
        model = BOMSyncMap
        fields = ('source_bom', 'target_bom', 'drift_summary')
        widgets = {'drift_summary': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            qs = BillOfMaterials.objects.filter(tenant=tenant)
            self.fields['source_bom'].queryset = qs
            self.fields['target_bom'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get('source_bom')
        tgt = cleaned.get('target_bom')
        if src and tgt:
            if src.pk == tgt.pk:
                self.add_error('target_bom', 'Source and target BOM must be different.')
            elif src.bom_type == tgt.bom_type:
                self.add_error('target_bom',
                               'Source and target must have different BOM types (e.g. EBOM → MBOM).')
        return cleaned
