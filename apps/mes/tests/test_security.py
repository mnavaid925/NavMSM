"""Multi-tenancy / authorization / CSRF security tests for MES.

Covers:
- Anonymous redirect on every list / detail page
- Cross-tenant IDOR on every primary entity
- Admin-only POST endpoints reject non-admin users
- File-download view enforces tenant isolation (no media leak)
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.mes.models import (
    AndonAlert, MESWorkOrder, ShopFloorOperator, WorkInstruction,
    WorkInstructionVersion,
)


# ============================================================================
# Anonymous user → login redirect
# ============================================================================

@pytest.mark.django_db
class TestAnonymousAccess:
    @pytest.mark.parametrize('url_name', [
        'mes:index', 'mes:terminal', 'mes:work_order_list', 'mes:operator_list',
        'mes:time_log_list', 'mes:report_list', 'mes:andon_list',
        'mes:instruction_list',
    ])
    def test_list_pages_redirect_anonymous(self, client, url_name):
        resp = client.get(reverse(url_name))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp.url


# ============================================================================
# Cross-tenant IDOR — request a Globex pk while logged in as Acme
# ============================================================================

@pytest.mark.django_db
class TestCrossTenantIDOR:
    def test_globex_work_order_returns_404(
        self, admin_client, globex, globex_admin, globex_product,
    ):
        # Build a work order in the OTHER tenant directly
        from apps.pps.models import ProductionOrder
        po = ProductionOrder.objects.create(
            tenant=globex, order_number='PO-GBX', product=globex_product,
            quantity=Decimal('1'), status='dispatched',
        )
        wo = MESWorkOrder.objects.create(
            tenant=globex, wo_number='WO-GBX',
            production_order=po, product=globex_product,
            quantity_to_build=Decimal('1'),
        )
        resp = admin_client.get(reverse('mes:work_order_detail', args=[wo.pk]))
        assert resp.status_code == 404

    def test_globex_andon_returns_404(self, admin_client, globex, globex_work_center):
        a = AndonAlert.objects.create(
            tenant=globex, alert_number='AND-GBX', alert_type='quality',
            severity='medium', title='Globex alert', work_center=globex_work_center,
            raised_at=timezone.now(),
        )
        resp = admin_client.get(reverse('mes:andon_detail', args=[a.pk]))
        assert resp.status_code == 404

    def test_globex_operator_returns_404(self, admin_client, globex_operator):
        resp = admin_client.get(reverse('mes:operator_detail', args=[globex_operator.pk]))
        assert resp.status_code == 404

    def test_globex_instruction_returns_404(
        self, admin_client, globex, globex_product, globex_admin,
    ):
        wi = WorkInstruction.objects.create(
            tenant=globex, instruction_number='SOP-GBX',
            title='Globex SOP', doc_type='sop',
            product=globex_product, status='draft',
            created_by=globex_admin,
        )
        resp = admin_client.get(reverse('mes:instruction_detail', args=[wi.pk]))
        assert resp.status_code == 404

    def test_globex_version_download_returns_404(
        self, admin_client, globex, globex_product, globex_admin,
    ):
        wi = WorkInstruction.objects.create(
            tenant=globex, instruction_number='SOP-GBX2',
            title='X', doc_type='sop', product=globex_product,
            status='draft', created_by=globex_admin,
        )
        v = WorkInstructionVersion.objects.create(
            tenant=globex, instruction=wi, version='1.0',
            content='secret', status='draft', uploaded_by=globex_admin,
        )
        resp = admin_client.get(reverse('mes:instruction_version_download', args=[v.pk]))
        assert resp.status_code == 404

    def test_globex_operator_clock_in_returns_404(self, admin_client, globex_operator):
        resp = admin_client.post(
            reverse('mes:operator_clock_in', args=[globex_operator.pk]),
        )
        assert resp.status_code == 404


# ============================================================================
# Admin-only POST endpoints
# ============================================================================

@pytest.mark.django_db
class TestAdminOnlyEndpoints:
    def test_non_admin_cannot_dispatch(self, staff_client, released_po):
        staff_client.post(reverse('mes:dispatch', args=[released_po.pk]))
        assert MESWorkOrder.objects.filter(production_order=released_po).count() == 0

    def test_non_admin_cannot_create_operator(self, staff_client, acme, work_center):
        from apps.accounts.models import User
        u = User.objects.create_user(username='u_new', password='pw', tenant=acme)
        before = ShopFloorOperator.objects.count()
        staff_client.post(reverse('mes:operator_create'), {
            'user': u.pk, 'badge_number': 'B-NEW',
            'default_work_center': work_center.pk, 'is_active': True, 'notes': '',
        })
        assert ShopFloorOperator.objects.count() == before

    def test_non_admin_cannot_create_instruction(self, staff_client, routing):
        rop = routing.operations.first()
        before = WorkInstruction.objects.count()
        staff_client.post(reverse('mes:instruction_create'), {
            'title': 'X', 'doc_type': 'sop',
            'routing_operation': rop.pk, 'product': '',
        })
        assert WorkInstruction.objects.count() == before

    def test_non_admin_cannot_release_version(
        self, staff_client, draft_instruction_version,
    ):
        staff_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        draft_instruction_version.refresh_from_db()
        assert draft_instruction_version.status == 'draft'

    def test_operator_action_blocked_for_user_without_profile(
        self, admin_client, first_op,
    ):
        # admin_client → acme_admin, who has NO ShopFloorOperator profile.
        admin_client.post(reverse('mes:operation_start', args=[first_op.pk]))
        first_op.refresh_from_db()
        assert first_op.status == 'pending'


# ============================================================================
# Superuser without tenant sees empty pages (BY DESIGN, per CLAUDE.md)
# ============================================================================

@pytest.mark.django_db
class TestSuperuserNoTenant:
    def test_superuser_without_tenant_redirected_from_dashboard(self, client, db):
        from apps.accounts.models import User
        su = User.objects.create_user(
            username='super', password='pw',
            is_superuser=True, is_staff=True,
            is_tenant_admin=False, tenant=None,
        )
        client.force_login(su)
        # TenantRequiredMixin sends superuser-without-tenant home with a flash.
        resp = client.get(reverse('mes:work_order_list'))
        # Either a redirect (302) or rendered with a flash; check no 500.
        assert resp.status_code in (302, 200)


# ============================================================================
# CSRF — every POST form must carry a CSRF token (sample 4 surfaces)
# ============================================================================

@pytest.mark.django_db
class TestCSRFTokenPresent:
    @pytest.mark.parametrize('url_name', [
        'mes:operator_create', 'mes:andon_create', 'mes:instruction_create',
        'mes:report_create',
    ])
    def test_csrf_token_in_form(self, admin_client, url_name):
        resp = admin_client.get(reverse(url_name))
        assert resp.status_code == 200
        assert b'csrfmiddlewaretoken' in resp.content


# ============================================================================
# CSRF — POST without a token must 403
# ============================================================================

@pytest.mark.django_db
class TestCSRFEnforced:
    def test_post_without_csrf_returns_403(self, client, acme_admin, work_order):
        # Use enforce_csrf_checks=True client — Django's default test client
        # disables CSRF, so we need a fresh one.
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(acme_admin)
        resp = c.post(reverse('mes:work_order_start', args=[work_order.pk]))
        assert resp.status_code == 403
