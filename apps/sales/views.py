"""Views for Module 17 - Sales (17.1 portion).

CRUD-complete per CLAUDE.md "CRUD Completeness Rules". Every list view
pre-parses filter params, filters by `request.tenant` first, then
paginates. Filter context fed back to the template via the existing
`request.GET` pattern.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    CommunicationLogForm,
    CustomerCategoryForm,
    CustomerContactForm,
    CustomerDocumentForm,
    CustomerForm,
    PriceListForm,
    PriceListItemForm,
)
from .models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    PriceList,
    PriceListItem,
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
