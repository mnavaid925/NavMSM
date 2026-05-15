"""Django admin registration for Module 19 - Document & Knowledge Management.

Note: DocumentSignature is FDA 21 CFR Part 11 immutable - admin
readonly_fields = '__all__' enforces no in-place edits.
"""
from django.contrib import admin

from .models import (
    ApprovalAction,
    ApprovalStage,
    ApprovalWorkflow,
    AssignmentTarget,
    Document,
    DocumentApprovalRequest,
    DocumentArchive,
    DocumentAccessRule,
    DocumentAssignment,
    DocumentCategory,
    DocumentSignature,
    DocumentTemplate,
    DocumentVersion,
    LegalHold,
    MediaAttachment,
    ReadAcknowledgment,
    RetentionPolicy,
    TemplateField,
)


# ----- 19.1  Controlled Document Repository -----

@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'parent', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'code')


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = ('version', 'status', 'checked_out_by', 'released_at')
    readonly_fields = ('checked_out_by', 'released_at')


class DocumentAccessRuleInline(admin.TabularInline):
    model = DocumentAccessRule
    extra = 0
    autocomplete_fields = ('user', 'department', 'position')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'title', 'doc_type', 'status', 'is_locked',
        'effective_date', 'expiry_date', 'tenant',
    )
    list_filter = ('doc_type', 'status', 'is_locked', 'tenant')
    search_fields = ('code', 'title', 'summary', 'keywords')
    inlines = [DocumentVersionInline, DocumentAccessRuleInline]
    autocomplete_fields = ('category', 'owner', 'current_version', 'retention_policy')
    readonly_fields = ('code', 'retention_until')


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'document', 'version', 'status', 'checked_out_by', 'released_at', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('document__code', 'document__title', 'version')
    readonly_fields = ('checked_out_at', 'released_at')


@admin.register(DocumentAccessRule)
class DocumentAccessRuleAdmin(admin.ModelAdmin):
    list_display = ('document', 'role', 'user', 'department', 'position', 'tenant')
    list_filter = ('role', 'tenant')
    search_fields = ('document__code', 'document__title')


# ----- 19.2  SOP & Work Instruction Authoring -----

class TemplateFieldInline(admin.TabularInline):
    model = TemplateField
    extra = 0


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'applies_to_doc_type', 'is_active', 'tenant')
    list_filter = ('applies_to_doc_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')
    inlines = [TemplateFieldInline]
    readonly_fields = ('code',)


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    list_display = ('template', 'field_name', 'label', 'field_type', 'is_required', 'order', 'tenant')
    list_filter = ('field_type', 'is_required', 'tenant')
    search_fields = ('field_name', 'label', 'template__name')


@admin.register(MediaAttachment)
class MediaAttachmentAdmin(admin.ModelAdmin):
    list_display = ('document_version', 'media_type', 'caption', 'order', 'tenant')
    list_filter = ('media_type', 'tenant')
    search_fields = ('caption', 'document_version__document__code')


# ----- 19.3  Document Approval Workflows -----

class ApprovalStageInline(admin.TabularInline):
    model = ApprovalStage
    extra = 0


@admin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(admin.ModelAdmin):
    list_display = ('name', 'applies_to_doc_type', 'is_active', 'tenant')
    list_filter = ('applies_to_doc_type', 'is_active', 'tenant')
    search_fields = ('name', 'description')
    inlines = [ApprovalStageInline]


@admin.register(ApprovalStage)
class ApprovalStageAdmin(admin.ModelAdmin):
    list_display = (
        'workflow', 'stage_no', 'name', 'approver_role',
        'min_approvals', 'requires_signature', 'tenant',
    )
    list_filter = ('approver_role', 'tenant')
    search_fields = ('workflow__name', 'name')


class ApprovalActionInline(admin.TabularInline):
    model = ApprovalAction
    extra = 0
    readonly_fields = ('stage_no', 'decision', 'decided_by', 'decided_at', 'signature')


@admin.register(DocumentApprovalRequest)
class DocumentApprovalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'document', 'workflow', 'current_stage_no',
        'status', 'requested_at', 'decided_at', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'document__code', 'document__title')
    inlines = [ApprovalActionInline]
    readonly_fields = ('code', 'requested_at', 'decided_at')


@admin.register(ApprovalAction)
class ApprovalActionAdmin(admin.ModelAdmin):
    list_display = ('request', 'stage_no', 'decision', 'decided_by', 'decided_at', 'tenant')
    list_filter = ('decision', 'tenant')
    search_fields = ('request__code',)
    readonly_fields = ('decided_at',)


@admin.register(DocumentSignature)
class DocumentSignatureAdmin(admin.ModelAdmin):
    """FDA 21 CFR Part 11 - immutable. Every field is read-only in admin."""

    list_display = ('document', 'signer', 'meaning', 'typed_name', 'signed_at', 'tenant')
    list_filter = ('meaning', 'tenant')
    search_fields = ('document__code', 'typed_name', 'signer__username')
    readonly_fields = (
        'document', 'signer', 'signed_at', 'meaning',
        'typed_name', 'ip_address', 'user_agent', 'tenant',
        'created_at', 'updated_at',
    )

    def has_change_permission(self, request, obj=None):
        # Immutable - allow add but not edit.
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)


# ----- 19.4  Training Document Assignment -----

class AssignmentTargetInline(admin.TabularInline):
    model = AssignmentTarget
    extra = 0
    autocomplete_fields = ('department', 'position', 'employee', 'user')


@admin.register(DocumentAssignment)
class DocumentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'document', 'status', 'due_date', 'assigned_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'document__code', 'document__title')
    inlines = [AssignmentTargetInline]
    readonly_fields = ('code', 'assigned_at')


@admin.register(AssignmentTarget)
class AssignmentTargetAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'role', 'department', 'position', 'employee', 'user', 'tenant')
    list_filter = ('role', 'tenant')
    search_fields = ('assignment__code',)


@admin.register(ReadAcknowledgment)
class ReadAcknowledgmentAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'assignment', 'document_version', 'acknowledger',
        'acknowledged_at', 'tenant',
    )
    list_filter = ('tenant',)
    search_fields = ('code', 'assignment__code', 'acknowledger__username', 'typed_name')
    readonly_fields = ('code', 'acknowledged_at', 'ip_address', 'user_agent')


# ----- 19.5  Archive & Retention Policy -----

@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'applies_to_doc_type', 'retention_years',
        'archive_action', 'is_active', 'tenant',
    )
    list_filter = ('archive_action', 'applies_to_doc_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')
    readonly_fields = ('code',)


@admin.register(DocumentArchive)
class DocumentArchiveAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'document', 'status', 'archived_at',
        'retention_until', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'document__code', 'document__title')
    readonly_fields = ('code', 'archived_at', 'restored_at')


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'status', 'requested_at',
        'released_at', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'name', 'reason')
    filter_horizontal = ('documents',)
    readonly_fields = ('code', 'requested_at', 'released_at')
