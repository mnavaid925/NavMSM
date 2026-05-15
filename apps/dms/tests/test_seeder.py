"""Seeder + cron command tests."""
import pytest
from django.core.management import call_command

from apps.dms.models import (
    Document, DocumentArchive, DocumentTemplate, LegalHold, RetentionPolicy,
)


@pytest.fixture
def seeded_tenant(db):
    """Create a tenant + admin user the way seed_data does."""
    from apps.accounts.models import User
    from apps.core.models import Tenant, set_current_tenant
    t = Tenant.objects.create(name='Seed Test', slug='seed-test')
    set_current_tenant(t)
    User.objects.create_user(
        username='admin_seed-test', password='Welcome@123',
        email='a@example.com', tenant=t, is_tenant_admin=True, role='tenant_admin',
    )
    yield t
    set_current_tenant(None)


@pytest.mark.django_db
class TestSeedDms:
    def test_seed_creates_expected_counts(self, seeded_tenant):
        call_command('seed_dms', tenant='seed-test')
        assert Document.objects.filter(tenant=seeded_tenant).count() == 5
        assert DocumentTemplate.objects.filter(tenant=seeded_tenant).count() == 2
        assert RetentionPolicy.objects.filter(tenant=seeded_tenant).count() == 2
        assert LegalHold.objects.filter(tenant=seeded_tenant, status='active').count() == 1
        assert DocumentArchive.objects.filter(tenant=seeded_tenant).count() == 1

    def test_seed_idempotent(self, seeded_tenant):
        call_command('seed_dms', tenant='seed-test')
        c1 = Document.objects.filter(tenant=seeded_tenant).count()
        call_command('seed_dms', tenant='seed-test')
        c2 = Document.objects.filter(tenant=seeded_tenant).count()
        assert c1 == c2

    def test_seed_flush_then_seed(self, seeded_tenant):
        call_command('seed_dms', tenant='seed-test')
        call_command('seed_dms', tenant='seed-test', flush=True)
        assert Document.objects.filter(tenant=seeded_tenant).count() == 5


@pytest.mark.django_db
class TestCronArchiveDue:
    def test_archive_due_dry_run_does_nothing(self, tenant_a):
        from datetime import date
        from apps.dms.models import Document
        d = Document.objects.create(tenant=tenant_a, title='Old')
        Document.all_objects.filter(pk=d.pk).update(
            retention_until=date(2020, 1, 1), status='effective',
        )
        call_command('archive_due_documents', dry_run=True)
        d.refresh_from_db()
        assert d.status == 'effective'

    def test_archive_due_flips_status(self, tenant_a):
        from datetime import date
        d = Document.objects.create(tenant=tenant_a, title='Old')
        Document.all_objects.filter(pk=d.pk).update(
            retention_until=date(2020, 1, 1), status='effective',
        )
        call_command('archive_due_documents')
        d.refresh_from_db()
        assert d.status == 'archived'
        assert DocumentArchive.objects.filter(document=d).exists()

    def test_archive_due_skips_locked(self, tenant_a):
        from datetime import date
        d = Document.objects.create(tenant=tenant_a, title='Old Locked')
        Document.all_objects.filter(pk=d.pk).update(
            retention_until=date(2020, 1, 1),
            status='effective', is_locked=True,
        )
        call_command('archive_due_documents')
        d.refresh_from_db()
        assert d.status == 'effective'


@pytest.mark.django_db
class TestCronExpireAssignments:
    def test_expire_assignments_reports(self, tenant_a):
        from datetime import date
        from apps.dms.models import Document, DocumentAssignment
        d = Document.objects.create(tenant=tenant_a, title='X')
        DocumentAssignment.objects.create(
            tenant=tenant_a, document=d, status='active',
            due_date=date(2020, 1, 1),
        )
        # Read-only command - just verify it runs without error.
        call_command('expire_assignments')
