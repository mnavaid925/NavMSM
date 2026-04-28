"""Form-layer tests — Lesson L-01 manual unique_together + file allowlist."""
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.mes.forms import (
    AndonAlertForm, ProductionReportForm, ShopFloorOperatorForm,
    WorkInstructionForm, WorkInstructionVersionForm,
)


# ============================================================================
# Lesson L-01 — manual (tenant, …) unique_together check on forms that
# exclude tenant from Meta.fields.
# ============================================================================

@pytest.mark.django_db
class TestShopFloorOperatorFormUniqueness:
    def test_duplicate_badge_returns_form_error_not_500(
        self, acme, acme_staff, work_center, operator,
    ):
        from apps.accounts.models import User
        # Make a fresh user that has no operator profile yet.
        u2 = User.objects.create_user(username='u2', password='pw', tenant=acme)
        form = ShopFloorOperatorForm(
            data={'user': u2.pk, 'badge_number': 'B0001',  # already used
                  'default_work_center': work_center.pk, 'is_active': True, 'notes': ''},
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'badge_number' in form.errors

    def test_duplicate_user_returns_form_error(
        self, acme, acme_staff, work_center, operator,
    ):
        # acme_staff already has an operator (the `operator` fixture).
        form = ShopFloorOperatorForm(
            data={'user': acme_staff.pk, 'badge_number': 'B-NEW',
                  'default_work_center': work_center.pk, 'is_active': True, 'notes': ''},
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'user' in form.errors

    def test_edit_self_does_not_collide(self, acme, operator):
        form = ShopFloorOperatorForm(
            data={'user': operator.user.pk, 'badge_number': operator.badge_number,
                  'default_work_center': operator.default_work_center.pk,
                  'is_active': True, 'notes': ''},
            instance=operator, tenant=acme,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestProductionReportForm:
    def test_all_zero_rejected(self):
        form = ProductionReportForm(data={
            'good_qty': '0', 'scrap_qty': '0', 'rework_qty': '0',
            'scrap_reason': '', 'cycle_time_minutes': '', 'notes': '',
        })
        assert not form.is_valid()
        # Form-level error
        assert form.non_field_errors()

    def test_scrap_without_reason_rejected(self):
        form = ProductionReportForm(data={
            'good_qty': '0', 'scrap_qty': '3', 'rework_qty': '0',
            'scrap_reason': '', 'cycle_time_minutes': '', 'notes': '',
        })
        assert not form.is_valid()
        assert 'scrap_reason' in form.errors

    def test_good_only_passes(self):
        form = ProductionReportForm(data={
            'good_qty': '5', 'scrap_qty': '0', 'rework_qty': '0',
            'scrap_reason': '', 'cycle_time_minutes': '', 'notes': '',
        })
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestAndonAlertForm:
    def test_blank_title_with_other_type_rejected(self, acme, work_center):
        form = AndonAlertForm(
            data={
                'alert_type': 'other', 'severity': 'medium',
                'title': '   ',  # whitespace-only
                'message': 'foo', 'work_center': work_center.pk,
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'title' in form.errors

    def test_quality_with_blank_title_uses_field_required_error(self, acme, work_center):
        # Title is required at the model level too, so the basic ModelForm
        # validation also rejects.
        form = AndonAlertForm(
            data={
                'alert_type': 'quality', 'severity': 'medium',
                'title': '', 'message': 'foo', 'work_center': work_center.pk,
            },
            tenant=acme,
        )
        assert not form.is_valid()
        assert 'title' in form.errors


@pytest.mark.django_db
class TestWorkInstructionForm:
    def test_blank_links_rejected(self, acme):
        form = WorkInstructionForm(
            data={'title': 'X', 'doc_type': 'sop',
                  'routing_operation': '', 'product': ''},
            tenant=acme,
        )
        assert not form.is_valid()

    def test_with_routing_op_passes(self, acme, routing):
        rop = routing.operations.first()
        form = WorkInstructionForm(
            data={'title': 'X', 'doc_type': 'sop',
                  'routing_operation': rop.pk, 'product': ''},
            tenant=acme,
        )
        assert form.is_valid(), form.errors

    def test_with_product_only_passes(self, acme, product):
        form = WorkInstructionForm(
            data={'title': 'X', 'doc_type': 'sop',
                  'routing_operation': '', 'product': product.pk},
            tenant=acme,
        )
        assert form.is_valid(), form.errors


# ============================================================================
# File-allowlist tests on WorkInstructionVersionForm
# ============================================================================

@pytest.mark.django_db
class TestVersionFileAllowlist:
    def test_pdf_attachment_accepted(self, acme, draft_instruction):
        f = SimpleUploadedFile('manual.pdf', b'%PDF-1.4 sample', content_type='application/pdf')
        form = WorkInstructionVersionForm(
            data={'version': '1.0', 'content': 'x', 'video_url': '', 'change_notes': ''},
            files={'attachment': f},
            tenant=acme, instruction=draft_instruction,
        )
        assert form.is_valid(), form.errors

    def test_exe_rejected(self, acme, draft_instruction):
        f = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
        form = WorkInstructionVersionForm(
            data={'version': '1.0', 'content': 'x', 'video_url': '', 'change_notes': ''},
            files={'attachment': f},
            tenant=acme, instruction=draft_instruction,
        )
        assert not form.is_valid()
        assert 'attachment' in form.errors

    def test_oversized_rejected(self, acme, draft_instruction):
        # Build a fake file that reports >25 MB by overriding .size.
        big = SimpleUploadedFile('big.pdf', b'%PDF-1.4', content_type='application/pdf')
        big.size = 26 * 1024 * 1024  # 26 MB
        form = WorkInstructionVersionForm(
            data={'version': '1.0', 'content': 'x', 'video_url': '', 'change_notes': ''},
            files={'attachment': big},
            tenant=acme, instruction=draft_instruction,
        )
        assert not form.is_valid()
        assert 'attachment' in form.errors

    def test_duplicate_version_rejected_per_instruction(
        self, acme, draft_instruction, draft_instruction_version,
    ):
        form = WorkInstructionVersionForm(
            data={'version': '1.0', 'content': 'x', 'video_url': '', 'change_notes': ''},
            tenant=acme, instruction=draft_instruction,
        )
        assert not form.is_valid()
        assert 'version' in form.errors
