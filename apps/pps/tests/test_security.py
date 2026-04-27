"""OWASP-mapped security tests — D-01 (XSS), D-07 (RBAC), CSRF."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone


# --- A01 Broken Access Control ---

@pytest.mark.django_db
class TestA01_BrokenAccessControl:
    def test_anonymous_redirected_to_login(self, client):
        r = client.get('/pps/')
        assert r.status_code == 302
        assert '/accounts/login/' in r.url

    def test_non_admin_blocked_from_creating_workcenter(self, staff_client):
        r = staff_client.post('/pps/work-centers/new/', {
            'code': 'X', 'name': 'X', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        # TenantAdminRequiredMixin redirects non-admins to dashboard.
        assert r.status_code == 302
        from apps.pps.models import WorkCenter
        assert not WorkCenter.objects.filter(code='X').exists()

    def test_non_admin_cannot_obsolete_mps_d07(self, staff_client, draft_mps):
        from apps.pps.models import MasterProductionSchedule
        MasterProductionSchedule.objects.filter(pk=draft_mps.pk).update(status='released')
        r = staff_client.post(f'/pps/mps/{draft_mps.pk}/obsolete/')
        assert r.status_code == 302  # redirected to dashboard
        draft_mps.refresh_from_db()
        assert draft_mps.status == 'released'  # NOT flipped

    def test_non_admin_cannot_release_order(self, staff_client, planned_order):
        r = staff_client.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 302
        planned_order.refresh_from_db()
        assert planned_order.status == 'planned'

    def test_non_admin_can_still_view_lists(self, staff_client):
        # Read-only views remain on TenantRequiredMixin — staff can browse.
        r = staff_client.get('/pps/orders/')
        assert r.status_code == 200


# --- A03 Injection / XSS — D-01 regression ---

@pytest.mark.django_db
class TestA03_XSS_D01:
    def test_gantt_escapes_user_controlled_sku(self, admin_client, acme, work_center, acme_admin):
        from apps.plm.models import Product
        from apps.pps.models import (
            ProductionOrder, ScheduledOperation, Routing, RoutingOperation,
        )

        bad = '</script><img src=x onerror=alert(1)>'
        product = Product.objects.create(
            tenant=acme, sku=bad, name='Malicious', product_type='finished_good',
            unit_of_measure='ea', status='active',
        )
        routing = Routing.objects.create(
            tenant=acme, product=product, version='A', routing_number='ROUT-X',
            status='active', is_default=True, created_by=acme_admin,
        )
        op = RoutingOperation.objects.create(
            tenant=acme, routing=routing, sequence=10, operation_name='Test',
            work_center=work_center, setup_minutes=Decimal('5'),
            run_minutes_per_unit=Decimal('1'),
            queue_minutes=Decimal('1'), move_minutes=Decimal('1'),
        )
        order = ProductionOrder.objects.create(
            tenant=acme, order_number='PO-X', product=product, routing=routing,
            quantity=Decimal('1'), status='released', priority='normal',
            scheduling_method='forward', created_by=acme_admin,
        )
        ScheduledOperation.objects.create(
            tenant=acme, production_order=order, routing_operation=op,
            work_center=work_center, sequence=10,
            planned_start=timezone.now(),
            planned_end=timezone.now() + timedelta(hours=1),
            planned_minutes=60,
        )
        r = admin_client.get('/pps/orders/gantt/')
        assert r.status_code == 200
        # Verbatim </script>< must NOT survive in the rendered body — that's
        # the precise sequence that breaks out of the script tag. After the
        # json_script fix it's HTML-escaped.
        assert b'</script><img src=x' not in r.content

    def test_gantt_uses_json_script_tag(self, admin_client):
        r = admin_client.get('/pps/orders/gantt/')
        assert r.status_code == 200
        # The fixed template emits <script type="application/json" id="gantt-chart-data">
        assert b'id="gantt-chart-data"' in r.content


# --- A04 Insecure design — D-02, D-04 view-level integration ---

@pytest.mark.django_db
class TestA04_InsecureDesign:
    def test_workcenter_create_negative_capacity_returns_form_error(self, admin_client):
        r = admin_client.post('/pps/work-centers/new/', {
            'code': 'BAD', 'name': 'Bad', 'work_center_type': 'machine',
            'capacity_per_hour': '-5', 'efficiency_pct': '999',
            'cost_per_hour': '-100', 'description': '', 'is_active': True,
        })
        # Form re-renders with errors; status 200; no DB row created.
        assert r.status_code == 200
        from apps.pps.models import WorkCenter
        assert not WorkCenter.objects.filter(code='BAD').exists()

    def test_workcenter_edit_to_duplicate_code_does_not_500(self, admin_client, acme):
        from apps.pps.models import WorkCenter
        from decimal import Decimal as D
        WorkCenter.objects.create(
            tenant=acme, code='A', name='A', work_center_type='machine',
            capacity_per_hour=D('1'), efficiency_pct=D('100'),
            cost_per_hour=D('1'),
        )
        b = WorkCenter.objects.create(
            tenant=acme, code='B', name='B', work_center_type='machine',
            capacity_per_hour=D('1'), efficiency_pct=D('100'),
            cost_per_hour=D('1'),
        )
        r = admin_client.post(f'/pps/work-centers/{b.pk}/edit/', {
            'code': 'A',  # collides with the first one
            'name': 'B-renamed', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert r.status_code == 200  # MUST NOT be 500
        b.refresh_from_db()
        assert b.code == 'B'  # not changed


# --- CSRF ---

@pytest.mark.django_db
class TestCSRF:
    def test_post_without_csrf_rejected(self, acme_admin, planned_order):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(acme_admin)
        r = c.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 403
