"""Views for Module 18 - Returns & RMA Management.

CRUD-complete per CLAUDE.md "CRUD Completeness Rules". Every list view
filters by `request.tenant` first, parses GET filter params, then
paginates. Workflow / delete views are POST-only and gated to tenant
admins via `@tenant_admin_required` (L-10).
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    FailureModeForm,
    RMALineForm,
    RMARequestForm,
    RMAReasonForm,
    RepairCompleteForm,
    RepairLaborLogForm,
    RepairOrderForm,
    RepairPartUsageForm,
    ReturnAnalysisForm,
    ReturnReceiptForm,
    ReturnReceiptLineForm,
    RootCauseCategoryForm,
    SupplierChargebackForm,
    WarrantyClaimForm,
    WarrantyPolicyForm,
    WarrantyRegistrationForm,
)
from .models import (
    FailureMode,
    RMAApproval,
    RMALine,
    RMARequest,
    RMAReason,
    RepairLaborLog,
    RepairOrder,
    RepairPartUsage,
    ReturnAnalysis,
    ReturnReceipt,
    ReturnReceiptLine,
    RootCauseCategory,
    SupplierChargeback,
    WarrantyClaim,
    WarrantyPolicy,
    WarrantyRegistration,
)
from .services.chargeback import apply_transition

PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# RBAC helper (L-10): workflow + delete mutations require a tenant admin.
# ---------------------------------------------------------------------------

def _is_admin(user):
    return bool(getattr(user, 'is_tenant_admin', False) or user.is_superuser)


def tenant_admin_required(view_func):
    """Block non-admin users from state-changing views.

    Stacks UNDER @login_required. Non-admins get a flash error and are
    bounced to the module dashboard - the mutation never runs.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_admin(request.user):
            messages.error(
                request, 'You do not have permission to perform this action.',
            )
            return redirect('rma:index')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def index_view(request):
    tenant = request.tenant
    if tenant is None:
        return render(request, 'rma/index.html', {'kpi': {}})
    rmas = RMARequest.objects.filter(tenant=tenant)
    repairs = RepairOrder.objects.filter(tenant=tenant)
    regs = WarrantyRegistration.objects.filter(tenant=tenant)
    kpi = {
        'open_rmas': rmas.exclude(status__in=('rejected', 'cancelled')).count(),
        'pending_approval': rmas.filter(status='submitted').count(),
        'receipts_inspecting': ReturnReceipt.objects.filter(
            tenant=tenant, status='inspecting',
        ).count(),
        'open_repairs': repairs.filter(
            status__in=('draft', 'in_progress', 'on_hold'),
        ).count(),
        'active_warranties': regs.filter(status='active').count(),
        'open_chargebacks': SupplierChargeback.objects.filter(
            tenant=tenant,
        ).exclude(status__in=('recovered', 'written_off')).count(),
    }
    recent_rmas = rmas.select_related('customer').order_by('-request_date', '-id')[:8]
    open_repairs = (
        repairs.select_related('product')
        .filter(status__in=('draft', 'in_progress', 'on_hold'))
        .order_by('-id')[:8]
    )
    expiring = (
        regs.filter(status='active', end_date__isnull=False)
        .select_related('product', 'customer')
        .order_by('end_date')[:8]
    )
    return render(request, 'rma/index.html', {
        'kpi': kpi,
        'recent_rmas': recent_rmas,
        'open_repairs': open_repairs,
        'expiring': expiring,
    })


# ===========================================================================
# 18.1  RMA REASONS (catalog)
# ===========================================================================

@login_required
def reason_list_view(request):
    qs = RMAReason.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'rma/reasons/list.html', {
        'page_obj': page,
        'category_choices': RMAReason.CATEGORY_CHOICES,
    })


@login_required
def reason_create_view(request):
    if request.method == 'POST':
        form = RMAReasonForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Return reason "{obj.name}" created.')
            return redirect('rma:reason_list')
    else:
        form = RMAReasonForm(tenant=request.tenant)
    return render(request, 'rma/reasons/form.html', {'form': form, 'mode': 'create'})


@login_required
def reason_edit_view(request, pk):
    obj = get_object_or_404(RMAReason, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = RMAReasonForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Return reason updated.')
            return redirect('rma:reason_list')
    else:
        form = RMAReasonForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/reasons/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def reason_delete_view(request, pk):
    obj = get_object_or_404(RMAReason, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Return reason deleted.')
        except Exception as exc:  # PROTECT FK violation
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('rma:reason_list')


# ===========================================================================
# 18.1  RMA REQUESTS
# ===========================================================================

@login_required
def request_list_view(request):
    qs = RMARequest.objects.filter(tenant=request.tenant).select_related('customer')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(customer__name__icontains=q)
            | Q(customer_reference__icontains=q) | Q(reason_summary__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    action = request.GET.get('requested_action', '')
    if action:
        qs = qs.filter(requested_action=action)
    cust = request.GET.get('customer', '')
    if cust:
        qs = qs.filter(customer_id=cust)
    page = Paginator(qs.order_by('-request_date', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    from apps.sales.models import Customer
    return render(request, 'rma/requests/list.html', {
        'page_obj': page,
        'status_choices': RMARequest.STATUS_CHOICES,
        'action_choices': RMARequest.ACTION_CHOICES,
        'customers': Customer.objects.filter(tenant=request.tenant),
    })


@login_required
def request_create_view(request):
    if request.method == 'POST':
        form = RMARequestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'RMA {obj.code} created. Add lines next.')
            return redirect('rma:request_detail', pk=obj.pk)
    else:
        form = RMARequestForm(tenant=request.tenant)
    return render(request, 'rma/requests/form.html', {'form': form, 'mode': 'create'})


@login_required
def request_detail_view(request, pk):
    obj = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    lines = obj.lines.select_related('product', 'reason').order_by('line_no')
    approvals = obj.approvals.select_related('performed_by').order_by('-performed_at')
    receipts = obj.receipts.order_by('-id')
    line_form = RMALineForm(tenant=request.tenant)
    return render(request, 'rma/requests/detail.html', {
        'obj': obj, 'lines': lines, 'approvals': approvals,
        'receipts': receipts, 'line_form': line_form,
    })


@login_required
def request_edit_view(request, pk):
    obj = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if not obj.is_editable():
        messages.error(request, 'Only draft RMAs can be edited.')
        return redirect('rma:request_detail', pk=obj.pk)
    if request.method == 'POST':
        form = RMARequestForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'RMA updated.')
            return redirect('rma:request_detail', pk=obj.pk)
    else:
        form = RMARequestForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/requests/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def request_delete_view(request, pk):
    obj = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if obj.status != 'draft':
        messages.error(request, 'Only draft RMAs can be deleted. Cancel instead.')
        return redirect('rma:request_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'RMA deleted.')
        return redirect('rma:request_list')
    return redirect('rma:request_detail', pk=obj.pk)


# ---- RMA lines ----

@login_required
def rma_line_add_view(request, rma_pk):
    rma = get_object_or_404(RMARequest, pk=rma_pk, tenant=request.tenant)
    if not rma.is_editable():
        messages.error(request, 'Cannot add lines to a non-draft RMA.')
        return redirect('rma:request_detail', pk=rma.pk)
    if request.method == 'POST':
        form = RMALineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.rma = rma
            line.save()
            messages.success(request, 'Line added.')
            return redirect('rma:request_detail', pk=rma.pk)
    else:
        form = RMALineForm(tenant=request.tenant)
    return render(request, 'rma/requests/line_form.html', {
        'form': form, 'rma': rma, 'mode': 'create',
    })


@login_required
def rma_line_edit_view(request, pk):
    obj = get_object_or_404(RMALine, pk=pk, tenant=request.tenant)
    rma = obj.rma
    if not rma.is_editable():
        messages.error(request, 'Cannot edit lines on a non-draft RMA.')
        return redirect('rma:request_detail', pk=rma.pk)
    if request.method == 'POST':
        form = RMALineForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Line updated.')
            return redirect('rma:request_detail', pk=rma.pk)
    else:
        form = RMALineForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/requests/line_form.html', {
        'form': form, 'rma': rma, 'obj': obj, 'mode': 'edit',
    })


@login_required
def rma_line_delete_view(request, pk):
    obj = get_object_or_404(RMALine, pk=pk, tenant=request.tenant)
    rma = obj.rma
    if not rma.is_editable():
        messages.error(request, 'Cannot remove lines from a non-draft RMA.')
        return redirect('rma:request_detail', pk=rma.pk)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Line removed.')
        except Exception as exc:  # PROTECT FK violation (receipt/analysis exists)
            messages.error(request, f'Cannot remove line: {exc}')
    return redirect('rma:request_detail', pk=rma.pk)


# ---- RMA workflow ----

def _log_rma(rma, action, from_status, to_status, user, notes=''):
    RMAApproval.objects.create(
        tenant=rma.tenant, rma=rma, action=action,
        from_status=from_status, to_status=to_status,
        performed_by=user, notes=notes,
    )


@login_required
@tenant_admin_required
def request_submit_view(request, pk):
    rma = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not rma.can_submit():
            messages.error(request, 'RMA must be a draft with at least one line to submit.')
        else:
            prev = rma.status
            rma.status = 'submitted'
            rma.submitted_at = timezone.now()
            rma.save(update_fields=['status', 'submitted_at', 'updated_at'])
            _log_rma(rma, 'submit', prev, rma.status, request.user)
            messages.success(request, f'RMA {rma.code} submitted for approval.')
    return redirect('rma:request_detail', pk=rma.pk)


@login_required
@tenant_admin_required
def request_approve_view(request, pk):
    rma = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not rma.can_approve():
            messages.error(request, 'Only submitted RMAs can be approved.')
        else:
            prev = rma.status
            notes = request.POST.get('notes', '').strip()
            rma.status = 'approved'
            rma.decided_at = timezone.now()
            rma.decided_by = request.user
            rma.decision_notes = notes
            rma.save(update_fields=[
                'status', 'decided_at', 'decided_by', 'decision_notes', 'updated_at',
            ])
            _log_rma(rma, 'approve', prev, rma.status, request.user, notes)
            messages.success(request, f'RMA {rma.code} approved. A draft return receipt was created.')
    return redirect('rma:request_detail', pk=rma.pk)


@login_required
@tenant_admin_required
def request_reject_view(request, pk):
    rma = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        if not rma.can_reject():
            messages.error(request, 'Only submitted RMAs can be rejected.')
        elif not notes:
            messages.error(request, 'A rejection reason is required.')
        else:
            prev = rma.status
            rma.status = 'rejected'
            rma.decided_at = timezone.now()
            rma.decided_by = request.user
            rma.decision_notes = notes
            rma.save(update_fields=[
                'status', 'decided_at', 'decided_by', 'decision_notes', 'updated_at',
            ])
            _log_rma(rma, 'reject', prev, rma.status, request.user, notes)
            messages.success(request, f'RMA {rma.code} rejected.')
    return redirect('rma:request_detail', pk=rma.pk)


@login_required
@tenant_admin_required
def request_cancel_view(request, pk):
    rma = get_object_or_404(RMARequest, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not rma.can_cancel():
            messages.error(request, 'This RMA can no longer be cancelled.')
        else:
            prev = rma.status
            notes = request.POST.get('notes', '').strip()
            rma.status = 'cancelled'
            rma.save(update_fields=['status', 'updated_at'])
            _log_rma(rma, 'cancel', prev, rma.status, request.user, notes)
            messages.success(request, f'RMA {rma.code} cancelled.')
    return redirect('rma:request_detail', pk=rma.pk)


# ===========================================================================
# 18.2  RETURN RECEIPTS
# ===========================================================================

@login_required
def receipt_list_view(request):
    qs = ReturnReceipt.objects.filter(tenant=request.tenant).select_related(
        'rma__customer', 'warehouse',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(rma__code__icontains=q)
            | Q(tracking_number__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-received_date', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'rma/receipts/list.html', {
        'page_obj': page,
        'status_choices': ReturnReceipt.STATUS_CHOICES,
    })


@login_required
def receipt_create_view(request):
    if request.method == 'POST':
        form = ReturnReceiptForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.received_by = request.user
            obj.save()
            messages.success(request, f'Return receipt {obj.code} created.')
            return redirect('rma:receipt_detail', pk=obj.pk)
    else:
        form = ReturnReceiptForm(tenant=request.tenant)
    return render(request, 'rma/receipts/form.html', {'form': form, 'mode': 'create'})


@login_required
def receipt_detail_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    lines = obj.lines.select_related(
        'rma_line__product', 'stock_movement',
    ).order_by('id')
    line_form = ReturnReceiptLineForm(receipt=obj)
    return render(request, 'rma/receipts/detail.html', {
        'obj': obj, 'lines': lines, 'line_form': line_form,
    })


@login_required
def receipt_edit_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    if not obj.is_editable():
        messages.error(request, 'Only draft or inspecting receipts can be edited.')
        return redirect('rma:receipt_detail', pk=obj.pk)
    if request.method == 'POST':
        form = ReturnReceiptForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Return receipt updated.')
            return redirect('rma:receipt_detail', pk=obj.pk)
    else:
        form = ReturnReceiptForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/receipts/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def receipt_delete_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    if obj.status not in ('draft', 'cancelled'):
        messages.error(request, 'Only draft or cancelled receipts can be deleted.')
        return redirect('rma:receipt_detail', pk=obj.pk)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Return receipt deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('rma:receipt_list')
    return redirect('rma:receipt_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def receipt_start_inspection_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_start_inspection():
            messages.error(request, 'Receipt must be a draft with at least one line.')
        else:
            obj.status = 'inspecting'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Inspection started.')
    return redirect('rma:receipt_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def receipt_complete_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_complete():
            messages.error(request, 'Only a receipt under inspection can be completed.')
        else:
            obj.status = 'completed'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Return receipt completed.')
    return redirect('rma:receipt_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def receipt_cancel_view(request, pk):
    obj = get_object_or_404(ReturnReceipt, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_cancel():
            messages.error(request, 'This receipt can no longer be cancelled.')
        else:
            obj.status = 'cancelled'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Return receipt cancelled.')
    return redirect('rma:receipt_detail', pk=obj.pk)


# ---- Receipt lines ----

@login_required
def receipt_line_add_view(request, receipt_pk):
    receipt = get_object_or_404(ReturnReceipt, pk=receipt_pk, tenant=request.tenant)
    if not receipt.is_editable():
        messages.error(request, 'Cannot add lines to a completed/cancelled receipt.')
        return redirect('rma:receipt_detail', pk=receipt.pk)
    if request.method == 'POST':
        form = ReturnReceiptLineForm(request.POST, receipt=receipt)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.receipt = receipt
            line.inspected_by = request.user
            line.save()
            messages.success(request, 'Inspection line added.')
            return redirect('rma:receipt_detail', pk=receipt.pk)
    else:
        form = ReturnReceiptLineForm(receipt=receipt)
    return render(request, 'rma/receipts/line_form.html', {
        'form': form, 'receipt': receipt, 'mode': 'create',
    })


@login_required
def receipt_line_edit_view(request, pk):
    obj = get_object_or_404(ReturnReceiptLine, pk=pk, tenant=request.tenant)
    receipt = obj.receipt
    if not receipt.is_editable():
        messages.error(request, 'Cannot edit lines on a completed/cancelled receipt.')
        return redirect('rma:receipt_detail', pk=receipt.pk)
    if request.method == 'POST':
        form = ReturnReceiptLineForm(request.POST, instance=obj, receipt=receipt)
        if form.is_valid():
            line = form.save(commit=False)
            line.inspected_by = request.user
            line.save()
            messages.success(request, 'Inspection line updated.')
            return redirect('rma:receipt_detail', pk=receipt.pk)
    else:
        form = ReturnReceiptLineForm(instance=obj, receipt=receipt)
    return render(request, 'rma/receipts/line_form.html', {
        'form': form, 'receipt': receipt, 'obj': obj, 'mode': 'edit',
    })


@login_required
def receipt_line_delete_view(request, pk):
    obj = get_object_or_404(ReturnReceiptLine, pk=pk, tenant=request.tenant)
    receipt_pk = obj.receipt_id
    if not obj.receipt.is_editable():
        messages.error(request, 'Cannot remove lines from a completed/cancelled receipt.')
        return redirect('rma:receipt_detail', pk=receipt_pk)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Inspection line removed.')
        except Exception as exc:
            messages.error(request, f'Cannot remove line: {exc}')
    return redirect('rma:receipt_detail', pk=receipt_pk)


# ===========================================================================
# 18.3  REPAIR & REFURBISHMENT
# ===========================================================================

@login_required
def repair_list_view(request):
    qs = RepairOrder.objects.filter(tenant=request.tenant).select_related('product')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(product__name__icontains=q)
            | Q(problem_description__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    order_type = request.GET.get('order_type', '')
    if order_type:
        qs = qs.filter(order_type=order_type)
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'rma/repairs/list.html', {
        'page_obj': page,
        'status_choices': RepairOrder.STATUS_CHOICES,
        'type_choices': RepairOrder.TYPE_CHOICES,
    })


@login_required
def repair_create_view(request):
    if request.method == 'POST':
        form = RepairOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Repair order {obj.code} created.')
            return redirect('rma:repair_detail', pk=obj.pk)
    else:
        form = RepairOrderForm(tenant=request.tenant)
    return render(request, 'rma/repairs/form.html', {'form': form, 'mode': 'create'})


@login_required
def repair_detail_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    parts = obj.part_usages.select_related('part').order_by('id')
    labor = obj.labor_logs.select_related('employee').order_by('-work_date', '-id')
    part_form = RepairPartUsageForm(tenant=request.tenant)
    labor_form = RepairLaborLogForm(tenant=request.tenant)
    complete_form = RepairCompleteForm()
    return render(request, 'rma/repairs/detail.html', {
        'obj': obj, 'parts': parts, 'labor': labor,
        'part_form': part_form, 'labor_form': labor_form,
        'complete_form': complete_form,
    })


@login_required
def repair_edit_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if not obj.is_editable():
        messages.error(request, 'Cannot edit a completed/cancelled repair order.')
        return redirect('rma:repair_detail', pk=obj.pk)
    if request.method == 'POST':
        form = RepairOrderForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Repair order updated.')
            return redirect('rma:repair_detail', pk=obj.pk)
    else:
        form = RepairOrderForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/repairs/form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def repair_delete_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if obj.status not in ('draft', 'cancelled'):
        messages.error(request, 'Only draft or cancelled repair orders can be deleted.')
        return redirect('rma:repair_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Repair order deleted.')
        return redirect('rma:repair_list')
    return redirect('rma:repair_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def repair_start_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_start():
            messages.error(request, 'Only a draft repair order can be started.')
        else:
            obj.status = 'in_progress'
            obj.started_at = timezone.now()
            obj.save(update_fields=['status', 'started_at', 'updated_at'])
            messages.success(request, 'Repair started.')
    return redirect('rma:repair_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def repair_hold_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_hold():
            messages.error(request, 'Only an in-progress repair can be put on hold.')
        else:
            obj.status = 'on_hold'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Repair placed on hold.')
    return redirect('rma:repair_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def repair_resume_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_resume():
            messages.error(request, 'Only a repair on hold can be resumed.')
        else:
            obj.status = 'in_progress'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Repair resumed.')
    return redirect('rma:repair_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def repair_complete_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = RepairCompleteForm(request.POST)
        if not obj.can_complete():
            messages.error(request, 'Only an in-progress or on-hold repair can be completed.')
        elif not form.is_valid():
            messages.error(request, 'A resolution note is required to complete a repair.')
        else:
            obj.status = 'completed'
            obj.completed_at = timezone.now()
            obj.resolution_notes = form.cleaned_data['resolution_notes']
            obj.save(update_fields=[
                'status', 'completed_at', 'resolution_notes', 'updated_at',
            ])
            messages.success(request, f'Repair order {obj.code} completed.')
    return redirect('rma:repair_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def repair_cancel_view(request, pk):
    obj = get_object_or_404(RepairOrder, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_cancel():
            messages.error(request, 'This repair order can no longer be cancelled.')
        else:
            obj.status = 'cancelled'
            obj.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Repair order cancelled.')
    return redirect('rma:repair_detail', pk=obj.pk)


# ---- Repair parts ----

@login_required
def repair_part_add_view(request, repair_pk):
    repair = get_object_or_404(RepairOrder, pk=repair_pk, tenant=request.tenant)
    if not repair.is_editable():
        messages.error(request, 'Cannot add parts to a completed/cancelled repair order.')
        return redirect('rma:repair_detail', pk=repair.pk)
    if request.method == 'POST':
        form = RepairPartUsageForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            part = form.save(commit=False)
            part.tenant = request.tenant
            part.repair_order = repair
            part.save()
            messages.success(request, 'Part usage recorded.')
            return redirect('rma:repair_detail', pk=repair.pk)
    else:
        form = RepairPartUsageForm(tenant=request.tenant)
    return render(request, 'rma/repairs/part_form.html', {
        'form': form, 'repair': repair,
    })


@login_required
def repair_part_delete_view(request, pk):
    obj = get_object_or_404(RepairPartUsage, pk=pk, tenant=request.tenant)
    repair_pk = obj.repair_order_id
    if not obj.repair_order.is_editable():
        messages.error(request, 'Cannot remove parts from a completed/cancelled repair order.')
        return redirect('rma:repair_detail', pk=repair_pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Part usage removed.')
    return redirect('rma:repair_detail', pk=repair_pk)


# ---- Repair labor ----

@login_required
def repair_labor_add_view(request, repair_pk):
    repair = get_object_or_404(RepairOrder, pk=repair_pk, tenant=request.tenant)
    if not repair.is_editable():
        messages.error(request, 'Cannot log labor on a completed/cancelled repair order.')
        return redirect('rma:repair_detail', pk=repair.pk)
    if request.method == 'POST':
        form = RepairLaborLogForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            log = form.save(commit=False)
            log.tenant = request.tenant
            log.repair_order = repair
            log.save()
            messages.success(request, 'Labor logged.')
            return redirect('rma:repair_detail', pk=repair.pk)
    else:
        form = RepairLaborLogForm(tenant=request.tenant)
    return render(request, 'rma/repairs/labor_form.html', {
        'form': form, 'repair': repair,
    })


@login_required
def repair_labor_delete_view(request, pk):
    obj = get_object_or_404(RepairLaborLog, pk=pk, tenant=request.tenant)
    repair_pk = obj.repair_order_id
    if not obj.repair_order.is_editable():
        messages.error(request, 'Cannot remove labor from a completed/cancelled repair order.')
        return redirect('rma:repair_detail', pk=repair_pk)
    if request.method == 'POST':
        from .services.repair import recompute_repair_costs
        repair = obj.repair_order
        obj.delete()
        recompute_repair_costs(repair)
        messages.success(request, 'Labor entry removed.')
    return redirect('rma:repair_detail', pk=repair_pk)


# ===========================================================================
# 18.4  WARRANTY POLICIES
# ===========================================================================

@login_required
def policy_list_view(request):
    qs = WarrantyPolicy.objects.filter(tenant=request.tenant).select_related('product')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    coverage = request.GET.get('coverage_type', '')
    if coverage:
        qs = qs.filter(coverage_type=coverage)
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'rma/warranty/policy_list.html', {
        'page_obj': page,
        'coverage_choices': WarrantyPolicy.COVERAGE_CHOICES,
    })


@login_required
def policy_create_view(request):
    if request.method == 'POST':
        form = WarrantyPolicyForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Warranty policy {obj.code} created.')
            return redirect('rma:policy_list')
    else:
        form = WarrantyPolicyForm(tenant=request.tenant)
    return render(request, 'rma/warranty/policy_form.html', {'form': form, 'mode': 'create'})


@login_required
def policy_edit_view(request, pk):
    obj = get_object_or_404(WarrantyPolicy, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = WarrantyPolicyForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warranty policy updated.')
            return redirect('rma:policy_list')
    else:
        form = WarrantyPolicyForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/warranty/policy_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def policy_delete_view(request, pk):
    obj = get_object_or_404(WarrantyPolicy, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Warranty policy deleted.')
        except Exception as exc:  # PROTECT - registrations exist
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('rma:policy_list')


# ===========================================================================
# 18.4  WARRANTY REGISTRATIONS
# ===========================================================================

@login_required
def registration_list_view(request):
    qs = WarrantyRegistration.objects.filter(tenant=request.tenant).select_related(
        'product', 'customer', 'policy',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(serial_number__icontains=q)
            | Q(customer__name__icontains=q) | Q(product__name__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    expiring = request.GET.get('expiring', '')
    if expiring == 'soon':
        today = timezone.now().date()
        qs = qs.filter(
            status='active', end_date__isnull=False,
            end_date__gte=today, end_date__lte=today + timezone.timedelta(days=30),
        )
    page = Paginator(qs.order_by('-start_date', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'rma/warranty/registration_list.html', {
        'page_obj': page,
        'status_choices': WarrantyRegistration.STATUS_CHOICES,
    })


@login_required
def registration_create_view(request):
    if request.method == 'POST':
        form = WarrantyRegistrationForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Warranty registration {obj.code} created.')
            return redirect('rma:registration_detail', pk=obj.pk)
    else:
        form = WarrantyRegistrationForm(tenant=request.tenant)
    return render(request, 'rma/warranty/registration_form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def registration_detail_view(request, pk):
    obj = get_object_or_404(WarrantyRegistration, pk=pk, tenant=request.tenant)
    claims = obj.claims.order_by('-claim_date', '-id')
    return render(request, 'rma/warranty/registration_detail.html', {
        'obj': obj, 'claims': claims,
    })


@login_required
def registration_edit_view(request, pk):
    obj = get_object_or_404(WarrantyRegistration, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = WarrantyRegistrationForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warranty registration updated.')
            return redirect('rma:registration_detail', pk=obj.pk)
    else:
        form = WarrantyRegistrationForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/warranty/registration_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def registration_delete_view(request, pk):
    obj = get_object_or_404(WarrantyRegistration, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Warranty registration deleted.')
        except Exception as exc:  # PROTECT - claims exist
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('rma:registration_list')
    return redirect('rma:registration_detail', pk=obj.pk)


# ===========================================================================
# 18.4  WARRANTY CLAIMS
# ===========================================================================

@login_required
def claim_list_view(request):
    qs = WarrantyClaim.objects.filter(tenant=request.tenant).select_related(
        'registration__product', 'registration__customer',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(registration__code__icontains=q)
            | Q(defect_description__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    resolution = request.GET.get('resolution', '')
    if resolution:
        qs = qs.filter(resolution=resolution)
    page = Paginator(qs.order_by('-claim_date', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'rma/warranty/claim_list.html', {
        'page_obj': page,
        'status_choices': WarrantyClaim.STATUS_CHOICES,
        'resolution_choices': WarrantyClaim.RESOLUTION_CHOICES,
    })


@login_required
def claim_create_view(request):
    if request.method == 'POST':
        form = WarrantyClaimForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Warranty claim {obj.code} created.')
            return redirect('rma:claim_detail', pk=obj.pk)
    else:
        form = WarrantyClaimForm(tenant=request.tenant)
    return render(request, 'rma/warranty/claim_form.html', {'form': form, 'mode': 'create'})


@login_required
def claim_detail_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    return render(request, 'rma/warranty/claim_detail.html', {'obj': obj})


@login_required
def claim_edit_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if obj.status not in ('submitted', 'validated'):
        messages.error(request, 'Only submitted or validated claims can be edited.')
        return redirect('rma:claim_detail', pk=obj.pk)
    if request.method == 'POST':
        form = WarrantyClaimForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warranty claim updated.')
            return redirect('rma:claim_detail', pk=obj.pk)
    else:
        form = WarrantyClaimForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/warranty/claim_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def claim_delete_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if obj.status != 'submitted':
        messages.error(request, 'Only submitted claims can be deleted.')
        return redirect('rma:claim_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Warranty claim deleted.')
        return redirect('rma:claim_list')
    return redirect('rma:claim_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def claim_validate_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_validate():
            messages.error(request, 'Only a submitted claim can be validated.')
        else:
            obj.status = 'validated'
            obj.validation_notes = request.POST.get('notes', '').strip()
            obj.save(update_fields=['status', 'validation_notes', 'updated_at'])
            messages.success(request, f'Claim {obj.code} validated.')
    return redirect('rma:claim_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def claim_approve_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_approve():
            messages.error(request, 'Only a validated claim can be approved.')
        else:
            obj.status = 'approved'
            obj.decided_by = request.user
            obj.decided_at = timezone.now()
            obj.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
            msg = f'Claim {obj.code} approved.'
            if obj.resolution == 'replace':
                msg += ' A draft replacement sales order was created.'
            messages.success(request, msg)
    return redirect('rma:claim_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def claim_reject_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        if not obj.can_reject():
            messages.error(request, 'Only a submitted or validated claim can be rejected.')
        elif not notes:
            messages.error(request, 'A rejection reason is required.')
        else:
            obj.status = 'rejected'
            obj.decided_by = request.user
            obj.decided_at = timezone.now()
            obj.validation_notes = notes
            obj.save(update_fields=[
                'status', 'decided_by', 'decided_at', 'validation_notes', 'updated_at',
            ])
            messages.success(request, f'Claim {obj.code} rejected.')
    return redirect('rma:claim_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def claim_fulfill_view(request, pk):
    obj = get_object_or_404(WarrantyClaim, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if not obj.can_fulfill():
            messages.error(request, 'Only an approved claim can be fulfilled.')
        else:
            obj.status = 'fulfilled'
            obj.save(update_fields=['status', 'updated_at'])
            # Mark the registration as claimed once a claim is fulfilled.
            reg = obj.registration
            if reg.status == 'active':
                reg.status = 'claimed'
                reg.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Claim {obj.code} fulfilled.')
    return redirect('rma:claim_detail', pk=obj.pk)


# ===========================================================================
# 18.5  FAILURE MODES (catalog)
# ===========================================================================

@login_required
def failure_mode_list_view(request):
    qs = FailureMode.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'rma/analytics/failure_mode_list.html', {
        'page_obj': page,
        'category_choices': FailureMode.CATEGORY_CHOICES,
    })


@login_required
def failure_mode_create_view(request):
    if request.method == 'POST':
        form = FailureModeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Failure mode "{obj.name}" created.')
            return redirect('rma:failure_mode_list')
    else:
        form = FailureModeForm(tenant=request.tenant)
    return render(request, 'rma/analytics/failure_mode_form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def failure_mode_edit_view(request, pk):
    obj = get_object_or_404(FailureMode, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = FailureModeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Failure mode updated.')
            return redirect('rma:failure_mode_list')
    else:
        form = FailureModeForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/analytics/failure_mode_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def failure_mode_delete_view(request, pk):
    obj = get_object_or_404(FailureMode, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Failure mode deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('rma:failure_mode_list')


# ===========================================================================
# 18.5  ROOT CAUSE CATEGORIES (catalog)
# ===========================================================================

@login_required
def root_cause_list_view(request):
    qs = RootCauseCategory.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    area = request.GET.get('responsible_area', '')
    if area:
        qs = qs.filter(responsible_area=area)
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'rma/analytics/root_cause_list.html', {
        'page_obj': page,
        'area_choices': RootCauseCategory.AREA_CHOICES,
    })


@login_required
def root_cause_create_view(request):
    if request.method == 'POST':
        form = RootCauseCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Root cause category "{obj.name}" created.')
            return redirect('rma:root_cause_list')
    else:
        form = RootCauseCategoryForm(tenant=request.tenant)
    return render(request, 'rma/analytics/root_cause_form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def root_cause_edit_view(request, pk):
    obj = get_object_or_404(RootCauseCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = RootCauseCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Root cause category updated.')
            return redirect('rma:root_cause_list')
    else:
        form = RootCauseCategoryForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/analytics/root_cause_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def root_cause_delete_view(request, pk):
    obj = get_object_or_404(RootCauseCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Root cause category deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('rma:root_cause_list')


# ===========================================================================
# 18.5  RETURN ANALYSES
# ===========================================================================

@login_required
def analysis_list_view(request):
    qs = ReturnAnalysis.objects.filter(tenant=request.tenant).select_related(
        'rma_line__rma', 'rma_line__product', 'failure_mode',
        'root_cause_category', 'supplier',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(rma_line__rma__code__icontains=q)
            | Q(analysis_notes__icontains=q),
        )
    fm = request.GET.get('failure_mode', '')
    if fm:
        qs = qs.filter(failure_mode_id=fm)
    rc = request.GET.get('root_cause_category', '')
    if rc:
        qs = qs.filter(root_cause_category_id=rc)
    page = Paginator(qs.order_by('-analyzed_at', '-id'), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return render(request, 'rma/analytics/analysis_list.html', {
        'page_obj': page,
        'failure_modes': FailureMode.objects.filter(tenant=request.tenant, is_active=True),
        'root_causes': RootCauseCategory.objects.filter(tenant=request.tenant, is_active=True),
    })


@login_required
def analysis_create_view(request):
    if request.method == 'POST':
        form = ReturnAnalysisForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.analyzed_by = request.user
            obj.save()
            messages.success(request, f'Return analysis {obj.code} created.')
            return redirect('rma:analysis_detail', pk=obj.pk)
    else:
        form = ReturnAnalysisForm(tenant=request.tenant)
    return render(request, 'rma/analytics/analysis_form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def analysis_detail_view(request, pk):
    obj = get_object_or_404(ReturnAnalysis, pk=pk, tenant=request.tenant)
    chargebacks = obj.chargebacks.select_related('supplier').order_by('-id')
    return render(request, 'rma/analytics/analysis_detail.html', {
        'obj': obj, 'chargebacks': chargebacks,
    })


@login_required
def analysis_edit_view(request, pk):
    obj = get_object_or_404(ReturnAnalysis, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ReturnAnalysisForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Return analysis updated.')
            return redirect('rma:analysis_detail', pk=obj.pk)
    else:
        form = ReturnAnalysisForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/analytics/analysis_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def analysis_delete_view(request, pk):
    obj = get_object_or_404(ReturnAnalysis, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Return analysis deleted.')
        except Exception as exc:  # PROTECT - chargebacks exist
            messages.error(request, f'Cannot delete: {exc}')
        return redirect('rma:analysis_list')
    return redirect('rma:analysis_detail', pk=obj.pk)


# ===========================================================================
# 18.5  SUPPLIER CHARGEBACKS
# ===========================================================================

@login_required
def chargeback_list_view(request):
    qs = SupplierChargeback.objects.filter(tenant=request.tenant).select_related(
        'supplier', 'analysis',
    )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(supplier__name__icontains=q)
            | Q(reference__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    totals = qs.aggregate(total=Sum('amount'))
    return render(request, 'rma/analytics/chargeback_list.html', {
        'page_obj': page,
        'status_choices': SupplierChargeback.STATUS_CHOICES,
        'total_amount': totals['total'] or 0,
    })


@login_required
def chargeback_create_view(request):
    if request.method == 'POST':
        form = SupplierChargebackForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Supplier chargeback {obj.code} created.')
            return redirect('rma:chargeback_detail', pk=obj.pk)
    else:
        form = SupplierChargebackForm(tenant=request.tenant)
    return render(request, 'rma/analytics/chargeback_form.html', {
        'form': form, 'mode': 'create',
    })


@login_required
def chargeback_detail_view(request, pk):
    obj = get_object_or_404(SupplierChargeback, pk=pk, tenant=request.tenant)
    from .services.chargeback import _TRANSITIONS
    next_statuses = sorted(_TRANSITIONS.get(obj.status, set()))
    return render(request, 'rma/analytics/chargeback_detail.html', {
        'obj': obj, 'next_statuses': next_statuses,
    })


@login_required
def chargeback_edit_view(request, pk):
    obj = get_object_or_404(SupplierChargeback, pk=pk, tenant=request.tenant)
    if obj.status not in ('draft', 'pending'):
        messages.error(request, 'Only draft or pending chargebacks can be edited.')
        return redirect('rma:chargeback_detail', pk=obj.pk)
    if request.method == 'POST':
        form = SupplierChargebackForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier chargeback updated.')
            return redirect('rma:chargeback_detail', pk=obj.pk)
    else:
        form = SupplierChargebackForm(instance=obj, tenant=request.tenant)
    return render(request, 'rma/analytics/chargeback_form.html', {
        'form': form, 'obj': obj, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def chargeback_delete_view(request, pk):
    obj = get_object_or_404(SupplierChargeback, pk=pk, tenant=request.tenant)
    if obj.status not in ('draft',):
        messages.error(request, 'Only draft chargebacks can be deleted.')
        return redirect('rma:chargeback_detail', pk=obj.pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Supplier chargeback deleted.')
        return redirect('rma:chargeback_list')
    return redirect('rma:chargeback_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def chargeback_transition_view(request, pk):
    obj = get_object_or_404(SupplierChargeback, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        to_status = request.POST.get('to_status', '')
        try:
            apply_transition(obj, to_status, performed_by=request.user)
            messages.success(request, f'Chargeback {obj.code} moved to {obj.get_status_display()}.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect('rma:chargeback_detail', pk=obj.pk)
