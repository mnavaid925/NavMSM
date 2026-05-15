"""URL configuration for Module 18 - Returns & RMA Management.

Standard list / create / detail / edit / delete naming per sub-module;
workflow transitions are POST-only and gated to tenant admins in views.
"""
from django.urls import path

from . import views

app_name = 'rma'

urlpatterns = [
    # Dashboard
    path('', views.index_view, name='index'),

    # ----- 18.1  RMA Reasons (catalog) -----
    path('reasons/', views.reason_list_view, name='reason_list'),
    path('reasons/new/', views.reason_create_view, name='reason_create'),
    path('reasons/<int:pk>/edit/', views.reason_edit_view, name='reason_edit'),
    path('reasons/<int:pk>/delete/', views.reason_delete_view, name='reason_delete'),

    # ----- 18.1  RMA Requests -----
    path('requests/', views.request_list_view, name='request_list'),
    path('requests/new/', views.request_create_view, name='request_create'),
    path('requests/<int:pk>/', views.request_detail_view, name='request_detail'),
    path('requests/<int:pk>/edit/', views.request_edit_view, name='request_edit'),
    path('requests/<int:pk>/delete/', views.request_delete_view, name='request_delete'),
    path('requests/<int:pk>/submit/', views.request_submit_view, name='request_submit'),
    path('requests/<int:pk>/approve/', views.request_approve_view, name='request_approve'),
    path('requests/<int:pk>/reject/', views.request_reject_view, name='request_reject'),
    path('requests/<int:pk>/cancel/', views.request_cancel_view, name='request_cancel'),
    # RMA lines (nested under a request)
    path('requests/<int:rma_pk>/lines/new/', views.rma_line_add_view, name='rma_line_add'),
    path('rma-lines/<int:pk>/edit/', views.rma_line_edit_view, name='rma_line_edit'),
    path('rma-lines/<int:pk>/delete/', views.rma_line_delete_view, name='rma_line_delete'),

    # ----- 18.2  Returns Receiving & Inspection -----
    path('receipts/', views.receipt_list_view, name='receipt_list'),
    path('receipts/new/', views.receipt_create_view, name='receipt_create'),
    path('receipts/<int:pk>/', views.receipt_detail_view, name='receipt_detail'),
    path('receipts/<int:pk>/edit/', views.receipt_edit_view, name='receipt_edit'),
    path('receipts/<int:pk>/delete/', views.receipt_delete_view, name='receipt_delete'),
    path('receipts/<int:pk>/start-inspection/', views.receipt_start_inspection_view, name='receipt_start_inspection'),
    path('receipts/<int:pk>/complete/', views.receipt_complete_view, name='receipt_complete'),
    path('receipts/<int:pk>/cancel/', views.receipt_cancel_view, name='receipt_cancel'),
    # Receipt lines (nested)
    path('receipts/<int:receipt_pk>/lines/new/', views.receipt_line_add_view, name='receipt_line_add'),
    path('receipt-lines/<int:pk>/edit/', views.receipt_line_edit_view, name='receipt_line_edit'),
    path('receipt-lines/<int:pk>/delete/', views.receipt_line_delete_view, name='receipt_line_delete'),

    # ----- 18.3  Repair & Refurbishment Tracking -----
    path('repairs/', views.repair_list_view, name='repair_list'),
    path('repairs/new/', views.repair_create_view, name='repair_create'),
    path('repairs/<int:pk>/', views.repair_detail_view, name='repair_detail'),
    path('repairs/<int:pk>/edit/', views.repair_edit_view, name='repair_edit'),
    path('repairs/<int:pk>/delete/', views.repair_delete_view, name='repair_delete'),
    path('repairs/<int:pk>/start/', views.repair_start_view, name='repair_start'),
    path('repairs/<int:pk>/hold/', views.repair_hold_view, name='repair_hold'),
    path('repairs/<int:pk>/resume/', views.repair_resume_view, name='repair_resume'),
    path('repairs/<int:pk>/complete/', views.repair_complete_view, name='repair_complete'),
    path('repairs/<int:pk>/cancel/', views.repair_cancel_view, name='repair_cancel'),
    # Repair parts (nested)
    path('repairs/<int:repair_pk>/parts/new/', views.repair_part_add_view, name='repair_part_add'),
    path('repair-parts/<int:pk>/delete/', views.repair_part_delete_view, name='repair_part_delete'),
    # Repair labor (nested)
    path('repairs/<int:repair_pk>/labor/new/', views.repair_labor_add_view, name='repair_labor_add'),
    path('repair-labor/<int:pk>/delete/', views.repair_labor_delete_view, name='repair_labor_delete'),

    # ----- 18.4  Warranty Policies -----
    path('warranty/policies/', views.policy_list_view, name='policy_list'),
    path('warranty/policies/new/', views.policy_create_view, name='policy_create'),
    path('warranty/policies/<int:pk>/edit/', views.policy_edit_view, name='policy_edit'),
    path('warranty/policies/<int:pk>/delete/', views.policy_delete_view, name='policy_delete'),

    # ----- 18.4  Warranty Registrations -----
    path('warranty/registrations/', views.registration_list_view, name='registration_list'),
    path('warranty/registrations/new/', views.registration_create_view, name='registration_create'),
    path('warranty/registrations/<int:pk>/', views.registration_detail_view, name='registration_detail'),
    path('warranty/registrations/<int:pk>/edit/', views.registration_edit_view, name='registration_edit'),
    path('warranty/registrations/<int:pk>/delete/', views.registration_delete_view, name='registration_delete'),

    # ----- 18.4  Warranty Claims -----
    path('warranty/claims/', views.claim_list_view, name='claim_list'),
    path('warranty/claims/new/', views.claim_create_view, name='claim_create'),
    path('warranty/claims/<int:pk>/', views.claim_detail_view, name='claim_detail'),
    path('warranty/claims/<int:pk>/edit/', views.claim_edit_view, name='claim_edit'),
    path('warranty/claims/<int:pk>/delete/', views.claim_delete_view, name='claim_delete'),
    path('warranty/claims/<int:pk>/validate/', views.claim_validate_view, name='claim_validate'),
    path('warranty/claims/<int:pk>/approve/', views.claim_approve_view, name='claim_approve'),
    path('warranty/claims/<int:pk>/reject/', views.claim_reject_view, name='claim_reject'),
    path('warranty/claims/<int:pk>/fulfill/', views.claim_fulfill_view, name='claim_fulfill'),

    # ----- 18.5  Failure Modes (catalog) -----
    path('analytics/failure-modes/', views.failure_mode_list_view, name='failure_mode_list'),
    path('analytics/failure-modes/new/', views.failure_mode_create_view, name='failure_mode_create'),
    path('analytics/failure-modes/<int:pk>/edit/', views.failure_mode_edit_view, name='failure_mode_edit'),
    path('analytics/failure-modes/<int:pk>/delete/', views.failure_mode_delete_view, name='failure_mode_delete'),

    # ----- 18.5  Root Cause Categories (catalog) -----
    path('analytics/root-causes/', views.root_cause_list_view, name='root_cause_list'),
    path('analytics/root-causes/new/', views.root_cause_create_view, name='root_cause_create'),
    path('analytics/root-causes/<int:pk>/edit/', views.root_cause_edit_view, name='root_cause_edit'),
    path('analytics/root-causes/<int:pk>/delete/', views.root_cause_delete_view, name='root_cause_delete'),

    # ----- 18.5  Return Analyses -----
    path('analytics/analyses/', views.analysis_list_view, name='analysis_list'),
    path('analytics/analyses/new/', views.analysis_create_view, name='analysis_create'),
    path('analytics/analyses/<int:pk>/', views.analysis_detail_view, name='analysis_detail'),
    path('analytics/analyses/<int:pk>/edit/', views.analysis_edit_view, name='analysis_edit'),
    path('analytics/analyses/<int:pk>/delete/', views.analysis_delete_view, name='analysis_delete'),

    # ----- 18.5  Supplier Chargebacks -----
    path('analytics/chargebacks/', views.chargeback_list_view, name='chargeback_list'),
    path('analytics/chargebacks/new/', views.chargeback_create_view, name='chargeback_create'),
    path('analytics/chargebacks/<int:pk>/', views.chargeback_detail_view, name='chargeback_detail'),
    path('analytics/chargebacks/<int:pk>/edit/', views.chargeback_edit_view, name='chargeback_edit'),
    path('analytics/chargebacks/<int:pk>/delete/', views.chargeback_delete_view, name='chargeback_delete'),
    path('analytics/chargebacks/<int:pk>/transition/', views.chargeback_transition_view, name='chargeback_transition'),
]
