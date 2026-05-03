"""Service-layer tests: post_movement, allocation, cycle_count math."""
from decimal import Decimal

import pytest

from apps.inventory import models as inv_models
from apps.inventory.services.allocation import (
    InsufficientStockError, allocate_fefo, allocate_fifo,
)
from apps.inventory.services.cycle_count import classify_abc, compute_variance
from apps.inventory.services.grn import suggest_bin
from apps.inventory.services.movements import post_movement, reverse_movement


pytestmark = pytest.mark.django_db


# ---------- post_movement ----------

def test_post_movement_receipt_creates_stock_item(acme, fg_product, bin_a):
    mv = post_movement(
        tenant=acme, movement_type='receipt',
        product=fg_product, qty=Decimal('5'), to_bin=bin_a,
    )
    assert mv.pk
    item = inv_models.StockItem.all_objects.get(
        tenant=acme, product=fg_product, bin=bin_a, lot=None, serial=None,
    )
    assert item.qty_on_hand == Decimal('5')


def test_post_movement_issue_decrements(acme, fg_product, bin_a):
    post_movement(
        tenant=acme, movement_type='receipt',
        product=fg_product, qty=Decimal('10'), to_bin=bin_a,
    )
    post_movement(
        tenant=acme, movement_type='issue',
        product=fg_product, qty=Decimal('3'), from_bin=bin_a,
    )
    item = inv_models.StockItem.all_objects.get(
        tenant=acme, product=fg_product, bin=bin_a,
    )
    assert item.qty_on_hand == Decimal('7')


def test_post_movement_insufficient_stock_raises(acme, fg_product, bin_a):
    with pytest.raises(ValueError, match='insufficient stock'):
        post_movement(
            tenant=acme, movement_type='issue',
            product=fg_product, qty=Decimal('1'), from_bin=bin_a,
        )


def test_post_movement_transfer_moves_balance(acme, fg_product, bin_a, bin_b):
    post_movement(
        tenant=acme, movement_type='receipt',
        product=fg_product, qty=Decimal('10'), to_bin=bin_a,
    )
    post_movement(
        tenant=acme, movement_type='transfer',
        product=fg_product, qty=Decimal('4'),
        from_bin=bin_a, to_bin=bin_b,
    )
    a_item = inv_models.StockItem.all_objects.get(
        tenant=acme, product=fg_product, bin=bin_a,
    )
    b_item = inv_models.StockItem.all_objects.get(
        tenant=acme, product=fg_product, bin=bin_b,
    )
    assert a_item.qty_on_hand == Decimal('6')
    assert b_item.qty_on_hand == Decimal('4')


def test_post_movement_requires_to_bin_for_receipt(acme, fg_product):
    with pytest.raises(ValueError, match='to_bin is required'):
        post_movement(
            tenant=acme, movement_type='receipt',
            product=fg_product, qty=Decimal('1'),
        )


def test_post_movement_requires_from_bin_for_issue(acme, fg_product):
    with pytest.raises(ValueError, match='from_bin is required'):
        post_movement(
            tenant=acme, movement_type='issue',
            product=fg_product, qty=Decimal('1'),
        )


def test_post_movement_transfer_requires_both(acme, fg_product, bin_a):
    with pytest.raises(ValueError, match='transfer requires both'):
        post_movement(
            tenant=acme, movement_type='transfer',
            product=fg_product, qty=Decimal('1'), from_bin=bin_a,
        )


def test_post_movement_adjustment_requires_one(acme, fg_product, bin_a, bin_b):
    with pytest.raises(ValueError, match='exactly one'):
        post_movement(
            tenant=acme, movement_type='adjustment',
            product=fg_product, qty=Decimal('1'),
            from_bin=bin_a, to_bin=bin_b,
        )


def test_post_movement_negative_qty_rejected(acme, fg_product, bin_a):
    with pytest.raises(ValueError, match='must be positive'):
        post_movement(
            tenant=acme, movement_type='receipt',
            product=fg_product, qty=Decimal('-1'), to_bin=bin_a,
        )


def test_reverse_movement_compensates(acme, fg_product, bin_a):
    mv = post_movement(
        tenant=acme, movement_type='receipt',
        product=fg_product, qty=Decimal('5'), to_bin=bin_a,
    )
    reverse_movement(mv, reason='test reversal')
    item = inv_models.StockItem.all_objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item.qty_on_hand == Decimal('0')


# ---------- Allocation ----------

class _Row:
    def __init__(self, qty, lot=None):
        self.qty_on_hand = qty
        self.lot = lot


def test_allocate_fifo_uses_oldest_first():
    rows = [_Row(Decimal('3'), 'old'), _Row(Decimal('5'), 'new')]
    alloc = allocate_fifo(rows, Decimal('4'))
    assert len(alloc) == 2
    assert alloc[0][1] == Decimal('3')
    assert alloc[1][1] == Decimal('1')


def test_allocate_fifo_single_row():
    rows = [_Row(Decimal('10'))]
    alloc = allocate_fifo(rows, Decimal('5'))
    assert alloc == [(rows[0], Decimal('5'))]


def test_allocate_fifo_insufficient():
    rows = [_Row(Decimal('2')), _Row(Decimal('3'))]
    with pytest.raises(InsufficientStockError) as exc:
        allocate_fifo(rows, Decimal('10'))
    assert exc.value.requested == Decimal('10')
    assert exc.value.available == Decimal('5')


def test_allocate_fefo_alias():
    rows = [_Row(Decimal('10'))]
    alloc = allocate_fefo(rows, Decimal('3'))
    assert alloc == [(rows[0], Decimal('3'))]


def test_allocate_fifo_zero_rows_skipped():
    rows = [_Row(Decimal('0')), _Row(Decimal('5'))]
    alloc = allocate_fifo(rows, Decimal('3'))
    assert len(alloc) == 1
    assert alloc[0][1] == Decimal('3')


# ---------- Cycle count math ----------

def test_compute_variance_within_threshold():
    var, pct, recount = compute_variance(Decimal('100'), Decimal('103'))
    assert var == Decimal('3')
    assert recount is False  # 3% < 5%


def test_compute_variance_triggers_recount():
    var, pct, recount = compute_variance(Decimal('100'), Decimal('110'))
    assert var == Decimal('10')
    assert recount is True


def test_compute_variance_zero_system_qty():
    var, pct, recount = compute_variance(Decimal('0'), Decimal('5'))
    assert var == Decimal('5')
    assert pct == Decimal('100')


def test_classify_abc_pareto():
    consumption = {
        1: Decimal('1000'), 2: Decimal('500'),
        3: Decimal('100'), 4: Decimal('50'),
        5: Decimal('20'),  6: Decimal('10'),
        7: Decimal('5'),   8: Decimal('2'),
        9: Decimal('1'),   10: Decimal('1'),
    }
    cls = classify_abc(consumption)
    # Top 20% (2 items) -> A; next 30% (3 items) -> B; rest -> C
    assert cls[1] == 'A'
    assert cls[2] == 'A'
    assert cls[3] == 'B'
    assert cls[10] == 'C'


def test_classify_abc_empty():
    assert classify_abc({}) == {}


# ---------- GRN suggest_bin ----------

def test_suggest_bin_nearest_empty_picks_unused(acme, warehouse, receiving_zone, storage_zone, bin_a, bin_b, fg_product):
    # bin_a has no stock; bin_b has stock — so nearest_empty should prefer bin_a
    inv_models.StockItem.objects.create(
        tenant=acme, product=fg_product, bin=bin_b, qty_on_hand=Decimal('1'),
    )
    grn = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    line = inv_models.GRNLine.objects.create(
        tenant=acme, grn=grn, product=fg_product,
        receiving_zone=storage_zone, expected_qty=Decimal('1'),
    )
    suggested = suggest_bin(line, strategy='nearest_empty')
    assert suggested == bin_a


def test_suggest_bin_directed_returns_none(acme, warehouse, storage_zone, fg_product, bin_a):
    grn = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    line = inv_models.GRNLine.objects.create(
        tenant=acme, grn=grn, product=fg_product,
        receiving_zone=storage_zone, expected_qty=Decimal('1'),
    )
    assert suggest_bin(line, strategy='directed') is None
