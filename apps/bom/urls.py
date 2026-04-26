from django.urls import path

from . import views

app_name = 'bom'

urlpatterns = [
    # Index / dashboard
    path('', views.BOMIndexView.as_view(), name='index'),

    # ---- Bills of Materials ----
    path('boms/', views.BOMListView.as_view(), name='bom_list'),
    path('boms/new/', views.BOMCreateView.as_view(), name='bom_create'),
    path('boms/<int:pk>/', views.BOMDetailView.as_view(), name='bom_detail'),
    path('boms/<int:pk>/edit/', views.BOMEditView.as_view(), name='bom_edit'),
    path('boms/<int:pk>/delete/', views.BOMDeleteView.as_view(), name='bom_delete'),

    # Workflow actions
    path('boms/<int:pk>/submit/', views.BOMSubmitView.as_view(), name='bom_submit'),
    path('boms/<int:pk>/approve/', views.BOMApproveView.as_view(), name='bom_approve'),
    path('boms/<int:pk>/reject/', views.BOMRejectView.as_view(), name='bom_reject'),
    path('boms/<int:pk>/release/', views.BOMReleaseView.as_view(), name='bom_release'),
    path('boms/<int:pk>/obsolete/', views.BOMObsoleteView.as_view(), name='bom_obsolete'),
    path('boms/<int:pk>/recompute/', views.BOMRecomputeRollupView.as_view(), name='bom_recompute'),
    path('boms/<int:pk>/explode/', views.BOMExplodeView.as_view(), name='bom_explode'),

    # ---- Lines ----
    path('boms/<int:bom_id>/lines/new/', views.BOMLineCreateView.as_view(), name='line_create'),
    path('lines/<int:pk>/edit/', views.BOMLineEditView.as_view(), name='line_edit'),
    path('lines/<int:pk>/delete/', views.BOMLineDeleteView.as_view(), name='line_delete'),

    # ---- Revisions ----
    path('boms/<int:bom_id>/revisions/new/', views.BOMRevisionCreateView.as_view(), name='revision_create'),
    path('revisions/<int:pk>/', views.BOMRevisionDetailView.as_view(), name='revision_detail'),
    path('revisions/<int:pk>/rollback/', views.BOMRollbackView.as_view(), name='revision_rollback'),

    # ---- Alternates ----
    path('lines/<int:line_id>/alternates/new/', views.AlternateCreateView.as_view(), name='alt_create'),
    path('alternates/<int:pk>/edit/', views.AlternateEditView.as_view(), name='alt_edit'),
    path('alternates/<int:pk>/delete/', views.AlternateDeleteView.as_view(), name='alt_delete'),
    path('alternates/<int:pk>/approve/', views.AlternateApproveView.as_view(), name='alt_approve'),
    path('alternates/<int:pk>/reject/', views.AlternateRejectView.as_view(), name='alt_reject'),

    # ---- Substitution rules ----
    path('rules/', views.SubstitutionRuleListView.as_view(), name='rule_list'),
    path('rules/new/', views.SubstitutionRuleCreateView.as_view(), name='rule_create'),
    path('rules/<int:pk>/edit/', views.SubstitutionRuleEditView.as_view(), name='rule_edit'),
    path('rules/<int:pk>/delete/', views.SubstitutionRuleDeleteView.as_view(), name='rule_delete'),

    # ---- Cost elements ----
    path('costs/', views.CostElementListView.as_view(), name='cost_list'),
    path('costs/new/', views.CostElementCreateView.as_view(), name='cost_create'),
    path('costs/<int:pk>/edit/', views.CostElementEditView.as_view(), name='cost_edit'),
    path('costs/<int:pk>/delete/', views.CostElementDeleteView.as_view(), name='cost_delete'),

    # ---- Sync maps ----
    path('sync/', views.BOMSyncMapListView.as_view(), name='sync_list'),
    path('sync/new/', views.BOMSyncMapCreateView.as_view(), name='sync_create'),
    path('sync/<int:pk>/', views.BOMSyncMapDetailView.as_view(), name='sync_detail'),
    path('sync/<int:pk>/edit/', views.BOMSyncMapEditView.as_view(), name='sync_edit'),
    path('sync/<int:pk>/delete/', views.BOMSyncMapDeleteView.as_view(), name='sync_delete'),
    path('sync/<int:pk>/run/', views.BOMSyncRunView.as_view(), name='sync_run'),
]
