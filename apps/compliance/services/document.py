"""Sub-module 13.2 services - regulatory document lifecycle.

Workflow transitions write a sibling DocumentApproval row so audit history
is append-only and can be reviewed against FDA 21 CFR §11.10(e).
"""
from django.db import transaction
from django.utils import timezone

from apps.compliance import models


@transaction.atomic
def submit_for_review(doc, *, by=None, comment=''):
    if not doc.is_submittable():
        return doc
    doc.status = 'in_review'
    doc.save(update_fields=['status', 'updated_at'])
    models.DocumentApproval.objects.create(
        tenant=doc.tenant, document=doc, action='submit',
        actor=by, comment=comment, acted_at=timezone.now(),
    )
    return doc


@transaction.atomic
def approve(doc, *, by=None, comment=''):
    if not doc.is_approvable():
        return doc
    doc.status = 'approved'
    doc.save(update_fields=['status', 'updated_at'])
    models.DocumentApproval.objects.create(
        tenant=doc.tenant, document=doc, action='approve',
        actor=by, comment=comment, acted_at=timezone.now(),
    )
    return doc


@transaction.atomic
def reject(doc, *, by=None, comment=''):
    if not doc.is_approvable():
        return doc
    doc.status = 'draft'  # back to draft for revision
    doc.save(update_fields=['status', 'updated_at'])
    models.DocumentApproval.objects.create(
        tenant=doc.tenant, document=doc, action='reject',
        actor=by, comment=comment, acted_at=timezone.now(),
    )
    return doc


@transaction.atomic
def publish(doc, *, by=None, comment=''):
    """Move ``approved`` -> ``effective``. Sets effective_from on first publish."""
    if not doc.is_publishable():
        return doc
    doc.status = 'effective'
    if not doc.effective_from:
        doc.effective_from = timezone.now().date()
    doc.save(update_fields=['status', 'effective_from', 'updated_at'])
    models.DocumentApproval.objects.create(
        tenant=doc.tenant, document=doc, action='publish',
        actor=by, comment=comment, acted_at=timezone.now(),
    )
    return doc


@transaction.atomic
def supersede(doc, *, by=None, comment=''):
    if not doc.is_supersedable():
        return doc
    doc.status = 'superseded'
    doc.effective_to = timezone.now().date()
    doc.save(update_fields=['status', 'effective_to', 'updated_at'])
    models.DocumentApproval.objects.create(
        tenant=doc.tenant, document=doc, action='supersede',
        actor=by, comment=comment, acted_at=timezone.now(),
    )
    return doc


@transaction.atomic
def apply_signature(doc, *, signer, typed_name, role, reason, ip_address=None):
    """Persist a 21 CFR §11.50 e-signature row.

    Immutable: each call appends a new row. The ElectronicSignature.save()
    override raises if pk is already set, so the row cannot be mutated post-hoc.
    """
    return models.ElectronicSignature.objects.create(
        tenant=doc.tenant,
        document=doc,
        signer=signer,
        typed_name=typed_name,
        role=role,
        reason=reason,
        signed_at=timezone.now(),
        ip_address=ip_address,
    )
