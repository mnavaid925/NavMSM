"""Views for Module 17 - Sales (17.1 portion).

CRUD-complete per CLAUDE.md "CRUD Completeness Rules". Every list view
pre-parses filter params, filters by `request.tenant` first, then
paginates. Filter context fed back to the template via the existing
`request.GET` pattern.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ATPRequestForm,
    CTPRequestForm,
    CommunicationLogForm,
    CustomerCategoryForm,
    CustomerContactForm,
    CustomerDocumentForm,
    CustomerForm,
    DeliveryRouteForm,
    PriceListForm,
    PriceListItemForm,
    ProofOfDeliveryForm,
    SalesInvoiceForm,
    SalesInvoiceLineForm,
    SalesOrderForm,
    SalesOrderLineForm,
    SalesOrderReviseForm,
    ShipmentForm,
    ShipmentLineForm,
)
from .models import (
    ATPCalculation,
    CTPCalculation,
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    DeliveryRoute,
    OrderPromise,
    PriceList,
    PriceListItem,
    ProofOfDelivery,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderApprovalLog,
    SalesOrderLine,
    SalesOrderRevision,
    Shipment,
    ShipmentLine,
)

PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def index_view(request):
    """Sales module dashboard - lightweight in 17.1; will grow with 17.2/17.4."""
    tenant = request.tenant
    if tenant is None:
        return render(request, 'sales/index.html', {'kpi': {}, 'recent_customers': []})
    customers_qs = Customer.objects.filter(tenant=tenant)
    kpi = {
        'total_customers': customers_qs.count(),
        'active_customers': customers_qs.filter(status='active').count(),
        'on_hold_customers': customers_qs.filter(status='on_hold').count(),
        'blacklisted_customers': customers_qs.filter(status='blacklisted').count(),
        'price_lists': PriceList.objects.filter(tenant=tenant, is_active=True).count(),
        'open_communications': CommunicationLog.objects.filter(
            tenant=tenant, status='open',
        ).count(),
    }
    recent_customers = customers_qs.order_by('-created_at')[:8]
    recent_comms = (
        CommunicationLog.objects.filter(tenant=tenant)
        .select_related('customer').order_by('-occurred_at')[:8]
    )
    return render(request, 'sales/index.html', {
        'kpi': kpi,
        'recent_customers': recent_customers,
        'recent_comms': recent_comms,
    })


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

@login_required
def customer_list_view(request):
    qs = Customer.objects.filter(tenant=request.tenant).select_related('category')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(legal_name__icontains=q)
            | Q(code__icontains=q) | Q(email__icontains=q)
            | Q(tax_id__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    klass = request.GET.get('customer_class', '')
    if klass:
        qs = qs.filter(customer_class=klass)
    cat = request.GET.get('category', '')
    if cat:
        qs = qs.filter(category_id=cat)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/customers/list.html', {
        'page_obj': page,
        'status_choices': Customer.STATUS_CHOICES,
        'class_choices': Customer.CUSTOMER_CLASS_CHOICES,
        'categories': CustomerCategory.objects.filter(
            tenant=request.tenant, is_active=True,
        ),
    })


@login_required
def customer_create_view(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Customer "{obj.name}" created.')
            return redirect('sales:customer_detail', pk=obj.pk)
    else:
        form = CustomerForm(tenant=request.tenant)
    return render(request, 'sales/customers/form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def customer_detail_view(request, pk):
    obj = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    contacts = obj.contacts.order_by('-is_primary', 'full_name')
    comms = obj.communications.order_by('-occurred_at')[:20]
    docs = obj.documents.order_by('-created_at')
    return render(request, 'sales/customers/detail.html', {
        'obj': obj,
        'contacts': contacts,
        'comms': comms,
        'docs': docs,
    })


@login_required
def customer_edit_view(request, pk):
    obj = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated.')
            return redirect('sales:customer_detail', pk=obj.pk)
    else:
        form = CustomerForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/customers/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def customer_delete_view(request, pk):
    obj = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Customer deleted.')
        return redirect('sales:customer_list')
    return redirect('sales:customer_list')


@login_required
def customer_toggle_active_view(request, pk):
    obj = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.status = 'inactive' if obj.status == 'active' else 'active'
        obj.save(update_fields=['status', 'updated_at'])
        messages.info(request, f'Customer is now {obj.get_status_display()}.')
    return redirect('sales:customer_detail', pk=obj.pk)


# ---------------------------------------------------------------------------
# CustomerContact
# ---------------------------------------------------------------------------

@login_required
def contact_add_view(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerContactForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.tenant = request.tenant
            c.customer = customer
            c.save()
            messages.success(request, 'Contact added.')
            return redirect('sales:customer_detail', pk=customer.pk)
    else:
        form = CustomerContactForm()
    return render(request, 'sales/customers/contact_form.html', {
        'form': form, 'customer': customer, 'mode': 'create',
    })


@login_required
def contact_edit_view(request, pk):
    obj = get_object_or_404(CustomerContact, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerContactForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contact updated.')
            return redirect('sales:customer_detail', pk=obj.customer.pk)
    else:
        form = CustomerContactForm(instance=obj)
    return render(request, 'sales/customers/contact_form.html', {
        'form': form, 'obj': obj, 'customer': obj.customer, 'mode': 'edit',
    })


@login_required
def contact_delete_view(request, pk):
    obj = get_object_or_404(CustomerContact, pk=pk, tenant=request.tenant)
    customer_pk = obj.customer_id
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Contact removed.')
    return redirect('sales:customer_detail', pk=customer_pk)


# ---------------------------------------------------------------------------
# CommunicationLog
# ---------------------------------------------------------------------------

@login_required
def comm_list_view(request):
    qs = CommunicationLog.objects.filter(tenant=request.tenant).select_related(
        'customer', 'contact',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(subject__icontains=q) | Q(body__icontains=q)
            | Q(customer__name__icontains=q) | Q(code__icontains=q),
        )
    t = request.GET.get('type', '')
    if t:
        qs = qs.filter(type=t)
    direction = request.GET.get('direction', '')
    if direction:
        qs = qs.filter(direction=direction)
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-occurred_at'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'sales/customers/communication_list.html', {
        'page_obj': page,
        'type_choices': CommunicationLog.TYPE_CHOICES,
        'direction_choices': CommunicationLog.DIRECTION_CHOICES,
        'status_choices': CommunicationLog.STATUS_CHOICES,
    })


@login_required
def comm_add_view(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CommunicationLogForm(request.POST, customer=customer)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.customer = customer
            obj.created_by = request.user
            obj.save()
            messages.success(request, 'Communication logged.')
            return redirect('sales:customer_detail', pk=customer.pk)
    else:
        form = CommunicationLogForm(customer=customer)
    return render(request, 'sales/customers/communication_form.html', {
        'form': form, 'customer': customer, 'mode': 'create',
    })


@login_required
def comm_edit_view(request, pk):
    obj = get_object_or_404(CommunicationLog, pk=pk, tenant=request.tenant)
    if obj.is_locked():
        messages.error(
            request, 'Communication is older than 24h and cannot be edited.',
        )
        return redirect('sales:customer_detail', pk=obj.customer.pk)
    if request.method == 'POST':
        form = CommunicationLogForm(
            request.POST, instance=obj, customer=obj.customer,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Communication updated.')
            return redirect('sales:customer_detail', pk=obj.customer.pk)
    else:
        form = CommunicationLogForm(instance=obj, customer=obj.customer)
    return render(request, 'sales/customers/communication_form.html', {
        'form': form, 'obj': obj, 'customer': obj.customer, 'mode': 'edit',
    })


@login_required
def comm_delete_view(request, pk):
    obj = get_object_or_404(CommunicationLog, pk=pk, tenant=request.tenant)
    customer_pk = obj.customer_id
    if obj.is_locked():
        messages.error(
            request, 'Communication is older than 24h and cannot be deleted.',
        )
        return redirect('sales:customer_detail', pk=customer_pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Communication removed.')
    return redirect('sales:customer_detail', pk=customer_pk)


# ---------------------------------------------------------------------------
# CustomerDocument
# ---------------------------------------------------------------------------

@login_required
def document_upload_view(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.customer = customer
            obj.uploaded_by = request.user
            obj.save()
            messages.success(request, 'Document uploaded.')
            return redirect('sales:customer_detail', pk=customer.pk)
    else:
        form = CustomerDocumentForm()
    return render(request, 'sales/customers/document_upload.html', {
        'form': form, 'customer': customer,
    })


@login_required
def document_delete_view(request, pk):
    obj = get_object_or_404(CustomerDocument, pk=pk, tenant=request.tenant)
    customer_pk = obj.customer_id
    if request.method == 'POST':
        obj.file.delete(save=False)
        obj.delete()
        messages.success(request, 'Document removed.')
    return redirect('sales:customer_detail', pk=customer_pk)


@login_required
def document_download_view(request, pk):
    """Auth-gated download. Cross-tenant access yields 404."""
    obj = get_object_or_404(CustomerDocument, pk=pk, tenant=request.tenant)
    try:
        return FileResponse(obj.file.open('rb'), as_attachment=True, filename=obj.file.name.rsplit('/', 1)[-1])
    except FileNotFoundError:
        raise Http404


# ---------------------------------------------------------------------------
# CustomerCategory
# ---------------------------------------------------------------------------

@login_required
def category_list_view(request):
    qs = CustomerCategory.objects.filter(tenant=request.tenant).select_related('parent')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/categories/list.html', {'page_obj': page})


@login_required
def category_create_view(request):
    if request.method == 'POST':
        form = CustomerCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Category created.')
            return redirect('sales:category_list')
    else:
        form = CustomerCategoryForm(tenant=request.tenant)
    return render(request, 'sales/categories/form.html', {'form': form, 'mode': 'create'})


@login_required
def category_edit_view(request, pk):
    obj = get_object_or_404(CustomerCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.')
            return redirect('sales:category_list')
    else:
        form = CustomerCategoryForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/categories/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def category_delete_view(request, pk):
    obj = get_object_or_404(CustomerCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Category deleted.')
        except Exception as exc:  # PROTECT FK violations
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('sales:category_list')


# ---------------------------------------------------------------------------
# PriceList
# ---------------------------------------------------------------------------

@login_required
def pricelist_list_view(request):
    qs = PriceList.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('-is_default', 'name'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'sales/pricelists/list.html', {'page_obj': page})


@login_required
def pricelist_create_view(request):
    if request.method == 'POST':
        form = PriceListForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Price list "{obj.name}" created.')
            return redirect('sales:pricelist_detail', pk=obj.pk)
    else:
        form = PriceListForm()
    return render(request, 'sales/pricelists/form.html', {'form': form, 'mode': 'create'})


@login_required
def pricelist_detail_view(request, pk):
    obj = get_object_or_404(PriceList, pk=pk, tenant=request.tenant)
    items = obj.items.select_related('product').order_by('product__code', 'min_qty')
    return render(request, 'sales/pricelists/detail.html', {'obj': obj, 'items': items})


@login_required
def pricelist_edit_view(request, pk):
    obj = get_object_or_404(PriceList, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = PriceListForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Price list updated.')
            return redirect('sales:pricelist_detail', pk=obj.pk)
    else:
        form = PriceListForm(instance=obj)
    return render(request, 'sales/pricelists/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def pricelist_delete_view(request, pk):
    obj = get_object_or_404(PriceList, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Price list deleted.')
    return redirect('sales:pricelist_list')


# ---------------------------------------------------------------------------
# PriceListItem (nested under a PriceList)
# ---------------------------------------------------------------------------

@login_required
def pricelist_item_add_view(request, pricelist_pk):
    pl = get_object_or_404(PriceList, pk=pricelist_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = PriceListItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.price_list = pl
            obj.save()
            messages.success(request, 'Item added.')
            return redirect('sales:pricelist_detail', pk=pl.pk)
    else:
        form = PriceListItemForm(tenant=request.tenant)
    return render(request, 'sales/pricelists/item_form.html', {
        'form': form, 'pricelist': pl, 'mode': 'create',
    })


@login_required
def pricelist_item_edit_view(request, pk):
    obj = get_object_or_404(PriceListItem, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = PriceListItemForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item updated.')
            return redirect('sales:pricelist_detail', pk=obj.price_list_id)
    else:
        form = PriceListItemForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/pricelists/item_form.html', {
        'form': form, 'obj': obj, 'pricelist': obj.price_list, 'mode': 'edit',
    })


@login_required
def pricelist_item_delete_view(request, pk):
    obj = get_object_or_404(PriceListItem, pk=pk, tenant=request.tenant)
    pl_pk = obj.price_list_id
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Item removed.')
    return redirect('sales:pricelist_detail', pk=pl_pk)


# ===========================================================================
# 17.2  SALES ORDER PROCESSING
# ===========================================================================

@login_required
def order_list_view(request):
    qs = SalesOrder.objects.filter(tenant=request.tenant).select_related(
        'customer', 'sales_rep',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(customer__name__icontains=q)
            | Q(customer_po_number__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    priority = request.GET.get('priority', '')
    if priority:
        qs = qs.filter(priority=priority)
    credit_hold = request.GET.get('credit_hold', '')
    if credit_hold == 'yes':
        qs = qs.filter(credit_hold=True)
    elif credit_hold == 'no':
        qs = qs.filter(credit_hold=False)
    cust = request.GET.get('customer', '')
    if cust:
        qs = qs.filter(customer_id=cust)
    page = Paginator(qs.order_by('-order_date', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'sales/orders/list.html', {
        'page_obj': page,
        'status_choices': SalesOrder.STATUS_CHOICES,
        'priority_choices': SalesOrder.PRIORITY_CHOICES,
        'customers': Customer.objects.filter(tenant=request.tenant, status='active'),
    })


@login_required
def order_create_view(request):
    if request.method == 'POST':
        form = SalesOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            # Default address snapshot from customer if blank
            if not obj.billing_address:
                obj.billing_address = obj.customer.billing_address
            if not obj.shipping_address:
                obj.shipping_address = obj.customer.shipping_address
            obj.save()
            messages.success(request, f'Sales order {obj.code} created. Add lines next.')
            return redirect('sales:order_detail', pk=obj.pk)
    else:
        form = SalesOrderForm(tenant=request.tenant)
    return render(request, 'sales/orders/form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def order_detail_view(request, pk):
    obj = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    lines = obj.lines.select_related('product').order_by('line_no')
    revisions = obj.revisions.order_by('-version_no')
    logs = obj.approval_logs.order_by('-performed_at')
    revise_form = SalesOrderReviseForm()
    return render(request, 'sales/orders/detail.html', {
        'obj': obj, 'lines': lines, 'revisions': revisions,
        'logs': logs, 'revise_form': revise_form,
    })


@login_required
def order_edit_view(request, pk):
    obj = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    if not obj.is_editable():
        messages.error(
            request, f'Cannot edit a {obj.get_status_display().lower()} order.',
        )
        return redirect('sales:order_detail', pk=obj.pk)
    if request.method == 'POST':
        form = SalesOrderForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sales order updated.')
            return redirect('sales:order_detail', pk=obj.pk)
    else:
        form = SalesOrderForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/orders/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def order_delete_view(request, pk):
    obj = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    if obj.status != 'draft':
        messages.error(request, 'Only draft orders can be deleted. Cancel instead.')
        return redirect('sales:order_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Sales order deleted.')
        return redirect('sales:order_list')
    return redirect('sales:order_detail', pk=obj.pk)


# ---- SalesOrderLine ----

@login_required
def order_line_add_view(request, order_pk):
    order = get_object_or_404(SalesOrder, pk=order_pk, tenant=request.tenant)
    if not order.is_editable():
        messages.error(request, 'Cannot add lines to a non-editable order.')
        return redirect('sales:order_detail', pk=order.pk)
    if request.method == 'POST':
        form = SalesOrderLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.sales_order = order
            line.save()
            order.recompute_totals()
            messages.success(request, 'Line added.')
            return redirect('sales:order_detail', pk=order.pk)
    else:
        form = SalesOrderLineForm(tenant=request.tenant)
    return render(request, 'sales/orders/line_form.html', {
        'form': form, 'order': order, 'mode': 'create',
    })


@login_required
def order_line_edit_view(request, pk):
    obj = get_object_or_404(SalesOrderLine, pk=pk, tenant=request.tenant)
    order = obj.sales_order
    if not order.is_editable():
        messages.error(request, 'Cannot edit lines on a non-editable order.')
        return redirect('sales:order_detail', pk=order.pk)
    if request.method == 'POST':
        form = SalesOrderLineForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            order.recompute_totals()
            messages.success(request, 'Line updated.')
            return redirect('sales:order_detail', pk=order.pk)
    else:
        form = SalesOrderLineForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/orders/line_form.html', {
        'form': form, 'order': order, 'obj': obj, 'mode': 'edit',
    })


@login_required
def order_line_delete_view(request, pk):
    obj = get_object_or_404(SalesOrderLine, pk=pk, tenant=request.tenant)
    order = obj.sales_order
    if not order.is_editable():
        messages.error(request, 'Cannot remove lines from a non-editable order.')
        return redirect('sales:order_detail', pk=order.pk)
    if request.method == 'POST':
        obj.delete()
        order.recompute_totals()
        messages.success(request, 'Line removed.')
    return redirect('sales:order_detail', pk=order.pk)


# ---- Workflow actions ----

def _wf_call(request, order, fn, success_msg):
    from apps.sales.services import workflow
    try:
        fn(order, performed_by=request.user)
        messages.success(request, success_msg)
    except ValueError as exc:
        messages.error(request, str(exc))


@login_required
def order_submit_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import submit_sales_order
    if request.method == 'POST':
        try:
            result = submit_sales_order(order, performed_by=request.user)
            if result.is_hold:
                messages.warning(request, f'Submitted - moved to credit_check: {result.message}')
            else:
                messages.success(request, 'Submitted. Credit check passed.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_confirm_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import confirm_sales_order
    if request.method == 'POST':
        try:
            confirm_sales_order(order, performed_by=request.user)
            messages.success(request, f'Order {order.code} confirmed.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_release_credit_hold_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import release_credit_hold
    if request.method == 'POST':
        if release_credit_hold(order, performed_by=request.user):
            messages.success(request, 'Credit hold released.')
        else:
            messages.info(request, 'No credit hold to release.')
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_cancel_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import cancel_sales_order
    if request.method == 'POST':
        try:
            cancel_sales_order(order, performed_by=request.user)
            messages.success(request, 'Order cancelled.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_hold_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import hold_sales_order
    if request.method == 'POST':
        try:
            hold_sales_order(order, performed_by=request.user)
            messages.success(request, 'Order placed on hold.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_resume_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import resume_sales_order
    if request.method == 'POST':
        try:
            resume_sales_order(order, performed_by=request.user)
            messages.success(request, 'Order resumed.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_revise_view(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant)
    from apps.sales.services.workflow import revise_sales_order
    if request.method == 'POST':
        form = SalesOrderReviseForm(request.POST)
        if form.is_valid():
            try:
                rev = revise_sales_order(
                    order, reason=form.cleaned_data['reason'],
                    performed_by=request.user,
                )
                messages.success(request, f'Snapshot v{rev.version_no} captured.')
            except ValueError as exc:
                messages.error(request, str(exc))
    return redirect('sales:order_detail', pk=order.pk)


@login_required
def order_revision_detail_view(request, pk):
    rev = get_object_or_404(SalesOrderRevision, pk=pk, tenant=request.tenant)
    return render(request, 'sales/orders/revision_detail.html', {
        'rev': rev, 'order': rev.sales_order,
    })


# ===========================================================================
# 17.3  ORDER PROMISING & ATP / CTP
# ===========================================================================

@login_required
def atp_list_view(request):
    qs = ATPCalculation.objects.filter(tenant=request.tenant).select_related(
        'product', 'order_line__sales_order',
    )
    page = Paginator(qs.order_by('-computed_at'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/promising/atp_list.html', {
        'page_obj': page,
    })


@login_required
def atp_request_view(request):
    from apps.sales.services.atp import compute_atp
    result = None
    if request.method == 'POST':
        form = ATPRequestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = compute_atp(
                tenant=request.tenant,
                product=form.cleaned_data['product'],
                requested_qty=form.cleaned_data['requested_qty'],
                requested_date=form.cleaned_data['requested_date'],
                warehouse=form.cleaned_data['warehouse'],
                method=form.cleaned_data['method'],
            )
            calc = ATPCalculation.objects.create(
                tenant=request.tenant,
                product=form.cleaned_data['product'],
                requested_qty=form.cleaned_data['requested_qty'],
                requested_date=form.cleaned_data['requested_date'],
                method=form.cleaned_data['method'],
                available_qty=r.available_qty,
                available_date=r.available_date,
                result_status=r.result_status,
                snapshot_json=r.breakdown,
                computed_by=request.user,
            )
            messages.success(request, f'ATP {calc.code} computed.')
            return redirect('sales:atp_detail', pk=calc.pk)
    else:
        form = ATPRequestForm(tenant=request.tenant)
    return render(request, 'sales/promising/atp_request.html', {
        'form': form, 'result': result,
    })


@login_required
def atp_detail_view(request, pk):
    obj = get_object_or_404(ATPCalculation, pk=pk, tenant=request.tenant)
    return render(request, 'sales/promising/atp_detail.html', {'obj': obj})


@login_required
def ctp_list_view(request):
    qs = CTPCalculation.objects.filter(tenant=request.tenant).select_related(
        'product', 'order_line__sales_order',
    )
    page = Paginator(qs.order_by('-computed_at'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/promising/ctp_list.html', {'page_obj': page})


@login_required
def ctp_request_view(request):
    from apps.sales.services.ctp import compute_ctp
    if request.method == 'POST':
        form = CTPRequestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = compute_ctp(
                tenant=request.tenant,
                product=form.cleaned_data['product'],
                shortfall_qty=form.cleaned_data['shortfall_qty'],
                target_date=form.cleaned_data['target_date'],
            )
            bottleneck = None
            if r.bottleneck_work_center_id:
                try:
                    from apps.pps.models import WorkCenter
                    bottleneck = WorkCenter.all_objects.filter(
                        pk=r.bottleneck_work_center_id,
                    ).first()
                except Exception:
                    pass
            calc = CTPCalculation.objects.create(
                tenant=request.tenant,
                product=form.cleaned_data['product'],
                shortfall_qty=form.cleaned_data['shortfall_qty'],
                target_date=form.cleaned_data['target_date'],
                capable_qty=r.capable_qty,
                earliest_completion_date=r.earliest_completion_date,
                bottleneck_work_center=bottleneck,
                simulation_json=r.trace,
                computed_by=request.user,
            )
            messages.success(request, f'CTP {calc.code} computed.')
            return redirect('sales:ctp_detail', pk=calc.pk)
    else:
        form = CTPRequestForm(tenant=request.tenant)
    return render(request, 'sales/promising/ctp_request.html', {'form': form})


@login_required
def ctp_detail_view(request, pk):
    obj = get_object_or_404(CTPCalculation, pk=pk, tenant=request.tenant)
    return render(request, 'sales/promising/ctp_detail.html', {'obj': obj})


@login_required
def promise_confirm_view(request, order_line_pk):
    line = get_object_or_404(
        SalesOrderLine, pk=order_line_pk, tenant=request.tenant,
    )
    if request.method == 'POST':
        atp = ATPCalculation.objects.filter(
            tenant=request.tenant, order_line=line,
        ).order_by('-computed_at').first()
        ctp = CTPCalculation.objects.filter(
            tenant=request.tenant, order_line=line,
        ).order_by('-computed_at').first()
        # Decide promise_type heuristically
        if atp and atp.available_qty >= line.qty_ordered:
            ptype = 'stock'
            promised_qty = line.qty_ordered
            promised_date = atp.available_date
        elif atp and atp.available_qty > 0:
            ptype = 'mixed' if ctp else 'partial'
            promised_qty = atp.available_qty
            promised_date = ctp.earliest_completion_date if ctp else atp.available_date
        elif ctp:
            ptype = 'production'
            promised_qty = ctp.capable_qty
            promised_date = ctp.earliest_completion_date
        else:
            ptype = 'unfulfillable'
            promised_qty = 0
            promised_date = None
        from django.utils import timezone
        OrderPromise.objects.update_or_create(
            order_line=line,
            defaults={
                'tenant': request.tenant,
                'promise_type': ptype,
                'promised_qty': promised_qty,
                'promised_date': promised_date,
                'atp_ref': atp,
                'ctp_ref': ctp,
                'confirmed_at': timezone.now(),
                'confirmed_by': request.user,
            },
        )
        # Also reflect on the SO line denorm
        line.qty_promised = promised_qty
        if promised_date:
            line.promised_date = promised_date
        line.save(update_fields=['qty_promised', 'promised_date', 'updated_at'])
        messages.success(request, f'Promise recorded: {ptype}.')
    return redirect('sales:order_detail', pk=line.sales_order_id)


# ===========================================================================
# 17.4  DELIVERY SCHEDULING & DISPATCH + INVOICING
# ===========================================================================

# ---- DeliveryRoute ----

@login_required
def route_list_view(request):
    qs = DeliveryRoute.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(driver_name__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-route_date'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/routes/list.html', {
        'page_obj': page,
        'status_choices': DeliveryRoute.STATUS_CHOICES,
    })


@login_required
def route_create_view(request):
    if request.method == 'POST':
        form = DeliveryRouteForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Route {obj.code} created.')
            return redirect('sales:route_detail', pk=obj.pk)
    else:
        form = DeliveryRouteForm()
    return render(request, 'sales/routes/form.html', {'form': form, 'mode': 'create'})


@login_required
def route_detail_view(request, pk):
    obj = get_object_or_404(DeliveryRoute, pk=pk, tenant=request.tenant)
    shipments = obj.shipments.select_related('sales_order').order_by('-id')
    return render(request, 'sales/routes/detail.html', {'obj': obj, 'shipments': shipments})


@login_required
def route_edit_view(request, pk):
    obj = get_object_or_404(DeliveryRoute, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = DeliveryRouteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Route updated.')
            return redirect('sales:route_detail', pk=obj.pk)
    else:
        form = DeliveryRouteForm(instance=obj)
    return render(request, 'sales/routes/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
def route_delete_view(request, pk):
    obj = get_object_or_404(DeliveryRoute, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Route deleted.')
    return redirect('sales:route_list')


# ---- Shipment ----

@login_required
def shipment_list_view(request):
    qs = Shipment.objects.filter(tenant=request.tenant).select_related(
        'sales_order__customer', 'route',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(sales_order__code__icontains=q)
            | Q(tracking_number__icontains=q) | Q(carrier_name__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/shipments/list.html', {
        'page_obj': page,
        'status_choices': Shipment.STATUS_CHOICES,
    })


@login_required
def shipment_create_view(request):
    if request.method == 'POST':
        form = ShipmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'Shipment {obj.code} created.')
            return redirect('sales:shipment_detail', pk=obj.pk)
    else:
        form = ShipmentForm(tenant=request.tenant)
    return render(request, 'sales/shipments/form.html', {'form': form, 'mode': 'create'})


@login_required
def shipment_detail_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    lines = obj.shipment_lines.select_related('order_line__product', 'source_bin').order_by('id')
    pod = getattr(obj, 'pod', None)
    invoice_form = ProofOfDeliveryForm() if obj.can_deliver() else None
    return render(request, 'sales/shipments/detail.html', {
        'obj': obj, 'lines': lines, 'pod': pod,
        'pod_form': ProofOfDeliveryForm(),
    })


@login_required
def shipment_edit_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    if not obj.is_editable():
        messages.error(request, 'Cannot edit a shipment after picking.')
        return redirect('sales:shipment_detail', pk=obj.pk)
    if request.method == 'POST':
        form = ShipmentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shipment updated.')
            return redirect('sales:shipment_detail', pk=obj.pk)
    else:
        form = ShipmentForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/shipments/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def shipment_delete_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    if obj.status not in ('planned', 'cancelled'):
        messages.error(request, 'Only planned or cancelled shipments can be deleted.')
        return redirect('sales:shipment_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Shipment deleted.')
    return redirect('sales:shipment_list')


# ---- ShipmentLine ----

@login_required
def shipment_line_add_view(request, shipment_pk):
    shipment = get_object_or_404(Shipment, pk=shipment_pk, tenant=request.tenant)
    if not shipment.is_editable():
        messages.error(request, 'Cannot add lines after picking.')
        return redirect('sales:shipment_detail', pk=shipment.pk)
    if request.method == 'POST':
        form = ShipmentLineForm(request.POST, shipment=shipment, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.shipment = shipment
            line.save()
            messages.success(request, 'Line added.')
            return redirect('sales:shipment_detail', pk=shipment.pk)
    else:
        form = ShipmentLineForm(shipment=shipment, tenant=request.tenant)
    return render(request, 'sales/shipments/line_form.html', {
        'form': form, 'shipment': shipment, 'mode': 'create',
    })


@login_required
def shipment_line_edit_view(request, pk):
    obj = get_object_or_404(ShipmentLine, pk=pk, tenant=request.tenant)
    shipment = obj.shipment
    if request.method == 'POST':
        form = ShipmentLineForm(
            request.POST, instance=obj, shipment=shipment, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Line updated.')
            return redirect('sales:shipment_detail', pk=shipment.pk)
    else:
        form = ShipmentLineForm(instance=obj, shipment=shipment, tenant=request.tenant)
    return render(request, 'sales/shipments/line_form.html', {
        'form': form, 'shipment': shipment, 'obj': obj, 'mode': 'edit',
    })


@login_required
def shipment_line_delete_view(request, pk):
    obj = get_object_or_404(ShipmentLine, pk=pk, tenant=request.tenant)
    shipment_pk = obj.shipment_id
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Line removed.')
    return redirect('sales:shipment_detail', pk=shipment_pk)


# ---- Shipment workflow ----

@login_required
def shipment_pick_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    from apps.sales.services.shipping import pick_shipment
    if request.method == 'POST':
        try:
            pick_shipment(obj, performed_by=request.user)
            messages.success(request, 'Shipment picked.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:shipment_detail', pk=obj.pk)


@login_required
def shipment_pack_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    from apps.sales.services.shipping import pack_shipment
    if request.method == 'POST':
        try:
            pack_shipment(obj, performed_by=request.user)
            messages.success(request, 'Shipment packed.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:shipment_detail', pk=obj.pk)


@login_required
def shipment_dispatch_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    from apps.sales.services.shipping import dispatch_shipment
    if request.method == 'POST':
        try:
            dispatch_shipment(obj, performed_by=request.user)
            messages.success(request, 'Shipment dispatched.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:shipment_detail', pk=obj.pk)


@login_required
def shipment_mark_delivered_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    from apps.sales.services.shipping import confirm_delivery
    if request.method == 'POST':
        try:
            confirm_delivery(obj, performed_by=request.user)
            messages.success(request, 'Shipment delivered. Inventory updated.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:shipment_detail', pk=obj.pk)


@login_required
def shipment_cancel_view(request, pk):
    obj = get_object_or_404(Shipment, pk=pk, tenant=request.tenant)
    from apps.sales.services.shipping import cancel_shipment
    if request.method == 'POST':
        try:
            cancel_shipment(obj, performed_by=request.user)
            messages.success(request, 'Shipment cancelled.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:shipment_detail', pk=obj.pk)


# ---- ProofOfDelivery ----

@login_required
def pod_record_view(request, shipment_pk):
    shipment = get_object_or_404(Shipment, pk=shipment_pk, tenant=request.tenant)
    instance = getattr(shipment, 'pod', None)
    if request.method == 'POST':
        form = ProofOfDeliveryForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            pod = form.save(commit=False)
            pod.tenant = request.tenant
            pod.shipment = shipment
            pod.recorded_by = request.user
            pod.save()
            messages.success(request, 'Proof of delivery recorded.')
            return redirect('sales:shipment_detail', pk=shipment.pk)
    else:
        form = ProofOfDeliveryForm(instance=instance)
    return render(request, 'sales/shipments/pod_form.html', {
        'form': form, 'shipment': shipment,
    })


# ---- SalesInvoice ----

@login_required
def invoice_list_view(request):
    qs = SalesInvoice.objects.filter(tenant=request.tenant).select_related(
        'sales_order__customer',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(sales_order__code__icontains=q)
            | Q(sales_order__customer__name__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-invoice_date'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/invoices/list.html', {
        'page_obj': page,
        'status_choices': SalesInvoice.STATUS_CHOICES,
    })


@login_required
def invoice_create_view(request):
    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.issued_by = request.user
            obj.save()
            messages.success(request, f'Invoice {obj.code} created.')
            return redirect('sales:invoice_detail', pk=obj.pk)
    else:
        form = SalesInvoiceForm(tenant=request.tenant)
    return render(request, 'sales/invoices/form.html', {'form': form, 'mode': 'create'})


@login_required
def invoice_create_from_shipment_view(request, shipment_pk):
    """Auto-generate a draft invoice from a shipment (idempotent)."""
    shipment = get_object_or_404(Shipment, pk=shipment_pk, tenant=request.tenant)
    from apps.sales.services.invoicing import generate_invoice_from_shipment
    invoice = generate_invoice_from_shipment(shipment, issued_by=request.user)
    messages.success(request, f'Invoice {invoice.code} ready (draft).')
    return redirect('sales:invoice_detail', pk=invoice.pk)


@login_required
def invoice_detail_view(request, pk):
    obj = get_object_or_404(SalesInvoice, pk=pk, tenant=request.tenant)
    return render(request, 'sales/invoices/detail.html', {
        'obj': obj, 'lines': obj.lines.all().order_by('id'),
    })


@login_required
def invoice_edit_view(request, pk):
    obj = get_object_or_404(SalesInvoice, pk=pk, tenant=request.tenant)
    if obj.status not in ('draft', 'overdue'):
        messages.error(request, 'Only draft or overdue invoices can be edited.')
        return redirect('sales:invoice_detail', pk=obj.pk)
    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Invoice updated.')
            return redirect('sales:invoice_detail', pk=obj.pk)
    else:
        form = SalesInvoiceForm(instance=obj, tenant=request.tenant)
    return render(request, 'sales/invoices/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
def invoice_delete_view(request, pk):
    obj = get_object_or_404(SalesInvoice, pk=pk, tenant=request.tenant)
    if obj.status != 'draft':
        messages.error(request, 'Only draft invoices can be deleted.')
        return redirect('sales:invoice_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Invoice deleted.')
    return redirect('sales:invoice_list')


@login_required
def invoice_issue_view(request, pk):
    obj = get_object_or_404(SalesInvoice, pk=pk, tenant=request.tenant)
    if request.method == 'POST' and obj.status == 'draft':
        obj.status = 'issued'
        obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Invoice issued.')
    return redirect('sales:invoice_detail', pk=obj.pk)


@login_required
def invoice_mark_paid_view(request, pk):
    obj = get_object_or_404(SalesInvoice, pk=pk, tenant=request.tenant)
    from apps.sales.services.invoicing import mark_invoice_paid
    if request.method == 'POST':
        try:
            mark_invoice_paid(obj, performed_by=request.user)
            messages.success(request, 'Invoice marked paid.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('sales:invoice_detail', pk=obj.pk)


# ---- SalesInvoiceLine ----

@login_required
def invoice_line_add_view(request, invoice_pk):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_pk, tenant=request.tenant)
    if invoice.status not in ('draft', 'overdue'):
        messages.error(request, 'Cannot add lines after issue.')
        return redirect('sales:invoice_detail', pk=invoice.pk)
    if request.method == 'POST':
        form = SalesInvoiceLineForm(request.POST)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.invoice = invoice
            line.save()
            invoice.recompute_totals()
            messages.success(request, 'Line added.')
            return redirect('sales:invoice_detail', pk=invoice.pk)
    else:
        form = SalesInvoiceLineForm()
    return render(request, 'sales/invoices/line_form.html', {
        'form': form, 'invoice': invoice, 'mode': 'create',
    })


@login_required
def invoice_line_delete_view(request, pk):
    obj = get_object_or_404(SalesInvoiceLine, pk=pk, tenant=request.tenant)
    invoice = obj.invoice
    if request.method == 'POST':
        obj.delete()
        invoice.recompute_totals()
        messages.success(request, 'Line removed.')
    return redirect('sales:invoice_detail', pk=invoice.pk)


# ===========================================================================
# 17.5  CUSTOMER PORTAL  (scoped to request.user.customer_company)
# ===========================================================================

def _customer_company(request):
    """Return the Customer FK on the logged-in user, or None.

    All portal views call this first; an empty result triggers a redirect
    to the main dashboard with an explanatory message.
    """
    return getattr(request.user, 'customer_company', None)


@login_required
def portal_dashboard_view(request):
    customer = _customer_company(request)
    if customer is None:
        messages.warning(request, 'Your account is not linked to a customer.')
        return redirect('dashboard')
    qs = customer.sales_orders.all()
    kpi = {
        'open_orders': qs.exclude(status__in=('closed', 'cancelled')).count(),
        'in_transit_shipments': Shipment.objects.filter(
            tenant=request.tenant, sales_order__customer=customer,
            status='in_transit',
        ).count(),
        'unpaid_invoices': SalesInvoice.objects.filter(
            tenant=request.tenant, sales_order__customer=customer,
            status__in=('issued', 'overdue'),
        ).count(),
        'total_outstanding': SalesInvoice.objects.filter(
            tenant=request.tenant, sales_order__customer=customer,
            status__in=('issued', 'overdue'),
        ).aggregate(s=Sum('grand_total'))['s'] or 0,
    }
    recent_orders = qs.order_by('-order_date')[:6]
    recent_shipments = Shipment.objects.filter(
        tenant=request.tenant, sales_order__customer=customer,
    ).select_related('sales_order').order_by('-id')[:6]
    return render(request, 'sales/portal/dashboard.html', {
        'customer': customer, 'kpi': kpi,
        'recent_orders': recent_orders, 'recent_shipments': recent_shipments,
    })


@login_required
def portal_order_list_view(request):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    qs = customer.sales_orders.select_related().all()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-order_date'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/portal/order_list.html', {
        'customer': customer, 'page_obj': page,
        'status_choices': SalesOrder.STATUS_CHOICES,
    })


@login_required
def portal_order_detail_view(request, pk):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    obj = get_object_or_404(SalesOrder, pk=pk, tenant=request.tenant, customer=customer)
    lines = obj.lines.select_related('product').order_by('line_no')
    shipments = obj.shipments.order_by('-id')
    invoices = obj.invoices.order_by('-invoice_date')
    return render(request, 'sales/portal/order_detail.html', {
        'customer': customer, 'obj': obj, 'lines': lines,
        'shipments': shipments, 'invoices': invoices,
    })


@login_required
def portal_shipment_tracking_view(request, pk):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    obj = get_object_or_404(
        Shipment, pk=pk, tenant=request.tenant,
        sales_order__customer=customer,
    )
    return render(request, 'sales/portal/tracking.html', {
        'customer': customer, 'obj': obj,
        'pod': getattr(obj, 'pod', None),
    })


@login_required
def portal_invoice_list_view(request):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    qs = SalesInvoice.objects.filter(
        tenant=request.tenant, sales_order__customer=customer,
    ).select_related('sales_order')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-invoice_date'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'sales/portal/invoice_list.html', {
        'customer': customer, 'page_obj': page,
        'status_choices': SalesInvoice.STATUS_CHOICES,
    })


@login_required
def portal_invoice_detail_view(request, pk):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    obj = get_object_or_404(
        SalesInvoice, pk=pk, tenant=request.tenant,
        sales_order__customer=customer,
    )
    return render(request, 'sales/portal/invoice_detail.html', {
        'customer': customer, 'obj': obj, 'lines': obj.lines.all().order_by('id'),
    })


@login_required
def portal_document_download_view(request, pk):
    customer = _customer_company(request)
    if customer is None:
        return redirect('dashboard')
    doc = get_object_or_404(
        CustomerDocument, pk=pk, tenant=request.tenant, customer=customer,
    )
    from django.http import FileResponse, Http404 as _Http404
    try:
        return FileResponse(doc.file.open('rb'), as_attachment=True,
                            filename=doc.file.name.rsplit('/', 1)[-1])
    except FileNotFoundError:
        raise _Http404
