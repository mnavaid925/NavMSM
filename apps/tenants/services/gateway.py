"""Payment gateway abstraction.

WARNING — security notes for real integrations:
- Never trust a client-submitted amount; derive the charge amount from the Invoice on the server.
- Always verify webhook signatures (Stripe: Stripe-Signature header + webhook secret;
  Razorpay: X-Razorpay-Signature). Reject webhooks that fail verification.
- Store only tokenized references, never raw card numbers.
- Run over HTTPS in production; set CSRF_COOKIE_SECURE + SESSION_COOKIE_SECURE.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass
class ChargeResult:
    ok: bool
    gateway_ref: str
    message: str = ''


class PaymentGateway(Protocol):
    name: str

    def charge(self, *, amount: Decimal, currency: str, description: str,
               customer_ref: str = '', metadata: dict | None = None) -> ChargeResult: ...

    def refund(self, *, gateway_ref: str, amount: Decimal) -> ChargeResult: ...

    def webhook_verify(self, payload: bytes, signature: str) -> bool: ...


class MockGateway:
    """Dev-only gateway: always succeeds. Swap for Stripe/Razorpay in production."""

    name = 'mock'

    def charge(self, *, amount, currency, description, customer_ref='', metadata=None):
        return ChargeResult(
            ok=True,
            gateway_ref=f'mock_{secrets.token_hex(8)}',
            message='Mock charge succeeded.',
        )

    def refund(self, *, gateway_ref, amount):
        return ChargeResult(ok=True, gateway_ref=f'mock_rfnd_{secrets.token_hex(6)}')

    def webhook_verify(self, payload, signature):
        # WARNING: real gateway MUST verify cryptographic signatures.
        return True


def get_gateway() -> PaymentGateway:
    """Resolve the configured gateway. Extend this when wiring Stripe/Razorpay."""
    from django.conf import settings
    name = getattr(settings, 'PAYMENT_GATEWAY', 'mock')
    if name == 'mock':
        return MockGateway()
    raise NotImplementedError(f'Gateway {name!r} not configured.')
