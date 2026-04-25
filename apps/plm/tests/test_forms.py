"""Form-level validation. Includes regression guards for D-01 and D-02."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.plm.forms import (
    CADDocumentVersionForm, CAD_ALLOWED_EXTS, ECOImpactedItemForm,
)


@pytest.mark.django_db
class TestECOImpactedItemFormD01:
    """D-01 regression: revision must belong to selected product."""

    def test_rejects_cross_product_revision(self, acme, product, other_revision):
        f = ECOImpactedItemForm(
            data={
                'product': product.pk,
                'before_revision': other_revision.pk,
                'after_revision': '',
                'change_summary': 'x',
            },
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'before_revision' in f.errors

    def test_accepts_matching_product_revision(self, acme, product, revision):
        f = ECOImpactedItemForm(
            data={
                'product': product.pk,
                'before_revision': revision.pk,
                'after_revision': '',
                'change_summary': 'x',
            },
            tenant=acme,
        )
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestCADUploadAllowlistD02:
    """D-02 regression: .svg must NOT be in CAD_ALLOWED_EXTS."""

    def test_svg_not_in_allowlist(self):
        assert '.svg' not in CAD_ALLOWED_EXTS

    @pytest.mark.parametrize('ext,expected_valid', [
        ('pdf', True), ('dwg', True), ('step', True), ('png', True),
        ('exe', False), ('bat', False), ('php', False), ('svg', False),
    ])
    def test_extension_allowlist(self, ext, expected_valid):
        f = CADDocumentVersionForm(
            data={'version': '1.0', 'change_notes': '', 'status': 'draft'},
            files={'file': SimpleUploadedFile(f'test.{ext}', b'\x00' * 100)},
        )
        assert f.is_valid() == expected_valid

    def test_size_cap_25mb(self):
        big = b'\x00' * (25 * 1024 * 1024 + 1)
        f = CADDocumentVersionForm(
            data={'version': '1.0', 'change_notes': '', 'status': 'draft'},
            files={'file': SimpleUploadedFile('big.pdf', big)},
        )
        assert not f.is_valid()
        assert 'too large' in str(f.errors).lower()
