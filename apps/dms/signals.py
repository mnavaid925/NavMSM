"""Module 19 - DMS - cross-module signal handlers.

All handlers are module-level (strong reference - L-18 safe), carry a
`dispatch_uid`, and are idempotent on a natural key so a re-save never
double-emits.

  1. DocumentVersion.status='released'
        -> supersede prior released versions on the same document
        -> update Document.current_version
  2. DocumentApprovalRequest.status='approved'
        -> flip Document.status='effective' + set effective_date
  3. LegalHold.documents M2M change
        -> recompute Document.is_locked for impacted documents
  4. RetentionPolicy.post_save / Document.post_save
        -> recompute Document.retention_until via
           services/retention.compute_retention_until
  5. DocumentSignature.pre_save
        -> reject updates (immutable FDA 21 CFR Part 11 model);
           only INSERT is allowed
  6. Document.pre_delete
        -> defensive: refuse to delete a locked Document at the
           model layer (views also guard, but signal is the last line)

Every side-effect is best-effort: a failure in a downstream module
is logged at WARNING (L-23) and swallowed so the DMS workflow never
blocks on another module's configuration.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import (
    m2m_changed, post_save, pre_delete, pre_save,
)
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# 1. DocumentVersion released -> supersede prior, set Document.current_version
# ----------------------------------------------------------------------------

@receiver(post_save, sender='dms.DocumentVersion', dispatch_uid='dms.version_released')
def _version_released_cascade(sender, instance, created, **kwargs):
    if instance.status != 'released':
        return
    try:
        from apps.dms.models import Document, DocumentVersion
        with transaction.atomic():
            # Supersede prior releases (exclude self).
            (
                DocumentVersion.all_objects
                .filter(document=instance.document, status='released')
                .exclude(pk=instance.pk)
                .update(status='superseded')
            )
            # Bump Document.current_version (denorm).
            Document.all_objects.filter(pk=instance.document_id).update(
                current_version=instance,
            )
    except Exception as exc:
        logger.warning(
            'dms version-released cascade failed version=%s err=%s',
            instance.pk, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 2. ApprovalRequest approved -> Document effective + effective_date
# ----------------------------------------------------------------------------
# Note: the approval view layer already sets Document.status='effective'
# transactionally when the final stage clears. This signal is a defensive
# convergence path so that direct-DB / admin / shell paths still cascade.

@receiver(post_save, sender='dms.DocumentApprovalRequest', dispatch_uid='dms.approval_approved')
def _approval_approved_cascade(sender, instance, created, **kwargs):
    if instance.status != 'approved':
        return
    try:
        from apps.dms.models import Document
        doc = Document.all_objects.filter(pk=instance.document_id).first()
        if doc is None or doc.status == 'effective':
            return
        new_eff = instance.effective_date or timezone.localdate()
        Document.all_objects.filter(pk=doc.pk).update(
            status='effective', effective_date=new_eff,
        )
    except Exception as exc:
        logger.warning(
            'dms approval-approved cascade failed request=%s err=%s',
            instance.code, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 3. LegalHold.documents M2M -> recompute Document.is_locked
# ----------------------------------------------------------------------------

@receiver(m2m_changed, sender='dms.LegalHold_documents', dispatch_uid='dms.legal_hold_m2m')
def _legal_hold_documents_changed(sender, instance, action, pk_set, **kwargs):
    """Recompute is_locked on docs whose hold M2M membership changed."""
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    try:
        from apps.dms.models import Document, LegalHold

        if action == 'post_add' and getattr(instance, 'status', None) == 'active':
            if pk_set:
                Document.all_objects.filter(pk__in=pk_set).update(is_locked=True)
            return

        if action == 'post_remove':
            for doc_pk in (pk_set or set()):
                other_active = (
                    LegalHold.all_objects
                    .filter(documents__pk=doc_pk, status='active')
                    .exclude(pk=instance.pk)
                    .exists()
                )
                Document.all_objects.filter(pk=doc_pk).update(is_locked=other_active)
            return

        if action == 'post_clear':
            # Best-effort - we can't know which docs were attached;
            # nothing to do here since the through-rows are gone.
            return
    except Exception as exc:
        logger.warning(
            'dms legal-hold m2m cascade failed hold=%s action=%s err=%s',
            getattr(instance, 'pk', None), action, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 4. Retention denorm refresh
# ----------------------------------------------------------------------------

@receiver(post_save, sender='dms.Document', dispatch_uid='dms.doc_retention_refresh')
def _doc_retention_refresh(sender, instance, created, **kwargs):
    """Keep Document.retention_until in sync with policy + effective_date."""
    try:
        from apps.dms.models import Document
        from apps.dms.services.retention import compute_retention_until
        expected = None
        if instance.retention_policy and instance.effective_date:
            expected = compute_retention_until(
                instance.effective_date,
                instance.retention_policy.retention_years,
            )
        if expected != instance.retention_until:
            Document.all_objects.filter(pk=instance.pk).update(retention_until=expected)
    except Exception as exc:
        logger.warning(
            'dms doc retention recompute failed doc=%s err=%s',
            instance.pk, exc, exc_info=True,
        )


@receiver(post_save, sender='dms.RetentionPolicy', dispatch_uid='dms.policy_retention_refresh')
def _policy_retention_refresh(sender, instance, created, **kwargs):
    """When a policy's retention_years changes, refresh every linked Document."""
    if created:
        return
    try:
        from apps.dms.models import Document
        from apps.dms.services.retention import compute_retention_until
        for doc in Document.all_objects.filter(retention_policy=instance):
            new = compute_retention_until(doc.effective_date, instance.retention_years)
            if new != doc.retention_until:
                Document.all_objects.filter(pk=doc.pk).update(retention_until=new)
    except Exception as exc:
        logger.warning(
            'dms policy retention refresh failed policy=%s err=%s',
            instance.pk, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 5. DocumentSignature immutability
# ----------------------------------------------------------------------------

@receiver(pre_save, sender='dms.DocumentSignature', dispatch_uid='dms.signature_immutable')
def _signature_immutable(sender, instance, **kwargs):
    """Reject any UPDATE on a DocumentSignature row.

    INSERTs land with instance.pk = None at this point in pre_save.
    Once a signature exists in the DB, changing any field is forbidden -
    FDA 21 CFR Part 11.
    """
    if not instance.pk:
        return  # INSERT - allowed
    try:
        from apps.dms.models import DocumentSignature
        existing = DocumentSignature.all_objects.filter(pk=instance.pk).first()
    except Exception:
        return
    if existing is None:
        return
    immutable_fields = (
        'document_id', 'signer_id', 'signed_at', 'meaning',
        'typed_name', 'ip_address', 'user_agent', 'tenant_id',
    )
    for f in immutable_fields:
        if getattr(existing, f) != getattr(instance, f):
            raise PermissionError(
                'DocumentSignature is immutable (FDA 21 CFR Part 11). '
                f'Field "{f}" cannot be modified after creation.'
            )


# ----------------------------------------------------------------------------
# 6. Document delete guard - never allow deleting a locked document
# ----------------------------------------------------------------------------

@receiver(pre_delete, sender='dms.Document', dispatch_uid='dms.doc_locked_no_delete')
def _doc_locked_no_delete(sender, instance, **kwargs):
    if instance.is_locked:
        raise PermissionError(
            f'Document {instance.code} is under legal hold and cannot be deleted.'
        )
