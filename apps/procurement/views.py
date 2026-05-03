"""Module 9 - Procurement & Supplier Portal views.

Read-only surfaces use ``TenantRequiredMixin`` (Lesson L-10).
State-changing surfaces (workflow transitions, deletes, admin CRUD) use
``TenantAdminRequiredMixin``. Supplier-portal pages use the in-module
``SupplierPortalRequiredMixin`` and additionally scope every queryset to
``request.user.supplier_company``.

Workflow transitions use a conditional ``UPDATE ... WHERE status IN (...)``
for race safety (Lessons L-03, L-12).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services.blanket import consume_release, reverse_release
from .services.conversion import convert_pr_to_po, convert_quotation_to_po
from .services.po_revision import next_revision_number, snapshot_po
from .services.scorecard import compute_scorecard


PAGE_SIZE = 25


def _paginate(qs, request, size=PAGE_SIZE):
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


# ============================================================================
# Supplier-portal mixin
# ============================================================================

class SupplierPortalRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Guard: user must be authenticated, role='supplier', and have supplier_company set."""

    raise_exception = False

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        return u.role == 'supplier' and u.supplier_company_id is not None

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                'This page is for external supplier portal users only.',
            )
            return redirect('dashboard')
        return super().handle_no_permission()


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'procurement/index.html'

    def get(self, request):
        t = request.tenant
        ctx = {
            'supplier_count': models.Supplier.objects.filter(tenant=t, is_active=True).count(),
            'open_pos': models.PurchaseOrder.objects.filter(
                tenant=t,
                status__in=('draft', 'submitted', 'approved', 'acknowledged', 'in_progress'),
            ).count(),
            'open_rfqs': models.RequestForQuotation.objects.filter(
                tenant=t, status__in=('draft', 'issued'),
            ).count(),
            'pending_invoices': models.SupplierInvoice.objects.filter(
                tenant=t, status__in=('submitted', 'under_review'),
            ).count(),
            'open_asns': models.SupplierASN.objects.filter(
                tenant=t, status__in=('submitted', 'in_transit'),
            ).count(),
            'active_blankets': models.BlanketOrder.objects.filter(
                tenant=t, status='active',
            ).count(),
            'recent_pos': models.PurchaseOrder.objects.filter(tenant=t).select_related(
                'supplier',
            ).order_by('-id')[:8],
            'recent_invoices': models.SupplierInvoice.objects.filter(tenant=t).select_related(
                'supplier',
            ).order_by('-id')[:8],
            'top_suppliers': models.SupplierScorecard.objects.filter(
                tenant=t,
            ).select_related('supplier').order_by('rank', '-overall_score')[:5],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 9.1  Suppliers
# ============================================================================

class SupplierListView(TenantRequiredMixin, View):
    template_name = 'procurement/suppliers/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.Supplier.objects.filter(tenant=t)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(email__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        approved = request.GET.get('approved', '')
        if approved == 'yes':
            qs = qs.filter(is_approved=True)
        elif approved == 'no':
            qs = qs.filter(is_approved=False)
        risk = request.GET.get('risk', '')
        if risk:
            qs = qs.filter(risk_rating=risk)
        page = _paginate(qs.order_by('code'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'active_filter': active, 'approved_filter': approved, 'risk_filter': risk,
            'risk_choices': models.Supplier.RISK_CHOICES,
        })


class SupplierCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/suppliers/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SupplierForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.SupplierForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Supplier {obj.code} created.')
            return redirect('procurement:supplier_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class SupplierDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/suppliers/detail.html'

    def get(self, request, pk):
        sup = get_object_or_404(models.Supplier, pk=pk, tenant=request.tenant)
        contacts = sup.contacts.filter(is_active=True)
        recent_pos = sup.purchase_orders.order_by('-id')[:8]
        latest_scorecard = sup.scorecards.order_by('-period_end').first()
        return render(request, self.template_name, {
            'sup': sup, 'contacts': contacts,
            'recent_pos': recent_pos, 'latest_scorecard': latest_scorecard,
            'contact_form': forms.SupplierContactForm(tenant=request.tenant),
        })


class SupplierEditView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/suppliers/form.html'

    def get(self, request, pk):
        sup = get_object_or_404(models.Supplier, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.SupplierForm(instance=sup, tenant=request.tenant),
            'sup': sup, 'is_create': False,
        })

    def post(self, request, pk):
        sup = get_object_or_404(models.Supplier, pk=pk, tenant=request.tenant)
        form = forms.SupplierForm(request.POST, instance=sup, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier updated.')
            return redirect('procurement:supplier_detail', pk=sup.pk)
        return render(request, self.template_name, {'form': form, 'sup': sup, 'is_create': False})


class SupplierDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        sup = get_object_or_404(models.Supplier, pk=pk, tenant=request.tenant)
        try:
            sup.delete()
            messages.success(request, 'Supplier deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete supplier: {e}')
        return redirect('procurement:supplier_list')

    def get(self, request, pk):
        return redirect('procurement:supplier_list')


class SupplierContactCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        sup = get_object_or_404(models.Supplier, pk=pk, tenant=request.tenant)
        form = forms.SupplierContactForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            c = form.save(commit=False)
            c.tenant = request.tenant
            c.supplier = sup
            c.save()
            messages.success(request, 'Contact added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:supplier_detail', pk=pk)


class SupplierContactDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        c = get_object_or_404(models.SupplierContact, pk=pk, tenant=request.tenant)
        sup_pk = c.supplier_id
        c.delete()
        messages.success(request, 'Contact removed.')
        return redirect('procurement:supplier_detail', pk=sup_pk)


# ============================================================================
# 9.1  Purchase Orders
# ============================================================================

class POListView(TenantRequiredMixin, View):
    template_name = 'procurement/po/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.PurchaseOrder.objects.filter(tenant=t).select_related('supplier')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(po_number__icontains=q)
                | Q(supplier__code__icontains=q)
                | Q(supplier__name__icontains=q)
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        priority = request.GET.get('priority', '')
        if priority:
            qs = qs.filter(priority=priority)
        supplier_pk = request.GET.get('supplier', '')
        if supplier_pk:
            qs = qs.filter(supplier_id=supplier_pk)
        page = _paginate(qs.order_by('-order_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q,
            'status_filter': status, 'priority_filter': priority,
            'supplier_filter': supplier_pk,
            'status_choices': models.PurchaseOrder.STATUS_CHOICES,
            'priority_choices': models.PurchaseOrder.PRIORITY_CHOICES,
            'suppliers': models.Supplier.objects.filter(tenant=t),
        })


class POCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/po/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.PurchaseOrderForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.PurchaseOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            po = form.save(commit=False)
            po.tenant = request.tenant
            po.created_by = request.user
            po.save()
            messages.success(request, f'PO {po.po_number} created. Add lines next.')
            return redirect('procurement:po_detail', pk=po.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class PODetailView(TenantRequiredMixin, View):
    template_name = 'procurement/po/detail.html'

    def get(self, request, pk):
        po = get_object_or_404(
            models.PurchaseOrder.objects.select_related('supplier', 'created_by', 'approved_by'),
            pk=pk, tenant=request.tenant,
        )
        lines = po.lines.select_related('product').order_by('line_number')
        revisions = po.revisions.select_related('changed_by').order_by('-revision_number')[:10]
        approvals = po.approvals.select_related('approver').order_by('-decided_at')[:10]
        asns = po.asns.order_by('-id')
        invoices = po.supplier_invoices.order_by('-id')
        line_form = forms.PurchaseOrderLineForm(tenant=request.tenant)
        return render(request, self.template_name, {
            'po': po, 'lines': lines, 'revisions': revisions, 'approvals': approvals,
            'asns': asns, 'invoices': invoices, 'line_form': line_form,
        })


class POEditView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/po/form.html'

    def get(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if not po.is_editable():
            messages.error(request, 'Only draft / rejected POs can be edited.')
            return redirect('procurement:po_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.PurchaseOrderForm(instance=po, tenant=request.tenant),
            'po': po, 'is_create': False,
        })

    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if not po.is_editable():
            messages.error(request, 'Only draft / rejected POs can be edited.')
            return redirect('procurement:po_detail', pk=pk)
        form = forms.PurchaseOrderForm(request.POST, instance=po, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'PO updated.')
            return redirect('procurement:po_detail', pk=po.pk)
        return render(request, self.template_name, {'form': form, 'po': po, 'is_create': False})


class PODeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if po.status not in ('draft', 'rejected', 'cancelled'):
            messages.error(request, 'Only draft / rejected / cancelled POs can be deleted.')
            return redirect('procurement:po_detail', pk=pk)
        try:
            po.delete()
            messages.success(request, 'PO deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete PO: {e}')
            return redirect('procurement:po_detail', pk=pk)
        return redirect('procurement:po_list')

    def get(self, request, pk):
        return redirect('procurement:po_detail', pk=pk)


class POLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if not po.is_editable():
            messages.error(request, 'PO not editable in current status.')
            return redirect('procurement:po_detail', pk=pk)
        form = forms.PurchaseOrderLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.po = po
            line.save()
            po.recompute_totals()
            messages.success(request, 'Line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:po_detail', pk=pk)


class POLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.PurchaseOrderLine, pk=pk, tenant=request.tenant)
        if not line.po.is_editable():
            messages.error(request, 'PO not editable in current status.')
            return redirect('procurement:po_detail', pk=line.po_id)
        po = line.po
        line.delete()
        po.recompute_totals()
        messages.success(request, 'Line removed.')
        return redirect('procurement:po_detail', pk=po.pk)


class POSubmitView(TenantRequiredMixin, View):
    """draft -> submitted (any tenant user can submit their own draft)."""

    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if not po.lines.exists():
            messages.error(request, 'Add at least one line before submitting.')
            return redirect('procurement:po_detail', pk=pk)
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('draft',), to_state='submitted',
        )
        if not ok:
            messages.error(request, 'PO is not in draft status.')
        else:
            messages.success(request, 'PO submitted for approval.')
        return redirect('procurement:po_detail', pk=pk)


class POApproveView(TenantAdminRequiredMixin, View):
    """submitted -> approved."""

    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('submitted',), to_state='approved',
            extra_fields={'approved_by': request.user, 'approved_at': timezone.now()},
        )
        if not ok:
            messages.error(request, 'PO is not pending approval.')
            return redirect('procurement:po_detail', pk=pk)
        models.PurchaseOrderApproval.all_objects.create(
            tenant=request.tenant, po=po, approver=request.user,
            decision='approved', comments=request.POST.get('comments', ''),
        )
        messages.success(request, 'PO approved.')
        return redirect('procurement:po_detail', pk=pk)


class PORejectView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        comments = (request.POST.get('comments') or '').strip()
        if not comments:
            messages.error(request, 'Reason is required when rejecting.')
            return redirect('procurement:po_detail', pk=pk)
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('submitted',), to_state='rejected',
        )
        if not ok:
            messages.error(request, 'PO is not pending approval.')
            return redirect('procurement:po_detail', pk=pk)
        models.PurchaseOrderApproval.all_objects.create(
            tenant=request.tenant, po=po, approver=request.user,
            decision='rejected', comments=comments,
        )
        messages.success(request, 'PO rejected.')
        return redirect('procurement:po_detail', pk=pk)


class POAcknowledgeView(TenantRequiredMixin, View):
    """approved -> acknowledged. Supplier user OR tenant admin."""

    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        u = request.user
        is_supplier = (u.role == 'supplier' and u.supplier_company_id == po.supplier_id)
        if not (u.is_tenant_admin or u.is_superuser or is_supplier):
            messages.error(request, 'Only the supplier or a tenant admin can acknowledge.')
            return redirect('procurement:po_detail', pk=pk)
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('approved',), to_state='acknowledged',
            extra_fields={
                'acknowledged_by': request.user,
                'acknowledged_at': timezone.now(),
            },
        )
        if not ok:
            messages.error(request, 'PO is not in approved status.')
        else:
            messages.success(request, 'PO acknowledged.')
        return redirect('procurement:po_detail', pk=pk)


class POCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('received',), to_state='closed',
        )
        if not ok:
            messages.error(request, 'PO can only be closed from received status.')
        else:
            messages.success(request, 'PO closed.')
        return redirect('procurement:po_detail', pk=pk)


class POCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.PurchaseOrder, pk, request.tenant,
            from_states=('draft', 'submitted', 'approved', 'acknowledged', 'in_progress'),
            to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'PO cannot be cancelled in its current state.')
        else:
            messages.success(request, 'PO cancelled.')
        return redirect('procurement:po_detail', pk=pk)


class POReviseView(TenantAdminRequiredMixin, View):
    """Snapshot the current PO into a new revision and revert to draft for edits."""

    def post(self, request, pk):
        po = get_object_or_404(models.PurchaseOrder, pk=pk, tenant=request.tenant)
        if po.status not in ('draft', 'submitted', 'approved', 'rejected'):
            messages.error(request, 'Only non-finalised POs can be revised.')
            return redirect('procurement:po_detail', pk=pk)
        summary = (request.POST.get('change_summary') or '').strip() or 'Revision'
        with transaction.atomic():
            models.PurchaseOrderRevision.all_objects.create(
                tenant=request.tenant,
                po=po,
                revision_number=next_revision_number(po),
                change_summary=summary,
                changed_by=request.user,
                snapshot_json=snapshot_po(po),
            )
            models.PurchaseOrder.all_objects.filter(pk=po.pk).update(status='draft')
        messages.success(request, 'PO revised - snapshot captured, status reset to draft.')
        return redirect('procurement:po_detail', pk=pk)


# ============================================================================
# 9.2  RFQs
# ============================================================================

class RFQListView(TenantRequiredMixin, View):
    template_name = 'procurement/rfq/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.RequestForQuotation.objects.filter(tenant=t)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(rfq_number__icontains=q) | Q(title__icontains=q))
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.RequestForQuotation.STATUS_CHOICES,
        })


class RFQCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/rfq/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.RFQForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.RFQForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.created_by = request.user
            r.save()
            messages.success(request, f'RFQ {r.rfq_number} created.')
            return redirect('procurement:rfq_detail', pk=r.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class RFQDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/rfq/detail.html'

    def get(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        lines = rfq.lines.select_related('product').order_by('line_number')
        invited = rfq.invited_suppliers.select_related('supplier')
        quotations = rfq.quotations.select_related('supplier').order_by('-quote_date')
        award = getattr(rfq, 'award', None)
        return render(request, self.template_name, {
            'rfq': rfq, 'lines': lines, 'invited': invited,
            'quotations': quotations, 'award': award,
            'line_form': forms.RFQLineForm(tenant=request.tenant),
            'supplier_form': forms.RFQSupplierForm(tenant=request.tenant),
            'award_form': forms.QuotationAwardForm(tenant=request.tenant, rfq=rfq),
        })


class RFQEditView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/rfq/form.html'

    def get(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if rfq.status != 'draft':
            messages.error(request, 'Only draft RFQs can be edited.')
            return redirect('procurement:rfq_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.RFQForm(instance=rfq, tenant=request.tenant),
            'rfq': rfq, 'is_create': False,
        })

    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if rfq.status != 'draft':
            messages.error(request, 'Only draft RFQs can be edited.')
            return redirect('procurement:rfq_detail', pk=pk)
        form = forms.RFQForm(request.POST, instance=rfq, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'RFQ updated.')
            return redirect('procurement:rfq_detail', pk=rfq.pk)
        return render(request, self.template_name, {'form': form, 'rfq': rfq, 'is_create': False})


class RFQDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if rfq.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft / cancelled RFQs can be deleted.')
            return redirect('procurement:rfq_detail', pk=pk)
        rfq.delete()
        messages.success(request, 'RFQ deleted.')
        return redirect('procurement:rfq_list')

    def get(self, request, pk):
        return redirect('procurement:rfq_detail', pk=pk)


class RFQLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if rfq.status != 'draft':
            messages.error(request, 'Only draft RFQs can be modified.')
            return redirect('procurement:rfq_detail', pk=pk)
        form = forms.RFQLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.rfq = rfq
            line.save()
            messages.success(request, 'Line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:rfq_detail', pk=pk)


class RFQLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.RFQLine, pk=pk, tenant=request.tenant)
        if line.rfq.status != 'draft':
            messages.error(request, 'Only draft RFQs can be modified.')
            return redirect('procurement:rfq_detail', pk=line.rfq_id)
        rfq_pk = line.rfq_id
        line.delete()
        messages.success(request, 'Line removed.')
        return redirect('procurement:rfq_detail', pk=rfq_pk)


class RFQSupplierInviteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if rfq.status not in ('draft', 'issued'):
            messages.error(request, 'Cannot invite suppliers once the RFQ is closed.')
            return redirect('procurement:rfq_detail', pk=pk)
        form = forms.RFQSupplierForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            sup = form.cleaned_data['supplier']
            invited, created = models.RFQSupplier.all_objects.get_or_create(
                tenant=request.tenant, rfq=rfq, supplier=sup,
                defaults={'participation_status': 'invited'},
            )
            if created:
                messages.success(request, f'Supplier {sup.code} invited.')
            else:
                messages.info(request, 'That supplier is already invited.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:rfq_detail', pk=pk)


class RFQSupplierRemoveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        invite = get_object_or_404(models.RFQSupplier, pk=pk, tenant=request.tenant)
        if invite.rfq.status != 'draft':
            messages.error(request, 'Only draft RFQs can be modified.')
            return redirect('procurement:rfq_detail', pk=invite.rfq_id)
        rfq_pk = invite.rfq_id
        invite.delete()
        messages.success(request, 'Invitation removed.')
        return redirect('procurement:rfq_detail', pk=rfq_pk)


class RFQIssueView(TenantAdminRequiredMixin, View):
    """draft -> issued."""

    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        if not rfq.lines.exists():
            messages.error(request, 'Add at least one line before issuing.')
            return redirect('procurement:rfq_detail', pk=pk)
        if not rfq.invited_suppliers.exists():
            messages.error(request, 'Invite at least one supplier before issuing.')
            return redirect('procurement:rfq_detail', pk=pk)
        ok = _atomic_status_transition(
            models.RequestForQuotation, pk, request.tenant,
            from_states=('draft',), to_state='issued',
            extra_fields={'issued_date': timezone.now().date()},
        )
        if not ok:
            messages.error(request, 'RFQ is not in draft status.')
        else:
            messages.success(request, 'RFQ issued.')
        return redirect('procurement:rfq_detail', pk=pk)


class RFQCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.RequestForQuotation, pk, request.tenant,
            from_states=('issued',), to_state='closed',
        )
        if not ok:
            messages.error(request, 'Only issued RFQs can be closed.')
        else:
            messages.success(request, 'RFQ closed.')
        return redirect('procurement:rfq_detail', pk=pk)


class RFQAwardView(TenantAdminRequiredMixin, View):
    """closed -> awarded. Optionally drafts a PO from the winning quote."""

    def post(self, request, pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=pk, tenant=request.tenant)
        form = forms.QuotationAwardForm(request.POST, tenant=request.tenant, rfq=rfq)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
            return redirect('procurement:rfq_detail', pk=pk)
        if hasattr(rfq, 'award'):
            messages.error(request, 'RFQ already awarded.')
            return redirect('procurement:rfq_detail', pk=pk)
        with transaction.atomic():
            ok = _atomic_status_transition(
                models.RequestForQuotation, pk, request.tenant,
                from_states=('closed',), to_state='awarded',
            )
            if not ok:
                messages.error(request, 'Only closed RFQs can be awarded.')
                return redirect('procurement:rfq_detail', pk=pk)
            award = form.save(commit=False)
            award.tenant = request.tenant
            award.rfq = rfq
            award.awarded_by = request.user
            award.save()
            # Mark winning quote accepted, others rejected.
            models.SupplierQuotation.all_objects.filter(rfq=rfq).exclude(
                pk=award.quotation_id,
            ).update(status='rejected')
            models.SupplierQuotation.all_objects.filter(pk=award.quotation_id).update(
                status='accepted',
            )
            if award.auto_create_po:
                po = convert_quotation_to_po(award.quotation, user=request.user)
                messages.success(
                    request,
                    f'RFQ awarded. Draft PO {po.po_number} created from winning quote.',
                )
                return redirect('procurement:po_detail', pk=po.pk)
        messages.success(request, 'RFQ awarded.')
        return redirect('procurement:rfq_detail', pk=pk)


class RFQCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.RequestForQuotation, pk, request.tenant,
            from_states=('draft', 'issued', 'closed'), to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'RFQ cannot be cancelled in current state.')
        else:
            messages.success(request, 'RFQ cancelled.')
        return redirect('procurement:rfq_detail', pk=pk)


# ============================================================================
# 9.2  Quotations
# ============================================================================

class QuotationListView(TenantRequiredMixin, View):
    template_name = 'procurement/quotations/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.SupplierQuotation.objects.filter(tenant=t).select_related(
            'rfq', 'supplier',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(quote_number__icontains=q)
                | Q(rfq__rfq_number__icontains=q)
                | Q(supplier__code__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-quote_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.SupplierQuotation.STATUS_CHOICES,
        })


class QuotationCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/quotations/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SupplierQuotationForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.SupplierQuotationForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            q = form.save(commit=False)
            q.tenant = request.tenant
            q.save()
            # Mark the corresponding RFQSupplier as quoted.
            models.RFQSupplier.all_objects.filter(
                rfq=q.rfq, supplier=q.supplier,
            ).update(participation_status='quoted', responded_at=timezone.now())
            messages.success(request, f'Quotation {q.quote_number} created.')
            return redirect('procurement:quotation_detail', pk=q.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class QuotationDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/quotations/detail.html'

    def get(self, request, pk):
        q = get_object_or_404(
            models.SupplierQuotation.objects.select_related('rfq', 'supplier'),
            pk=pk, tenant=request.tenant,
        )
        lines = q.lines.select_related('rfq_line__product').order_by('rfq_line__line_number')
        line_form = forms.QuotationLineForm(tenant=request.tenant, rfq=q.rfq)
        return render(request, self.template_name, {
            'q': q, 'lines': lines, 'line_form': line_form,
        })


class QuotationLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        q = get_object_or_404(models.SupplierQuotation, pk=pk, tenant=request.tenant)
        if q.status not in ('submitted', 'under_review'):
            messages.error(request, 'Quotation cannot be modified at this status.')
            return redirect('procurement:quotation_detail', pk=pk)
        form = forms.QuotationLineForm(request.POST, tenant=request.tenant, rfq=q.rfq)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.quotation = q
            line.save()
            q.recompute_totals()
            messages.success(request, 'Quotation line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:quotation_detail', pk=pk)


class QuotationLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.QuotationLine, pk=pk, tenant=request.tenant)
        q = line.quotation
        if q.status not in ('submitted', 'under_review'):
            messages.error(request, 'Quotation cannot be modified at this status.')
            return redirect('procurement:quotation_detail', pk=q.pk)
        line.delete()
        q.recompute_totals()
        messages.success(request, 'Line removed.')
        return redirect('procurement:quotation_detail', pk=q.pk)


class QuotationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        q = get_object_or_404(models.SupplierQuotation, pk=pk, tenant=request.tenant)
        if q.status == 'accepted':
            messages.error(request, 'Cannot delete an accepted quotation.')
            return redirect('procurement:quotation_detail', pk=pk)
        q.delete()
        messages.success(request, 'Quotation deleted.')
        return redirect('procurement:quotation_list')

    def get(self, request, pk):
        return redirect('procurement:quotation_detail', pk=pk)


class RFQQuotationCompareView(TenantRequiredMixin, View):
    """Side-by-side matrix of all quotations for one RFQ."""

    template_name = 'procurement/quotations/compare.html'

    def get(self, request, rfq_pk):
        rfq = get_object_or_404(models.RequestForQuotation, pk=rfq_pk, tenant=request.tenant)
        lines = list(rfq.lines.select_related('product').order_by('line_number'))
        quotations = list(
            rfq.quotations.select_related('supplier').prefetch_related('lines').order_by('quote_date')
        )
        # Build a price lookup keyed by (line_id, quote_id) and reshape into
        # template-friendly rows: each row is {'line': RFQLine, 'cells': [price|None, ...]}
        # in the same order as `quotations`. Avoids needing a custom template
        # filter to dereference dict-of-dicts.
        prices = {}
        for q in quotations:
            for ql in q.lines.all():
                prices[(ql.rfq_line_id, q.id)] = ql.unit_price
        rows = [
            {'line': line, 'cells': [prices.get((line.id, q.id)) for q in quotations]}
            for line in lines
        ]
        return render(request, self.template_name, {
            'rfq': rfq, 'lines': lines, 'quotations': quotations, 'rows': rows,
        })


# ============================================================================
# 9.3  Scorecards
# ============================================================================

class ScorecardListView(TenantRequiredMixin, View):
    template_name = 'procurement/scorecards/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.SupplierScorecard.objects.filter(tenant=t).select_related('supplier')
        period = request.GET.get('period', '')
        if period:
            qs = qs.filter(period_start__lte=period, period_end__gte=period)
        page = _paginate(qs.order_by('rank', '-overall_score'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'period_filter': period,
        })


class ScorecardDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/scorecards/detail.html'

    def get(self, request, pk):
        sc = get_object_or_404(
            models.SupplierScorecard.objects.select_related('supplier'),
            pk=pk, tenant=request.tenant,
        )
        events = models.SupplierMetricEvent.objects.filter(
            tenant=request.tenant, supplier=sc.supplier,
            posted_at__date__gte=sc.period_start,
            posted_at__date__lte=sc.period_end,
        ).order_by('-posted_at')[:50]
        return render(request, self.template_name, {'sc': sc, 'events': events})


class ScorecardRecomputeView(TenantAdminRequiredMixin, View):
    """Recompute every active supplier's scorecard for the given period.

    Period is inferred as the previous calendar month if no GET params.
    """

    def post(self, request):
        today = timezone.now().date()
        period_end = date(today.year, today.month, 1) - timedelta(days=1)
        period_start = date(period_end.year, period_end.month, 1)

        suppliers = list(models.Supplier.objects.filter(tenant=request.tenant, is_active=True))
        rankings = []
        for sup in suppliers:
            events = models.SupplierMetricEvent.objects.filter(
                tenant=request.tenant, supplier=sup,
                posted_at__date__gte=period_start,
                posted_at__date__lte=period_end,
            )
            result = compute_scorecard(events)
            total_pos = sum(
                1 for ev in events if ev.event_type in ('po_received_on_time', 'po_received_late')
            )
            total_value = (
                models.PurchaseOrder.objects.filter(
                    tenant=request.tenant, supplier=sup,
                    order_date__gte=period_start, order_date__lte=period_end,
                ).aggregate(s=Sum('grand_total'))['s'] or Decimal('0')
            )
            sc, _ = models.SupplierScorecard.all_objects.update_or_create(
                tenant=request.tenant, supplier=sup,
                period_start=period_start, period_end=period_end,
                defaults={
                    'otd_pct': result.otd_pct,
                    'quality_rating': result.quality_rating,
                    'defect_rate_pct': result.defect_rate_pct,
                    'price_variance_pct': result.price_variance_pct,
                    'responsiveness_rating': result.responsiveness_rating,
                    'overall_score': result.overall_score,
                    'total_pos': total_pos,
                    'total_value': total_value,
                    'computed_at': timezone.now(),
                    'computed_by': request.user,
                },
            )
            rankings.append(sc)

        rankings.sort(key=lambda x: -x.overall_score)
        for idx, sc in enumerate(rankings, start=1):
            models.SupplierScorecard.all_objects.filter(pk=sc.pk).update(rank=idx)

        messages.success(
            request, f'Recomputed {len(rankings)} scorecards for {period_start}..{period_end}.',
        )
        return redirect('procurement:scorecard_list')


# ============================================================================
# 9.4  Supplier ASNs
# ============================================================================

class ASNListView(TenantRequiredMixin, View):
    template_name = 'procurement/asn/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.SupplierASN.objects.filter(tenant=t).select_related(
            'purchase_order__supplier',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(asn_number__icontains=q)
                | Q(tracking_number__icontains=q)
                | Q(purchase_order__po_number__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-ship_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.SupplierASN.STATUS_CHOICES,
        })


class ASNCreateView(TenantRequiredMixin, View):
    template_name = 'procurement/asn/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SupplierASNForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.SupplierASNForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            asn = form.save(commit=False)
            asn.tenant = request.tenant
            asn.submitted_by = request.user
            asn.save()
            messages.success(request, f'ASN {asn.asn_number} created. Add lines next.')
            return redirect('procurement:asn_detail', pk=asn.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class ASNDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/asn/detail.html'

    def get(self, request, pk):
        asn = get_object_or_404(
            models.SupplierASN.objects.select_related('purchase_order__supplier'),
            pk=pk, tenant=request.tenant,
        )
        lines = asn.lines.select_related('po_line__product')
        line_form = forms.SupplierASNLineForm(tenant=request.tenant, asn=asn)
        return render(request, self.template_name, {
            'asn': asn, 'lines': lines, 'line_form': line_form,
        })


class ASNLineCreateView(TenantRequiredMixin, View):
    def post(self, request, pk):
        asn = get_object_or_404(models.SupplierASN, pk=pk, tenant=request.tenant)
        if asn.status not in ('draft',):
            messages.error(request, 'Only draft ASNs can be modified.')
            return redirect('procurement:asn_detail', pk=pk)
        form = forms.SupplierASNLineForm(request.POST, tenant=request.tenant, asn=asn)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.asn = asn
            line.save()
            messages.success(request, 'ASN line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:asn_detail', pk=pk)


class ASNLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.SupplierASNLine, pk=pk, tenant=request.tenant)
        if line.asn.status != 'draft':
            messages.error(request, 'Only draft ASNs can be modified.')
            return redirect('procurement:asn_detail', pk=line.asn_id)
        asn_pk = line.asn_id
        line.delete()
        messages.success(request, 'Line removed.')
        return redirect('procurement:asn_detail', pk=asn_pk)


class ASNSubmitView(TenantRequiredMixin, View):
    def post(self, request, pk):
        asn = get_object_or_404(models.SupplierASN, pk=pk, tenant=request.tenant)
        if not asn.lines.exists():
            messages.error(request, 'Add at least one line before submitting.')
            return redirect('procurement:asn_detail', pk=pk)
        ok = _atomic_status_transition(
            models.SupplierASN, pk, request.tenant,
            from_states=('draft',), to_state='in_transit',
            extra_fields={'submitted_at': timezone.now(), 'submitted_by': request.user},
        )
        if not ok:
            messages.error(request, 'ASN is not in draft status.')
        else:
            # Bump the underlying PO to in_progress on first ASN submission.
            models.PurchaseOrder.objects.filter(
                pk=asn.purchase_order_id, status='acknowledged',
            ).update(status='in_progress')
            messages.success(request, 'ASN submitted, marked in transit.')
        return redirect('procurement:asn_detail', pk=pk)


class ASNReceiveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierASN, pk, request.tenant,
            from_states=('in_transit', 'submitted'), to_state='received',
            extra_fields={'received_at': timezone.now(), 'received_by': request.user},
        )
        if not ok:
            messages.error(request, 'ASN is not in transit / submitted status.')
        else:
            messages.success(request, 'ASN marked received.')
        return redirect('procurement:asn_detail', pk=pk)


class ASNCancelView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierASN, pk, request.tenant,
            from_states=('draft', 'submitted', 'in_transit'), to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'ASN cannot be cancelled in current state.')
        else:
            messages.success(request, 'ASN cancelled.')
        return redirect('procurement:asn_detail', pk=pk)


# ============================================================================
# 9.4  Supplier Invoices
# ============================================================================

class InvoiceListView(TenantRequiredMixin, View):
    template_name = 'procurement/supplier_invoices/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.SupplierInvoice.objects.filter(tenant=t).select_related(
            'supplier', 'purchase_order',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q)
                | Q(vendor_invoice_number__icontains=q)
                | Q(supplier__code__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-invoice_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.SupplierInvoice.STATUS_CHOICES,
        })


class InvoiceCreateView(TenantRequiredMixin, View):
    template_name = 'procurement/supplier_invoices/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SupplierInvoiceForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.SupplierInvoiceForm(
            request.POST, request.FILES, tenant=request.tenant,
        )
        if form.is_valid():
            inv = form.save(commit=False)
            inv.tenant = request.tenant
            inv.submitted_by = request.user
            inv.save()
            messages.success(request, f'Invoice {inv.invoice_number} submitted.')
            return redirect('procurement:invoice_detail', pk=inv.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class InvoiceDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/supplier_invoices/detail.html'

    def get(self, request, pk):
        inv = get_object_or_404(
            models.SupplierInvoice.objects.select_related(
                'supplier', 'purchase_order', 'submitted_by',
            ),
            pk=pk, tenant=request.tenant,
        )
        lines = inv.lines.select_related('po_line').order_by('line_number')
        return render(request, self.template_name, {'inv': inv, 'lines': lines})


class InvoiceReviewView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierInvoice, pk, request.tenant,
            from_states=('submitted',), to_state='under_review',
        )
        if not ok:
            messages.error(request, 'Invoice not in submitted state.')
        else:
            messages.success(request, 'Invoice moved to under review.')
        return redirect('procurement:invoice_detail', pk=pk)


class InvoiceApproveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierInvoice, pk, request.tenant,
            from_states=('submitted', 'under_review'), to_state='approved',
        )
        if not ok:
            messages.error(request, 'Invoice cannot be approved in current state.')
        else:
            messages.success(request, 'Invoice approved.')
        return redirect('procurement:invoice_detail', pk=pk)


class InvoicePayView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ref = (request.POST.get('payment_reference') or '').strip()
        if not ref:
            messages.error(request, 'Payment reference required to mark paid.')
            return redirect('procurement:invoice_detail', pk=pk)
        ok = _atomic_status_transition(
            models.SupplierInvoice, pk, request.tenant,
            from_states=('approved',), to_state='paid',
            extra_fields={
                'payment_reference': ref,
                'paid_at': timezone.now(),
            },
        )
        if not ok:
            messages.error(request, 'Invoice must be approved first.')
        else:
            messages.success(request, 'Invoice marked paid.')
        return redirect('procurement:invoice_detail', pk=pk)


class InvoiceRejectView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierInvoice, pk, request.tenant,
            from_states=('submitted', 'under_review'), to_state='rejected',
        )
        if not ok:
            messages.error(request, 'Invoice cannot be rejected in current state.')
        else:
            messages.success(request, 'Invoice rejected.')
        return redirect('procurement:invoice_detail', pk=pk)


class InvoiceDisputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.SupplierInvoice, pk, request.tenant,
            from_states=('under_review', 'approved'), to_state='disputed',
        )
        if not ok:
            messages.error(request, 'Invoice cannot be disputed in current state.')
        else:
            messages.success(request, 'Invoice marked disputed.')
        return redirect('procurement:invoice_detail', pk=pk)


class InvoiceDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        inv = get_object_or_404(models.SupplierInvoice, pk=pk, tenant=request.tenant)
        if inv.status not in ('submitted', 'rejected'):
            messages.error(request, 'Only submitted or rejected invoices can be deleted.')
            return redirect('procurement:invoice_detail', pk=pk)
        inv.delete()
        messages.success(request, 'Invoice deleted.')
        return redirect('procurement:invoice_list')

    def get(self, request, pk):
        return redirect('procurement:invoice_detail', pk=pk)


# ============================================================================
# 9.5  Blanket Orders & Releases
# ============================================================================

class BlanketListView(TenantRequiredMixin, View):
    template_name = 'procurement/blanket/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.BlanketOrder.objects.filter(tenant=t).select_related('supplier')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(bpo_number__icontains=q) | Q(supplier__code__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-start_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.BlanketOrder.STATUS_CHOICES,
        })


class BlanketCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/blanket/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.BlanketOrderForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.BlanketOrderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            b = form.save(commit=False)
            b.tenant = request.tenant
            b.created_by = request.user
            b.save()
            messages.success(request, f'Blanket order {b.bpo_number} created.')
            return redirect('procurement:blanket_detail', pk=b.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class BlanketDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/blanket/detail.html'

    def get(self, request, pk):
        b = get_object_or_404(
            models.BlanketOrder.objects.select_related('supplier'),
            pk=pk, tenant=request.tenant,
        )
        lines = b.lines.select_related('product').order_by('line_number')
        releases = b.releases.order_by('-release_date')[:20]
        line_form = forms.BlanketOrderLineForm(tenant=request.tenant)
        return render(request, self.template_name, {
            'b': b, 'lines': lines, 'releases': releases, 'line_form': line_form,
        })


class BlanketEditView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/blanket/form.html'

    def get(self, request, pk):
        b = get_object_or_404(models.BlanketOrder, pk=pk, tenant=request.tenant)
        if b.status != 'draft':
            messages.error(request, 'Only draft blankets can be edited.')
            return redirect('procurement:blanket_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.BlanketOrderForm(instance=b, tenant=request.tenant),
            'b': b, 'is_create': False,
        })

    def post(self, request, pk):
        b = get_object_or_404(models.BlanketOrder, pk=pk, tenant=request.tenant)
        if b.status != 'draft':
            messages.error(request, 'Only draft blankets can be edited.')
            return redirect('procurement:blanket_detail', pk=pk)
        form = forms.BlanketOrderForm(request.POST, instance=b, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Blanket order updated.')
            return redirect('procurement:blanket_detail', pk=b.pk)
        return render(request, self.template_name, {'form': form, 'b': b, 'is_create': False})


class BlanketDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        b = get_object_or_404(models.BlanketOrder, pk=pk, tenant=request.tenant)
        if b.status not in ('draft', 'cancelled'):
            messages.error(request, 'Only draft / cancelled blankets can be deleted.')
            return redirect('procurement:blanket_detail', pk=pk)
        try:
            b.delete()
            messages.success(request, 'Blanket order deleted.')
        except Exception as e:
            messages.error(request, f'Cannot delete: {e}')
            return redirect('procurement:blanket_detail', pk=pk)
        return redirect('procurement:blanket_list')

    def get(self, request, pk):
        return redirect('procurement:blanket_detail', pk=pk)


class BlanketLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        b = get_object_or_404(models.BlanketOrder, pk=pk, tenant=request.tenant)
        if b.status != 'draft':
            messages.error(request, 'Only draft blankets can be modified.')
            return redirect('procurement:blanket_detail', pk=pk)
        form = forms.BlanketOrderLineForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.blanket_order = b
            line.save()
            messages.success(request, 'Line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:blanket_detail', pk=pk)


class BlanketLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.BlanketOrderLine, pk=pk, tenant=request.tenant)
        if line.blanket_order.status != 'draft':
            messages.error(request, 'Only draft blankets can be modified.')
            return redirect('procurement:blanket_detail', pk=line.blanket_order_id)
        b_pk = line.blanket_order_id
        line.delete()
        messages.success(request, 'Line removed.')
        return redirect('procurement:blanket_detail', pk=b_pk)


class BlanketActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        b = get_object_or_404(models.BlanketOrder, pk=pk, tenant=request.tenant)
        if not b.lines.exists():
            messages.error(request, 'Add at least one line before activating.')
            return redirect('procurement:blanket_detail', pk=pk)
        ok = _atomic_status_transition(
            models.BlanketOrder, pk, request.tenant,
            from_states=('draft',), to_state='active',
            extra_fields={'signed_at': timezone.now(), 'signed_by': request.user},
        )
        if not ok:
            messages.error(request, 'Blanket is not in draft status.')
        else:
            messages.success(request, 'Blanket order activated.')
        return redirect('procurement:blanket_detail', pk=pk)


class BlanketCloseView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.BlanketOrder, pk, request.tenant,
            from_states=('active',), to_state='closed',
        )
        if not ok:
            messages.error(request, 'Only active blankets can be closed.')
        else:
            messages.success(request, 'Blanket order closed.')
        return redirect('procurement:blanket_detail', pk=pk)


class BlanketCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.BlanketOrder, pk, request.tenant,
            from_states=('draft', 'active'), to_state='cancelled',
        )
        if not ok:
            messages.error(request, 'Cannot cancel in current state.')
        else:
            messages.success(request, 'Blanket order cancelled.')
        return redirect('procurement:blanket_detail', pk=pk)


# ---- Schedule Releases ---------------------------------------------------

class ReleaseListView(TenantRequiredMixin, View):
    template_name = 'procurement/releases/list.html'

    def get(self, request):
        t = request.tenant
        qs = models.ScheduleRelease.objects.filter(tenant=t).select_related(
            'blanket_order__supplier',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(release_number__icontains=q)
                | Q(blanket_order__bpo_number__icontains=q),
            )
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-release_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'q': q, 'status_filter': status,
            'status_choices': models.ScheduleRelease.STATUS_CHOICES,
        })


class ReleaseCreateView(TenantAdminRequiredMixin, View):
    template_name = 'procurement/releases/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ScheduleReleaseForm(tenant=request.tenant), 'is_create': True,
        })

    def post(self, request):
        form = forms.ScheduleReleaseForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.created_by = request.user
            r.save()
            messages.success(request, f'Release {r.release_number} created.')
            return redirect('procurement:release_detail', pk=r.pk)
        return render(request, self.template_name, {'form': form, 'is_create': True})


class ReleaseDetailView(TenantRequiredMixin, View):
    template_name = 'procurement/releases/detail.html'

    def get(self, request, pk):
        r = get_object_or_404(
            models.ScheduleRelease.objects.select_related('blanket_order__supplier'),
            pk=pk, tenant=request.tenant,
        )
        lines = r.lines.select_related('blanket_order_line__product')
        line_form = forms.ScheduleReleaseLineForm(tenant=request.tenant, release=r)
        return render(request, self.template_name, {
            'r': r, 'lines': lines, 'line_form': line_form,
        })


class ReleaseLineCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        r = get_object_or_404(models.ScheduleRelease, pk=pk, tenant=request.tenant)
        if r.status != 'draft':
            messages.error(request, 'Only draft releases can be modified.')
            return redirect('procurement:release_detail', pk=pk)
        form = forms.ScheduleReleaseLineForm(request.POST, tenant=request.tenant, release=r)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.release = r
            line.save()
            r.recompute_total()
            messages.success(request, 'Line added.')
        else:
            for err in form.errors.values():
                messages.error(request, '; '.join(err))
        return redirect('procurement:release_detail', pk=pk)


class ReleaseLineDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(models.ScheduleReleaseLine, pk=pk, tenant=request.tenant)
        if line.release.status != 'draft':
            messages.error(request, 'Only draft releases can be modified.')
            return redirect('procurement:release_detail', pk=line.release_id)
        rel = line.release
        line.delete()
        rel.recompute_total()
        messages.success(request, 'Line removed.')
        return redirect('procurement:release_detail', pk=rel.pk)


class ReleaseReleaseView(TenantAdminRequiredMixin, View):
    """draft -> released. Consumes the parent blanket commitment."""

    def post(self, request, pk):
        r = get_object_or_404(models.ScheduleRelease, pk=pk, tenant=request.tenant)
        if not r.lines.exists():
            messages.error(request, 'Add at least one line before releasing.')
            return redirect('procurement:release_detail', pk=pk)
        try:
            with transaction.atomic():
                ok = _atomic_status_transition(
                    models.ScheduleRelease, pk, request.tenant,
                    from_states=('draft',), to_state='released',
                )
                if not ok:
                    raise ValueError('Release is not in draft state.')
                r.refresh_from_db()
                consume_release(r)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('procurement:release_detail', pk=pk)
        messages.success(request, 'Release issued and blanket consumption updated.')
        return redirect('procurement:release_detail', pk=pk)


class ReleaseReceiveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.ScheduleRelease, pk, request.tenant,
            from_states=('released',), to_state='received',
        )
        if not ok:
            messages.error(request, 'Release must be in released state.')
        else:
            messages.success(request, 'Release marked received.')
        return redirect('procurement:release_detail', pk=pk)


class ReleaseCancelView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        r = get_object_or_404(models.ScheduleRelease, pk=pk, tenant=request.tenant)
        try:
            with transaction.atomic():
                old_status = r.status
                ok = _atomic_status_transition(
                    models.ScheduleRelease, pk, request.tenant,
                    from_states=('draft', 'released'), to_state='cancelled',
                )
                if not ok:
                    raise ValueError('Release cannot be cancelled in current state.')
                if old_status == 'released':
                    r.refresh_from_db()
                    reverse_release(r)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('procurement:release_detail', pk=pk)
        messages.success(request, 'Release cancelled.')
        return redirect('procurement:release_detail', pk=pk)


# ============================================================================
# Supplier Portal (external user)
# ============================================================================

class PortalDashboardView(SupplierPortalRequiredMixin, View):
    template_name = 'procurement/portal/dashboard.html'

    def get(self, request):
        sup_id = request.user.supplier_company_id
        ctx = {
            'open_pos': models.PurchaseOrder.all_objects.filter(
                supplier_id=sup_id,
                status__in=('approved', 'acknowledged', 'in_progress'),
            ).count(),
            'pending_acks': models.PurchaseOrder.all_objects.filter(
                supplier_id=sup_id, status='approved',
            ).count(),
            'submitted_invoices': models.SupplierInvoice.all_objects.filter(
                supplier_id=sup_id, status__in=('submitted', 'under_review'),
            ).count(),
            'in_transit_asns': models.SupplierASN.all_objects.filter(
                purchase_order__supplier_id=sup_id, status='in_transit',
            ).count(),
            'recent_pos': models.PurchaseOrder.all_objects.filter(
                supplier_id=sup_id,
            ).order_by('-id')[:8],
        }
        return render(request, self.template_name, ctx)


class PortalPOListView(SupplierPortalRequiredMixin, View):
    template_name = 'procurement/portal/my_pos.html'

    def get(self, request):
        sup_id = request.user.supplier_company_id
        qs = models.PurchaseOrder.all_objects.filter(supplier_id=sup_id)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-order_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'status_filter': status,
            'status_choices': models.PurchaseOrder.STATUS_CHOICES,
        })


class PortalASNListView(SupplierPortalRequiredMixin, View):
    template_name = 'procurement/portal/my_asns.html'

    def get(self, request):
        sup_id = request.user.supplier_company_id
        qs = models.SupplierASN.all_objects.filter(
            purchase_order__supplier_id=sup_id,
        ).select_related('purchase_order')
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-ship_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'status_filter': status,
            'status_choices': models.SupplierASN.STATUS_CHOICES,
        })


class PortalInvoiceListView(SupplierPortalRequiredMixin, View):
    template_name = 'procurement/portal/my_invoices.html'

    def get(self, request):
        sup_id = request.user.supplier_company_id
        qs = models.SupplierInvoice.all_objects.filter(supplier_id=sup_id)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        page = _paginate(qs.order_by('-invoice_date', '-id'), request)
        return render(request, self.template_name, {
            'page_obj': page, 'status_filter': status,
            'status_choices': models.SupplierInvoice.STATUS_CHOICES,
        })
