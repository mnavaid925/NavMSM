"""PR view tests — workflow + RBAC + IDOR.

Regression coverage for D-01 (RBAC), D-07 (delete restriction), L-03.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestPRApprove:
    def test_admin_can_approve_draft(self, admin_client, acme, calc, raw_product, acme_admin, make_pr):
        pr = make_pr(acme, calc, raw_product)
        r = admin_client.post(reverse('mrp:pr_approve', args=[pr.pk]))
        assert r.status_code == 302
        pr.refresh_from_db()
        assert pr.status == 'approved'
        assert pr.approved_by_id == acme_admin.pk
        assert pr.approved_at is not None

    def test_staff_cannot_approve_d01(self, staff_client, acme, calc, raw_product, make_pr):
        """F-01 / D-01: non-admin tenant users must NOT be able to approve PRs."""
        pr = make_pr(acme, calc, raw_product)
        r = staff_client.post(reverse('mrp:pr_approve', args=[pr.pk]))
        # TenantAdminRequiredMixin redirects non-admins to dashboard.
        assert r.status_code == 302
        pr.refresh_from_db()
        assert pr.status == 'draft'

    def test_approve_already_approved_no_change(self, admin_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='approved')
        prior_approved_at = pr.approved_at
        admin_client.post(reverse('mrp:pr_approve', args=[pr.pk]))
        pr.refresh_from_db()
        assert pr.status == 'approved'
        # atomic transition only updates rows whose current status is 'draft'
        assert pr.approved_at == prior_approved_at

    def test_cross_tenant_approve_idor_blocked(self, globex_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product)
        r = globex_client.post(reverse('mrp:pr_approve', args=[pr.pk]))
        # Atomic transition silently no-ops because tenant filter does not match.
        assert r.status_code == 302
        pr.refresh_from_db()
        assert pr.status == 'draft'


@pytest.mark.django_db
class TestPRCancel:
    def test_admin_can_cancel_approved(self, admin_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='approved')
        r = admin_client.post(reverse('mrp:pr_cancel', args=[pr.pk]))
        assert r.status_code == 302
        pr.refresh_from_db()
        assert pr.status == 'cancelled'

    def test_staff_cannot_cancel_d01(self, staff_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='approved')
        staff_client.post(reverse('mrp:pr_cancel', args=[pr.pk]))
        pr.refresh_from_db()
        assert pr.status == 'approved'


@pytest.mark.django_db
class TestPRDelete:
    def test_delete_draft_allowed(self, admin_client, acme, calc, raw_product, make_pr):
        from apps.mrp.models import MRPPurchaseRequisition
        pr = make_pr(acme, calc, raw_product, status='draft')
        r = admin_client.post(reverse('mrp:pr_delete', args=[pr.pk]))
        assert r.status_code == 302
        assert not MRPPurchaseRequisition.objects.filter(pk=pr.pk).exists()

    def test_delete_approved_blocked(self, admin_client, acme, calc, raw_product, make_pr):
        from apps.mrp.models import MRPPurchaseRequisition
        pr = make_pr(acme, calc, raw_product, status='approved')
        admin_client.post(reverse('mrp:pr_delete', args=[pr.pk]))
        assert MRPPurchaseRequisition.objects.filter(pk=pr.pk).exists()

    def test_delete_cancelled_allowed(self, admin_client, acme, calc, raw_product, make_pr):
        from apps.mrp.models import MRPPurchaseRequisition
        pr = make_pr(acme, calc, raw_product, status='cancelled')
        admin_client.post(reverse('mrp:pr_delete', args=[pr.pk]))
        assert not MRPPurchaseRequisition.objects.filter(pk=pr.pk).exists()


@pytest.mark.django_db
class TestPREdit:
    def test_edit_draft_allowed(self, admin_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='draft')
        r = admin_client.get(reverse('mrp:pr_edit', args=[pr.pk]))
        assert r.status_code == 200

    def test_edit_approved_redirected(self, admin_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product, status='approved')
        r = admin_client.get(reverse('mrp:pr_edit', args=[pr.pk]))
        # Form rejects edit for non-draft, redirects to detail.
        assert r.status_code == 302
        assert reverse('mrp:pr_detail', args=[pr.pk]) in r.url
