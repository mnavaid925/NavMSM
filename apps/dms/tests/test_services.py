"""Pure-function service tests."""
from datetime import date

import pytest

from apps.dms.services import approval as approval_svc
from apps.dms.services import checkout as checkout_svc
from apps.dms.services import legal_hold as legal_hold_svc
from apps.dms.services import retention as retention_svc
from apps.dms.services.numbering import next_code


@pytest.mark.django_db
class TestNumbering:
    def test_first_code(self, tenant_a):
        from apps.dms.models import Document
        code = next_code(Document, tenant_a, 'DOC', 5)
        assert code == 'DOC-00001'


@pytest.mark.django_db
class TestCheckout:
    def test_check_out_marks_user(self, version, tenant_admin):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        assert version.checked_out_by_id == tenant_admin.id
        assert version.checked_out_at is not None

    def test_double_checkout_by_other_user_raises(self, version, tenant_admin, staff_user):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        with pytest.raises(checkout_svc.CheckoutError):
            checkout_svc.check_out(version, staff_user)

    def test_self_check_out_is_idempotent(self, version, tenant_admin):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        checkout_svc.check_out(version, tenant_admin)  # no error

    def test_check_in_by_holder(self, version, tenant_admin):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        checkout_svc.check_in(version, tenant_admin)
        version.refresh_from_db()
        assert version.checked_out_by_id is None
        assert version.checked_out_at is None

    def test_check_in_by_other_user_raises(self, version, tenant_admin, staff_user):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        with pytest.raises(checkout_svc.CheckoutError):
            checkout_svc.check_in(version, staff_user)

    def test_check_in_by_admin_allowed(self, version, tenant_admin, staff_user):
        checkout_svc.check_out(version, tenant_admin)
        version.refresh_from_db()
        # Admin override.
        checkout_svc.check_in(version, staff_user, is_admin=True)
        version.refresh_from_db()
        assert version.checked_out_by_id is None


class TestRetentionMath:
    def test_compute_basic(self):
        d = date(2025, 6, 15)
        assert retention_svc.compute_retention_until(d, 5) == date(2030, 6, 15)

    def test_compute_zero_years(self):
        d = date(2025, 6, 15)
        assert retention_svc.compute_retention_until(d, 0) == d

    def test_compute_none_effective(self):
        assert retention_svc.compute_retention_until(None, 5) is None

    def test_leap_day_clamped(self):
        d = date(2024, 2, 29)
        assert retention_svc.compute_retention_until(d, 1) == date(2025, 2, 28)


@pytest.mark.django_db
class TestRetentionDue:
    def test_due_when_past(self, tenant_a, document):
        from apps.dms.models import Document
        Document.all_objects.filter(pk=document.pk).update(
            retention_until=date.today().replace(year=2000),
        )
        document.refresh_from_db()
        assert retention_svc.is_due_for_archive(document)

    def test_not_due_when_locked(self, tenant_a, document):
        from apps.dms.models import Document
        Document.all_objects.filter(pk=document.pk).update(
            retention_until=date.today().replace(year=2000),
            is_locked=True,
        )
        document.refresh_from_db()
        assert not retention_svc.is_due_for_archive(document)


@pytest.mark.django_db
class TestApprovalAdvance:
    def test_advance_from_incomplete_stays(self, tenant_a, document, workflow_with_stages):
        from apps.dms.models import DocumentApprovalRequest
        req = DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='in_progress',
        )
        assert approval_svc.current_stage(req).stage_no == 1
        # No approve actions yet -> still on stage 1.
        assert approval_svc.advance_stage(req) == 1


@pytest.mark.django_db
class TestLegalHoldCascade:
    def test_apply_hold_locks_docs(self, tenant_a, document):
        from apps.dms.models import LegalHold
        hold = LegalHold.objects.create(tenant=tenant_a, name='X', status='active')
        hold.documents.add(document)
        # signal already applies via m2m_changed; service is idempotent here.
        legal_hold_svc.apply_hold(hold)
        document.refresh_from_db()
        assert document.is_locked

    def test_release_clears_lock_when_only_hold(self, tenant_a, document):
        from apps.dms.models import LegalHold
        hold = LegalHold.objects.create(tenant=tenant_a, name='X', status='active')
        hold.documents.add(document)
        legal_hold_svc.apply_hold(hold)
        # Mark released.
        hold.status = 'released'
        hold.save(update_fields=['status'])
        legal_hold_svc.release_hold(hold)
        document.refresh_from_db()
        assert not document.is_locked

    def test_release_keeps_lock_when_another_active(self, tenant_a, document):
        from apps.dms.models import LegalHold
        h1 = LegalHold.objects.create(tenant=tenant_a, name='H1', status='active')
        h1.documents.add(document)
        h2 = LegalHold.objects.create(tenant=tenant_a, name='H2', status='active')
        h2.documents.add(document)
        h1.status = 'released'
        h1.save(update_fields=['status'])
        legal_hold_svc.release_hold(h1)
        document.refresh_from_db()
        assert document.is_locked  # still locked by h2
