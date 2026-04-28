"""Exception management views — ack / resolve / ignore / delete + RBAC.

Covers D-01 (RBAC), D-06 (resolution_notes required), D-07 (delete restricted).
"""
import pytest
from django.urls import reverse

from apps.mrp.models import MRPException


def _make_exc(acme, calc, raw_product, *, status='open'):
    return MRPException.objects.create(
        tenant=acme, mrp_calculation=calc, product=raw_product,
        exception_type='late_order', severity='high',
        message='past due', status=status,
    )


@pytest.mark.django_db
class TestExceptionAcknowledge:
    def test_ack_open(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product)
        admin_client.post(reverse('mrp:exception_acknowledge', args=[exc.pk]))
        exc.refresh_from_db()
        assert exc.status == 'acknowledged'

    def test_ack_already_acknowledged_no_change(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product, status='acknowledged')
        admin_client.post(reverse('mrp:exception_acknowledge', args=[exc.pk]))
        exc.refresh_from_db()
        assert exc.status == 'acknowledged'


@pytest.mark.django_db
class TestExceptionResolve:
    def test_resolve_with_notes(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product)
        r = admin_client.post(
            reverse('mrp:exception_resolve', args=[exc.pk]),
            {'resolution_notes': 'Closed manually after expediting.'},
        )
        assert r.status_code == 302
        exc.refresh_from_db()
        assert exc.status == 'resolved'
        assert exc.resolved_at is not None

    def test_resolve_empty_notes_blocked_d06(self, admin_client, acme, calc, raw_product):
        """F-12 / D-06: empty resolution_notes must NOT close the exception."""
        exc = _make_exc(acme, calc, raw_product)
        admin_client.post(
            reverse('mrp:exception_resolve', args=[exc.pk]),
            {'resolution_notes': ''},
        )
        exc.refresh_from_db()
        assert exc.status == 'open'

    def test_staff_cannot_resolve_d01(self, staff_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product)
        staff_client.post(
            reverse('mrp:exception_resolve', args=[exc.pk]),
            {'resolution_notes': 'force close'},
        )
        exc.refresh_from_db()
        assert exc.status == 'open'


@pytest.mark.django_db
class TestExceptionIgnore:
    def test_ignore_open(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product)
        admin_client.post(reverse('mrp:exception_ignore', args=[exc.pk]))
        exc.refresh_from_db()
        assert exc.status == 'ignored'

    def test_staff_cannot_ignore_d01(self, staff_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product)
        staff_client.post(reverse('mrp:exception_ignore', args=[exc.pk]))
        exc.refresh_from_db()
        assert exc.status == 'open'


@pytest.mark.django_db
class TestExceptionDeleteD07:
    def test_open_exception_undeletable(self, admin_client, acme, calc, raw_product):
        """F-07 / D-07: open / acknowledged exceptions must NOT be deletable."""
        exc = _make_exc(acme, calc, raw_product, status='open')
        admin_client.post(reverse('mrp:exception_delete', args=[exc.pk]))
        assert MRPException.objects.filter(pk=exc.pk).exists()

    def test_acknowledged_exception_undeletable(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product, status='acknowledged')
        admin_client.post(reverse('mrp:exception_delete', args=[exc.pk]))
        assert MRPException.objects.filter(pk=exc.pk).exists()

    def test_resolved_deletable(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product, status='resolved')
        admin_client.post(reverse('mrp:exception_delete', args=[exc.pk]))
        assert not MRPException.objects.filter(pk=exc.pk).exists()

    def test_ignored_deletable(self, admin_client, acme, calc, raw_product):
        exc = _make_exc(acme, calc, raw_product, status='ignored')
        admin_client.post(reverse('mrp:exception_delete', args=[exc.pk]))
        assert not MRPException.objects.filter(pk=exc.pk).exists()
