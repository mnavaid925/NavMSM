"""Price-list resolution service for the sales app.

Pure function. Walks (customer.default_price_list -> tenant-default
PriceList -> Product.list_price) and respects min_qty tier breaks plus
PriceListItem.discount_pct.

Used by SalesOrderLine in 17.2 to auto-fill `unit_price` when the user
hasn't overridden it. Never writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.utils import timezone


@dataclass(frozen=True)
class PriceResolution:
    unit_price: Decimal
    discount_pct: Decimal
    source: str           # 'customer_pricelist' | 'tenant_default_pricelist' | 'product_list_price'
    price_list_id: Optional[int]
    price_list_item_id: Optional[int]


def _walk_price_list(price_list, product, qty: Decimal, on_date):
    """Return the most-specific PriceListItem matching (product, qty, date)."""
    from django.db.models import Q
    if price_list is None:
        return None
    qs = price_list.items.filter(product=product, min_qty__lte=qty)
    qs = qs.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=on_date))
    qs = qs.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))
    return qs.order_by('-min_qty').first()


def resolve_price(
    customer,
    product,
    qty: Decimal,
    on_date=None,
) -> PriceResolution:
    """Resolve the effective unit price + discount for (customer, product, qty).

    Args:
        customer: sales.Customer (may be None for ad-hoc / one-time sale)
        product:  plm.Product
        qty:      Decimal (always positive)
        on_date:  datetime.date | None - defaults to today

    Walking order:
        1. customer.default_price_list (if customer + price list set)
        2. tenant default PriceList (PriceList.is_default=True, is_active)
        3. fall back to Product.list_price (if the PLM Product model has
           that attribute) or Decimal('0')

    Returns a frozen `PriceResolution` dataclass - never mutates state.
    """
    on_date = on_date or timezone.now().date()
    qty = Decimal(qty)

    # Tier 1 - customer-specific price list
    customer_pl = (
        getattr(customer, 'default_price_list', None) if customer else None
    )
    item = _walk_price_list(customer_pl, product, qty, on_date)
    if item is not None:
        return PriceResolution(
            unit_price=item.unit_price,
            discount_pct=item.discount_pct or Decimal('0'),
            source='customer_pricelist',
            price_list_id=customer_pl.id,
            price_list_item_id=item.id,
        )

    # Tier 2 - tenant default price list
    from apps.sales.models import PriceList  # local import to avoid app-loading cycle
    tenant = getattr(customer, 'tenant', None) or getattr(product, 'tenant', None)
    if tenant is not None:
        default_pl = (
            PriceList.all_objects
            .filter(tenant=tenant, is_default=True, is_active=True)
            .first()
        )
        item = _walk_price_list(default_pl, product, qty, on_date)
        if item is not None:
            return PriceResolution(
                unit_price=item.unit_price,
                discount_pct=item.discount_pct or Decimal('0'),
                source='tenant_default_pricelist',
                price_list_id=default_pl.id,
                price_list_item_id=item.id,
            )

    # Tier 3 - product.list_price fallback (or zero)
    list_price = getattr(product, 'list_price', None) or Decimal('0')
    return PriceResolution(
        unit_price=Decimal(list_price),
        discount_pct=Decimal('0'),
        source='product_list_price',
        price_list_id=None,
        price_list_item_id=None,
    )
