"""Integration tests for production order workflow + tenant isolation + RBAC."""
import pytest


@pytest.mark.django_db
class TestProductionOrderWorkflow:
    def test_release_planned_order(self, admin_client, planned_order):
        r = admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        assert r.status_code == 302
        planned_order.refresh_from_db()
        assert planned_order.status == 'released'

    def test_cannot_start_a_planned_order(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/start/')
        planned_order.refresh_from_db()
        assert planned_order.status == 'planned'  # rejected — needs released first

    def test_schedule_forward_creates_operations(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        r = admin_client.post(
            f'/pps/orders/{planned_order.pk}/schedule/',
            {'method': 'forward'},
        )
        assert r.status_code == 302
        assert planned_order.scheduled_operations.count() == 2

    def test_double_release_only_advances_once(self, admin_client, planned_order):
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        admin_client.post(f'/pps/orders/{planned_order.pk}/release/')
        planned_order.refresh_from_db()
        assert planned_order.status == 'released'


@pytest.mark.django_db
class TestTenantIsolation:
    def test_globex_cannot_view_acme_order(self, globex_client, planned_order):
        r = globex_client.get(f'/pps/orders/{planned_order.pk}/')
        assert r.status_code == 404

    def test_globex_cannot_release_acme_order(self, globex_client, planned_order):
        r = globex_client.post(f'/pps/orders/{planned_order.pk}/release/')
        # The atomic UPDATE filters by tenant — rowcount is 0 for cross-tenant
        # POSTs, the view redirects with a warning. Either 302 or 404 is
        # acceptable; the security property is that the order MUST NOT change.
        assert r.status_code in (302, 404)
        planned_order.refresh_from_db()
        assert planned_order.status == 'planned'
