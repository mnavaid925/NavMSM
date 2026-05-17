"""Views for Module 20 - Workflow & Business Process Automation.

CRUD-complete per CLAUDE.md "CRUD Completeness Rules". Every list view
filters by ``request.tenant`` first, parses GET filter params, then
paginates. Workflow / delete views are POST-only and gated to tenant
admins via ``@tenant_admin_required`` (L-10).
"""
from __future__ import annotations

import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import models as M
from . import forms as F
from .services import approval as approval_svc
from .services import bpmn_engine
from .services import integration as integration_svc
from .services import notification as notification_svc
from .services import process_mining

logger = logging.getLogger(__name__)
User = get_user_model()
PAGE_SIZE = 25


# ----------------------------------------------------------------------------
# RBAC helper (L-10)
# ----------------------------------------------------------------------------

def _is_admin(user):
    return bool(getattr(user, 'is_tenant_admin', False) or user.is_superuser)


def tenant_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_admin(request.user):
            messages.error(request, 'You do not have permission to perform this action.')
            return redirect('wfa:index')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _paginate(request, queryset):
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return page, paginator


# ----------------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------------

@login_required
def index_view(request):
    tenant = request.tenant
    ctx = {'kpi': {}, 'recent_instances': [], 'pending_approvals': [], 'recent_runs': []}
    if tenant is None:
        return render(request, 'wfa/index.html', ctx)
    instances = M.ProcessInstance.objects.filter(tenant=tenant)
    requests_qs = M.ApprovalRequest.objects.filter(tenant=tenant)
    notes = M.Notification.objects.filter(tenant=tenant)
    runs = M.IntegrationRun.objects.filter(tenant=tenant)
    today = timezone.localdate()
    ctx['kpi'] = {
        'active_definitions': M.ProcessDefinition.objects.filter(tenant=tenant, status='active').count(),
        'running_instances': instances.filter(status__in=('pending', 'running')).count(),
        'pending_approvals': requests_qs.filter(status__in=('pending', 'in_progress', 'escalated')).count(),
        'my_pending': requests_qs.filter(
            status__in=('pending', 'in_progress', 'escalated'),
            requested_by=request.user,
        ).count(),
        'notifications_today': notes.filter(triggered_at__date=today).count(),
        'failed_integrations': runs.filter(status='failed').count(),
        'open_suggestions': M.ProcessOptimizationSuggestion.objects.filter(
            tenant=tenant, status='new',
        ).count(),
    }
    ctx['recent_instances'] = instances.select_related('definition').order_by('-started_at')[:8]
    ctx['pending_approvals'] = requests_qs.select_related('policy').filter(
        status__in=('pending', 'in_progress', 'escalated'),
    ).order_by('-requested_at')[:8]
    ctx['recent_runs'] = runs.select_related('flow').order_by('-started_at')[:8]
    return render(request, 'wfa/index.html', ctx)


# ============================================================================
# 20.1  Visual Workflow Designer
# ============================================================================

# --- ProcessCategory ---------------------------------------------------------

@login_required
def category_list_view(request):
    qs = M.ProcessCategory.objects.filter(tenant=request.tenant) if request.tenant else M.ProcessCategory.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.order_by('name'))
    return render(request, 'wfa/processes/category_list.html', {'page': page, 'q': q, 'active': active})


@login_required
@tenant_admin_required
def category_create_view(request):
    if request.method == 'POST':
        form = F.ProcessCategoryForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Process category created.')
            return redirect('wfa:category_list')
    else:
        form = F.ProcessCategoryForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/processes/category_form.html', {'form': form, 'is_edit': False})


@login_required
@tenant_admin_required
def category_edit_view(request, pk):
    obj = get_object_or_404(M.ProcessCategory, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ProcessCategoryForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Process category updated.')
            return redirect('wfa:category_list')
    else:
        form = F.ProcessCategoryForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/processes/category_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def category_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessCategory, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Process category deleted.')
    return redirect('wfa:category_list')


# --- ProcessDefinition ------------------------------------------------------

@login_required
def process_list_view(request):
    qs = M.ProcessDefinition.objects.filter(tenant=request.tenant) if request.tenant else M.ProcessDefinition.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category_id=category)
    page, _ = _paginate(request, qs.select_related('category').order_by('-id'))
    return render(request, 'wfa/processes/list.html', {
        'page': page, 'q': q, 'status': status, 'category': category,
        'status_choices': M.PROCESS_STATUS_CHOICES,
        'categories': M.ProcessCategory.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
@tenant_admin_required
def process_create_view(request):
    if request.method == 'POST':
        form = F.ProcessDefinitionForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Process {obj.code} created.')
            return redirect('wfa:process_detail', pk=obj.pk)
    else:
        form = F.ProcessDefinitionForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/processes/form.html', {'form': form, 'is_edit': False})


@login_required
def process_detail_view(request, pk):
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    nodes = obj.nodes.all().order_by('order', 'id')
    transitions = obj.transitions.select_related('from_node', 'to_node').all()
    return render(request, 'wfa/processes/detail.html', {
        'obj': obj, 'nodes': nodes, 'transitions': transitions,
        'instances': obj.instances.order_by('-started_at')[:10],
    })


@login_required
@tenant_admin_required
def process_edit_view(request, pk):
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ProcessDefinitionForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Process updated.')
            return redirect('wfa:process_detail', pk=obj.pk)
    else:
        form = F.ProcessDefinitionForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/processes/form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def process_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    if obj.status != 'draft':
        messages.error(request, 'Only draft processes can be deleted.')
        return redirect('wfa:process_detail', pk=obj.pk)
    obj.delete()
    messages.success(request, 'Process deleted.')
    return redirect('wfa:process_list')


@login_required
@tenant_admin_required
@require_POST
def process_activate_view(request, pk):
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    updated = M.ProcessDefinition.all_objects.filter(pk=obj.pk, status='draft').update(status='active')
    if updated:
        messages.success(request, 'Process activated.')
    else:
        messages.error(request, 'Only draft processes can be activated.')
    return redirect('wfa:process_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def process_archive_view(request, pk):
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    M.ProcessDefinition.all_objects.filter(pk=obj.pk, status='active').update(status='archived')
    messages.success(request, 'Process archived.')
    return redirect('wfa:process_detail', pk=obj.pk)


@login_required
def process_diagram_view(request, pk):
    """Server-side SVG of the process graph - no JS canvas."""
    obj = get_object_or_404(M.ProcessDefinition, pk=pk, tenant=request.tenant)
    nodes = list(obj.nodes.all().order_by('order', 'id'))
    transitions = list(obj.transitions.select_related('from_node', 'to_node').all())
    # Auto-place nodes in a simple left-to-right flow if positions are zero.
    spacing_x, spacing_y, box_w, box_h = 180, 90, 140, 50
    layout = {}
    auto_idx = 0
    for n in nodes:
        if n.position_x or n.position_y:
            layout[n.pk] = (n.position_x, n.position_y)
        else:
            layout[n.pk] = (40 + auto_idx * spacing_x, 60)
            auto_idx += 1
    width = max((x for x, _ in layout.values()), default=200) + box_w + 60
    height = max((y for _, y in layout.values()), default=200) + box_h + 60
    return render(request, 'wfa/processes/diagram.html', {
        'obj': obj, 'nodes': nodes, 'transitions': transitions,
        'layout': layout, 'box_w': box_w, 'box_h': box_h,
        'svg_w': width, 'svg_h': height,
    })


# --- ProcessNode -------------------------------------------------------------

@login_required
@tenant_admin_required
def node_create_view(request, definition_pk):
    definition = get_object_or_404(M.ProcessDefinition, pk=definition_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ProcessNodeForm(request.POST, tenant=request.tenant, user=request.user, initial={'definition': definition})
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.definition = definition
            obj.save()
            messages.success(request, 'Node added.')
            return redirect('wfa:process_detail', pk=definition.pk)
    else:
        form = F.ProcessNodeForm(tenant=request.tenant, user=request.user, initial={'definition': definition})
    return render(request, 'wfa/processes/node_form.html', {
        'form': form, 'definition': definition, 'is_edit': False,
    })


@login_required
@tenant_admin_required
def node_edit_view(request, pk):
    obj = get_object_or_404(M.ProcessNode, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ProcessNodeForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Node updated.')
            return redirect('wfa:process_detail', pk=obj.definition_id)
    else:
        form = F.ProcessNodeForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/processes/node_form.html', {
        'form': form, 'definition': obj.definition, 'is_edit': True, 'obj': obj,
    })


@login_required
@tenant_admin_required
@require_POST
def node_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessNode, pk=pk, tenant=request.tenant)
    definition_pk = obj.definition_id
    try:
        obj.delete()
        messages.success(request, 'Node deleted.')
    except Exception as exc:
        messages.error(request, f'Cannot delete node: {exc}')
    return redirect('wfa:process_detail', pk=definition_pk)


# --- ProcessTransition -------------------------------------------------------

@login_required
@tenant_admin_required
def transition_create_view(request, definition_pk):
    definition = get_object_or_404(M.ProcessDefinition, pk=definition_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ProcessTransitionForm(request.POST, tenant=request.tenant, user=request.user, initial={'definition': definition})
        # Constrain from/to node querysets to this definition.
        form.fields['from_node'].queryset = definition.nodes.all()
        form.fields['to_node'].queryset = definition.nodes.all()
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.definition = definition
            obj.save()
            messages.success(request, 'Transition added.')
            return redirect('wfa:process_detail', pk=definition.pk)
    else:
        form = F.ProcessTransitionForm(tenant=request.tenant, user=request.user, initial={'definition': definition})
        form.fields['from_node'].queryset = definition.nodes.all()
        form.fields['to_node'].queryset = definition.nodes.all()
    return render(request, 'wfa/processes/transition_form.html', {
        'form': form, 'definition': definition, 'is_edit': False,
    })


@login_required
@tenant_admin_required
@require_POST
def transition_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessTransition, pk=pk, tenant=request.tenant)
    definition_pk = obj.definition_id
    obj.delete()
    messages.success(request, 'Transition deleted.')
    return redirect('wfa:process_detail', pk=definition_pk)


# --- ProcessInstance ---------------------------------------------------------

@login_required
def instance_list_view(request):
    qs = M.ProcessInstance.objects.filter(tenant=request.tenant) if request.tenant else M.ProcessInstance.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(definition__name__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    definition = request.GET.get('definition', '')
    if definition:
        qs = qs.filter(definition_id=definition)
    page, _ = _paginate(request, qs.select_related('definition').order_by('-started_at'))
    return render(request, 'wfa/instances/list.html', {
        'page': page, 'q': q, 'status': status, 'definition': definition,
        'status_choices': M.INSTANCE_STATUS_CHOICES,
        'definitions': M.ProcessDefinition.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
@tenant_admin_required
def instance_create_view(request):
    if request.method == 'POST':
        form = F.ProcessInstanceForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.started_by = request.user
            start_node = obj.definition.nodes.filter(node_type='start').order_by('order', 'id').first()
            obj.current_node = start_node
            obj.status = 'running' if start_node else 'pending'
            obj.save()
            M.ProcessActivity.all_objects.create(
                tenant=request.tenant,
                instance=obj,
                node=start_node,
                event='entered',
                actor=request.user,
            )
            messages.success(request, f'Instance {obj.code} started.')
            return redirect('wfa:instance_detail', pk=obj.pk)
    else:
        form = F.ProcessInstanceForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/instances/form.html', {'form': form, 'is_edit': False})


@login_required
def instance_detail_view(request, pk):
    obj = get_object_or_404(M.ProcessInstance, pk=pk, tenant=request.tenant)
    activities = obj.activities.select_related('node', 'actor').order_by('-recorded_at')[:50]
    variables = obj.variables.all().order_by('name')
    metrics = obj.metrics.select_related('node').order_by('-recorded_at')
    return render(request, 'wfa/instances/detail.html', {
        'obj': obj, 'activities': activities, 'variables': variables, 'metrics': metrics,
    })


@login_required
@tenant_admin_required
@require_POST
def instance_advance_view(request, pk):
    obj = get_object_or_404(M.ProcessInstance, pk=pk, tenant=request.tenant)
    if not obj.is_active():
        messages.error(request, 'Instance is no longer active.')
        return redirect('wfa:instance_detail', pk=obj.pk)
    with transaction.atomic():
        nxt = bpmn_engine.next_node(obj)
        if nxt is None:
            # Terminal - mark complete.
            M.ProcessInstance.all_objects.filter(pk=obj.pk).update(
                status='completed',
                completed_at=timezone.now(),
                current_node=None,
            )
            M.ProcessActivity.all_objects.create(
                tenant=request.tenant,
                instance=obj,
                node=obj.current_node,
                event='completed',
                actor=request.user,
            )
            messages.success(request, 'Instance completed.')
        else:
            M.ProcessInstance.all_objects.filter(pk=obj.pk).update(current_node=nxt)
            M.ProcessActivity.all_objects.create(
                tenant=request.tenant,
                instance=obj,
                node=nxt,
                event='entered',
                actor=request.user,
            )
            messages.success(request, f'Advanced to {nxt.name}.')
    return redirect('wfa:instance_detail', pk=obj.pk)


@login_required
@tenant_admin_required
def instance_cancel_view(request, pk):
    obj = get_object_or_404(M.ProcessInstance, pk=pk, tenant=request.tenant)
    if not obj.is_active():
        messages.error(request, 'Instance is no longer active.')
        return redirect('wfa:instance_detail', pk=obj.pk)
    if request.method == 'POST':
        form = F.ProcessInstanceCancelForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                M.ProcessInstance.all_objects.filter(pk=obj.pk).update(
                    status='cancelled', completed_at=timezone.now(),
                )
                M.ProcessActivity.all_objects.create(
                    tenant=request.tenant,
                    instance=obj,
                    node=obj.current_node,
                    event='cancelled',
                    actor=request.user,
                    notes=form.cleaned_data['reason'],
                )
            messages.success(request, 'Instance cancelled.')
            return redirect('wfa:instance_detail', pk=obj.pk)
    else:
        form = F.ProcessInstanceCancelForm()
    return render(request, 'wfa/instances/cancel.html', {'obj': obj, 'form': form})


@login_required
@tenant_admin_required
@require_POST
def instance_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessInstance, pk=pk, tenant=request.tenant)
    if obj.is_active():
        messages.error(request, 'Cannot delete an active instance; cancel it first.')
        return redirect('wfa:instance_detail', pk=obj.pk)
    obj.delete()
    messages.success(request, 'Instance deleted.')
    return redirect('wfa:instance_list')


# ============================================================================
# 20.2  Approval Engine
# ============================================================================

# --- ApprovalPolicy ----------------------------------------------------------

@login_required
def policy_list_view(request):
    qs = M.ApprovalPolicy.objects.filter(tenant=request.tenant) if request.tenant else M.ApprovalPolicy.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(applies_to_type__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.order_by('name'))
    return render(request, 'wfa/approvals/policy_list.html', {'page': page, 'q': q, 'active': active})


@login_required
@tenant_admin_required
def policy_create_view(request):
    if request.method == 'POST':
        form = F.ApprovalPolicyForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Policy created.')
            return redirect('wfa:policy_detail', pk=obj.pk)
    else:
        form = F.ApprovalPolicyForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/policy_form.html', {'form': form, 'is_edit': False})


@login_required
def policy_detail_view(request, pk):
    obj = get_object_or_404(M.ApprovalPolicy, pk=pk, tenant=request.tenant)
    levels = obj.levels.order_by('level_no')
    rules = obj.escalation_rules.order_by('level_no', 'trigger_hours_overdue')
    requests_qs = obj.requests.order_by('-requested_at')[:20]
    return render(request, 'wfa/approvals/policy_detail.html', {
        'obj': obj, 'levels': levels, 'rules': rules, 'requests_qs': requests_qs,
    })


@login_required
@tenant_admin_required
def policy_edit_view(request, pk):
    obj = get_object_or_404(M.ApprovalPolicy, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ApprovalPolicyForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Policy updated.')
            return redirect('wfa:policy_detail', pk=obj.pk)
    else:
        form = F.ApprovalPolicyForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/policy_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def policy_delete_view(request, pk):
    obj = get_object_or_404(M.ApprovalPolicy, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Policy deleted.')
    return redirect('wfa:policy_list')


# --- ApprovalLevel -----------------------------------------------------------

@login_required
@tenant_admin_required
def level_create_view(request, policy_pk):
    policy = get_object_or_404(M.ApprovalPolicy, pk=policy_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ApprovalLevelForm(request.POST, tenant=request.tenant, user=request.user, initial={'policy': policy})
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.policy = policy
            obj.save()
            messages.success(request, 'Level added.')
            return redirect('wfa:policy_detail', pk=policy.pk)
    else:
        next_no = (policy.levels.order_by('-level_no').first().level_no + 1) if policy.levels.exists() else 1
        form = F.ApprovalLevelForm(tenant=request.tenant, user=request.user, initial={'policy': policy, 'level_no': next_no})
    return render(request, 'wfa/approvals/level_form.html', {'form': form, 'policy': policy, 'is_edit': False})


@login_required
@tenant_admin_required
def level_edit_view(request, pk):
    obj = get_object_or_404(M.ApprovalLevel, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ApprovalLevelForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Level updated.')
            return redirect('wfa:policy_detail', pk=obj.policy_id)
    else:
        form = F.ApprovalLevelForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/level_form.html', {'form': form, 'policy': obj.policy, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def level_delete_view(request, pk):
    obj = get_object_or_404(M.ApprovalLevel, pk=pk, tenant=request.tenant)
    policy_pk = obj.policy_id
    obj.delete()
    messages.success(request, 'Level deleted.')
    return redirect('wfa:policy_detail', pk=policy_pk)


# --- EscalationRule ----------------------------------------------------------

@login_required
@tenant_admin_required
def escalation_create_view(request, policy_pk):
    policy = get_object_or_404(M.ApprovalPolicy, pk=policy_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.EscalationRuleForm(request.POST, tenant=request.tenant, user=request.user, initial={'policy': policy})
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.policy = policy
            obj.save()
            messages.success(request, 'Escalation rule added.')
            return redirect('wfa:policy_detail', pk=policy.pk)
    else:
        form = F.EscalationRuleForm(tenant=request.tenant, user=request.user, initial={'policy': policy})
    return render(request, 'wfa/approvals/escalation_form.html', {'form': form, 'policy': policy, 'is_edit': False})


@login_required
@tenant_admin_required
@require_POST
def escalation_delete_view(request, pk):
    obj = get_object_or_404(M.EscalationRule, pk=pk, tenant=request.tenant)
    policy_pk = obj.policy_id
    obj.delete()
    messages.success(request, 'Escalation rule deleted.')
    return redirect('wfa:policy_detail', pk=policy_pk)


# --- ApprovalRequest ---------------------------------------------------------

@login_required
def request_list_view(request):
    qs = M.ApprovalRequest.objects.filter(tenant=request.tenant) if request.tenant else M.ApprovalRequest.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(subject__icontains=q))
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    policy = request.GET.get('policy', '')
    if policy:
        qs = qs.filter(policy_id=policy)
    page, _ = _paginate(request, qs.select_related('policy', 'requested_by').order_by('-requested_at'))
    return render(request, 'wfa/approvals/request_list.html', {
        'page': page, 'q': q, 'status': status, 'policy': policy,
        'status_choices': M.APPROVAL_STATUS_CHOICES,
        'policies': M.ApprovalPolicy.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
def my_requests_view(request):
    qs = M.ApprovalRequest.objects.filter(
        tenant=request.tenant, requested_by=request.user,
    ) if request.tenant else M.ApprovalRequest.objects.none()
    page, _ = _paginate(request, qs.select_related('policy').order_by('-requested_at'))
    return render(request, 'wfa/approvals/my_requests.html', {'page': page})


@login_required
def request_create_view(request):
    if request.method == 'POST':
        form = F.ApprovalRequestForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.requested_by = request.user
                obj.save()
                approval_svc.submit(obj, actor=request.user)
            messages.success(request, f'Request {obj.code} submitted.')
            return redirect('wfa:request_detail', pk=obj.pk)
    else:
        form = F.ApprovalRequestForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/request_form.html', {'form': form, 'is_edit': False})


@login_required
def request_detail_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    logs = obj.action_logs.select_related('actor', 'delegated_to').order_by('-decided_at')
    cur_level = approval_svc.current_level(obj)
    return render(request, 'wfa/approvals/request_detail.html', {
        'obj': obj, 'logs': logs, 'current_level': cur_level,
        'decision_form': F.ApprovalDecisionForm(),
        'reject_form': F.ApprovalRejectForm(),
        'delegate_form': F.ApprovalDelegateActionForm(),
    })


@login_required
@tenant_admin_required
@require_POST
def request_approve_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    if not obj.is_open():
        messages.error(request, 'Request is no longer open.')
        return redirect('wfa:request_detail', pk=obj.pk)
    notes = request.POST.get('notes', '')
    approval_svc.approve(obj, actor=request.user, notes=notes)
    messages.success(request, 'Approval recorded.')
    return redirect('wfa:request_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def request_reject_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    if not obj.is_open():
        messages.error(request, 'Request is no longer open.')
        return redirect('wfa:request_detail', pk=obj.pk)
    form = F.ApprovalRejectForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Rejection notes are required.')
        return redirect('wfa:request_detail', pk=obj.pk)
    approval_svc.reject(obj, actor=request.user, notes=form.cleaned_data['notes'])
    messages.success(request, 'Request rejected.')
    return redirect('wfa:request_detail', pk=obj.pk)


@login_required
@require_POST
def request_delegate_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    if not obj.is_open():
        messages.error(request, 'Request is no longer open.')
        return redirect('wfa:request_detail', pk=obj.pk)
    form = F.ApprovalDelegateActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Provide a delegate user.')
        return redirect('wfa:request_detail', pk=obj.pk)
    delegate_user = User.objects.filter(pk=form.cleaned_data['delegate_id']).first()
    if delegate_user is None:
        messages.error(request, 'Delegate user not found.')
        return redirect('wfa:request_detail', pk=obj.pk)
    approval_svc.delegate(obj, actor=request.user, delegate_user=delegate_user, notes=form.cleaned_data.get('notes', ''))
    messages.success(request, 'Request delegated.')
    return redirect('wfa:request_detail', pk=obj.pk)


@login_required
@require_POST
def request_recall_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    if obj.requested_by_id != request.user.id and not _is_admin(request.user):
        messages.error(request, 'Only the requester or an admin can recall this.')
        return redirect('wfa:request_detail', pk=obj.pk)
    if not obj.is_open():
        messages.error(request, 'Request is no longer open.')
        return redirect('wfa:request_detail', pk=obj.pk)
    approval_svc.recall(obj, actor=request.user, notes=request.POST.get('notes', ''))
    messages.success(request, 'Request recalled.')
    return redirect('wfa:request_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def request_escalate_view(request, pk):
    obj = get_object_or_404(M.ApprovalRequest, pk=pk, tenant=request.tenant)
    if not obj.is_open():
        messages.error(request, 'Request is no longer open.')
        return redirect('wfa:request_detail', pk=obj.pk)
    approval_svc.escalate(obj, actor=request.user, notes=request.POST.get('notes', ''))
    messages.success(request, 'Request escalated.')
    return redirect('wfa:request_detail', pk=obj.pk)


# --- ApprovalDelegation ------------------------------------------------------

@login_required
def delegation_list_view(request):
    qs = M.ApprovalDelegation.objects.filter(tenant=request.tenant) if request.tenant else M.ApprovalDelegation.objects.none()
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.select_related('delegator', 'delegate', 'policy').order_by('-starts_at'))
    return render(request, 'wfa/approvals/delegation_list.html', {'page': page, 'active': active})


@login_required
@tenant_admin_required
def delegation_create_view(request):
    if request.method == 'POST':
        form = F.ApprovalDelegationForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Delegation created.')
            return redirect('wfa:delegation_list')
    else:
        form = F.ApprovalDelegationForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/delegation_form.html', {'form': form, 'is_edit': False})


@login_required
@tenant_admin_required
def delegation_edit_view(request, pk):
    obj = get_object_or_404(M.ApprovalDelegation, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ApprovalDelegationForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Delegation updated.')
            return redirect('wfa:delegation_list')
    else:
        form = F.ApprovalDelegationForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/approvals/delegation_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def delegation_delete_view(request, pk):
    obj = get_object_or_404(M.ApprovalDelegation, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Delegation deleted.')
    return redirect('wfa:delegation_list')


# ============================================================================
# 20.3  Notification & Escalation Matrix
# ============================================================================

@login_required
def channel_list_view(request):
    qs = M.NotificationChannel.objects.filter(tenant=request.tenant) if request.tenant else M.NotificationChannel.objects.none()
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.order_by('code'))
    return render(request, 'wfa/notifications/channel_list.html', {
        'page': page, 'active': active,
        'channel_codes': M.CHANNEL_CODE_CHOICES,
    })


@login_required
@tenant_admin_required
def channel_create_view(request):
    if request.method == 'POST':
        form = F.NotificationChannelForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Channel created.')
            return redirect('wfa:channel_list')
    else:
        form = F.NotificationChannelForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/channel_form.html', {'form': form, 'is_edit': False})


@login_required
@tenant_admin_required
def channel_edit_view(request, pk):
    obj = get_object_or_404(M.NotificationChannel, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.NotificationChannelForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Channel updated.')
            return redirect('wfa:channel_list')
    else:
        form = F.NotificationChannelForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/channel_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def channel_delete_view(request, pk):
    obj = get_object_or_404(M.NotificationChannel, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Channel deleted.')
    return redirect('wfa:channel_list')


@login_required
def template_list_view(request):
    qs = M.NotificationTemplate.objects.filter(tenant=request.tenant) if request.tenant else M.NotificationTemplate.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(event_type__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.order_by('event_type', 'code'))
    return render(request, 'wfa/notifications/template_list.html', {'page': page, 'q': q, 'active': active})


@login_required
@tenant_admin_required
def template_create_view(request):
    if request.method == 'POST':
        form = F.NotificationTemplateForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.channels = [c.strip() for c in (form.cleaned_data.get('channels_csv') or '').split(',') if c.strip()]
            obj.save()
            messages.success(request, 'Template created.')
            return redirect('wfa:template_list')
    else:
        form = F.NotificationTemplateForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/template_form.html', {'form': form, 'is_edit': False})


@login_required
@tenant_admin_required
def template_edit_view(request, pk):
    obj = get_object_or_404(M.NotificationTemplate, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.NotificationTemplateForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template updated.')
            return redirect('wfa:template_list')
    else:
        form = F.NotificationTemplateForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/template_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def template_delete_view(request, pk):
    obj = get_object_or_404(M.NotificationTemplate, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Template deleted.')
    return redirect('wfa:template_list')


@login_required
def rule_list_view(request):
    qs = M.NotificationRule.objects.filter(tenant=request.tenant) if request.tenant else M.NotificationRule.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(event_type__icontains=q))
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.select_related('template').order_by('event_type', 'code'))
    return render(request, 'wfa/notifications/rule_list.html', {'page': page, 'q': q, 'active': active})


@login_required
@tenant_admin_required
def rule_create_view(request):
    if request.method == 'POST':
        form = F.NotificationRuleForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Rule created.')
            return redirect('wfa:rule_list')
    else:
        form = F.NotificationRuleForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/rule_form.html', {'form': form, 'is_edit': False})


@login_required
@tenant_admin_required
def rule_edit_view(request, pk):
    obj = get_object_or_404(M.NotificationRule, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.NotificationRuleForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rule updated.')
            return redirect('wfa:rule_list')
    else:
        form = F.NotificationRuleForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/notifications/rule_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def rule_delete_view(request, pk):
    obj = get_object_or_404(M.NotificationRule, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Rule deleted.')
    return redirect('wfa:rule_list')


@login_required
def notification_list_view(request):
    qs = M.Notification.objects.filter(tenant=request.tenant) if request.tenant else M.Notification.objects.none()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    event = request.GET.get('event', '').strip()
    if event:
        qs = qs.filter(event_type__icontains=event)
    page, _ = _paginate(request, qs.select_related('rule', 'recipient').order_by('-triggered_at'))
    return render(request, 'wfa/notifications/list.html', {
        'page': page, 'status': status, 'event': event,
        'status_choices': M.NOTIFICATION_STATUS_CHOICES,
    })


@login_required
def notification_detail_view(request, pk):
    obj = get_object_or_404(M.Notification, pk=pk, tenant=request.tenant)
    deliveries = obj.deliveries.select_related('channel').order_by('-attempted_at')
    return render(request, 'wfa/notifications/detail.html', {
        'obj': obj, 'deliveries': deliveries,
    })


@login_required
@require_POST
def notification_dispatch_view(request, pk):
    obj = get_object_or_404(M.Notification, pk=pk, tenant=request.tenant)
    try:
        notification_svc.dispatch(obj)
        messages.success(request, 'Notification dispatched.')
    except Exception as exc:
        logger.warning('wfa dispatch failed: %s', exc, exc_info=True)
        messages.error(request, f'Dispatch failed: {exc}')
    return redirect('wfa:notification_detail', pk=obj.pk)


@login_required
def delivery_list_view(request):
    qs = M.NotificationDelivery.objects.filter(tenant=request.tenant) if request.tenant else M.NotificationDelivery.objects.none()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page, _ = _paginate(request, qs.select_related('notification', 'channel').order_by('-attempted_at'))
    return render(request, 'wfa/notifications/delivery_list.html', {
        'page': page, 'status': status,
        'status_choices': M.DELIVERY_STATUS_CHOICES,
    })


@login_required
def sms_list_view(request):
    qs = M.SMSDelivery.objects.filter(tenant=request.tenant) if request.tenant else M.SMSDelivery.objects.none()
    page, _ = _paginate(request, qs.order_by('-sent_at'))
    return render(request, 'wfa/notifications/sms_list.html', {'page': page})


# ============================================================================
# 20.4  Integration Orchestration
# ============================================================================

@login_required
def connector_list_view(request):
    qs = M.Connector.objects.filter(tenant=request.tenant) if request.tenant else M.Connector.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    connector_type = request.GET.get('type', '')
    if connector_type:
        qs = qs.filter(connector_type=connector_type)
    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    page, _ = _paginate(request, qs.order_by('code'))
    return render(request, 'wfa/integrations/connector_list.html', {
        'page': page, 'q': q, 'type': connector_type, 'active': active,
        'type_choices': M.CONNECTOR_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def connector_create_view(request):
    if request.method == 'POST':
        form = F.ConnectorForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Connector {obj.code} created.')
            return redirect('wfa:connector_detail', pk=obj.pk)
    else:
        form = F.ConnectorForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/connector_form.html', {'form': form, 'is_edit': False})


@login_required
def connector_detail_view(request, pk):
    obj = get_object_or_404(M.Connector, pk=pk, tenant=request.tenant)
    endpoints = obj.endpoints.order_by('name')
    return render(request, 'wfa/integrations/connector_detail.html', {'obj': obj, 'endpoints': endpoints})


@login_required
@tenant_admin_required
def connector_edit_view(request, pk):
    obj = get_object_or_404(M.Connector, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ConnectorForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Connector updated.')
            return redirect('wfa:connector_detail', pk=obj.pk)
    else:
        form = F.ConnectorForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/connector_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def connector_delete_view(request, pk):
    obj = get_object_or_404(M.Connector, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Connector deleted.')
    return redirect('wfa:connector_list')


@login_required
@tenant_admin_required
def endpoint_create_view(request, connector_pk):
    connector = get_object_or_404(M.Connector, pk=connector_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ConnectorEndpointForm(request.POST, tenant=request.tenant, user=request.user, initial={'connector': connector})
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.connector = connector
            obj.save()
            messages.success(request, 'Endpoint added.')
            return redirect('wfa:connector_detail', pk=connector.pk)
    else:
        form = F.ConnectorEndpointForm(tenant=request.tenant, user=request.user, initial={'connector': connector})
    return render(request, 'wfa/integrations/endpoint_form.html', {
        'form': form, 'connector': connector, 'is_edit': False,
    })


@login_required
@tenant_admin_required
def endpoint_edit_view(request, pk):
    obj = get_object_or_404(M.ConnectorEndpoint, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.ConnectorEndpointForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Endpoint updated.')
            return redirect('wfa:connector_detail', pk=obj.connector_id)
    else:
        form = F.ConnectorEndpointForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/endpoint_form.html', {
        'form': form, 'connector': obj.connector, 'is_edit': True, 'obj': obj,
    })


@login_required
@tenant_admin_required
@require_POST
def endpoint_delete_view(request, pk):
    obj = get_object_or_404(M.ConnectorEndpoint, pk=pk, tenant=request.tenant)
    connector_pk = obj.connector_id
    obj.delete()
    messages.success(request, 'Endpoint deleted.')
    return redirect('wfa:connector_detail', pk=connector_pk)


@login_required
def flow_list_view(request):
    qs = M.IntegrationFlow.objects.filter(tenant=request.tenant) if request.tenant else M.IntegrationFlow.objects.none()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    trigger = request.GET.get('trigger', '')
    if trigger:
        qs = qs.filter(trigger_type=trigger)
    page, _ = _paginate(request, qs.order_by('code'))
    return render(request, 'wfa/integrations/flow_list.html', {
        'page': page, 'q': q, 'trigger': trigger,
        'trigger_choices': M.TRIGGER_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def flow_create_view(request):
    if request.method == 'POST':
        form = F.IntegrationFlowForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Flow created.')
            return redirect('wfa:flow_detail', pk=obj.pk)
    else:
        form = F.IntegrationFlowForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/flow_form.html', {'form': form, 'is_edit': False})


@login_required
def flow_detail_view(request, pk):
    obj = get_object_or_404(M.IntegrationFlow, pk=pk, tenant=request.tenant)
    steps = obj.steps.order_by('step_no')
    runs = obj.runs.order_by('-started_at')[:10]
    return render(request, 'wfa/integrations/flow_detail.html', {'obj': obj, 'steps': steps, 'runs': runs})


@login_required
@tenant_admin_required
def flow_edit_view(request, pk):
    obj = get_object_or_404(M.IntegrationFlow, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.IntegrationFlowForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Flow updated.')
            return redirect('wfa:flow_detail', pk=obj.pk)
    else:
        form = F.IntegrationFlowForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/flow_form.html', {'form': form, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def flow_delete_view(request, pk):
    obj = get_object_or_404(M.IntegrationFlow, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Flow deleted.')
    return redirect('wfa:flow_list')


@login_required
@tenant_admin_required
@require_POST
def flow_run_view(request, pk):
    flow = get_object_or_404(M.IntegrationFlow, pk=pk, tenant=request.tenant)
    try:
        run = integration_svc.execute_flow(flow, triggered_by=request.user)
        messages.success(request, f'Flow run {run.code} {run.status}.')
        return redirect('wfa:run_detail', pk=run.pk)
    except Exception as exc:
        logger.warning('wfa flow run failed: %s', exc, exc_info=True)
        messages.error(request, f'Flow run failed: {exc}')
        return redirect('wfa:flow_detail', pk=flow.pk)


@login_required
@tenant_admin_required
def step_create_view(request, flow_pk):
    flow = get_object_or_404(M.IntegrationFlow, pk=flow_pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.FlowStepForm(request.POST, tenant=request.tenant, user=request.user, initial={'flow': flow})
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.flow = flow
            obj.save()
            messages.success(request, 'Step added.')
            return redirect('wfa:flow_detail', pk=flow.pk)
    else:
        next_no = (flow.steps.order_by('-step_no').first().step_no + 1) if flow.steps.exists() else 1
        form = F.FlowStepForm(tenant=request.tenant, user=request.user, initial={'flow': flow, 'step_no': next_no})
    return render(request, 'wfa/integrations/step_form.html', {'form': form, 'flow': flow, 'is_edit': False})


@login_required
@tenant_admin_required
def step_edit_view(request, pk):
    obj = get_object_or_404(M.FlowStep, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = F.FlowStepForm(request.POST, instance=obj, tenant=request.tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Step updated.')
            return redirect('wfa:flow_detail', pk=obj.flow_id)
    else:
        form = F.FlowStepForm(instance=obj, tenant=request.tenant, user=request.user)
    return render(request, 'wfa/integrations/step_form.html', {'form': form, 'flow': obj.flow, 'is_edit': True, 'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def step_delete_view(request, pk):
    obj = get_object_or_404(M.FlowStep, pk=pk, tenant=request.tenant)
    flow_pk = obj.flow_id
    obj.delete()
    messages.success(request, 'Step deleted.')
    return redirect('wfa:flow_detail', pk=flow_pk)


@login_required
def run_list_view(request):
    qs = M.IntegrationRun.objects.filter(tenant=request.tenant) if request.tenant else M.IntegrationRun.objects.none()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    flow = request.GET.get('flow', '')
    if flow:
        qs = qs.filter(flow_id=flow)
    page, _ = _paginate(request, qs.select_related('flow').order_by('-started_at'))
    return render(request, 'wfa/integrations/run_list.html', {
        'page': page, 'status': status, 'flow': flow,
        'status_choices': M.RUN_STATUS_CHOICES,
        'flows': M.IntegrationFlow.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
def run_detail_view(request, pk):
    obj = get_object_or_404(M.IntegrationRun, pk=pk, tenant=request.tenant)
    return render(request, 'wfa/integrations/run_detail.html', {'obj': obj})


@login_required
def outbox_list_view(request):
    qs = M.WebhookOutboxEntry.objects.filter(tenant=request.tenant) if request.tenant else M.WebhookOutboxEntry.objects.none()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    page, _ = _paginate(request, qs.order_by('-id'))
    return render(request, 'wfa/integrations/outbox_list.html', {
        'page': page, 'status': status,
        'status_choices': M.OUTBOX_STATUS_CHOICES,
    })


# ============================================================================
# 20.5  Process Mining & Optimization
# ============================================================================

@login_required
def bottleneck_list_view(request):
    qs = M.BottleneckAnalysis.objects.filter(tenant=request.tenant) if request.tenant else M.BottleneckAnalysis.objects.none()
    severity = request.GET.get('severity', '')
    if severity:
        qs = qs.filter(severity=severity)
    definition = request.GET.get('definition', '')
    if definition:
        qs = qs.filter(definition_id=definition)
    page, _ = _paginate(request, qs.select_related('definition', 'bottleneck_node').order_by('-period_end'))
    return render(request, 'wfa/mining/bottleneck_list.html', {
        'page': page, 'severity': severity, 'definition': definition,
        'severity_choices': M.SEVERITY_CHOICES,
        'definitions': M.ProcessDefinition.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
@tenant_admin_required
def bottleneck_create_view(request):
    if request.method == 'POST':
        form = F.BottleneckAnalysisForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            node, avg, count = process_mining.detect_bottleneck(
                obj.definition,
                period_start=obj.period_start,
                period_end=obj.period_end,
            )
            obj.bottleneck_node = node
            obj.avg_wait_seconds = avg
            obj.instance_count = count
            obj.severity = process_mining.classify_severity(avg)
            obj.save()
            messages.success(request, f'Analysis {obj.code} created.')
            return redirect('wfa:bottleneck_detail', pk=obj.pk)
    else:
        form = F.BottleneckAnalysisForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/mining/bottleneck_form.html', {'form': form, 'is_edit': False})


@login_required
def bottleneck_detail_view(request, pk):
    obj = get_object_or_404(M.BottleneckAnalysis, pk=pk, tenant=request.tenant)
    suggestions = obj.suggestions.order_by('-id')
    return render(request, 'wfa/mining/bottleneck_detail.html', {'obj': obj, 'suggestions': suggestions})


@login_required
@tenant_admin_required
@require_POST
def bottleneck_delete_view(request, pk):
    obj = get_object_or_404(M.BottleneckAnalysis, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Analysis deleted.')
    return redirect('wfa:bottleneck_list')


@login_required
def suggestion_list_view(request):
    qs = M.ProcessOptimizationSuggestion.objects.filter(tenant=request.tenant) if request.tenant else M.ProcessOptimizationSuggestion.objects.none()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    type_ = request.GET.get('type', '')
    if type_:
        qs = qs.filter(suggestion_type=type_)
    page, _ = _paginate(request, qs.select_related('definition', 'analysis').order_by('-id'))
    return render(request, 'wfa/mining/suggestion_list.html', {
        'page': page, 'status': status, 'type': type_,
        'status_choices': M.SUGGESTION_STATUS_CHOICES,
        'type_choices': M.SUGGESTION_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def suggestion_create_view(request):
    if request.method == 'POST':
        form = F.ProcessOptimizationSuggestionForm(request.POST, tenant=request.tenant, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Suggestion {obj.code} created.')
            return redirect('wfa:suggestion_detail', pk=obj.pk)
    else:
        form = F.ProcessOptimizationSuggestionForm(tenant=request.tenant, user=request.user)
    return render(request, 'wfa/mining/suggestion_form.html', {'form': form, 'is_edit': False})


@login_required
def suggestion_detail_view(request, pk):
    obj = get_object_or_404(M.ProcessOptimizationSuggestion, pk=pk, tenant=request.tenant)
    return render(request, 'wfa/mining/suggestion_detail.html', {
        'obj': obj, 'dismiss_form': F.SuggestionStatusForm(),
    })


@login_required
@require_POST
def suggestion_ack_view(request, pk):
    obj = get_object_or_404(M.ProcessOptimizationSuggestion, pk=pk, tenant=request.tenant)
    M.ProcessOptimizationSuggestion.all_objects.filter(pk=obj.pk, status='new').update(
        status='acknowledged',
        acknowledged_by=request.user,
        acknowledged_at=timezone.now(),
    )
    messages.success(request, 'Suggestion acknowledged.')
    return redirect('wfa:suggestion_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def suggestion_dismiss_view(request, pk):
    obj = get_object_or_404(M.ProcessOptimizationSuggestion, pk=pk, tenant=request.tenant)
    form = F.SuggestionStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Notes are required to dismiss a suggestion.')
        return redirect('wfa:suggestion_detail', pk=obj.pk)
    M.ProcessOptimizationSuggestion.all_objects.filter(
        pk=obj.pk, status__in=('new', 'acknowledged'),
    ).update(status='dismissed', notes=form.cleaned_data['notes'])
    messages.success(request, 'Suggestion dismissed.')
    return redirect('wfa:suggestion_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def suggestion_apply_view(request, pk):
    obj = get_object_or_404(M.ProcessOptimizationSuggestion, pk=pk, tenant=request.tenant)
    M.ProcessOptimizationSuggestion.all_objects.filter(pk=obj.pk).update(status='applied')
    messages.success(request, 'Suggestion marked as applied.')
    return redirect('wfa:suggestion_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def suggestion_delete_view(request, pk):
    obj = get_object_or_404(M.ProcessOptimizationSuggestion, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Suggestion deleted.')
    return redirect('wfa:suggestion_list')


@login_required
def cycle_time_list_view(request):
    qs = M.CycleTimeReport.objects.filter(tenant=request.tenant) if request.tenant else M.CycleTimeReport.objects.none()
    definition = request.GET.get('definition', '')
    if definition:
        qs = qs.filter(definition_id=definition)
    page, _ = _paginate(request, qs.select_related('definition').order_by('-period_end'))
    return render(request, 'wfa/mining/cycle_time_list.html', {
        'page': page, 'definition': definition,
        'definitions': M.ProcessDefinition.objects.filter(tenant=request.tenant) if request.tenant else [],
    })


@login_required
def cycle_time_detail_view(request, pk):
    obj = get_object_or_404(M.CycleTimeReport, pk=pk, tenant=request.tenant)
    return render(request, 'wfa/mining/cycle_time_detail.html', {'obj': obj})


@login_required
@tenant_admin_required
@require_POST
def cycle_time_delete_view(request, pk):
    obj = get_object_or_404(M.CycleTimeReport, pk=pk, tenant=request.tenant)
    obj.delete()
    messages.success(request, 'Report deleted.')
    return redirect('wfa:cycle_time_list')
