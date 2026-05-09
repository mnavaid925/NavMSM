"""Form validation — D-CR-04 (date inversion), D-CR-05 (unique trap), file allowlist."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.plm.forms import ProductComplianceForm
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestComplianceFormDateValidationD04:
    def test_expiry_before_issued_rejected(self, acme, product):
        std = make_standard()
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'compliant',
                'certification_number': 'X', 'issuing_body': 'TUV',
                'issued_date': '2025-12-31', 'expiry_date': '2024-01-01',
                'notes': '',
            }, tenant=acme,
        )
        assert not f.is_valid()
        assert 'expiry_date' in f.errors
        assert 'on or after' in str(f.errors['expiry_date']).lower()

    @pytest.mark.parametrize('issued,expiry', [
        ('2025-01-01', '2026-01-01'),  # future expiry
        ('2025-01-01', '2025-01-01'),  # same day OK
    ])
    def test_valid_date_pairs(self, acme, product, issued, expiry):
        std = make_standard()
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'compliant',
                'certification_number': 'X', 'issuing_body': 'TUV',
                'issued_date': issued, 'expiry_date': expiry, 'notes': '',
            }, tenant=acme,
        )
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestComplianceFormUniqueTrapD05:
    """Duplicate (tenant, product, standard) must surface a clean form error,
    not propagate an IntegrityError to the view."""

    def test_duplicate_blocked_at_form_layer(self, acme, product):
        std = make_standard()
        make_compliance(tenant=acme, product=product, standard=std)
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'pending',
                'certification_number': 'DUP', 'issuing_body': 'TUV',
                'notes': '',
            }, tenant=acme,
        )
        assert not f.is_valid()
        assert 'already exists' in str(f.errors).lower()

    def test_edit_existing_does_not_self_collide(self, acme, product):
        """Editing the same record must not flag it as a duplicate of itself."""
        std = make_standard()
        rec = make_compliance(tenant=acme, product=product, standard=std)
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'pending',
                'certification_number': rec.certification_number,
                'issuing_body': rec.issuing_body, 'notes': 'edited',
            }, tenant=acme, instance=rec,
        )
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestComplianceFormFileValidation:
    @pytest.mark.parametrize('ext,expected_valid', [
        ('pdf', True), ('png', True), ('jpg', True), ('jpeg', True), ('zip', True),
        ('svg', False), ('exe', False), ('php', False), ('docx', False),
    ])
    def test_extension_allowlist(self, acme, product, ext, expected_valid):
        std = make_standard()
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'pending',
                'certification_number': 'X', 'issuing_body': 'TUV', 'notes': '',
            },
            files={'certificate_file': SimpleUploadedFile(f'cert.{ext}', b'\x00' * 100)},
            tenant=acme,
        )
        assert f.is_valid() == expected_valid

    def test_size_cap_25mb(self, acme, product):
        std = make_standard()
        big = b'\x00' * (25 * 1024 * 1024 + 1)
        f = ProductComplianceForm(
            data={
                'product': product.pk, 'standard': std.pk, 'status': 'pending',
                'certification_number': 'X', 'issuing_body': 'TUV', 'notes': '',
            },
            files={'certificate_file': SimpleUploadedFile('big.pdf', big)},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'too large' in str(f.errors).lower()
