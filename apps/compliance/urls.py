"""URL patterns for Module 13 - Compliance & Regulatory Management.

Mirrors the cost / utility module conventions:
    <resource>_list / _create / _detail / _edit / _delete plus per-workflow
    POST endpoints (submit / approve / sign / start / complete / cancel /
    close / supersede / send / acknowledge).
"""
from django.urls import path

from . import views

app_name = 'compliance'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 13.1 EHS — Incident Types
    path('incident-types/', views.IncidentTypeListView.as_view(), name='incident_type_list'),
    path('incident-types/new/', views.IncidentTypeCreateView.as_view(), name='incident_type_create'),
    path('incident-types/<int:pk>/edit/', views.IncidentTypeEditView.as_view(), name='incident_type_edit'),
    path('incident-types/<int:pk>/delete/', views.IncidentTypeDeleteView.as_view(), name='incident_type_delete'),

    # 13.1 EHS — Incidents
    path('incidents/', views.IncidentListView.as_view(), name='incident_list'),
    path('incidents/new/', views.IncidentCreateView.as_view(), name='incident_create'),
    path('incidents/<int:pk>/', views.IncidentDetailView.as_view(), name='incident_detail'),
    path('incidents/<int:pk>/edit/', views.IncidentEditView.as_view(), name='incident_edit'),
    path('incidents/<int:pk>/investigate/', views.IncidentInvestigateView.as_view(), name='incident_investigate'),
    path('incidents/<int:pk>/action/', views.IncidentActionView.as_view(), name='incident_action'),
    path('incidents/<int:pk>/close/', views.IncidentCloseView.as_view(), name='incident_close'),
    path('incidents/<int:pk>/cancel/', views.IncidentCancelView.as_view(), name='incident_cancel'),
    path('incidents/<int:pk>/delete/', views.IncidentDeleteView.as_view(), name='incident_delete'),

    # 13.1 EHS — Risk Assessments
    path('risks/', views.RiskListView.as_view(), name='risk_list'),
    path('risks/new/', views.RiskCreateView.as_view(), name='risk_create'),
    path('risks/<int:pk>/', views.RiskDetailView.as_view(), name='risk_detail'),
    path('risks/<int:pk>/edit/', views.RiskEditView.as_view(), name='risk_edit'),
    path('risks/<int:pk>/submit/', views.RiskSubmitView.as_view(), name='risk_submit'),
    path('risks/<int:pk>/approve/', views.RiskApproveView.as_view(), name='risk_approve'),
    path('risks/<int:pk>/archive/', views.RiskArchiveView.as_view(), name='risk_archive'),
    path('risks/<int:pk>/delete/', views.RiskDeleteView.as_view(), name='risk_delete'),

    # 13.1 EHS — Safety Audit Checklists
    path('checklists/', views.ChecklistListView.as_view(), name='checklist_list'),
    path('checklists/new/', views.ChecklistCreateView.as_view(), name='checklist_create'),
    path('checklists/<int:pk>/', views.ChecklistDetailView.as_view(), name='checklist_detail'),
    path('checklists/<int:pk>/edit/', views.ChecklistEditView.as_view(), name='checklist_edit'),
    path('checklists/<int:pk>/delete/', views.ChecklistDeleteView.as_view(), name='checklist_delete'),

    # 13.1 EHS — Safety Audits
    path('audits/', views.AuditListView.as_view(), name='audit_list'),
    path('audits/new/', views.AuditCreateView.as_view(), name='audit_create'),
    path('audits/<int:pk>/', views.AuditDetailView.as_view(), name='audit_detail'),
    path('audits/<int:pk>/start/', views.AuditStartView.as_view(), name='audit_start'),
    path('audits/<int:pk>/record/', views.AuditRecordItemView.as_view(), name='audit_record'),
    path('audits/<int:pk>/complete/', views.AuditCompleteView.as_view(), name='audit_complete'),
    path('audits/<int:pk>/cancel/', views.AuditCancelView.as_view(), name='audit_cancel'),
    path('audits/<int:pk>/delete/', views.AuditDeleteView.as_view(), name='audit_delete'),

    # 13.2 Documents
    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('documents/new/', views.DocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('documents/<int:pk>/edit/', views.DocumentEditView.as_view(), name='document_edit'),
    path('documents/<int:pk>/submit/', views.DocumentSubmitView.as_view(), name='document_submit'),
    path('documents/<int:pk>/approve/', views.DocumentApproveView.as_view(), name='document_approve'),
    path('documents/<int:pk>/reject/', views.DocumentRejectView.as_view(), name='document_reject'),
    path('documents/<int:pk>/publish/', views.DocumentPublishView.as_view(), name='document_publish'),
    path('documents/<int:pk>/sign/', views.DocumentSignView.as_view(), name='document_sign'),
    path('documents/<int:pk>/supersede/', views.DocumentSupersedeView.as_view(), name='document_supersede'),
    path('documents/<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),

    # 13.3 Audit Trail
    path('audit-trail/', views.AuditTrailListView.as_view(), name='audit_trail_list'),
    path('audit-trail/archives/', views.ArchiveListView.as_view(), name='archive_list'),
    path('audit-trail/archives/generate/', views.ArchiveGenerateView.as_view(), name='archive_generate'),
    path('audit-trail/archives/<int:pk>/', views.ArchiveDetailView.as_view(), name='archive_detail'),

    # 13.4 Waste — Categories
    path('waste-categories/', views.WasteCategoryListView.as_view(), name='waste_category_list'),
    path('waste-categories/new/', views.WasteCategoryCreateView.as_view(), name='waste_category_create'),
    path('waste-categories/<int:pk>/edit/', views.WasteCategoryEditView.as_view(), name='waste_category_edit'),
    path('waste-categories/<int:pk>/delete/', views.WasteCategoryDeleteView.as_view(), name='waste_category_delete'),

    # 13.4 Waste — Manifests
    path('waste-manifests/', views.ManifestListView.as_view(), name='manifest_list'),
    path('waste-manifests/new/', views.ManifestCreateView.as_view(), name='manifest_create'),
    path('waste-manifests/<int:pk>/', views.ManifestDetailView.as_view(), name='manifest_detail'),
    path('waste-manifests/<int:pk>/edit/', views.ManifestEditView.as_view(), name='manifest_edit'),
    path('waste-manifests/<int:pk>/dispatch/', views.ManifestDispatchView.as_view(), name='manifest_dispatch'),
    path('waste-manifests/<int:pk>/dispose/', views.ManifestDisposeView.as_view(), name='manifest_dispose'),
    path('waste-manifests/<int:pk>/reconcile/', views.ManifestReconcileView.as_view(), name='manifest_reconcile'),
    path('waste-manifests/<int:pk>/cancel/', views.ManifestCancelView.as_view(), name='manifest_cancel'),
    path('waste-manifests/<int:pk>/delete/', views.ManifestDeleteView.as_view(), name='manifest_delete'),
    path('waste-manifests/<int:manifest_pk>/lines/new/', views.DisposalRecordCreateView.as_view(), name='disposal_create'),
    path('waste-manifests/lines/<int:pk>/delete/', views.DisposalRecordDeleteView.as_view(), name='disposal_delete'),

    # 13.5 Recalls
    path('recalls/', views.RecallListView.as_view(), name='recall_list'),
    path('recalls/new/', views.RecallCreateView.as_view(), name='recall_create'),
    path('recalls/<int:pk>/', views.RecallDetailView.as_view(), name='recall_detail'),
    path('recalls/<int:pk>/edit/', views.RecallEditView.as_view(), name='recall_edit'),
    path('recalls/<int:pk>/progress/', views.RecallProgressView.as_view(), name='recall_progress'),
    path('recalls/<int:pk>/complete/', views.RecallCompleteView.as_view(), name='recall_complete'),
    path('recalls/<int:pk>/close/', views.RecallCloseView.as_view(), name='recall_close'),
    path('recalls/<int:pk>/cancel/', views.RecallCancelView.as_view(), name='recall_cancel'),
    path('recalls/<int:pk>/delete/', views.RecallDeleteView.as_view(), name='recall_delete'),
    path('recalls/<int:recall_pk>/lots/add/', views.AffectedLotAddView.as_view(), name='affected_lot_add'),
    path('recalls/lots/<int:pk>/remove/', views.AffectedLotRemoveView.as_view(), name='affected_lot_remove'),
    path('recalls/<int:recall_pk>/notices/new/', views.NoticeCreateView.as_view(), name='notice_create'),
    path('recalls/notices/<int:pk>/', views.NoticeDetailView.as_view(), name='notice_detail'),
    path('recalls/notices/<int:pk>/send/', views.NoticeSendView.as_view(), name='notice_send'),
    path('recalls/notices/<int:pk>/ack/', views.NoticeAcknowledgeView.as_view(), name='notice_ack'),
    path('recalls/notices/<int:pk>/delete/', views.NoticeDeleteView.as_view(), name='notice_delete'),
]
