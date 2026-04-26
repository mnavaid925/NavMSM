"""BOM views — full CRUD per CLAUDE.md across all 5 sub-modules.

Every view filters by request.tenant. Edit/Delete on workflow models
(BillOfMaterials) is gated by status (draft/under_review). Cost rollups
are recomputed on demand. Sync runs do drift detection between EBOM,
MBOM, and SBOM versions of the same product.
"""
import re
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import TenantRequiredMixin
from apps.plm.models import Product

from .forms import (
    AlternateMaterialForm, BillOfMaterialsForm, BOMLineForm, BOMRevisionForm,
    BOMSyncMapForm, CostElementForm, SubstitutionRuleForm,
)
from .models import (
    AlternateMaterial, BillOfMaterials, BOMCostRollup, BOMLine, BOMRevision,
    BOMSyncLog, BOMSyncMap, CostElement, SubstitutionRule,
)


# ============================================================================
# Helpers
# ============================================================================

_SEQ_RE = re.compile(r'^[A-Z]+-(\d+)$')


def _next_sequence_number(qs, field, prefix, width=5):
    last = qs.aggregate(Max(field))[f'{field}__max']
    next_num = 1
    if last:
        m = _SEQ_RE.match(str(last))
        next_num = int(m.group(1)) + 1 if m else qs.count() + 1
    return f'{prefix}-{next_num:0{width}d}'


def _save_with_unique_number(make_obj, max_attempts=5):
    last_err = None
    for _ in range(max_attempts):
        try:
            with transaction.atomic():
                return make_obj()
        except IntegrityError as e:
            last_err = e
            continue
    raise last_err


def _atomic_bom_transition(bom, request, from_states, to_state, stamp_field=None):
    fields = {'status': to_state}
    if stamp_field:
        fields[stamp_field] = timezone.now()
    with transaction.atomic():
        rowcount = BillOfMaterials.objects.filter(
            pk=bom.pk, tenant=request.tenant, status__in=from_states,
        ).update(**fields)
        if not rowcount:
            return False
        bom.refresh_from_db()
    return True


# ============================================================================
# Dashboard / index
# ============================================================================

class BOMIndexView(TenantRequiredMixin, View):
    template_name = 'bom/index.html'

    def get(self, request):
        t = request.tenant
        ctx = {
            'bom_count': BillOfMaterials.objects.filter(tenant=t).count(),
            'bom_draft': BillOfMaterials.objects.filter(tenant=t, status='draft').count(),
            'bom_review': BillOfMaterials.objects.filter(tenant=t, status='under_review').count(),
            'bom_released': BillOfMaterials.objects.filter(tenant=t, status='released').count(),
            'alt_pending': AlternateMaterial.objects.filter(
                tenant=t, approval_status='pending',
            ).count(),
            'drift_count': BOMSyncMap.objects.filter(
                tenant=t, sync_status='drift_detected',
            ).count(),
            'recent_boms': BillOfMaterials.objects.filter(
                tenant=t,
            ).select_related('product').order_by('-created_at')[:8],
            'recent_drifts': BOMSyncMap.objects.filter(
                tenant=t, sync_status='drift_detected',
            ).select_related('source_bom', 'target_bom').order_by('-updated_at')[:5],
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 3.1  BILL OF MATERIALS — CRUD + workflow
# ============================================================================

class BOMListView(TenantRequiredMixin, ListView):
    model = BillOfMaterials
    template_name = 'bom/boms/list.html'
    context_object_name = 'boms'
    paginate_by = 20

    def get_queryset(self):
        qs = BillOfMaterials.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product', 'created_by', 'approved_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(bom_number__icontains=q)
                | Q(name__icontains=q)
                | Q(product__sku__icontains=q),
            )
        for field in ('status', 'bom_type'):
            val = self.request.GET.get(field, '')
            if val:
                qs = qs.filter(**{field: val})
        product = self.request.GET.get('product', '')
        if product:
            qs = qs.filter(product_id=product)
        return qs.annotate(line_count=Count('lines')).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = BillOfMaterials.STATUS_CHOICES
        ctx['bom_type_choices'] = BillOfMaterials.BOM_TYPE_CHOICES
        ctx['products'] = Product.objects.filter(
            tenant=self.request.tenant,
        ).order_by('sku')
        return ctx


class BOMCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'bom/boms/form.html', {
            'form': BillOfMaterialsForm(tenant=request.tenant),
        })

    def post(self, request):
        form = BillOfMaterialsForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            def _make():
                bom = form.save(commit=False)
                bom.tenant = request.tenant
                bom.created_by = request.user
                bom.bom_number = _next_sequence_number(
                    BillOfMaterials.objects.filter(tenant=request.tenant),
                    'bom_number', 'BOM',
                )
                bom.save()
                return bom
            bom = _save_with_unique_number(_make)
            messages.success(request, f'BOM {bom.bom_number} created.')
            return redirect('bom:bom_detail', pk=bom.pk)
        return render(request, 'bom/boms/form.html', {'form': form})


class BOMDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        bom = get_object_or_404(
            BillOfMaterials.objects.select_related('product', 'created_by', 'approved_by'),
            pk=pk, tenant=request.tenant,
        )
        rollup = getattr(bom, 'cost_rollup', None)
        return render(request, 'bom/boms/detail.html', {
            'bom': bom,
            'lines': bom.lines.select_related('component', 'parent_line').order_by('sequence'),
            'revisions': bom.revisions.all().select_related('changed_by'),
            'sync_targets': bom.sync_targets.select_related('target_bom', 'target_bom__product'),
            'sync_sources': bom.sync_sources.select_related('source_bom', 'source_bom__product'),
            'rollup': rollup,
            'line_form': BOMLineForm(tenant=request.tenant, bom=bom),
            'revision_form': BOMRevisionForm(),
        })


class BOMEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if not bom.is_editable():
            messages.warning(request, 'BOM can only be edited in Draft or Under Review status.')
            return redirect('bom:bom_detail', pk=pk)
        return render(request, 'bom/boms/form.html', {
            'form': BillOfMaterialsForm(instance=bom, tenant=request.tenant),
            'bom': bom,
        })

    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if not bom.is_editable():
            messages.warning(request, 'BOM can only be edited in Draft or Under Review status.')
            return redirect('bom:bom_detail', pk=pk)
        form = BillOfMaterialsForm(request.POST, instance=bom, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'BOM updated.')
            return redirect('bom:bom_detail', pk=bom.pk)
        return render(request, 'bom/boms/form.html', {'form': form, 'bom': bom})


class BOMDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if bom.status == 'released':
            messages.error(request, 'Released BOMs cannot be deleted — mark Obsolete first.')
            return redirect('bom:bom_detail', pk=pk)
        try:
            bom.delete()
        except ProtectedError:
            messages.error(request, 'Cannot delete — BOM is referenced by other records.')
            return redirect('bom:bom_detail', pk=pk)
        messages.success(request, 'BOM deleted.')
        return redirect('bom:bom_list')


# ---- Workflow actions ----

class BOMSubmitView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if _atomic_bom_transition(bom, request, ['draft'], 'under_review'):
            messages.success(request, f'BOM {bom.bom_number} submitted for review.')
        else:
            messages.warning(request, 'Only Draft BOMs can be submitted.')
        return redirect('bom:bom_detail', pk=pk)


class BOMApproveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if _atomic_bom_transition(bom, request, ['under_review'], 'approved', 'approved_at'):
            BillOfMaterials.objects.filter(pk=bom.pk).update(approved_by=request.user)
            messages.success(request, f'BOM {bom.bom_number} approved.')
        else:
            messages.warning(request, 'BOM is not awaiting review.')
        return redirect('bom:bom_detail', pk=pk)


class BOMRejectView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if _atomic_bom_transition(bom, request, ['under_review'], 'draft'):
            messages.info(request, f'BOM {bom.bom_number} sent back to Draft.')
        else:
            messages.warning(request, 'BOM is not awaiting review.')
        return redirect('bom:bom_detail', pk=pk)


class BOMReleaseView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if not _atomic_bom_transition(bom, request, ['approved'], 'released', 'released_at'):
            messages.warning(request, 'Only Approved BOMs can be released.')
            return redirect('bom:bom_detail', pk=pk)
        # Supersede any prior released BOM of the same product + bom_type.
        BillOfMaterials.objects.filter(
            tenant=request.tenant,
            product=bom.product, bom_type=bom.bom_type, status='released',
        ).exclude(pk=bom.pk).update(status='obsolete')
        # Snapshot the release as a BOMRevision entry.
        BOMRevision.objects.create(
            tenant=request.tenant, bom=bom,
            version=bom.version, revision=bom.revision,
            revision_type='major',
            change_summary=f'Released by {request.user}.',
            snapshot_json=bom.snapshot(),
            changed_by=request.user,
        )
        messages.success(request, f'BOM {bom.bom_number} released.')
        return redirect('bom:bom_detail', pk=pk)


class BOMObsoleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        if _atomic_bom_transition(bom, request, ['released', 'approved'], 'obsolete'):
            messages.info(request, f'BOM {bom.bom_number} marked Obsolete.')
        else:
            messages.warning(request, 'BOM cannot be marked Obsolete from its current state.')
        return redirect('bom:bom_detail', pk=pk)


class BOMRecomputeRollupView(TenantRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BillOfMaterials, pk=pk, tenant=request.tenant)
        rollup = bom.compute_rollup(computed_by=request.user)
        messages.success(
            request,
            f'Rollup recomputed: total {rollup.total_cost} {rollup.currency}.',
        )
        return redirect('bom:bom_detail', pk=pk)


class BOMExplodeView(TenantRequiredMixin, View):
    def get(self, request, pk):
        bom = get_object_or_404(
            BillOfMaterials.objects.select_related('product'),
            pk=pk, tenant=request.tenant,
        )
        rows = list(bom.explode())
        return render(request, 'bom/boms/explode.html', {
            'bom': bom,
            'rows': rows,
        })


# ---- BOMLine (nested under BOM) ----

class BOMLineCreateView(TenantRequiredMixin, View):
    def post(self, request, bom_id):
        bom = get_object_or_404(BillOfMaterials, pk=bom_id, tenant=request.tenant)
        if not bom.is_editable():
            messages.warning(request, 'Lines can only be added while BOM is Draft or Under Review.')
            return redirect('bom:bom_detail', pk=bom_id)
        form = BOMLineForm(request.POST, tenant=request.tenant, bom=bom)
        if form.is_valid():
            line = form.save(commit=False)
            line.tenant = request.tenant
            line.bom = bom
            line.save()
            messages.success(request, f'Line {line.component.sku} added.')
        else:
            messages.error(
                request,
                'Could not add line: ' + '; '.join(
                    f'{k}: {v[0]}' for k, v in form.errors.items()
                ),
            )
        return redirect('bom:bom_detail', pk=bom_id)


class BOMLineEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        line = get_object_or_404(BOMLine, pk=pk, tenant=request.tenant)
        return render(request, 'bom/lines/form.html', {
            'form': BOMLineForm(instance=line, tenant=request.tenant, bom=line.bom),
            'line': line,
        })

    def post(self, request, pk):
        line = get_object_or_404(BOMLine, pk=pk, tenant=request.tenant)
        if not line.bom.is_editable():
            messages.warning(request, 'Lines can only be edited while BOM is Draft or Under Review.')
            return redirect('bom:bom_detail', pk=line.bom_id)
        form = BOMLineForm(request.POST, instance=line, tenant=request.tenant, bom=line.bom)
        if form.is_valid():
            form.save()
            messages.success(request, 'Line updated.')
            return redirect('bom:bom_detail', pk=line.bom_id)
        return render(request, 'bom/lines/form.html', {'form': form, 'line': line})


class BOMLineDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        line = get_object_or_404(BOMLine, pk=pk, tenant=request.tenant)
        if not line.bom.is_editable():
            messages.warning(request, 'Lines can only be deleted while BOM is Draft or Under Review.')
            return redirect('bom:bom_detail', pk=line.bom_id)
        bom_id = line.bom_id
        line.delete()
        messages.success(request, 'Line deleted.')
        return redirect('bom:bom_detail', pk=bom_id)


# ============================================================================
# 3.2  BOM REVISIONS
# ============================================================================

class BOMRevisionCreateView(TenantRequiredMixin, View):
    def post(self, request, bom_id):
        bom = get_object_or_404(BillOfMaterials, pk=bom_id, tenant=request.tenant)
        form = BOMRevisionForm(request.POST)
        if form.is_valid():
            rev = form.save(commit=False)
            rev.tenant = request.tenant
            rev.bom = bom
            rev.changed_by = request.user
            rev.snapshot_json = bom.snapshot()
            rev.save()
            messages.success(request, f'Revision {rev.version}.{rev.revision} captured.')
        else:
            messages.error(request, 'Could not record revision.')
        return redirect('bom:bom_detail', pk=bom_id)


class BOMRevisionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rev = get_object_or_404(
            BOMRevision.objects.select_related('bom', 'bom__product', 'changed_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'bom/revisions/detail.html', {'revision': rev})


class BOMRollbackView(TenantRequiredMixin, View):
    """Restore a BOM's lines from a stored revision snapshot."""

    def post(self, request, pk):
        rev = get_object_or_404(
            BOMRevision.objects.select_related('bom'),
            pk=pk, tenant=request.tenant,
        )
        bom = rev.bom
        if not bom.is_editable():
            messages.warning(request, 'Rollback requires BOM to be Draft or Under Review.')
            return redirect('bom:bom_detail', pk=bom.pk)
        snapshot_lines = rev.snapshot_json.get('lines', [])
        with transaction.atomic():
            bom.lines.all().delete()
            _restore_lines(bom, snapshot_lines, parent=None, tenant=request.tenant)
            BOMRevision.objects.create(
                tenant=request.tenant, bom=bom,
                version=bom.version, revision=bom.revision,
                revision_type='rollback',
                change_summary=f'Rolled back to revision {rev.pk} ({rev.version}.{rev.revision}).',
                snapshot_json=bom.snapshot(),
                changed_by=request.user,
            )
        messages.success(request, f'BOM rolled back to revision {rev.version}.{rev.revision}.')
        return redirect('bom:bom_detail', pk=bom.pk)


def _restore_lines(bom, snapshot_lines, parent, tenant):
    """Recursively re-create BOMLines from a snapshot tree.

    Components are matched by SKU; missing components silently skip the line.
    """
    for raw in snapshot_lines:
        component = Product.objects.filter(tenant=tenant, sku=raw.get('component_sku', '')).first()
        if component is None:
            continue
        line = BOMLine.objects.create(
            tenant=tenant, bom=bom, parent_line=parent,
            sequence=raw.get('sequence', 10),
            component=component,
            quantity=Decimal(str(raw.get('quantity', '1'))),
            unit_of_measure=raw.get('unit_of_measure', 'ea'),
            scrap_percent=Decimal(str(raw.get('scrap_percent', '0'))),
            is_phantom=bool(raw.get('is_phantom', False)),
            reference_designator=raw.get('reference_designator', ''),
            notes=raw.get('notes', ''),
        )
        children = raw.get('children', [])
        if children:
            _restore_lines(bom, children, parent=line, tenant=tenant)


# ============================================================================
# 3.3  ALTERNATES & SUBSTITUTION RULES
# ============================================================================

class AlternateCreateView(TenantRequiredMixin, View):
    def get(self, request, line_id):
        line = get_object_or_404(BOMLine, pk=line_id, tenant=request.tenant)
        return render(request, 'bom/alternates/form.html', {
            'form': AlternateMaterialForm(
                tenant=request.tenant, exclude_component=line.component,
            ),
            'line': line,
        })

    def post(self, request, line_id):
        line = get_object_or_404(BOMLine, pk=line_id, tenant=request.tenant)
        form = AlternateMaterialForm(
            request.POST, tenant=request.tenant, exclude_component=line.component,
        )
        if form.is_valid():
            alt = form.save(commit=False)
            alt.tenant = request.tenant
            alt.bom_line = line
            alt.save()
            messages.success(request, f'Alternate {alt.alternate_component.sku} added.')
            return redirect('bom:bom_detail', pk=line.bom_id)
        return render(request, 'bom/alternates/form.html', {'form': form, 'line': line})


class AlternateEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        alt = get_object_or_404(AlternateMaterial, pk=pk, tenant=request.tenant)
        return render(request, 'bom/alternates/form.html', {
            'form': AlternateMaterialForm(
                instance=alt, tenant=request.tenant,
                exclude_component=alt.bom_line.component,
            ),
            'alternate': alt, 'line': alt.bom_line,
        })

    def post(self, request, pk):
        alt = get_object_or_404(AlternateMaterial, pk=pk, tenant=request.tenant)
        form = AlternateMaterialForm(
            request.POST, instance=alt, tenant=request.tenant,
            exclude_component=alt.bom_line.component,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Alternate updated.')
            return redirect('bom:bom_detail', pk=alt.bom_line.bom_id)
        return render(request, 'bom/alternates/form.html', {
            'form': form, 'alternate': alt, 'line': alt.bom_line,
        })


class AlternateDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        alt = get_object_or_404(AlternateMaterial, pk=pk, tenant=request.tenant)
        bom_id = alt.bom_line.bom_id
        alt.delete()
        messages.success(request, 'Alternate removed.')
        return redirect('bom:bom_detail', pk=bom_id)


class AlternateApproveView(TenantRequiredMixin, View):
    def post(self, request, pk):
        alt = get_object_or_404(AlternateMaterial, pk=pk, tenant=request.tenant)
        alt.approval_status = 'approved'
        alt.approved_by = request.user
        alt.approved_at = timezone.now()
        alt.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
        messages.success(request, f'Alternate {alt.alternate_component.sku} approved.')
        return redirect('bom:bom_detail', pk=alt.bom_line.bom_id)


class AlternateRejectView(TenantRequiredMixin, View):
    def post(self, request, pk):
        alt = get_object_or_404(AlternateMaterial, pk=pk, tenant=request.tenant)
        alt.approval_status = 'rejected'
        alt.approved_by = request.user
        alt.approved_at = timezone.now()
        alt.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
        messages.info(request, f'Alternate {alt.alternate_component.sku} rejected.')
        return redirect('bom:bom_detail', pk=alt.bom_line.bom_id)


# ---- Substitution rules (top-level) ----

class SubstitutionRuleListView(TenantRequiredMixin, ListView):
    model = SubstitutionRule
    template_name = 'bom/substitution_rules/list.html'
    context_object_name = 'rules'
    paginate_by = 20

    def get_queryset(self):
        qs = SubstitutionRule.objects.filter(
            tenant=self.request.tenant,
        ).select_related('original_component', 'substitute_component')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(original_component__sku__icontains=q)
                | Q(substitute_component__sku__icontains=q),
            )
        active = self.request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs


class SubstitutionRuleCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'bom/substitution_rules/form.html', {
            'form': SubstitutionRuleForm(tenant=request.tenant),
        })

    def post(self, request):
        form = SubstitutionRuleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.tenant = request.tenant
            rule.save()
            messages.success(request, f'Rule "{rule.name}" created.')
            return redirect('bom:rule_list')
        return render(request, 'bom/substitution_rules/form.html', {'form': form})


class SubstitutionRuleEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        rule = get_object_or_404(SubstitutionRule, pk=pk, tenant=request.tenant)
        return render(request, 'bom/substitution_rules/form.html', {
            'form': SubstitutionRuleForm(instance=rule, tenant=request.tenant),
            'rule': rule,
        })

    def post(self, request, pk):
        rule = get_object_or_404(SubstitutionRule, pk=pk, tenant=request.tenant)
        form = SubstitutionRuleForm(request.POST, instance=rule, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rule updated.')
            return redirect('bom:rule_list')
        return render(request, 'bom/substitution_rules/form.html', {'form': form, 'rule': rule})


class SubstitutionRuleDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        rule = get_object_or_404(SubstitutionRule, pk=pk, tenant=request.tenant)
        rule.delete()
        messages.success(request, 'Rule deleted.')
        return redirect('bom:rule_list')


# ============================================================================
# 3.4  COST ELEMENTS
# ============================================================================

class CostElementListView(TenantRequiredMixin, ListView):
    model = CostElement
    template_name = 'bom/cost_elements/list.html'
    context_object_name = 'cost_elements'
    paginate_by = 20

    def get_queryset(self):
        qs = CostElement.objects.filter(
            tenant=self.request.tenant,
        ).select_related('product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(product__sku__icontains=q) | Q(product__name__icontains=q),
            )
        cost_type = self.request.GET.get('cost_type', '')
        if cost_type:
            qs = qs.filter(cost_type=cost_type)
        source = self.request.GET.get('source', '')
        if source:
            qs = qs.filter(source=source)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cost_type_choices'] = CostElement.COST_TYPE_CHOICES
        ctx['source_choices'] = CostElement.SOURCE_CHOICES
        return ctx


class CostElementCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'bom/cost_elements/form.html', {
            'form': CostElementForm(tenant=request.tenant),
        })

    def post(self, request):
        form = CostElementForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            ce = form.save(commit=False)
            ce.tenant = request.tenant
            try:
                ce.save()
            except IntegrityError:
                messages.error(
                    request,
                    f'A {ce.get_cost_type_display()} cost already exists for {ce.product.sku} — edit it instead.',
                )
                return render(request, 'bom/cost_elements/form.html', {'form': form})
            messages.success(request, f'Cost element for {ce.product.sku} created.')
            return redirect('bom:cost_list')
        return render(request, 'bom/cost_elements/form.html', {'form': form})


class CostElementEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        ce = get_object_or_404(CostElement, pk=pk, tenant=request.tenant)
        return render(request, 'bom/cost_elements/form.html', {
            'form': CostElementForm(instance=ce, tenant=request.tenant),
            'cost_element': ce,
        })

    def post(self, request, pk):
        ce = get_object_or_404(CostElement, pk=pk, tenant=request.tenant)
        form = CostElementForm(request.POST, instance=ce, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cost element updated.')
            return redirect('bom:cost_list')
        return render(request, 'bom/cost_elements/form.html', {'form': form, 'cost_element': ce})


class CostElementDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ce = get_object_or_404(CostElement, pk=pk, tenant=request.tenant)
        ce.delete()
        messages.success(request, 'Cost element deleted.')
        return redirect('bom:cost_list')


# ============================================================================
# 3.5  EBOM / MBOM / SBOM SYNC
# ============================================================================

class BOMSyncMapListView(TenantRequiredMixin, ListView):
    model = BOMSyncMap
    template_name = 'bom/sync_maps/list.html'
    context_object_name = 'sync_maps'
    paginate_by = 20

    def get_queryset(self):
        qs = BOMSyncMap.objects.filter(
            tenant=self.request.tenant,
        ).select_related('source_bom', 'target_bom', 'source_bom__product', 'target_bom__product')
        status = self.request.GET.get('sync_status', '')
        if status:
            qs = qs.filter(sync_status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sync_status_choices'] = BOMSyncMap.SYNC_STATUS_CHOICES
        return ctx


class BOMSyncMapCreateView(TenantRequiredMixin, View):
    def get(self, request):
        return render(request, 'bom/sync_maps/form.html', {
            'form': BOMSyncMapForm(tenant=request.tenant),
        })

    def post(self, request):
        form = BOMSyncMapForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            sm = form.save(commit=False)
            sm.tenant = request.tenant
            try:
                sm.save()
            except IntegrityError:
                messages.error(request, 'A sync map already exists between those two BOMs.')
                return render(request, 'bom/sync_maps/form.html', {'form': form})
            BOMSyncLog.objects.create(
                tenant=request.tenant, sync_map=sm,
                action='created', actor=request.user,
                notes=f'Mapping {sm.source_bom} → {sm.target_bom} created.',
            )
            messages.success(request, 'Sync map created.')
            return redirect('bom:sync_detail', pk=sm.pk)
        return render(request, 'bom/sync_maps/form.html', {'form': form})


class BOMSyncMapDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        sm = get_object_or_404(
            BOMSyncMap.objects.select_related(
                'source_bom', 'target_bom', 'source_bom__product', 'target_bom__product',
            ),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'bom/sync_maps/detail.html', {
            'sync_map': sm,
            'log_entries': sm.log_entries.all().select_related('actor'),
        })


class BOMSyncMapEditView(TenantRequiredMixin, View):
    def get(self, request, pk):
        sm = get_object_or_404(BOMSyncMap, pk=pk, tenant=request.tenant)
        return render(request, 'bom/sync_maps/form.html', {
            'form': BOMSyncMapForm(instance=sm, tenant=request.tenant),
            'sync_map': sm,
        })

    def post(self, request, pk):
        sm = get_object_or_404(BOMSyncMap, pk=pk, tenant=request.tenant)
        form = BOMSyncMapForm(request.POST, instance=sm, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sync map updated.')
            return redirect('bom:sync_detail', pk=sm.pk)
        return render(request, 'bom/sync_maps/form.html', {'form': form, 'sync_map': sm})


class BOMSyncMapDeleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        sm = get_object_or_404(BOMSyncMap, pk=pk, tenant=request.tenant)
        sm.delete()
        messages.success(request, 'Sync map deleted.')
        return redirect('bom:sync_list')


def _diff_boms(source, target):
    """Return a textual drift summary comparing flattened root lines."""
    src_lines = {l.component.sku: l.quantity for l in source.lines.all().select_related('component')}
    tgt_lines = {l.component.sku: l.quantity for l in target.lines.all().select_related('component')}
    only_src = sorted(set(src_lines) - set(tgt_lines))
    only_tgt = sorted(set(tgt_lines) - set(src_lines))
    qty_diff = [
        sku for sku in (set(src_lines) & set(tgt_lines))
        if src_lines[sku] != tgt_lines[sku]
    ]
    parts = []
    if only_src:
        parts.append(f'Only in source: {", ".join(only_src)}')
    if only_tgt:
        parts.append(f'Only in target: {", ".join(only_tgt)}')
    if qty_diff:
        parts.append(f'Quantity differs: {", ".join(sorted(qty_diff))}')
    return ' · '.join(parts) if parts else ''


class BOMSyncRunView(TenantRequiredMixin, View):
    """Run drift detection for a sync map. If drift is found, mark the map
    and write a log entry; otherwise mark in_sync."""

    def post(self, request, pk):
        sm = get_object_or_404(
            BOMSyncMap.objects.select_related('source_bom', 'target_bom'),
            pk=pk, tenant=request.tenant,
        )
        before_summary = sm.drift_summary
        diff = _diff_boms(sm.source_bom, sm.target_bom)
        if diff:
            sm.sync_status = 'drift_detected'
            sm.drift_summary = diff
            action = 'drift'
            msg = f'Drift detected between {sm.source_bom.bom_number} and {sm.target_bom.bom_number}.'
        else:
            sm.sync_status = 'in_sync'
            sm.drift_summary = ''
            action = 'reconciled'
            msg = f'{sm.source_bom.bom_number} and {sm.target_bom.bom_number} are in sync.'
        sm.last_synced_at = timezone.now()
        sm.synced_by = request.user
        sm.save(update_fields=['sync_status', 'drift_summary', 'last_synced_at', 'synced_by'])
        BOMSyncLog.objects.create(
            tenant=request.tenant, sync_map=sm,
            action=action, actor=request.user,
            before_json={'drift_summary': before_summary},
            after_json={'drift_summary': sm.drift_summary, 'sync_status': sm.sync_status},
            notes=msg,
        )
        messages.success(request, msg) if not diff else messages.warning(request, msg)
        return redirect('bom:sync_detail', pk=sm.pk)
