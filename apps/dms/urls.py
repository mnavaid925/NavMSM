"""URL configuration for Module 19 - Document & Knowledge Management.

Standard list / create / detail / edit / delete naming per sub-module;
workflow transitions are POST-only and gated to tenant admins in views.
"""
from django.urls import path

from . import views

app_name = 'dms'

urlpatterns = [
    # Dashboard
    path('', views.index_view, name='index'),

    # ----- 19.1  Document Categories (catalog) -----
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/new/', views.category_create_view, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_view, name='category_delete'),

    # ----- 19.1  Documents -----
    path('documents/', views.document_list_view, name='document_list'),
    path('documents/new/', views.document_create_view, name='document_create'),
    path('documents/<int:pk>/', views.document_detail_view, name='document_detail'),
    path('documents/<int:pk>/edit/', views.document_edit_view, name='document_edit'),
    path('documents/<int:pk>/delete/', views.document_delete_view, name='document_delete'),
    path('documents/<int:pk>/submit/', views.document_submit_view, name='document_submit'),
    path('documents/<int:pk>/archive/', views.document_archive_view, name='document_archive'),

    # Versions (nested under document)
    path('documents/<int:doc_pk>/versions/new/', views.version_create_view, name='version_create'),
    path('versions/<int:pk>/edit/', views.version_edit_view, name='version_edit'),
    path('versions/<int:pk>/delete/', views.version_delete_view, name='version_delete'),
    path('versions/<int:pk>/check-out/', views.version_check_out_view, name='version_check_out'),
    path('versions/<int:pk>/check-in/', views.version_check_in_view, name='version_check_in'),
    path('versions/<int:pk>/release/', views.version_release_view, name='version_release'),
    path('versions/<int:pk>/download/', views.version_download_view, name='version_download'),

    # Access rules (nested)
    path('documents/<int:doc_pk>/access/new/', views.access_create_view, name='access_create'),
    path('access/<int:pk>/delete/', views.access_delete_view, name='access_delete'),

    # ----- 19.2  Templates -----
    path('templates/', views.template_list_view, name='template_list'),
    path('templates/new/', views.template_create_view, name='template_create'),
    path('templates/<int:pk>/', views.template_detail_view, name='template_detail'),
    path('templates/<int:pk>/edit/', views.template_edit_view, name='template_edit'),
    path('templates/<int:pk>/delete/', views.template_delete_view, name='template_delete'),
    path('templates/<int:tpl_pk>/fields/new/', views.template_field_create_view, name='template_field_create'),
    path('template-fields/<int:pk>/edit/', views.template_field_edit_view, name='template_field_edit'),
    path('template-fields/<int:pk>/delete/', views.template_field_delete_view, name='template_field_delete'),

    # Media attachments (nested under version)
    path('versions/<int:version_pk>/media/new/', views.media_create_view, name='media_create'),
    path('media/<int:pk>/delete/', views.media_delete_view, name='media_delete'),

    # ----- 19.3  Approval Workflows -----
    path('workflows/', views.workflow_list_view, name='workflow_list'),
    path('workflows/new/', views.workflow_create_view, name='workflow_create'),
    path('workflows/<int:pk>/', views.workflow_detail_view, name='workflow_detail'),
    path('workflows/<int:pk>/edit/', views.workflow_edit_view, name='workflow_edit'),
    path('workflows/<int:pk>/delete/', views.workflow_delete_view, name='workflow_delete'),
    path('workflows/<int:wf_pk>/stages/new/', views.stage_create_view, name='stage_create'),
    path('stages/<int:pk>/edit/', views.stage_edit_view, name='stage_edit'),
    path('stages/<int:pk>/delete/', views.stage_delete_view, name='stage_delete'),

    # ----- 19.3  Approval Requests -----
    path('approvals/', views.approval_list_view, name='approval_list'),
    path('approvals/new/', views.approval_create_view, name='approval_create'),
    path('approvals/<int:pk>/', views.approval_detail_view, name='approval_detail'),
    path('approvals/<int:pk>/delete/', views.approval_delete_view, name='approval_delete'),
    path('approvals/<int:pk>/action/', views.approval_action_view, name='approval_action'),
    path('approvals/<int:pk>/cancel/', views.approval_cancel_view, name='approval_cancel'),

    # ----- 19.4  Assignments -----
    path('assignments/', views.assignment_list_view, name='assignment_list'),
    path('assignments/new/', views.assignment_create_view, name='assignment_create'),
    path('assignments/<int:pk>/', views.assignment_detail_view, name='assignment_detail'),
    path('assignments/<int:pk>/edit/', views.assignment_edit_view, name='assignment_edit'),
    path('assignments/<int:pk>/delete/', views.assignment_delete_view, name='assignment_delete'),
    path('assignments/<int:pk>/complete/', views.assignment_complete_view, name='assignment_complete'),
    path('assignments/<int:pk>/cancel/', views.assignment_cancel_view, name='assignment_cancel'),
    path('assignments/<int:pk>/ack/', views.assignment_ack_view, name='assignment_ack'),
    path('assignments/<int:asn_pk>/targets/new/', views.target_create_view, name='target_create'),
    path('targets/<int:pk>/delete/', views.target_delete_view, name='target_delete'),
    path('my-acknowledgments/', views.my_acknowledgments_view, name='my_acknowledgments'),

    # ----- 19.5  Retention Policies -----
    path('retention/policies/', views.policy_list_view, name='policy_list'),
    path('retention/policies/new/', views.policy_create_view, name='policy_create'),
    path('retention/policies/<int:pk>/edit/', views.policy_edit_view, name='policy_edit'),
    path('retention/policies/<int:pk>/delete/', views.policy_delete_view, name='policy_delete'),

    # ----- 19.5  Archives -----
    path('retention/archives/', views.archive_list_view, name='archive_list'),
    path('retention/archives/<int:pk>/', views.archive_detail_view, name='archive_detail'),
    path('retention/archives/<int:pk>/restore/', views.archive_restore_view, name='archive_restore'),

    # ----- 19.5  Legal Holds -----
    path('retention/legal-holds/', views.legal_hold_list_view, name='legal_hold_list'),
    path('retention/legal-holds/new/', views.legal_hold_create_view, name='legal_hold_create'),
    path('retention/legal-holds/<int:pk>/', views.legal_hold_detail_view, name='legal_hold_detail'),
    path('retention/legal-holds/<int:pk>/edit/', views.legal_hold_edit_view, name='legal_hold_edit'),
    path('retention/legal-holds/<int:pk>/delete/', views.legal_hold_delete_view, name='legal_hold_delete'),
    path('retention/legal-holds/<int:pk>/release/', views.legal_hold_release_view, name='legal_hold_release'),
]
