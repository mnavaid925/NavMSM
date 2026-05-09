"""Public verifier for the TenantAuditLog SHA-256 hash chain.

Wrapper around `apps.core.services.audit_chain.verify_chain` keyed to the
TenantAuditLog model. Use it from a management command, tests, or admin views
to detect tampering with the tenant audit log.
"""
from apps.core.services.audit_chain import verify_chain

from apps.tenants.models import TenantAuditLog


def verify_tenant_audit_chain(tenant) -> dict:
    """Verify the entire TenantAuditLog chain for `tenant`.

    Returns a dict with `ok: bool`, `rows_checked: int`, and a `broken: list`
    of dicts naming the row pk + reason + expected/actual digest. See the
    parent service for the full schema.
    """
    return verify_chain(TenantAuditLog, tenant=tenant, ordering_field='timestamp')
