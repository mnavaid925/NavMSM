from django import forms

from .models import (
    BillingAddress, BrandingSettings, EmailTemplate,
)
from apps.core.models import Tenant


class TenantOrgForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ('name', 'email', 'phone', 'website', 'industry', 'timezone', 'address', 'logo')
        widgets = {'address': forms.Textarea(attrs={'rows': 2})}


class BrandingForm(forms.ModelForm):
    class Meta:
        model = BrandingSettings
        fields = (
            'logo_light', 'logo_dark', 'favicon',
            'primary_color', 'secondary_color', 'sidebar_color', 'topbar_color',
            'email_from_name', 'email_from_address',
            'footer_text', 'support_email', 'support_url',
        )
        widgets = {
            'primary_color': forms.TextInput(attrs={'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color'}),
            'sidebar_color': forms.TextInput(attrs={'type': 'color'}),
            'topbar_color': forms.TextInput(attrs={'type': 'color'}),
        }


class BillingAddressForm(forms.ModelForm):
    class Meta:
        model = BillingAddress
        fields = ('line1', 'line2', 'city', 'state', 'postal_code', 'country', 'tax_id')


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ('code', 'subject', 'html_body', 'text_body', 'is_active')
        widgets = {
            'html_body': forms.Textarea(attrs={'rows': 10}),
            'text_body': forms.Textarea(attrs={'rows': 6}),
        }
