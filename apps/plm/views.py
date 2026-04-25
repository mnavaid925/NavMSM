"""PLM views — full CRUD per CLAUDE.md across all 5 sub-modules.

Every view filters by request.tenant. Edit/Delete on workflow models
(ECOs) is gated by status (draft only). All list views accept search +
status/type filters and pass the relevant choice tuples / FK querysets
to their template context.

# SECURITY — production hardening required for media uploads.
# The auth-gated download views below (cad_version_download, eco_attachment_download,
# compliance_certificate_download) protect PLM-uploaded files via tenant
# isolation. In production, the `static(MEDIA_URL, ...)` mount in
# config/urls.py must be removed and the web server (Nginx/Apache) configured
# to serve `MEDIA_ROOT/plm/*` ONLY via X-Accel-Redirect/X-Sendfile from these
# views (see Nginx `internal;` directive). In DEBUG mode the raw /media/...
# URLs are still reachable but the application never produces them — only
# the gated URLs are linked from templates.
"""
import re
from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import TenantRequiredMixin

from .forms import (
    CADDocumentForm, CADDocumentVersionForm, ECOAttachmentForm, ECOApprovalForm,
    ECOForm, ECOImpactedItemForm, NPIDeliverableForm, NPIProjectForm,
    NPIStageForm, ProductCategoryForm, ProductComplianceForm, ProductForm,
    ProductRevisionForm, ProductSpecificationForm, ProductVariantForm,
)
from .models import (
    CADDocument, CADDocumentVersion, ComplianceAuditLog, ComplianceStandard,
    ECOApproval, ECOAttachment, ECOImpactedItem, EngineeringChangeOrder,
    NPIDeliverable, NPIProject, NPIStage, Product, ProductCategory,
    ProductCompliance, ProductRevision, ProductSpecification, ProductVariant,
)


# ============================================================================
# Helpers
# ============================================================================

_SEQ_RE = re.compile(r'^[A-Z]+-(\d+)$')


def _next_sequence_number(qs, field, prefix, width=5):
    """Return next padded number like ECO-00007.

    Parses the trailing digit run of the current Max() value. If the max
    value doesn't match `^[A-Z]+-\\d+$` (e.g. someone imported legacy
    `ECO-Q1-00001`), falls back to `count() + 1` rather than silently
    truncating — fixes D-07.
    """
    last = qs.aggregate(Max(field))[f'{field}__max']
    next_num = 1
    if last:
        m = _SEQ_RE.match(str(last))
        next_num = int(m.group(1)) + 1 if m else qs.count() + 1
    return f'{prefix}-{next_num:0{width}d}'


def _save_with_unique_number(make_obj, max_attempts=5):
    """Run a create that allocates a unique `number` field, retrying on
    IntegrityError caused by races on the auto-numbering — fixes D-04.

    `make_obj` is a callable that, on each attempt, re-reads the next
    sequence number, sets it on the instance, and saves inside the
    surrounding atomic block. Returns the saved instance, or re-raises
    the last IntegrityError after `max_attempts`.
    """
    last_err = None
    for _ in range(max_attempts):
        try:
            with transaction.atomic():
                return make_obj()
        except IntegrityError as e:
            last_err = e
            continue
    raise last_err


# ============================================================================
# Dashboard / index
# ============================================================================

class PLMIndexView(TenantRequiredMixin, View):
    template_name = 'plm/index.html'

    def get(self, request):
        t = request.tenant
        ctx = {
            'product_count': Product.objects.filter(tenant=t).count(),
            'eco_open': EngineeringChangeOrder.objects.filter(
                tenant=t,
            ).exclude(status__in=['implemented', 'cancelled', 'rejected']).count(),
            'cad_count': CADDocument.objects.filter(tenant=t).count(),
            'compliance_compliant': ProductCompliance.objects.filter(
                tenant=t, status='compliant',
            ).count(),
            'compliance_pending': ProductCompliance.objects.filter(
                tenant=t,
            ).exclude(status='compliant').count(),
            'npi_active': NPIProject.objects.filter(
                tenant=t, status__in=['planning', 'in_progress'],
            ).count(),
            'recent_ecos': EngineeringChangeOrder.objects.filter(
                tenant=t,
            ).order_by('-created_at')[:5],
            'recent_npi': NPIProject.objects.filter(tenant=t).order_by('-created_at')[:5],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 2.1  PRODUCT MASTER DATA — CATEGORY CRUD
# ============================================================================

class CategoryListView(TenantRequiredMixin, ListView):
    model = ProductCategory
    template_name = 'plm/categories/list.html'
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductCategory.objects.filter(tenant=self.request.tenant).select_related('parent')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.annotate(product_count=Count('products')).order_by('name')


class CategoryCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/categories/form.html', {
            'form': ProductCategoryForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProductCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Category "{obj.name}" created.')
            return redirect('plm:category_list')
        return render(request, 'plm/categories/form.html', {'form': form})


class CategoryEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(ProductCategory, pk=pk, tenant=request.tenant)
        return render(request, 'plm/categories/form.html', {
            'form': ProductCategoryForm(instance=obj, tenant=request.tenant),
            'category': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(ProductCategory, pk=pk, tenant=request.tenant)
        form = ProductCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.')
            return redirect('plm:category_list')
        return render(request, 'plm/categories/form.html', {'form': form, 'category': obj})


class CategoryDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(ProductCategory, pk=pk, tenant=request.tenant)
        if obj.products.exists():
            messages.error(request, f'Cannot delete "{obj.name}" — it has assigned products.')
        else:
            obj.delete()
            messages.success(request, 'Category deleted.')
        return redirect('plm:category_list')


# ============================================================================
# 2.1  PRODUCT MASTER DATA — PRODUCT CRUD
# ============================================================================

class ProductListView(TenantRequiredMixin, ListView):
    model = Product
    template_name = 'plm/products/list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.filter(tenant=self.request.tenant).select_related('category', 'current_revision')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(sku__icontains=q) | Q(name__icontains=q))
        category = self.request.GET.get('category', '')
        if category:
            qs = qs.filter(category_id=category)
        ptype = self.request.GET.get('product_type', '')
        if ptype:
            qs = qs.filter(product_type=ptype)
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = Product.STATUS_CHOICES
        ctx['type_choices'] = Product.TYPE_CHOICES
        ctx['categories'] = ProductCategory.objects.filter(
            tenant=self.request.tenant, is_active=True,
        )
        return ctx


class ProductCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/products/form.html', {
            'form': ProductForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProductForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Product "{obj.sku}" created.')
            return redirect('plm:product_detail', pk=obj.pk)
        return render(request, 'plm/products/form.html', {'form': form})


class ProductDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        product = get_object_or_404(
            Product.objects.select_related('category', 'current_revision'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'plm/products/detail.html', {
            'product': product,
            'specifications': product.specifications.all().select_related('revision'),
            'revisions': product.revisions.all(),
            'variants': product.variants.all(),
            'cad_documents': product.cad_documents.all(),
            'compliance': product.compliance_records.all().select_related('standard'),
        })


class ProductEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk, tenant=request.tenant)
        return render(request, 'plm/products/form.html', {
            'form': ProductForm(instance=product, tenant=request.tenant),
            'product': product,
        })

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, tenant=request.tenant)
        form = ProductForm(request.POST, request.FILES, instance=product, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('plm:product_detail', pk=product.pk)
        return render(request, 'plm/products/form.html', {'form': form, 'product': product})


class ProductDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, tenant=request.tenant)
        try:
            product.delete()
        except ProtectedError:
            messages.error(
                request,
                f'Cannot delete "{product.sku}" — it is referenced by ECO impacted '
                'items or other protected records. Remove those references first.',
            )
            return redirect('plm:product_detail', pk=product.pk)
        messages.success(request, 'Product deleted.')
        return redirect('plm:product_list')


# Revisions — nested under product
class RevisionCreateView(TenantRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        form = ProductRevisionForm(request.POST)
        if form.is_valid():
            rev = form.save(commit=False)
            rev.tenant = request.tenant
            rev.product = product
            rev.save()
            if rev.status == 'active':
                # Mark previous active revisions as superseded.
                ProductRevision.objects.filter(
                    product=product, status='active',
                ).exclude(pk=rev.pk).update(status='superseded')
                product.current_revision = rev
                product.save(update_fields=['current_revision'])
            messages.success(request, f'Revision {rev.revision_code} added.')
        else:
            messages.error(request, 'Could not add revision: ' + '; '.join(
                f'{k}: {v[0]}' for k, v in form.errors.items()
            ))
        return redirect('plm:product_detail', pk=product.pk)


class RevisionDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        rev = get_object_or_404(ProductRevision, pk=pk, tenant=request.tenant)
        product_id = rev.product_id
        rev.delete()
        messages.success(request, 'Revision deleted.')
        return redirect('plm:product_detail', pk=product_id)


# Specifications
class SpecificationCreateView(TenantRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        form = ProductSpecificationForm(request.POST, product=product)
        if form.is_valid():
            spec = form.save(commit=False)
            spec.tenant = request.tenant
            spec.product = product
            spec.save()
            messages.success(request, 'Specification added.')
        else:
            messages.error(request, 'Could not add specification.')
        return redirect('plm:product_detail', pk=product.pk)


class SpecificationDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        spec = get_object_or_404(ProductSpecification, pk=pk, tenant=request.tenant)
        product_id = spec.product_id
        spec.delete()
        messages.success(request, 'Specification deleted.')
        return redirect('plm:product_detail', pk=product_id)


# Variants
class VariantCreateView(TenantRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        form = ProductVariantForm(request.POST)
        if form.is_valid():
            v = form.save(commit=False)
            v.tenant = request.tenant
            v.product = product
            v.save()
            form.save()  # writes attributes JSON
            messages.success(request, f'Variant {v.variant_sku} added.')
        else:
            messages.error(request, 'Could not add variant.')
        return redirect('plm:product_detail', pk=product.pk)


class VariantEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        v = get_object_or_404(ProductVariant, pk=pk, tenant=request.tenant)
        return render(request, 'plm/products/variant_form.html', {
            'form': ProductVariantForm(instance=v), 'variant': v,
        })

    def post(self, request, pk):
        v = get_object_or_404(ProductVariant, pk=pk, tenant=request.tenant)
        form = ProductVariantForm(request.POST, instance=v)
        if form.is_valid():
            form.save()
            messages.success(request, 'Variant updated.')
            return redirect('plm:product_detail', pk=v.product_id)
        return render(request, 'plm/products/variant_form.html', {'form': form, 'variant': v})


class VariantDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        v = get_object_or_404(ProductVariant, pk=pk, tenant=request.tenant)
        product_id = v.product_id
        v.delete()
        messages.success(request, 'Variant deleted.')
        return redirect('plm:product_detail', pk=product_id)


# ============================================================================
# 2.2  ECO — CRUD + workflow actions
# ============================================================================

class ECOListView(TenantRequiredMixin, ListView):
    model = EngineeringChangeOrder
    template_name = 'plm/eco/list.html'
    context_object_name = 'ecos'
    paginate_by = 20

    def get_queryset(self):
        qs = EngineeringChangeOrder.objects.filter(tenant=self.request.tenant).select_related('requested_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q))
        for field in ('status', 'priority', 'change_type'):
            val = self.request.GET.get(field, '')
            if val:
                qs = qs.filter(**{field: val})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = EngineeringChangeOrder.STATUS_CHOICES
        ctx['priority_choices'] = EngineeringChangeOrder.PRIORITY_CHOICES
        ctx['change_type_choices'] = EngineeringChangeOrder.CHANGE_TYPE_CHOICES
        return ctx


class ECOCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/eco/form.html', {'form': ECOForm()})

    def post(self, request):
        form = ECOForm(request.POST)
        if form.is_valid():
            def _make():
                eco = form.save(commit=False)
                eco.tenant = request.tenant
                eco.requested_by = request.user
                eco.number = _next_sequence_number(
                    EngineeringChangeOrder.objects.filter(tenant=request.tenant),
                    'number', 'ECO',
                )
                eco.save()
                return eco
            eco = _save_with_unique_number(_make)
            messages.success(request, f'ECO {eco.number} created.')
            return redirect('plm:eco_detail', pk=eco.pk)
        return render(request, 'plm/eco/form.html', {'form': form})


class ECODetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        eco = get_object_or_404(
            EngineeringChangeOrder.objects.select_related('requested_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'plm/eco/detail.html', {
            'eco': eco,
            'impacted_items': eco.impacted_items.select_related('product', 'before_revision', 'after_revision'),
            'approvals': eco.approvals.select_related('approver'),
            'attachments': eco.attachments.all(),
            'item_form': ECOImpactedItemForm(tenant=request.tenant),
            'approval_form': ECOApprovalForm(tenant=request.tenant),
            'attachment_form': ECOAttachmentForm(),
        })


class ECOEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if not eco.is_editable():
            messages.warning(request, 'ECO can only be edited in Draft status.')
            return redirect('plm:eco_detail', pk=pk)
        return render(request, 'plm/eco/form.html', {'form': ECOForm(instance=eco), 'eco': eco})

    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if not eco.is_editable():
            messages.warning(request, 'ECO can only be edited in Draft status.')
            return redirect('plm:eco_detail', pk=pk)
        form = ECOForm(request.POST, instance=eco)
        if form.is_valid():
            form.save()
            messages.success(request, 'ECO updated.')
            return redirect('plm:eco_detail', pk=eco.pk)
        return render(request, 'plm/eco/form.html', {'form': form, 'eco': eco})


class ECODeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if not eco.is_editable():
            messages.error(request, 'Only Draft ECOs can be deleted.')
            return redirect('plm:eco_detail', pk=pk)
        eco.delete()
        messages.success(request, 'ECO deleted.')
        return redirect('plm:eco_list')


def _atomic_eco_transition(eco, request, from_states, to_state, stamp_field=None):
    """Atomic, race-safe ECO status transition (D-05).

    Uses a conditional UPDATE that only fires if the row is still in one
    of `from_states`. Returns True on success, False if another writer
    already advanced the status.
    """
    fields = {'status': to_state}
    if stamp_field:
        fields[stamp_field] = timezone.now()
    with transaction.atomic():
        rowcount = EngineeringChangeOrder.objects.filter(
            pk=eco.pk, tenant=request.tenant, status__in=from_states,
        ).update(**fields)
        if not rowcount:
            return False
        # Refresh in-memory copy so signals + audit log see new state.
        eco.refresh_from_db()
    return True


class ECOSubmitView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if _atomic_eco_transition(eco, request, ['draft'], 'submitted', 'submitted_at'):
            messages.success(request, f'ECO {eco.number} submitted for review.')
        else:
            messages.warning(request, 'Only Draft ECOs can be submitted (or it was already submitted by someone else).')
        return redirect('plm:eco_detail', pk=pk)


class ECOApproveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if _atomic_eco_transition(
            eco, request, ['submitted', 'under_review'], 'approved', 'approved_at',
        ):
            ECOApproval.objects.create(
                tenant=request.tenant, eco=eco, approver=request.user,
                decision='approved', comment=request.POST.get('comment', ''),
                decided_at=timezone.now(),
            )
            messages.success(request, f'ECO {eco.number} approved.')
        else:
            messages.warning(request, 'ECO is no longer in a reviewable state — another reviewer may have actioned it.')
        return redirect('plm:eco_detail', pk=pk)


class ECORejectView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if _atomic_eco_transition(
            eco, request, ['submitted', 'under_review'], 'rejected',
        ):
            ECOApproval.objects.create(
                tenant=request.tenant, eco=eco, approver=request.user,
                decision='rejected', comment=request.POST.get('comment', ''),
                decided_at=timezone.now(),
            )
            messages.info(request, f'ECO {eco.number} rejected.')
        else:
            messages.warning(request, 'ECO is no longer in a reviewable state.')
        return redirect('plm:eco_detail', pk=pk)


class ECOImplementView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        if _atomic_eco_transition(eco, request, ['approved'], 'implemented', 'implemented_at'):
            messages.success(request, f'ECO {eco.number} marked Implemented.')
        else:
            messages.warning(request, 'Only Approved ECOs can be marked Implemented.')
        return redirect('plm:eco_detail', pk=pk)


class ECOImpactedItemAddView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        form = ECOImpactedItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            item = form.save(commit=False)
            item.tenant = request.tenant
            item.eco = eco
            item.save()
            messages.success(request, 'Impacted item added.')
        else:
            messages.error(request, 'Could not add impacted item.')
        return redirect('plm:eco_detail', pk=pk)


class ECOImpactedItemDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(ECOImpactedItem, pk=pk, tenant=request.tenant)
        eco_id = item.eco_id
        item.delete()
        messages.success(request, 'Impacted item removed.')
        return redirect('plm:eco_detail', pk=eco_id)


class ECOAttachmentAddView(TenantRequiredMixin, View):
    def post(self, request, pk):
        eco = get_object_or_404(EngineeringChangeOrder, pk=pk, tenant=request.tenant)
        form = ECOAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.tenant = request.tenant
            att.eco = eco
            att.uploaded_by = request.user
            att.save()
            messages.success(request, 'Attachment uploaded.')
        else:
            messages.error(request, 'Upload failed: ' + '; '.join(
                f'{k}: {v[0]}' for k, v in form.errors.items()
            ))
        return redirect('plm:eco_detail', pk=pk)


class ECOAttachmentDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        att = get_object_or_404(ECOAttachment, pk=pk, tenant=request.tenant)
        eco_id = att.eco_id
        att.delete()
        messages.success(request, 'Attachment deleted.')
        return redirect('plm:eco_detail', pk=eco_id)


# ============================================================================
# 2.3  CAD — CRUD + version actions
# ============================================================================

class CADListView(TenantRequiredMixin, ListView):
    model = CADDocument
    template_name = 'plm/cad/list.html'
    context_object_name = 'documents'
    paginate_by = 20

    def get_queryset(self):
        qs = CADDocument.objects.filter(tenant=self.request.tenant).select_related('product', 'current_version')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(drawing_number__icontains=q) | Q(title__icontains=q))
        doc_type = self.request.GET.get('doc_type', '')
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doc_type_choices'] = CADDocument.DOC_TYPE_CHOICES
        return ctx


class CADCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/cad/form.html', {
            'form': CADDocumentForm(tenant=request.tenant),
        })

    def post(self, request):
        form = CADDocumentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.tenant = request.tenant
            doc.save()
            messages.success(request, f'Drawing {doc.drawing_number} created.')
            return redirect('plm:cad_detail', pk=doc.pk)
        return render(request, 'plm/cad/form.html', {'form': form})


class CADDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(
            CADDocument.objects.select_related('product', 'current_version'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'plm/cad/detail.html', {
            'document': doc,
            'versions': doc.versions.all().select_related('uploaded_by'),
            'version_form': CADDocumentVersionForm(),
        })


class CADEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(CADDocument, pk=pk, tenant=request.tenant)
        return render(request, 'plm/cad/form.html', {
            'form': CADDocumentForm(instance=doc, tenant=request.tenant),
            'document': doc,
        })

    def post(self, request, pk):
        doc = get_object_or_404(CADDocument, pk=pk, tenant=request.tenant)
        form = CADDocumentForm(request.POST, instance=doc, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Drawing updated.')
            return redirect('plm:cad_detail', pk=doc.pk)
        return render(request, 'plm/cad/form.html', {'form': form, 'document': doc})


class CADDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(CADDocument, pk=pk, tenant=request.tenant)
        doc.delete()
        messages.success(request, 'Drawing deleted.')
        return redirect('plm:cad_list')


class CADVersionUploadView(TenantRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(CADDocument, pk=pk, tenant=request.tenant)
        form = CADDocumentVersionForm(request.POST, request.FILES)
        if form.is_valid():
            v = form.save(commit=False)
            v.tenant = request.tenant
            v.document = doc
            v.uploaded_by = request.user
            v.save()
            # Auto-set current_version on first upload.
            if doc.current_version is None:
                doc.current_version = v
                doc.save(update_fields=['current_version'])
            messages.success(request, f'Version {v.version} uploaded.')
        else:
            messages.error(request, 'Upload failed: ' + '; '.join(
                f'{k}: {v[0]}' for k, v in form.errors.items()
            ))
        return redirect('plm:cad_detail', pk=pk)


class CADVersionReleaseView(TenantRequiredMixin, View):
    def post(self, request, pk):
        v = get_object_or_404(CADDocumentVersion, pk=pk, tenant=request.tenant)
        v.status = 'released'
        v.released_at = timezone.now()
        v.save(update_fields=['status', 'released_at'])
        # Mark previous released version as obsolete; promote this to current.
        CADDocumentVersion.objects.filter(
            document=v.document, status='released',
        ).exclude(pk=v.pk).update(status='obsolete')
        v.document.current_version = v
        v.document.save(update_fields=['current_version'])
        messages.success(request, f'Version {v.version} released.')
        return redirect('plm:cad_detail', pk=v.document_id)


class CADVersionDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        v = get_object_or_404(CADDocumentVersion, pk=pk, tenant=request.tenant)
        doc_id = v.document_id
        # Detach from document if it was the current one.
        if v.document.current_version_id == v.pk:
            v.document.current_version = None
            v.document.save(update_fields=['current_version'])
        v.delete()
        messages.success(request, 'Version deleted.')
        return redirect('plm:cad_detail', pk=doc_id)


# ============================================================================
# 2.4  COMPLIANCE — CRUD
# ============================================================================

class ComplianceListView(TenantRequiredMixin, ListView):
    model = ProductCompliance
    template_name = 'plm/compliance/list.html'
    context_object_name = 'records'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductCompliance.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'standard')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q)
                | Q(product__name__icontains=q)
                | Q(certification_number__icontains=q),
            )
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        standard = self.request.GET.get('standard', '')
        if standard:
            qs = qs.filter(standard_id=standard)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = ProductCompliance.STATUS_CHOICES
        ctx['standards'] = ComplianceStandard.objects.filter(is_active=True)
        today = timezone.now().date()
        soon = today + timedelta(days=30)
        ctx['expiring_soon_count'] = ProductCompliance.objects.filter(
            tenant=self.request.tenant,
            expiry_date__gte=today, expiry_date__lte=soon,
        ).count()
        return ctx


class ComplianceCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/compliance/form.html', {
            'form': ProductComplianceForm(tenant=request.tenant),
        })

    def post(self, request):
        form = ProductComplianceForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Compliance record created.')
            return redirect('plm:compliance_detail', pk=obj.pk)
        return render(request, 'plm/compliance/form.html', {'form': form})


class ComplianceDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(
            ProductCompliance.objects.select_related('product', 'standard'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'plm/compliance/detail.html', {
            'record': rec,
            'audit_entries': rec.audit_entries.all().select_related('performed_by'),
        })


class ComplianceEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(ProductCompliance, pk=pk, tenant=request.tenant)
        return render(request, 'plm/compliance/form.html', {
            'form': ProductComplianceForm(instance=rec, tenant=request.tenant),
            'record': rec,
        })

    def post(self, request, pk):
        rec = get_object_or_404(ProductCompliance, pk=pk, tenant=request.tenant)
        form = ProductComplianceForm(
            request.POST, request.FILES, instance=rec, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Compliance record updated.')
            return redirect('plm:compliance_detail', pk=rec.pk)
        return render(request, 'plm/compliance/form.html', {'form': form, 'record': rec})


class ComplianceDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        rec = get_object_or_404(ProductCompliance, pk=pk, tenant=request.tenant)
        rec.delete()
        messages.success(request, 'Compliance record deleted.')
        return redirect('plm:compliance_list')


# ============================================================================
# 2.5  NPI — CRUD + stage actions
# ============================================================================

class NPIListView(TenantRequiredMixin, ListView):
    model = NPIProject
    template_name = 'plm/npi/list.html'
    context_object_name = 'projects'
    paginate_by = 20

    def get_queryset(self):
        qs = NPIProject.objects.filter(tenant=self.request.tenant).select_related('product', 'project_manager')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        stage = self.request.GET.get('current_stage', '')
        if stage:
            qs = qs.filter(current_stage=stage)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = NPIProject.STATUS_CHOICES
        ctx['stage_choices'] = NPIProject.STAGE_CHOICES
        return ctx


class NPICreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'plm/npi/form.html', {
            'form': NPIProjectForm(tenant=request.tenant),
        })

    def post(self, request):
        form = NPIProjectForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                p = form.save(commit=False)
                p.tenant = request.tenant
                p.code = _next_sequence_number(
                    NPIProject.objects.filter(tenant=request.tenant), 'code', 'NPI',
                )
                p.save()
                for seq, (stage_code, _) in enumerate(NPIProject.STAGE_CHOICES, start=1):
                    NPIStage.objects.create(
                        tenant=request.tenant, project=p,
                        stage=stage_code, sequence=seq,
                    )
                return p
            p = _save_with_unique_number(_make)
            messages.success(request, f'NPI project {p.code} created.')
            return redirect('plm:npi_detail', pk=p.pk)
        return render(request, 'plm/npi/form.html', {'form': form})


class NPIDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        project = get_object_or_404(
            NPIProject.objects.select_related('product', 'project_manager'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'plm/npi/detail.html', {
            'project': project,
            'stages': project.stages.all().prefetch_related('deliverables'),
            'deliverable_form': NPIDeliverableForm(tenant=request.tenant),
        })


class NPIEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        project = get_object_or_404(NPIProject, pk=pk, tenant=request.tenant)
        return render(request, 'plm/npi/form.html', {
            'form': NPIProjectForm(instance=project, tenant=request.tenant),
            'project': project,
        })

    def post(self, request, pk):
        project = get_object_or_404(NPIProject, pk=pk, tenant=request.tenant)
        form = NPIProjectForm(request.POST, instance=project, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'NPI project updated.')
            return redirect('plm:npi_detail', pk=project.pk)
        return render(request, 'plm/npi/form.html', {'form': form, 'project': project})


class NPIDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(NPIProject, pk=pk, tenant=request.tenant)
        project.delete()
        messages.success(request, 'NPI project deleted.')
        return redirect('plm:npi_list')


class NPIStageEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        stage = get_object_or_404(NPIStage, pk=pk, tenant=request.tenant)
        return render(request, 'plm/npi/stage_form.html', {
            'form': NPIStageForm(instance=stage), 'stage': stage,
        })

    def post(self, request, pk):
        stage = get_object_or_404(NPIStage, pk=pk, tenant=request.tenant)
        form = NPIStageForm(request.POST, instance=stage)
        if form.is_valid():
            obj = form.save()
            if obj.gate_decision != 'pending' and obj.gate_decided_at is None:
                obj.gate_decided_at = timezone.now()
                obj.gate_decided_by = request.user
                obj.save(update_fields=['gate_decided_at', 'gate_decided_by'])
            # Sync project's current_stage if this stage just went in_progress.
            if obj.status == 'in_progress':
                obj.project.current_stage = obj.stage
                obj.project.save(update_fields=['current_stage'])
            messages.success(request, f'Stage {obj.get_stage_display()} updated.')
            return redirect('plm:npi_detail', pk=stage.project_id)
        return render(request, 'plm/npi/stage_form.html', {'form': form, 'stage': stage})


class NPIDeliverableAddView(TenantRequiredMixin, View):
    def post(self, request, stage_id):
        stage = get_object_or_404(NPIStage, pk=stage_id, tenant=request.tenant)
        form = NPIDeliverableForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            d = form.save(commit=False)
            d.tenant = request.tenant
            d.stage = stage
            d.save()
            messages.success(request, f'Deliverable "{d.name}" added.')
        else:
            messages.error(request, 'Could not add deliverable.')
        return redirect('plm:npi_detail', pk=stage.project_id)


class NPIDeliverableEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        d = get_object_or_404(NPIDeliverable, pk=pk, tenant=request.tenant)
        return render(request, 'plm/npi/deliverable_form.html', {
            'form': NPIDeliverableForm(instance=d, tenant=request.tenant),
            'deliverable': d,
        })

    def post(self, request, pk):
        d = get_object_or_404(NPIDeliverable, pk=pk, tenant=request.tenant)
        form = NPIDeliverableForm(request.POST, instance=d, tenant=request.tenant)
        if form.is_valid():
            obj = form.save()
            if obj.status == 'done' and obj.completed_at is None:
                obj.completed_at = timezone.now()
                obj.save(update_fields=['completed_at'])
            messages.success(request, 'Deliverable updated.')
            return redirect('plm:npi_detail', pk=d.stage.project_id)
        return render(request, 'plm/npi/deliverable_form.html', {'form': form, 'deliverable': d})


class NPIDeliverableCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        d = get_object_or_404(NPIDeliverable, pk=pk, tenant=request.tenant)
        d.status = 'done'
        d.completed_at = timezone.now()
        d.save(update_fields=['status', 'completed_at'])
        messages.success(request, f'Deliverable "{d.name}" marked done.')
        return redirect('plm:npi_detail', pk=d.stage.project_id)


class NPIDeliverableDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        d = get_object_or_404(NPIDeliverable, pk=pk, tenant=request.tenant)
        project_id = d.stage.project_id
        d.delete()
        messages.success(request, 'Deliverable deleted.')
        return redirect('plm:npi_detail', pk=project_id)


# ============================================================================
# AUTH-GATED FILE DOWNLOAD VIEWS (D-03)
# ============================================================================
# These replace direct linking to MEDIA_URL for PLM uploads. Templates use
# {% url 'plm:cad_version_download' v.pk %} etc., which routes through these
# views — they verify auth + tenant ownership before streaming the file.
# Production must additionally remove the static() MEDIA mount in
# config/urls.py and let the web server serve files via X-Accel-Redirect.

def _stream_file(file_field):
    """Helper: returns FileResponse with as_attachment=True. Raises 404 if
    the file is missing on disk."""
    if not file_field:
        raise Http404('File not available.')
    try:
        return FileResponse(
            file_field.open('rb'),
            as_attachment=True,
            filename=file_field.name.rsplit('/', 1)[-1],
        )
    except FileNotFoundError as e:
        raise Http404('File missing on server.') from e


class CADVersionDownloadView(TenantRequiredMixin, View):
    def get(self, request, pk):
        v = get_object_or_404(CADDocumentVersion, pk=pk, tenant=request.tenant)
        return _stream_file(v.file)


class ECOAttachmentDownloadView(TenantRequiredMixin, View):
    def get(self, request, pk):
        a = get_object_or_404(ECOAttachment, pk=pk, tenant=request.tenant)
        return _stream_file(a.file)


class ComplianceCertificateDownloadView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rec = get_object_or_404(ProductCompliance, pk=pk, tenant=request.tenant)
        return _stream_file(rec.certificate_file)
