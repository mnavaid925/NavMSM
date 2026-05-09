"""Public verifier for the ComplianceAuditLog SHA-256 hash chain (D-GAP-05)."""
from apps.core.services.audit_chain import verify_chain

from apps.plm.models import ComplianceAuditLog


def verify_compliance_audit_chain(tenant) -> dict:
    """Verify the entire ComplianceAuditLog chain for `tenant`.

    Returns a dict with `ok: bool`, `rows_checked: int`, and `broken: list`.
    See [apps/core/services/audit_chain.py](../../core/services/audit_chain.py)
    for the full schema.
    """
    return verify_chain(
        ComplianceAuditLog, tenant=tenant, ordering_field='performed_at',
    )
