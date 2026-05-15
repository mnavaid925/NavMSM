"""Views for Module 19 - Document & Knowledge Management.

CRUD-complete per CLAUDE.md "CRUD Completeness Rules". Every list view
filters by `request.tenant` first, parses GET filter params, then
paginates. Workflow / delete views are POST-only and gated to tenant
admins via `@tenant_admin_required` (L-10).
"""
from __future__ import annotations

import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    ApprovalActionForm,
    ApprovalStageForm,
    ApprovalWorkflowForm,
    AssignmentTargetForm,
    DocumentAccessRuleForm,
    DocumentApprovalRequestForm,
    DocumentArchiveRestoreForm,
    DocumentAssignmentForm,
    DocumentCategoryForm,
    DocumentForm,
    DocumentTemplateForm,
    DocumentVersionForm,
    LegalHoldForm,
    LegalHoldReleaseForm,
    MediaAttachmentForm,
    ReadAcknowledgmentForm,
    RetentionPolicyForm,
    TemplateFieldForm,
)
from .models import (
    ApprovalAction,
    ApprovalStage,
    ApprovalWorkflow,
    AssignmentTarget,
    DOC_TYPE_CHOICES,
    Document,
    DocumentApprovalRequest,
    DocumentArchive,
    DocumentAccessRule,
    DocumentAssignment,
    DocumentCategory,
    DocumentSignature,
    DocumentTemplate,
    DocumentVersion,
    LegalHold,
    MediaAttachment,
    ReadAcknowledgment,
    RetentionPolicy,
    TemplateField,
)
from .services import approval as approval_svc
from .services import checkout as checkout_svc
from .services import legal_hold as legal_hold_svc
from .services import retention as retention_svc

logger = logging.getLogger(__name__)
PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# RBAC helper (L-10)
# ---------------------------------------------------------------------------

def _is_admin(user):
    return bool(getattr(user, 'is_tenant_admin', False) or user.is_superuser)


def tenant_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_admin(request.user):
            messages.error(
                request, 'You do not have permission to perform this action.',
            )
            return redirect('dms:index')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or None


def _user_agent(request):
    return (request.META.get('HTTP_USER_AGENT', '') or '')[:1000]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def index_view(request):
    tenant = request.tenant
    if tenant is None:
        return render(request, 'dms/index.html', {'kpi': {}})
    docs = Document.objects.filter(tenant=tenant)
    today = timezone.localdate()
    soon = today + timezone.timedelta(days=30)
    kpi = {
        'total_docs': docs.count(),
        'in_review': docs.filter(status='in_review').count(),
        'pending_approvals': DocumentApprovalRequest.objects.filter(
            tenant=tenant, status__in=('pending', 'in_progress'),
        ).count(),
        'my_pending_acks': DocumentAssignment.objects.filter(
            tenant=tenant, status='active',
        ).exclude(
            acknowledgments__acknowledger=request.user,
        ).count(),
        'active_holds': LegalHold.objects.filter(
            tenant=tenant, status='active',
        ).count(),
        'expiring_soon': docs.filter(
            expiry_date__isnull=False, expiry_date__lte=soon, expiry_date__gte=today,
        ).count(),
    }
    recent_docs = docs.select_related('category', 'owner').order_by('-id')[:8]
    open_approvals = (
        DocumentApprovalRequest.objects
        .filter(tenant=tenant, status__in=('pending', 'in_progress'))
        .select_related('document', 'workflow')
        .order_by('-id')[:8]
    )
    pending_acks_for_me = (
        DocumentAssignment.objects
        .filter(tenant=tenant, status='active')
        .exclude(acknowledgments__acknowledger=request.user)
        .select_related('document')
        .order_by('-id')[:8]
    )
    return render(request, 'dms/index.html', {
        'kpi': kpi,
        'recent_docs': recent_docs,
        'open_approvals': open_approvals,
        'pending_acks_for_me': pending_acks_for_me,
    })


# ===========================================================================
# 19.1  DOCUMENT CATEGORIES
# ===========================================================================

@login_required
def category_list_view(request):
    qs = DocumentCategory.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/categories/list.html', {'page_obj': page})


@login_required
def category_create_view(request):
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Category "{obj.name}" created.')
            return redirect('dms:category_list')
    else:
        form = DocumentCategoryForm(tenant=request.tenant)
    return render(request, 'dms/categories/form.html', {'form': form, 'mode': 'create'})


@login_required
def category_edit_view(request, pk):
    obj = get_object_or_404(DocumentCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.')
            return redirect('dms:category_list')
    else:
        form = DocumentCategoryForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/categories/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def category_delete_view(request, pk):
    obj = get_object_or_404(DocumentCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Category deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:category_list')


# ===========================================================================
# 19.1  DOCUMENTS
# ===========================================================================

@login_required
def document_list_view(request):
    qs = Document.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(title__icontains=q)
            | Q(summary__icontains=q) | Q(keywords__icontains=q),
        )
    doc_type = request.GET.get('doc_type', '')
    if doc_type:
        qs = qs.filter(doc_type=doc_type)
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category_id=category)
    qs = qs.select_related('category', 'owner', 'current_version')
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/documents/list.html', {
        'page_obj': page,
        'doc_type_choices': DOC_TYPE_CHOICES,
        'status_choices': Document.STATUS_CHOICES,
        'categories': DocumentCategory.objects.filter(
            tenant=request.tenant, is_active=True,
        ).order_by('name'),
    })


@login_required
def document_create_view(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Document "{obj.title}" created.')
            return redirect('dms:document_detail', pk=obj.pk)
    else:
        form = DocumentForm(tenant=request.tenant)
    return render(request, 'dms/documents/form.html', {'form': form, 'mode': 'create'})


@login_required
def document_detail_view(request, pk):
    obj = get_object_or_404(
        Document.objects.select_related('category', 'owner', 'current_version', 'retention_policy'),
        pk=pk, tenant=request.tenant,
    )
    versions = obj.versions.select_related('checked_out_by', 'uploaded_by').order_by('-id')
    approvals = obj.approval_requests.select_related('workflow').order_by('-id')[:10]
    access_rules = obj.access_rules.select_related('user', 'department', 'position')
    signatures = obj.signatures.select_related('signer').order_by('-signed_at')[:10]
    assignments = obj.assignments.order_by('-id')[:10]
    return render(request, 'dms/documents/detail.html', {
        'obj': obj,
        'versions': versions,
        'approvals': approvals,
        'access_rules': access_rules,
        'signatures': signatures,
        'assignments': assignments,
        'is_admin': _is_admin(request.user),
    })


@login_required
def document_edit_view(request, pk):
    obj = get_object_or_404(Document, pk=pk, tenant=request.tenant)
    if obj.is_locked:
        messages.error(request, 'Document is under legal hold and cannot be edited.')
        return redirect('dms:document_detail', pk=obj.pk)
    if request.method == 'POST':
        form = DocumentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Document updated.')
            return redirect('dms:document_detail', pk=obj.pk)
    else:
        form = DocumentForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/documents/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def document_delete_view(request, pk):
    obj = get_object_or_404(Document, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if obj.is_locked:
            messages.error(request, 'Document is under legal hold and cannot be deleted.')
            return redirect('dms:document_detail', pk=obj.pk)
        try:
            obj.delete()
            messages.success(request, 'Document deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:document_list')


@login_required
def document_submit_view(request, pk):
    obj = get_object_or_404(Document, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not obj.can_submit():
        messages.error(request, 'Document cannot be submitted in its current state.')
        return redirect('dms:document_detail', pk=obj.pk)
    obj.status = 'in_review'
    obj.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Document submitted for review.')
    return redirect('dms:document_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def document_archive_view(request, pk):
    obj = get_object_or_404(Document, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not obj.can_archive():
        messages.error(request, 'Document cannot be archived (locked or already archived).')
        return redirect('dms:document_detail', pk=obj.pk)
    with transaction.atomic():
        DocumentArchive.objects.create(
            tenant=obj.tenant, document=obj,
            archived_by=request.user,
            retention_until=obj.retention_until,
            status='archived',
        )
        obj.status = 'archived'
        obj.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Document archived.')
    return redirect('dms:document_detail', pk=obj.pk)


# ----- 19.1  Document Versions -----

@login_required
def version_create_view(request, doc_pk):
    doc = get_object_or_404(Document, pk=doc_pk, tenant=request.tenant)
    if doc.is_locked:
        messages.error(request, 'Document is under legal hold.')
        return redirect('dms:document_detail', pk=doc.pk)
    if request.method == 'POST':
        form = DocumentVersionForm(request.POST, request.FILES)
        if form.is_valid():
            ver = form.save(commit=False)
            ver.tenant = request.tenant
            ver.document = doc
            ver.uploaded_by = request.user
            ver.save()
            messages.success(request, f'Version {ver.version} created.')
            return redirect('dms:document_detail', pk=doc.pk)
    else:
        form = DocumentVersionForm()
    return render(request, 'dms/documents/version_form.html', {
        'form': form, 'document': doc, 'mode': 'create',
    })


@login_required
def version_edit_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    if ver.checked_out_by_id and ver.checked_out_by_id != request.user.id and not _is_admin(request.user):
        messages.error(
            request,
            f'Version checked out by {ver.checked_out_by}. Check it in first or ask a tenant admin.',
        )
        return redirect('dms:document_detail', pk=ver.document_id)
    if request.method == 'POST':
        form = DocumentVersionForm(request.POST, request.FILES, instance=ver)
        if form.is_valid():
            form.save()
            messages.success(request, 'Version updated.')
            return redirect('dms:document_detail', pk=ver.document_id)
    else:
        form = DocumentVersionForm(instance=ver)
    return render(request, 'dms/documents/version_form.html', {
        'form': form, 'document': ver.document, 'obj': ver, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def version_delete_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    doc_pk = ver.document_id
    if request.method == 'POST':
        try:
            ver.delete()
            messages.success(request, 'Version deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:document_detail', pk=doc_pk)


@login_required
def version_check_out_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        checkout_svc.check_out(ver, request.user)
        messages.success(request, f'Version {ver.version} checked out.')
    except checkout_svc.CheckoutError as exc:
        messages.error(request, str(exc))
    return redirect('dms:document_detail', pk=ver.document_id)


@login_required
def version_check_in_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        checkout_svc.check_in(ver, request.user, is_admin=_is_admin(request.user))
        messages.success(request, f'Version {ver.version} checked in.')
    except checkout_svc.CheckoutError as exc:
        messages.error(request, str(exc))
    return redirect('dms:document_detail', pk=ver.document_id)


@login_required
@tenant_admin_required
def version_release_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if ver.status not in ('draft', 'under_review'):
        messages.error(request, 'Only draft / under-review versions can be released.')
        return redirect('dms:document_detail', pk=ver.document_id)
    ver.status = 'released'
    ver.released_at = timezone.now()
    ver.save(update_fields=['status', 'released_at', 'updated_at'])
    messages.success(request, f'Version {ver.version} released.')
    return redirect('dms:document_detail', pk=ver.document_id)


@login_required
def version_download_view(request, pk):
    ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.tenant)
    if not ver.file:
        raise Http404('No file uploaded for this version.')
    return FileResponse(ver.file.open('rb'), as_attachment=True, filename=ver.file.name.split('/')[-1])


# ----- 19.1  Document Access Rules -----

@login_required
@tenant_admin_required
def access_create_view(request, doc_pk):
    doc = get_object_or_404(Document, pk=doc_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = DocumentAccessRuleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.tenant = request.tenant
            rule.document = doc
            rule.save()
            messages.success(request, 'Access rule added.')
            return redirect('dms:document_detail', pk=doc.pk)
    else:
        form = DocumentAccessRuleForm(tenant=request.tenant)
    return render(request, 'dms/documents/access_form.html', {
        'form': form, 'document': doc,
    })


@login_required
@tenant_admin_required
def access_delete_view(request, pk):
    rule = get_object_or_404(DocumentAccessRule, pk=pk, tenant=request.tenant)
    doc_pk = rule.document_id
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Access rule removed.')
    return redirect('dms:document_detail', pk=doc_pk)


# ===========================================================================
# 19.2  TEMPLATES
# ===========================================================================

@login_required
def template_list_view(request):
    qs = DocumentTemplate.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    applies = request.GET.get('applies_to_doc_type', '')
    if applies:
        qs = qs.filter(applies_to_doc_type=applies)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/templates/list.html', {
        'page_obj': page,
        'doc_type_choices': DOC_TYPE_CHOICES + [('any', 'Any')],
    })


@login_required
def template_create_view(request):
    if request.method == 'POST':
        form = DocumentTemplateForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Template "{obj.name}" created.')
            return redirect('dms:template_detail', pk=obj.pk)
    else:
        form = DocumentTemplateForm(tenant=request.tenant)
    return render(request, 'dms/templates/form.html', {'form': form, 'mode': 'create'})


@login_required
def template_detail_view(request, pk):
    obj = get_object_or_404(DocumentTemplate, pk=pk, tenant=request.tenant)
    fields = obj.fields.order_by('order', 'field_name')
    return render(request, 'dms/templates/detail.html', {
        'obj': obj, 'fields': fields,
    })


@login_required
def template_edit_view(request, pk):
    obj = get_object_or_404(DocumentTemplate, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = DocumentTemplateForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template updated.')
            return redirect('dms:template_detail', pk=obj.pk)
    else:
        form = DocumentTemplateForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/templates/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def template_delete_view(request, pk):
    obj = get_object_or_404(DocumentTemplate, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Template deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:template_list')


@login_required
def template_field_create_view(request, tpl_pk):
    tpl = get_object_or_404(DocumentTemplate, pk=tpl_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = TemplateFieldForm(request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.tenant = request.tenant
            f.template = tpl
            f.save()
            messages.success(request, 'Field added.')
            return redirect('dms:template_detail', pk=tpl.pk)
    else:
        form = TemplateFieldForm()
    return render(request, 'dms/templates/field_form.html', {
        'form': form, 'template': tpl, 'mode': 'create',
    })


@login_required
def template_field_edit_view(request, pk):
    f = get_object_or_404(TemplateField, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = TemplateFieldForm(request.POST, instance=f)
        if form.is_valid():
            form.save()
            messages.success(request, 'Field updated.')
            return redirect('dms:template_detail', pk=f.template_id)
    else:
        form = TemplateFieldForm(instance=f)
    return render(request, 'dms/templates/field_form.html', {
        'form': form, 'template': f.template, 'obj': f, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def template_field_delete_view(request, pk):
    f = get_object_or_404(TemplateField, pk=pk, tenant=request.tenant)
    tpl_pk = f.template_id
    if request.method == 'POST':
        f.delete()
        messages.success(request, 'Field deleted.')
    return redirect('dms:template_detail', pk=tpl_pk)


# ----- 19.2  Media Attachments -----

@login_required
def media_create_view(request, version_pk):
    ver = get_object_or_404(DocumentVersion, pk=version_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = MediaAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save(commit=False)
            m.tenant = request.tenant
            m.document_version = ver
            m.uploaded_by = request.user
            m.save()
            messages.success(request, 'Media attached.')
            return redirect('dms:document_detail', pk=ver.document_id)
    else:
        form = MediaAttachmentForm()
    return render(request, 'dms/documents/media_form.html', {
        'form': form, 'version': ver,
    })


@login_required
@tenant_admin_required
def media_delete_view(request, pk):
    m = get_object_or_404(MediaAttachment, pk=pk, tenant=request.tenant)
    doc_pk = m.document_version.document_id
    if request.method == 'POST':
        m.delete()
        messages.success(request, 'Media deleted.')
    return redirect('dms:document_detail', pk=doc_pk)


# ===========================================================================
# 19.3  APPROVAL WORKFLOWS
# ===========================================================================

@login_required
def workflow_list_view(request):
    qs = ApprovalWorkflow.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/workflows/list.html', {'page_obj': page})


@login_required
def workflow_create_view(request):
    if request.method == 'POST':
        form = ApprovalWorkflowForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Workflow "{obj.name}" created.')
            return redirect('dms:workflow_detail', pk=obj.pk)
    else:
        form = ApprovalWorkflowForm(tenant=request.tenant)
    return render(request, 'dms/workflows/form.html', {'form': form, 'mode': 'create'})


@login_required
def workflow_detail_view(request, pk):
    obj = get_object_or_404(ApprovalWorkflow, pk=pk, tenant=request.tenant)
    stages = obj.stages.order_by('stage_no')
    return render(request, 'dms/workflows/detail.html', {'obj': obj, 'stages': stages})


@login_required
def workflow_edit_view(request, pk):
    obj = get_object_or_404(ApprovalWorkflow, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ApprovalWorkflowForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Workflow updated.')
            return redirect('dms:workflow_detail', pk=obj.pk)
    else:
        form = ApprovalWorkflowForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/workflows/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def workflow_delete_view(request, pk):
    obj = get_object_or_404(ApprovalWorkflow, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Workflow deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:workflow_list')


@login_required
def stage_create_view(request, wf_pk):
    wf = get_object_or_404(ApprovalWorkflow, pk=wf_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ApprovalStageForm(request.POST)
        if form.is_valid():
            s = form.save(commit=False)
            s.tenant = request.tenant
            s.workflow = wf
            s.save()
            messages.success(request, 'Stage added.')
            return redirect('dms:workflow_detail', pk=wf.pk)
    else:
        form = ApprovalStageForm(initial={'stage_no': wf.stages.count() + 1})
    return render(request, 'dms/workflows/stage_form.html', {
        'form': form, 'workflow': wf, 'mode': 'create',
    })


@login_required
def stage_edit_view(request, pk):
    s = get_object_or_404(ApprovalStage, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ApprovalStageForm(request.POST, instance=s)
        if form.is_valid():
            form.save()
            messages.success(request, 'Stage updated.')
            return redirect('dms:workflow_detail', pk=s.workflow_id)
    else:
        form = ApprovalStageForm(instance=s)
    return render(request, 'dms/workflows/stage_form.html', {
        'form': form, 'workflow': s.workflow, 'obj': s, 'mode': 'edit',
    })


@login_required
@tenant_admin_required
def stage_delete_view(request, pk):
    s = get_object_or_404(ApprovalStage, pk=pk, tenant=request.tenant)
    wf_pk = s.workflow_id
    if request.method == 'POST':
        s.delete()
        messages.success(request, 'Stage deleted.')
    return redirect('dms:workflow_detail', pk=wf_pk)


# ===========================================================================
# 19.3  APPROVAL REQUESTS
# ===========================================================================

@login_required
def approval_list_view(request):
    qs = DocumentApprovalRequest.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(document__title__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    qs = qs.select_related('document', 'workflow')
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/approvals/list.html', {
        'page_obj': page,
        'status_choices': DocumentApprovalRequest.STATUS_CHOICES,
    })


@login_required
def approval_create_view(request):
    if request.method == 'POST':
        form = DocumentApprovalRequestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.requested_by = request.user
            obj.status = 'in_progress'
            obj.save()
            # Flip document to in_review on submit.
            doc = obj.document
            if doc.status == 'draft':
                doc.status = 'in_review'
                doc.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Approval request {obj.code} created.')
            return redirect('dms:approval_detail', pk=obj.pk)
    else:
        form = DocumentApprovalRequestForm(tenant=request.tenant)
    return render(request, 'dms/approvals/form.html', {'form': form, 'mode': 'create'})


@login_required
def approval_detail_view(request, pk):
    obj = get_object_or_404(
        DocumentApprovalRequest.objects.select_related('document', 'workflow', 'requested_by'),
        pk=pk, tenant=request.tenant,
    )
    stages = obj.workflow.stages.order_by('stage_no')
    actions = obj.actions.select_related('decided_by').order_by('-decided_at')
    current_stage = approval_svc.current_stage(obj)
    action_form = ApprovalActionForm()
    return render(request, 'dms/approvals/detail.html', {
        'obj': obj,
        'stages': stages,
        'actions': actions,
        'current_stage': current_stage,
        'action_form': action_form,
        'is_admin': _is_admin(request.user),
    })


@login_required
@tenant_admin_required
def approval_delete_view(request, pk):
    obj = get_object_or_404(DocumentApprovalRequest, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if obj.is_open():
            messages.error(request, 'Cannot delete an open approval request. Cancel first.')
            return redirect('dms:approval_detail', pk=obj.pk)
        try:
            obj.delete()
            messages.success(request, 'Approval request deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:approval_list')


@login_required
@tenant_admin_required
def approval_action_view(request, pk):
    obj = get_object_or_404(DocumentApprovalRequest, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not obj.is_open():
        messages.error(request, 'Approval request is not open.')
        return redirect('dms:approval_detail', pk=obj.pk)
    form = ApprovalActionForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        return redirect('dms:approval_detail', pk=obj.pk)
    decision = form.cleaned_data['decision']
    notes = form.cleaned_data.get('notes', '')
    typed_name = (form.cleaned_data.get('typed_name') or '').strip()
    stage = approval_svc.current_stage(obj)
    if stage is None:
        messages.error(request, 'No current stage configured for this workflow.')
        return redirect('dms:approval_detail', pk=obj.pk)

    sig = None
    with transaction.atomic():
        if stage.requires_signature:
            if not typed_name:
                typed_name = request.user.get_full_name() or request.user.username
            sig = DocumentSignature.objects.create(
                tenant=obj.tenant,
                document=obj.document,
                signer=request.user,
                meaning='approver',
                typed_name=typed_name,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
        ApprovalAction.objects.create(
            tenant=obj.tenant,
            request=obj,
            stage_no=obj.current_stage_no,
            decision=decision,
            decided_by=request.user,
            notes=notes,
            signature=sig,
        )

        if decision == 'reject':
            obj.status = 'rejected'
            obj.decided_at = timezone.now()
            obj.save(update_fields=['status', 'decided_at', 'updated_at'])
            messages.success(request, 'Approval rejected.')
            return redirect('dms:approval_detail', pk=obj.pk)
        if decision == 'return_for_revision':
            obj.status = 'cancelled'
            obj.decided_at = timezone.now()
            obj.save(update_fields=['status', 'decided_at', 'updated_at'])
            # Bounce document back to draft so the owner can revise.
            doc = obj.document
            doc.status = 'draft'
            doc.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Returned for revision. Document is back in draft.')
            return redirect('dms:approval_detail', pk=obj.pk)

        # decision == 'approve'
        next_stage = approval_svc.advance_stage(obj)
        if next_stage is None:
            obj.status = 'approved'
            obj.decided_at = timezone.now()
            obj.save(update_fields=['status', 'decided_at', 'updated_at'])
            # Flip document to effective.
            doc = obj.document
            doc.status = 'effective'
            doc.effective_date = obj.effective_date or timezone.localdate()
            doc.save(update_fields=['status', 'effective_date', 'updated_at'])
            messages.success(request, 'Approval complete. Document is now effective.')
        elif next_stage != obj.current_stage_no:
            obj.current_stage_no = next_stage
            obj.save(update_fields=['current_stage_no', 'updated_at'])
            messages.success(request, f'Stage approved. Advanced to stage {next_stage}.')
        else:
            messages.success(request, 'Approval recorded. Awaiting more approvals at this stage.')
    return redirect('dms:approval_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def approval_cancel_view(request, pk):
    obj = get_object_or_404(DocumentApprovalRequest, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not obj.can_cancel():
        messages.error(request, 'Cannot cancel - request is not open.')
        return redirect('dms:approval_detail', pk=obj.pk)
    obj.status = 'cancelled'
    obj.decided_at = timezone.now()
    obj.save(update_fields=['status', 'decided_at', 'updated_at'])
    messages.success(request, 'Approval cancelled.')
    return redirect('dms:approval_detail', pk=obj.pk)


# ===========================================================================
# 19.4  ASSIGNMENTS
# ===========================================================================

@login_required
def assignment_list_view(request):
    qs = DocumentAssignment.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(document__title__icontains=q)
            | Q(instructions__icontains=q),
        )
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    qs = qs.select_related('document', 'assigned_by')
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/assignments/list.html', {
        'page_obj': page,
        'status_choices': DocumentAssignment.STATUS_CHOICES,
    })


@login_required
def assignment_create_view(request):
    if request.method == 'POST':
        form = DocumentAssignmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.assigned_by = request.user
            obj.save()
            messages.success(request, f'Assignment {obj.code} created.')
            return redirect('dms:assignment_detail', pk=obj.pk)
    else:
        form = DocumentAssignmentForm(tenant=request.tenant)
    return render(request, 'dms/assignments/form.html', {'form': form, 'mode': 'create'})


@login_required
def assignment_detail_view(request, pk):
    obj = get_object_or_404(
        DocumentAssignment.objects.select_related('document', 'assigned_by'),
        pk=pk, tenant=request.tenant,
    )
    targets = obj.targets.select_related('department', 'position', 'employee', 'user')
    acks = obj.acknowledgments.select_related('acknowledger').order_by('-acknowledged_at')
    has_acked = obj.acknowledgments.filter(acknowledger=request.user).exists()
    ack_form = ReadAcknowledgmentForm()
    return render(request, 'dms/assignments/detail.html', {
        'obj': obj,
        'targets': targets,
        'acks': acks,
        'has_acked': has_acked,
        'ack_form': ack_form,
        'is_admin': _is_admin(request.user),
    })


@login_required
def assignment_edit_view(request, pk):
    obj = get_object_or_404(DocumentAssignment, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = DocumentAssignmentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Assignment updated.')
            return redirect('dms:assignment_detail', pk=obj.pk)
    else:
        form = DocumentAssignmentForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/assignments/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def assignment_delete_view(request, pk):
    obj = get_object_or_404(DocumentAssignment, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Assignment deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:assignment_list')


@login_required
@tenant_admin_required
def assignment_complete_view(request, pk):
    obj = get_object_or_404(DocumentAssignment, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    obj.status = 'completed'
    obj.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Assignment marked complete.')
    return redirect('dms:assignment_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def assignment_cancel_view(request, pk):
    obj = get_object_or_404(DocumentAssignment, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    obj.status = 'cancelled'
    obj.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Assignment cancelled.')
    return redirect('dms:assignment_detail', pk=obj.pk)


@login_required
def assignment_ack_view(request, pk):
    obj = get_object_or_404(DocumentAssignment, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if obj.status != 'active':
        messages.error(request, 'Assignment is not active.')
        return redirect('dms:assignment_detail', pk=obj.pk)
    form = ReadAcknowledgmentForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        return redirect('dms:assignment_detail', pk=obj.pk)
    version = obj.document.current_version
    if version is None:
        latest = obj.document.versions.order_by('-id').first()
        if latest is None:
            messages.error(request, 'Document has no versions to acknowledge.')
            return redirect('dms:assignment_detail', pk=obj.pk)
        version = latest
    # Idempotent on (assignment, acknowledger, version).
    existing = ReadAcknowledgment.objects.filter(
        assignment=obj, acknowledger=request.user, document_version=version,
    ).first()
    if existing:
        messages.info(request, 'Already acknowledged.')
        return redirect('dms:assignment_detail', pk=obj.pk)
    typed = (form.cleaned_data.get('typed_name') or '').strip()
    if not typed:
        typed = request.user.get_full_name() or request.user.username
    ReadAcknowledgment.objects.create(
        tenant=obj.tenant,
        assignment=obj,
        document_version=version,
        acknowledger=request.user,
        typed_name=typed,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        notes=form.cleaned_data.get('notes', ''),
    )
    messages.success(request, 'Acknowledgment recorded.')
    return redirect('dms:assignment_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def target_create_view(request, asn_pk):
    asn = get_object_or_404(DocumentAssignment, pk=asn_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = AssignmentTargetForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            t = form.save(commit=False)
            t.tenant = request.tenant
            t.assignment = asn
            t.save()
            messages.success(request, 'Target added.')
            return redirect('dms:assignment_detail', pk=asn.pk)
    else:
        form = AssignmentTargetForm(tenant=request.tenant)
    return render(request, 'dms/assignments/target_form.html', {
        'form': form, 'assignment': asn,
    })


@login_required
@tenant_admin_required
def target_delete_view(request, pk):
    t = get_object_or_404(AssignmentTarget, pk=pk, tenant=request.tenant)
    asn_pk = t.assignment_id
    if request.method == 'POST':
        t.delete()
        messages.success(request, 'Target removed.')
    return redirect('dms:assignment_detail', pk=asn_pk)


@login_required
def my_acknowledgments_view(request):
    pending = (
        DocumentAssignment.objects
        .filter(tenant=request.tenant, status='active')
        .exclude(acknowledgments__acknowledger=request.user)
        .select_related('document')
        .order_by('-id')
    )
    page = Paginator(pending, PAGE_SIZE).get_page(request.GET.get('page'))
    completed = (
        ReadAcknowledgment.objects
        .filter(tenant=request.tenant, acknowledger=request.user)
        .select_related('assignment', 'document_version', 'document_version__document')
        .order_by('-acknowledged_at')[:20]
    )
    return render(request, 'dms/assignments/my_acknowledgments.html', {
        'page_obj': page,
        'completed': completed,
    })


# ===========================================================================
# 19.5  RETENTION POLICIES
# ===========================================================================

@login_required
def policy_list_view(request):
    qs = RetentionPolicy.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/retention/policy_list.html', {'page_obj': page})


@login_required
def policy_create_view(request):
    if request.method == 'POST':
        form = RetentionPolicyForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Policy "{obj.name}" created.')
            return redirect('dms:policy_list')
    else:
        form = RetentionPolicyForm(tenant=request.tenant)
    return render(request, 'dms/retention/policy_form.html', {'form': form, 'mode': 'create'})


@login_required
def policy_edit_view(request, pk):
    obj = get_object_or_404(RetentionPolicy, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = RetentionPolicyForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Policy updated.')
            return redirect('dms:policy_list')
    else:
        form = RetentionPolicyForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/retention/policy_form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def policy_delete_view(request, pk):
    obj = get_object_or_404(RetentionPolicy, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Policy deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:policy_list')


# ===========================================================================
# 19.5  ARCHIVES
# ===========================================================================

@login_required
def archive_list_view(request):
    qs = DocumentArchive.objects.filter(tenant=request.tenant).select_related('document')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(document__title__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-archived_at'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/retention/archive_list.html', {
        'page_obj': page,
        'status_choices': DocumentArchive.STATUS_CHOICES,
    })


@login_required
def archive_detail_view(request, pk):
    obj = get_object_or_404(
        DocumentArchive.objects.select_related('document', 'archived_by', 'restored_by'),
        pk=pk, tenant=request.tenant,
    )
    return render(request, 'dms/retention/archive_detail.html', {
        'obj': obj,
        'restore_form': DocumentArchiveRestoreForm(),
        'is_admin': _is_admin(request.user),
    })


@login_required
@tenant_admin_required
def archive_restore_view(request, pk):
    obj = get_object_or_404(DocumentArchive, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not obj.can_restore():
        messages.error(request, 'Cannot restore (already restored or document under hold).')
        return redirect('dms:archive_detail', pk=obj.pk)
    form = DocumentArchiveRestoreForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        return redirect('dms:archive_detail', pk=obj.pk)
    with transaction.atomic():
        obj.status = 'restored'
        obj.restored_at = timezone.now()
        obj.restored_by = request.user
        obj.notes = (obj.notes + '\n[restore] ' + form.cleaned_data['notes']).strip()
        obj.save(update_fields=['status', 'restored_at', 'restored_by', 'notes', 'updated_at'])
        doc = obj.document
        doc.status = 'effective' if doc.effective_date else 'draft'
        doc.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Archive restored.')
    return redirect('dms:archive_detail', pk=obj.pk)


# ===========================================================================
# 19.5  LEGAL HOLDS
# ===========================================================================

@login_required
def legal_hold_list_view(request):
    qs = LegalHold.objects.filter(tenant=request.tenant)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(reason__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-id'), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'dms/legal_holds/list.html', {
        'page_obj': page,
        'status_choices': LegalHold.STATUS_CHOICES,
    })


@login_required
@tenant_admin_required
def legal_hold_create_view(request):
    if request.method == 'POST':
        form = LegalHoldForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.requested_by = request.user
                obj.save()
                form.save_m2m()
                legal_hold_svc.apply_hold(obj)
            messages.success(request, f'Legal hold {obj.code} created.')
            return redirect('dms:legal_hold_detail', pk=obj.pk)
    else:
        form = LegalHoldForm(tenant=request.tenant)
    return render(request, 'dms/legal_holds/form.html', {'form': form, 'mode': 'create'})


@login_required
def legal_hold_detail_view(request, pk):
    obj = get_object_or_404(LegalHold, pk=pk, tenant=request.tenant)
    docs = obj.documents.all().order_by('code')
    return render(request, 'dms/legal_holds/detail.html', {
        'obj': obj,
        'docs': docs,
        'release_form': LegalHoldReleaseForm(),
        'is_admin': _is_admin(request.user),
    })


@login_required
@tenant_admin_required
def legal_hold_edit_view(request, pk):
    obj = get_object_or_404(LegalHold, pk=pk, tenant=request.tenant)
    if obj.status == 'released':
        messages.error(request, 'Released holds cannot be edited.')
        return redirect('dms:legal_hold_detail', pk=obj.pk)
    if request.method == 'POST':
        form = LegalHoldForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                legal_hold_svc.apply_hold(obj)
            messages.success(request, 'Legal hold updated.')
            return redirect('dms:legal_hold_detail', pk=obj.pk)
    else:
        form = LegalHoldForm(instance=obj, tenant=request.tenant)
    return render(request, 'dms/legal_holds/form.html', {'form': form, 'obj': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
def legal_hold_delete_view(request, pk):
    obj = get_object_or_404(LegalHold, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        if obj.status == 'active':
            messages.error(request, 'Release the hold before deleting.')
            return redirect('dms:legal_hold_detail', pk=obj.pk)
        try:
            obj.delete()
            messages.success(request, 'Legal hold deleted.')
        except Exception as exc:
            messages.error(request, f'Cannot delete: {exc}')
    return redirect('dms:legal_hold_list')


@login_required
@tenant_admin_required
def legal_hold_release_view(request, pk):
    obj = get_object_or_404(LegalHold, pk=pk, tenant=request.tenant)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if obj.status != 'active':
        messages.error(request, 'Hold is not active.')
        return redirect('dms:legal_hold_detail', pk=obj.pk)
    form = LegalHoldReleaseForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, '; '.join(err))
        return redirect('dms:legal_hold_detail', pk=obj.pk)
    with transaction.atomic():
        obj.status = 'released'
        obj.released_at = timezone.now()
        obj.released_by = request.user
        obj.release_notes = form.cleaned_data['release_notes']
        obj.save(update_fields=[
            'status', 'released_at', 'released_by', 'release_notes', 'updated_at',
        ])
        legal_hold_svc.release_hold(obj)
    messages.success(request, 'Legal hold released.')
    return redirect('dms:legal_hold_detail', pk=obj.pk)
