"""Inventory + Receipt + Seasonality CRUD view tests.

Converts manual plan §4.3.2 (SP CREATE), §4.3.3 (IS CREATE), §4.3.4 (RC CREATE),
§4.4 LIST, §4.5 DETAIL (inventory only), §4.6 EDIT, §4.7 DELETE.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.mrp.models import InventorySnapshot, ScheduledReceipt, SeasonalityProfile


@pytest.mark.django_db
class TestInventorySnapshotCRUD:
    def _payload(self, product, **overrides):
        base = {
            'product': product.pk,
            'on_hand_qty': '5', 'safety_stock': '2', 'reorder_point': '10',
            'lead_time_days': 7, 'lot_size_method': 'l4l',
            'lot_size_value': '0', 'lot_size_max': '0',
            'as_of_date': date.today().isoformat(), 'notes': '',
        }
        base.update(overrides)
        return base

    def test_create_happy_path(self, admin_client, acme, raw_product):
        # raw_product has no snapshot yet.
        r = admin_client.post(reverse('mrp:inventory_create'), self._payload(raw_product))
        assert r.status_code == 302
        assert InventorySnapshot.objects.filter(tenant=acme, product=raw_product).exists()

    def test_list_renders(self, admin_client, snapshot_fg, snapshot_rm):
        r = admin_client.get(reverse('mrp:inventory_list'))
        assert r.status_code == 200
        assert b'FG-1' in r.content or b'fg-1' in r.content.lower()

    def test_detail_shows_upcoming_receipts(
        self, admin_client, acme, raw_product, snapshot_rm,
    ):
        ScheduledReceipt.objects.create(
            tenant=acme, product=raw_product, receipt_type='open_po',
            quantity=Decimal('10'),
            expected_date=date.today() + timedelta(days=5),
            reference='PO-T1',
        )
        r = admin_client.get(reverse('mrp:inventory_detail', args=[snapshot_rm.pk]))
        assert r.status_code == 200
        assert b'PO-T1' in r.content

    def test_edit_pre_fills_and_saves(self, admin_client, snapshot_fg):
        r = admin_client.get(reverse('mrp:inventory_edit', args=[snapshot_fg.pk]))
        assert r.status_code == 200
        new_payload = self._payload(snapshot_fg.product, on_hand_qty='999')
        r = admin_client.post(
            reverse('mrp:inventory_edit', args=[snapshot_fg.pk]),
            new_payload,
        )
        assert r.status_code == 302
        snapshot_fg.refresh_from_db()
        assert snapshot_fg.on_hand_qty == Decimal('999.00')

    def test_delete_allowed(self, admin_client, snapshot_fg):
        snap_pk = snapshot_fg.pk
        r = admin_client.post(reverse('mrp:inventory_delete', args=[snap_pk]))
        assert r.status_code == 302
        assert not InventorySnapshot.objects.filter(pk=snap_pk).exists()

    def test_create_lead_time_over_max_rejected(self, admin_client, acme, raw_product):
        r = admin_client.post(
            reverse('mrp:inventory_create'),
            self._payload(raw_product, lead_time_days=400),
        )
        assert r.status_code == 200
        assert not InventorySnapshot.objects.filter(tenant=acme, product=raw_product).exists()


@pytest.mark.django_db
class TestScheduledReceiptCRUD:
    def _payload(self, product, **overrides):
        base = {
            'product': product.pk,
            'receipt_type': 'open_po',
            'quantity': '100',
            'expected_date': (date.today() + timedelta(days=7)).isoformat(),
            'reference': 'PO-MAN-001',
            'notes': '',
        }
        base.update(overrides)
        return base

    def test_create_happy_path(self, admin_client, acme, raw_product):
        r = admin_client.post(reverse('mrp:receipt_create'), self._payload(raw_product))
        assert r.status_code == 302
        assert ScheduledReceipt.objects.filter(
            tenant=acme, product=raw_product, reference='PO-MAN-001',
        ).exists()

    def test_create_quantity_zero_rejected(self, admin_client, acme, raw_product):
        r = admin_client.post(
            reverse('mrp:receipt_create'),
            self._payload(raw_product, quantity='0'),
        )
        assert r.status_code == 200
        assert not ScheduledReceipt.objects.filter(
            tenant=acme, product=raw_product,
        ).exists()

    def test_create_past_date_allowed(self, admin_client, acme, raw_product):
        r = admin_client.post(
            reverse('mrp:receipt_create'),
            self._payload(
                raw_product,
                expected_date=(date.today() - timedelta(days=5)).isoformat(),
                reference='PO-PAST',
            ),
        )
        assert r.status_code == 302
        assert ScheduledReceipt.objects.filter(reference='PO-PAST').exists()

    def test_list_orders_by_expected_date(
        self, admin_client, acme, raw_product, fg_product,
    ):
        r1 = ScheduledReceipt.objects.create(
            tenant=acme, product=raw_product, receipt_type='open_po',
            quantity=Decimal('5'),
            expected_date=date.today() + timedelta(days=10),
            reference='LATER',
        )
        r2 = ScheduledReceipt.objects.create(
            tenant=acme, product=fg_product, receipt_type='planned_production',
            quantity=Decimal('1'),
            expected_date=date.today() + timedelta(days=2),
            reference='EARLIER',
        )
        r = admin_client.get(reverse('mrp:receipt_list'))
        assert r.status_code == 200
        idx_earlier = r.content.find(b'EARLIER')
        idx_later = r.content.find(b'LATER')
        assert 0 <= idx_earlier < idx_later

    def test_edit_persists(self, admin_client, acme, raw_product):
        rcp = ScheduledReceipt.objects.create(
            tenant=acme, product=raw_product, receipt_type='open_po',
            quantity=Decimal('5'),
            expected_date=date.today() + timedelta(days=3),
            reference='ORIG',
        )
        r = admin_client.post(
            reverse('mrp:receipt_edit', args=[rcp.pk]),
            self._payload(raw_product, quantity='999', reference='UPDATED'),
        )
        assert r.status_code == 302
        rcp.refresh_from_db()
        assert rcp.quantity == Decimal('999.00')
        assert rcp.reference == 'UPDATED'

    def test_delete(self, admin_client, acme, raw_product):
        rcp = ScheduledReceipt.objects.create(
            tenant=acme, product=raw_product, receipt_type='open_po',
            quantity=Decimal('5'),
            expected_date=date.today() + timedelta(days=3),
            reference='DEL',
        )
        r = admin_client.post(reverse('mrp:receipt_delete', args=[rcp.pk]))
        assert r.status_code == 302
        assert not ScheduledReceipt.objects.filter(pk=rcp.pk).exists()


@pytest.mark.django_db
class TestSeasonalityCRUD:
    def _payload(self, product, **overrides):
        base = {
            'product': product.pk,
            'period_type': 'month', 'period_index': 1,
            'seasonal_index': '1.10', 'notes': '',
        }
        base.update(overrides)
        return base

    def test_create_happy_path(self, admin_client, acme, fg_product):
        r = admin_client.post(reverse('mrp:seasonality_create'), self._payload(fg_product))
        assert r.status_code == 302
        assert SeasonalityProfile.objects.filter(
            tenant=acme, product=fg_product, period_index=1,
        ).exists()

    def test_create_duplicate_blocked(self, admin_client, acme, fg_product):
        SeasonalityProfile.objects.create(
            tenant=acme, product=fg_product,
            period_type='month', period_index=1,
            seasonal_index=Decimal('1.10'),
        )
        r = admin_client.post(reverse('mrp:seasonality_create'), self._payload(fg_product))
        assert r.status_code == 200
        assert SeasonalityProfile.objects.filter(
            tenant=acme, product=fg_product, period_index=1,
        ).count() == 1

    def test_edit_persists(self, admin_client, acme, fg_product):
        sp = SeasonalityProfile.objects.create(
            tenant=acme, product=fg_product,
            period_type='month', period_index=2,
            seasonal_index=Decimal('1.00'),
        )
        r = admin_client.post(
            reverse('mrp:seasonality_edit', args=[sp.pk]),
            self._payload(fg_product, period_index=2, seasonal_index='0.7500'),
        )
        assert r.status_code == 302
        sp.refresh_from_db()
        assert sp.seasonal_index == Decimal('0.7500')

    def test_delete(self, admin_client, acme, fg_product):
        sp = SeasonalityProfile.objects.create(
            tenant=acme, product=fg_product,
            period_type='month', period_index=3,
            seasonal_index=Decimal('1.00'),
        )
        r = admin_client.post(reverse('mrp:seasonality_delete', args=[sp.pk]))
        assert r.status_code == 302
        assert not SeasonalityProfile.objects.filter(pk=sp.pk).exists()
