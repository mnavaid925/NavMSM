"""D-CR-01 regression: ComplianceAuditLog rejects delete + update at the model layer."""
import pytest
from django.core.exceptions import PermissionDenied

from apps.plm.models import ComplianceAuditLog
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestComplianceAuditImmutabilityD01:

    @pytest.fixture
    def audit_entry(self, acme, product):
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(), status='pending',
        )
        # `created` audit row written by signal
        return ComplianceAuditLog.all_objects.filter(compliance=rec).first()

    def test_instance_delete_blocked(self, audit_entry):
        with pytest.raises(PermissionDenied):
            audit_entry.delete()
        assert ComplianceAuditLog.all_objects.filter(pk=audit_entry.pk).exists()

    def test_queryset_delete_blocked(self, audit_entry):
        with pytest.raises(PermissionDenied):
            ComplianceAuditLog.objects.filter(pk=audit_entry.pk).delete()
        assert ComplianceAuditLog.all_objects.filter(pk=audit_entry.pk).exists()

    def test_all_objects_delete_blocked(self, audit_entry):
        with pytest.raises(PermissionDenied):
            ComplianceAuditLog.all_objects.filter(pk=audit_entry.pk).delete()
        assert ComplianceAuditLog.all_objects.filter(pk=audit_entry.pk).exists()

    def test_instance_save_after_pk_blocked(self, audit_entry):
        audit_entry.meta = {'tampered': True}
        with pytest.raises(PermissionDenied):
            audit_entry.save()

    def test_queryset_update_blocked(self, audit_entry):
        with pytest.raises(PermissionDenied):
            ComplianceAuditLog.objects.filter(pk=audit_entry.pk).update(event='renewed')
        # Verify nothing changed
        audit_entry.refresh_from_db()
        assert audit_entry.event != 'renewed'

    def test_parent_cascade_still_works(self, acme, product):
        """Deleting the parent ProductCompliance must still cascade-clean its
        audit_entries — that's record-lifecycle, not tampering."""
        rec = make_compliance(
            tenant=acme, product=product, standard=make_standard(), status='pending',
        )
        audit_pk = ComplianceAuditLog.all_objects.filter(compliance=rec).first().pk
        rec.delete()
        # Cascade should have removed the audit row too
        assert not ComplianceAuditLog.all_objects.filter(pk=audit_pk).exists()
