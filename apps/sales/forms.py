"""Forms for Module 17 - Sales (17.1 portion)."""
from django import forms

from .models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    DeliveryRoute,
    PriceList,
    PriceListItem,
    ProofOfDelivery,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
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


# ===== 17.2 - Sales Order Processing =====

class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = (
            'customer', 'customer_po_number',
            'order_date', 'requested_delivery_date', 'promised_delivery_date',
            'priority', 'currency', 'payment_terms',
            'source_warehouse', 'sales_rep',
            'billing_address', 'shipping_address',
            'shipping_total', 'notes',
        )
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'requested_delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'promised_delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'billing_address': forms.Textarea(attrs={'rows': 3}),
            'shipping_address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['customer'].queryset = Customer.objects.filter(
                tenant=tenant, status__in=('active', 'on_hold'),
            )
            from apps.inventory.models import Warehouse
            self.fields['source_warehouse'].queryset = Warehouse.objects.filter(
                tenant=tenant,
            )

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        if customer and customer.status == 'blacklisted':
            raise forms.ValidationError(
                'Cannot create an order for a blacklisted customer.',
            )
        return cleaned


class SalesOrderLineForm(forms.ModelForm):
    class Meta:
        model = SalesOrderLine
        fields = (
            'product', 'description', 'unit_of_measure',
            'qty_ordered', 'unit_price',
            'line_discount_pct', 'line_tax_pct',
            'requested_date', 'is_make_to_order', 'notes',
        )
        widgets = {
            'requested_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.TextInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)


class SalesOrderReviseForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text='Optional explanation captured in the revision snapshot.',
    )


# ===== 17.3 - ATP / CTP =====

class ATPRequestForm(forms.Form):
    product = forms.ModelChoiceField(queryset=None)
    requested_qty = forms.DecimalField(min_value=0, max_digits=14, decimal_places=4)
    requested_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    method = forms.ChoiceField(choices=[
        ('stock_only', 'On-hand stock only'),
        ('stock_plus_open_po', 'Stock + Open PO arrivals'),
        ('stock_plus_pps', 'Stock + Planned PPS production'),
    ])
    warehouse = forms.ModelChoiceField(queryset=None, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.plm.models import Product
        from apps.inventory.models import Warehouse
        self.fields['product'].queryset = Product.objects.filter(tenant=tenant) if tenant else Product.objects.none()
        self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant) if tenant else Warehouse.objects.none()


class CTPRequestForm(forms.Form):
    product = forms.ModelChoiceField(queryset=None)
    shortfall_qty = forms.DecimalField(min_value=0, max_digits=14, decimal_places=4)
    target_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.plm.models import Product
        self.fields['product'].queryset = Product.objects.filter(tenant=tenant) if tenant else Product.objects.none()


# ===== 17.4 - Shipment, Route, POD, Invoice =====

class DeliveryRouteForm(forms.ModelForm):
    class Meta:
        model = DeliveryRoute
        fields = ('name', 'route_date', 'driver_name', 'vehicle_no', 'status', 'notes')
        widgets = {
            'route_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class ShipmentForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = (
            'sales_order', 'route', 'source_warehouse',
            'carrier_name', 'tracking_number',
            'weight_kg', 'volume_m3',
            'planned_ship_date', 'expected_delivery_date',
            'freight_cost', 'insurance_cost', 'notes',
        )
        widgets = {
            'planned_ship_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant,
                status__in=('confirmed', 'in_production', 'fulfilled'),
            )
            self.fields['route'].queryset = DeliveryRoute.objects.filter(
                tenant=tenant, status__in=('planned', 'dispatched'),
            )
            from apps.inventory.models import Warehouse
            self.fields['source_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)


class ShipmentLineForm(forms.ModelForm):
    class Meta:
        model = ShipmentLine
        fields = (
            'order_line', 'qty_to_ship', 'qty_shipped',
            'lot_no', 'serial_no', 'source_bin', 'pick_status',
        )

    def __init__(self, *args, shipment=None, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if shipment is not None:
            self.fields['order_line'].queryset = shipment.sales_order.lines.all()
        if tenant is not None:
            from apps.inventory.models import StorageBin
            self.fields['source_bin'].queryset = StorageBin.objects.filter(
                tenant=tenant,
            )


def _validate_pod_image(file):
    """L-22: signatures and photos limited to 5 MB / 25 MB and image types."""
    from django.core.exceptions import ValidationError
    if file.size > 25 * 1024 * 1024:
        raise ValidationError('File exceeds 25 MB limit.')
    allowed = {'.png', '.jpg', '.jpeg', '.pdf'}
    name = (file.name or '').lower()
    if not any(name.endswith(ext) for ext in allowed):
        raise ValidationError('Allowed: PNG, JPG, JPEG, PDF.')


class ProofOfDeliveryForm(forms.ModelForm):
    class Meta:
        model = ProofOfDelivery
        fields = (
            'delivered_at', 'received_by_name',
            'received_by_signature', 'photo_attachment', 'notes',
        )
        widgets = {
            'delivered_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_received_by_signature(self):
        f = self.cleaned_data.get('received_by_signature')
        if f:
            _validate_pod_image(f)
        return f

    def clean_photo_attachment(self):
        f = self.cleaned_data.get('photo_attachment')
        if f:
            _validate_pod_image(f)
        return f


class SalesInvoiceForm(forms.ModelForm):
    class Meta:
        model = SalesInvoice
        fields = (
            'sales_order', 'shipment',
            'invoice_date', 'due_date', 'payment_terms',
            'shipping_total', 'notes',
        )
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(tenant=tenant)
            self.fields['shipment'].queryset = Shipment.objects.filter(tenant=tenant)


class SalesInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = SalesInvoiceLine
        fields = (
            'description', 'qty', 'unit_price',
            'line_discount_pct', 'line_tax_pct',
        )
