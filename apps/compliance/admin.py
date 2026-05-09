"""Admin registrations for Module 13 — Compliance & Regulatory Management."""
from django.contrib import admin

from . import models


@admin.register(models.IncidentType)
class IncidentTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'is_active', 'tenant']
    list_filter = ['category', 'is_active', 'tenant']
    search_fields = ['code', 'name']


@admin.register(models.IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = ['incident_number', 'title', 'severity', 'status', 'occurred_at', 'reporter']
    list_filter = ['status', 'severity', 'tenant']
    search_fields = ['incident_number', 'title', 'description']
    raw_id_fields = ['source_andon']


@admin.register(models.RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ['assessment_number', 'title', 'likelihood', 'severity', 'risk_score', 'status']
    list_filter = ['status', 'tenant']
    search_fields = ['assessment_number', 'title']


@admin.register(models.SafetyAuditChecklist)
class SafetyAuditChecklistAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant']
    search_fields = ['code', 'name']


@admin.register(models.SafetyAudit)
class SafetyAuditAdmin(admin.ModelAdmin):
    list_display = ['audit_number', 'checklist', 'scheduled_for', 'status', 'pass_count', 'fail_count']
    list_filter = ['status', 'tenant']


@admin.register(models.SafetyAuditItem)
class SafetyAuditItemAdmin(admin.ModelAdmin):
    list_display = ['audit', 'item_order', 'result']


@admin.register(models.ComplianceDocument)
class ComplianceDocumentAdmin(admin.ModelAdmin):
    list_display = ['doc_number', 'title', 'doc_type', 'version', 'status', 'effective_from']
    list_filter = ['doc_type', 'status', 'tenant']
    search_fields = ['doc_number', 'title']


@admin.register(models.DocumentApproval)
class DocumentApprovalAdmin(admin.ModelAdmin):
    list_display = ['document', 'action', 'actor', 'acted_at']
    list_filter = ['action', 'tenant']


@admin.register(models.ElectronicSignature)
class ElectronicSignatureAdmin(admin.ModelAdmin):
    list_display = ['document', 'signer', 'reason', 'signed_at']
    list_filter = ['reason', 'tenant']
    readonly_fields = ['document', 'signer', 'typed_name', 'role', 'reason', 'signed_at', 'ip_address']


@admin.register(models.AuditLogArchive)
class AuditLogArchiveAdmin(admin.ModelAdmin):
    list_display = ['archive_number', 'period_start', 'period_end', 'record_count', 'generated_at']
    list_filter = ['tenant']


@admin.register(models.WasteCategory)
class WasteCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'hazard_class', 'epa_code', 'is_active', 'tenant']
    list_filter = ['hazard_class', 'is_active', 'tenant']
    search_fields = ['code', 'name', 'epa_code']


@admin.register(models.WasteManifest)
class WasteManifestAdmin(admin.ModelAdmin):
    list_display = ['manifest_number', 'category', 'manifest_date', 'status', 'total_quantity_kg']
    list_filter = ['status', 'tenant']


@admin.register(models.WasteDisposalRecord)
class WasteDisposalRecordAdmin(admin.ModelAdmin):
    list_display = ['manifest', 'line_number', 'description', 'quantity_kg', 'disposal_method']


@admin.register(models.ProductRecall)
class ProductRecallAdmin(admin.ModelAdmin):
    list_display = ['recall_number', 'product', 'severity', 'status', 'initiated_at']
    list_filter = ['severity', 'status', 'tenant']
    search_fields = ['recall_number', 'title']


@admin.register(models.RecallAffectedLot)
class RecallAffectedLotAdmin(admin.ModelAdmin):
    list_display = ['recall', 'lot', 'affected_quantity', 'recovered_quantity']


@admin.register(models.RecallNotice)
class RecallNoticeAdmin(admin.ModelAdmin):
    list_display = ['notice_number', 'recall', 'channel', 'status', 'sent_at']
    list_filter = ['channel', 'status', 'tenant']
