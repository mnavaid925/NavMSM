"""OWASP A01 / A03 coverage and full RBAC matrix.

Includes:
- A01: anonymous access, superuser-no-tenant guard, IDOR via cross-tenant pk
- A03: XSS escape on user-controlled fields, CSRF enforcement on POST
- RBAC matrix: which endpoints require admin
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse


# --- A01 Broken Access Control ----------------------------------------------

@pytest.mark.django_db
class TestA01_AccessControl:
    def test_anonymous_redirected_to_login(self, client):
        r = client.get(reverse('mrp:index'))
        assert r.status_code == 302
        assert '/login' in r.url.lower() or 'accounts/login' in r.url.lower()

    def test_superuser_no_tenant_redirected_friendly(self, client, db):
        from apps.accounts.models import User
        su = User.objects.create_superuser(
            username='super_mrp', email='su@x.com', password='pw',
        )
        client.force_login(su)
        r = client.get(reverse('mrp:index'))
        # Superuser has tenant=None; TenantRequiredMixin bounces to dashboard.
        assert r.status_code == 302


@pytest.mark.django_db
class TestA01_IDOR:
    def test_cross_tenant_calc_detail_404(self, globex_client, calc):
        r = globex_client.get(reverse('mrp:calculation_detail', args=[calc.pk]))
        assert r.status_code == 404

    def test_cross_tenant_inventory_edit_404(self, globex_client, snapshot_fg):
        r = globex_client.get(reverse('mrp:inventory_edit', args=[snapshot_fg.pk]))
        assert r.status_code == 404

    def test_cross_tenant_pr_detail_404(self, globex_client, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product)
        r = globex_client.get(reverse('mrp:pr_detail', args=[pr.pk]))
        assert r.status_code == 404

    def test_cross_tenant_forecast_model_detail_404(self, globex_client, forecast_model):
        r = globex_client.get(reverse('mrp:forecast_model_detail', args=[forecast_model.pk]))
        assert r.status_code == 404


# --- A03 Injection / XSS ----------------------------------------------------

@pytest.mark.django_db
class TestA03_XSS:
    def test_pr_notes_escaped_on_detail(self, admin_client, acme, calc, raw_product):
        from apps.mrp.models import MRPPurchaseRequisition
        payload = '<script>alert(1)</script>'
        pr = MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-XSS', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('1'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='draft', priority='normal',
            notes=payload,
        )
        r = admin_client.get(reverse('mrp:pr_detail', args=[pr.pk]))
        assert r.status_code == 200
        # Literal payload must NOT appear unescaped
        assert payload.encode() not in r.content
        # Auto-escaped form must appear
        assert b'&lt;script&gt;' in r.content


@pytest.mark.django_db
class TestA03_CSRF:
    def test_post_without_csrf_blocked(self, acme_admin, calc):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(acme_admin)
        r = c.post(reverse('mrp:calculation_delete', args=[calc.pk]))
        assert r.status_code == 403


# --- RBAC matrix (D-01) ----------------------------------------------------

@pytest.mark.django_db
class TestRBACMatrix:
    """Smoke that every privileged endpoint requires admin and rejects staff.

    Read-only endpoints (lists, details) remain on TenantRequiredMixin so
    staff can browse. Only state-changing privileged actions are admin-gated.
    """
    def test_staff_can_view_lists(self, staff_client):
        # Read-only paths must remain accessible to non-admin staff.
        for url in [
            reverse('mrp:index'),
            reverse('mrp:calculation_list'),
            reverse('mrp:run_list'),
            reverse('mrp:pr_list'),
            reverse('mrp:exception_list'),
            reverse('mrp:inventory_list'),
            reverse('mrp:forecast_model_list'),
        ]:
            assert staff_client.get(url).status_code == 200

    def test_staff_blocked_from_privileged_post(
        self, staff_client, acme, calc, raw_product, make_pr,
    ):
        from apps.mrp.models import MRPException, MRPPurchaseRequisition, MRPRun
        pr = make_pr(acme, calc, raw_product)
        run = MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-RB', name='rb',
            run_type='regenerative', status='completed', mrp_calculation=calc,
        )
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='m',
        )
        privileged = [
            reverse('mrp:pr_approve', args=[pr.pk]),
            reverse('mrp:pr_cancel', args=[pr.pk]),
            reverse('mrp:run_apply', args=[run.pk]),
            reverse('mrp:run_discard', args=[run.pk]),
            reverse('mrp:exception_resolve', args=[exc.pk]),
            reverse('mrp:exception_ignore', args=[exc.pk]),
            reverse('mrp:calculation_delete', args=[calc.pk]),
        ]
        for url in privileged:
            r = staff_client.post(url, {'resolution_notes': 'x'})
            # Mixin redirects to dashboard with an error flash
            assert r.status_code == 302, f'{url} did not redirect for staff'

        # Verify NO state changed
        pr.refresh_from_db()
        run.refresh_from_db()
        exc.refresh_from_db()
        calc.refresh_from_db()
        assert pr.status == 'draft'
        assert run.status == 'completed'
        assert exc.status == 'open'
        assert MRPPurchaseRequisition.objects.filter(pk=pr.pk).exists()
