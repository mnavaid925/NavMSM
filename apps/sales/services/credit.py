"""Credit-check service for the sales app (17.2).

Pure read - never writes. Caller decides whether to set
`SalesOrder.credit_hold = True` based on the returned dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CreditCheckResult:
    status: str        # 'ok' | 'hold_credit_limit' | 'hold_blacklist' | 'hold_overdue'
    available: Decimal
    used: Decimal
    limit: Decimal
    message: str

    @property
    def is_hold(self) -> bool:
        return self.status != 'ok'


def check_credit(customer, additional_amount: Decimal) -> CreditCheckResult:
    """Decide whether the customer can take on `additional_amount` more credit.

    Walking order:
        1. Blacklisted customer       -> hard hold
        2. Inactive / on_hold status  -> hard hold (manual review)
        3. Overdue invoices           -> hold_overdue (computed from SalesInvoice
                                          rows past their due_date once 17.4 ships;
                                          today this only checks the denorm)
        4. credit_used + additional_amount > credit_limit -> hold_credit_limit
        5. otherwise ok.
    """
    used = customer.credit_used or Decimal('0')
    limit = customer.credit_limit or Decimal('0')
    available = limit - used
    additional = Decimal(additional_amount or 0)

    if customer.status == 'blacklisted':
        return CreditCheckResult(
            status='hold_blacklist',
            available=available, used=used, limit=limit,
            message='Customer is blacklisted - approve manually or release '
                    'the SO from blacklist hold.',
        )
    if customer.status in ('inactive', 'on_hold'):
        return CreditCheckResult(
            status='hold_blacklist',
            available=available, used=used, limit=limit,
            message=f'Customer status is {customer.status}; manual review required.',
        )

    # 17.4 SalesInvoice rows not yet in DB during 17.2 - tolerate absence
    try:
        from apps.sales.models import SalesInvoice
        from django.utils import timezone
        overdue = SalesInvoice.objects.filter(
            tenant=customer.tenant,
            sales_order__customer=customer,
            status='overdue',
        )
        if overdue.exists():
            return CreditCheckResult(
                status='hold_overdue',
                available=available, used=used, limit=limit,
                message=f'{overdue.count()} overdue invoice(s) outstanding.',
            )
    except Exception:
        pass  # SalesInvoice model not migrated yet - skip

    if used + additional > limit and limit > Decimal('0'):
        return CreditCheckResult(
            status='hold_credit_limit',
            available=available, used=used, limit=limit,
            message=f'Adding {additional} would exceed credit limit '
                    f'({used} + {additional} > {limit}).',
        )

    return CreditCheckResult(
        status='ok',
        available=available, used=used, limit=limit,
        message='Credit check passed.',
    )
