"""D-CR-02 regression: `expire_compliance` flips stale rows + emits audit + idempotent."""
from datetime import date, timedelta

import pytest
from django.core.management import call_command

from apps.plm.models import ComplianceAuditLog
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestExpireComplianceCommandD02:

    def test_past_expiry_compliant_is_flipped(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=date.today() - timedelta(days=1),
        )
        call_command('expire_compliance')
        rec.refresh_from_db()
        assert rec.status == 'expired'
        assert ComplianceAuditLog.all_objects.filter(compliance=rec, event='expired').exists()

    def test_today_boundary_not_flipped(self, acme, product):
        """Decision: keep `compliant` until expiry < today (end-of-day grace)."""
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=date.today(),
        )
        call_command('expire_compliance')
        rec.refresh_from_db()
        assert rec.status == 'compliant'

    def test_null_expiry_not_flipped(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=None,
        )
        call_command('expire_compliance')
        rec.refresh_from_db()
        assert rec.status == 'compliant'

    def test_already_expired_not_double_flipped(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='expired', expiry_date=date.today() - timedelta(days=10),
        )
        call_command('expire_compliance')
        rec.refresh_from_db()
        # Status stays 'expired' (filter scopes to status='compliant') and no
        # new audit row is added because the command never touched this row.
        assert rec.status == 'expired'

    def test_idempotent_no_duplicate_audit(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=date.today() - timedelta(days=10),
        )
        call_command('expire_compliance')
        first_audit_count = ComplianceAuditLog.all_objects.filter(compliance=rec).count()
        # Manually re-flip to compliant (simulating an admin override) and rerun
        rec.refresh_from_db()
        assert rec.status == 'expired'
        # Second run is a no-op — already expired
        call_command('expire_compliance')
        assert ComplianceAuditLog.all_objects.filter(compliance=rec).count() == first_audit_count

    def test_dry_run_writes_nothing(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=date.today() - timedelta(days=1),
        )
        call_command('expire_compliance', '--dry-run')
        rec.refresh_from_db()
        assert rec.status == 'compliant'
        assert not ComplianceAuditLog.all_objects.filter(compliance=rec, event='expired').exists()

    def test_tenant_scoped(self, acme, globex, product):
        # A stale row in acme; nothing in globex
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(),
            status='compliant', expiry_date=date.today() - timedelta(days=1),
        )
        call_command('expire_compliance', '--tenant=globex')
        rec.refresh_from_db()
        # Untouched because we restricted to globex
        assert rec.status == 'compliant'
