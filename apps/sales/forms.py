"""Forms for Module 17 - Sales (17.1 portion)."""
from django import forms

from .models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    PriceList,
    PriceListItem,
)


class CustomerCategoryForm(forms.ModelForm):
    class Meta:
        model = CustomerCategory
        fields = ('name', 'code', 'parent', 'description', 'is_active')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['parent'].queryset = CustomerCategory.objects.filter(
                tenant=tenant,
            ).exclude(pk=self.instance.pk or 0)


class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = (
            'name', 'currency', 'effective_from', 'effective_to',
            'is_default', 'is_active', 'notes',
        )
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }


class PriceListItemForm(forms.ModelForm):
    class Meta:
        model = PriceListItem
        fields = (
            'product', 'unit_price', 'min_qty', 'discount_pct',
            'valid_from', 'valid_to',
        )
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            'name', 'legal_name', 'customer_class', 'category',
            'email', 'phone', 'website', 'tax_id',
            'billing_address', 'shipping_address',
            'city', 'state', 'postal_code', 'country',
            'currency', 'payment_terms', 'credit_limit',
            'default_price_list', 'default_warehouse',
            'status', 'risk_flag', 'notes',
        )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['category'].queryset = CustomerCategory.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['default_price_list'].queryset = PriceList.objects.filter(
                tenant=tenant, is_active=True,
            )
            from apps.inventory.models import Warehouse
            self.fields['default_warehouse'].queryset = Warehouse.objects.filter(
                tenant=tenant,
            )


class CustomerContactForm(forms.ModelForm):
    class Meta:
        model = CustomerContact
        fields = (
            'full_name', 'designation', 'role',
            'email', 'phone_primary', 'phone_alt',
            'is_primary', 'is_active', 'notes',
        )


class CommunicationLogForm(forms.ModelForm):
    class Meta:
        model = CommunicationLog
        fields = (
            'contact', 'type', 'direction', 'subject', 'body',
            'occurred_at', 'follow_up_date', 'status',
        )
        widgets = {
            'occurred_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'follow_up_date': forms.DateInput(attrs={'type': 'date'}),
            'body': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if customer is not None:
            self.fields['contact'].queryset = CustomerContact.objects.filter(
                customer=customer, is_active=True,
            )
            self.fields['contact'].required = False


class CustomerDocumentForm(forms.ModelForm):
    class Meta:
        model = CustomerDocument
        fields = ('doc_type', 'title', 'file', 'expires_at', 'notes')
        widgets = {
            'expires_at': forms.DateInput(attrs={'type': 'date'}),
        }
