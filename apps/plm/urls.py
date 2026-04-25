from django.urls import path

from . import views

app_name = 'plm'

urlpatterns = [
    # Index
    path('', views.PLMIndexView.as_view(), name='index'),

    # ---- Categories ----
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/new/', views.CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/edit/', views.CategoryEditView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),

    # ---- Products ----
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/new/', views.ProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('products/<int:pk>/edit/', views.ProductEditView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),

    # Revisions / specs / variants nested under product
    path('products/<int:product_id>/revisions/new/', views.RevisionCreateView.as_view(), name='revision_create'),
    path('revisions/<int:pk>/delete/', views.RevisionDeleteView.as_view(), name='revision_delete'),
    path('products/<int:product_id>/specs/new/', views.SpecificationCreateView.as_view(), name='spec_create'),
    path('specs/<int:pk>/delete/', views.SpecificationDeleteView.as_view(), name='spec_delete'),
    path('products/<int:product_id>/variants/new/', views.VariantCreateView.as_view(), name='variant_create'),
    path('variants/<int:pk>/edit/', views.VariantEditView.as_view(), name='variant_edit'),
    path('variants/<int:pk>/delete/', views.VariantDeleteView.as_view(), name='variant_delete'),

    # ---- ECO ----
    path('eco/', views.ECOListView.as_view(), name='eco_list'),
    path('eco/new/', views.ECOCreateView.as_view(), name='eco_create'),
    path('eco/<int:pk>/', views.ECODetailView.as_view(), name='eco_detail'),
    path('eco/<int:pk>/edit/', views.ECOEditView.as_view(), name='eco_edit'),
    path('eco/<int:pk>/delete/', views.ECODeleteView.as_view(), name='eco_delete'),
    path('eco/<int:pk>/submit/', views.ECOSubmitView.as_view(), name='eco_submit'),
    path('eco/<int:pk>/approve/', views.ECOApproveView.as_view(), name='eco_approve'),
    path('eco/<int:pk>/reject/', views.ECORejectView.as_view(), name='eco_reject'),
    path('eco/<int:pk>/implement/', views.ECOImplementView.as_view(), name='eco_implement'),
    path('eco/<int:pk>/items/new/', views.ECOImpactedItemAddView.as_view(), name='eco_item_add'),
    path('eco/items/<int:pk>/delete/', views.ECOImpactedItemDeleteView.as_view(), name='eco_item_delete'),
    path('eco/<int:pk>/attachments/new/', views.ECOAttachmentAddView.as_view(), name='eco_attachment_add'),
    path('eco/attachments/<int:pk>/delete/', views.ECOAttachmentDeleteView.as_view(), name='eco_attachment_delete'),

    # ---- CAD ----
    path('cad/', views.CADListView.as_view(), name='cad_list'),
    path('cad/new/', views.CADCreateView.as_view(), name='cad_create'),
    path('cad/<int:pk>/', views.CADDetailView.as_view(), name='cad_detail'),
    path('cad/<int:pk>/edit/', views.CADEditView.as_view(), name='cad_edit'),
    path('cad/<int:pk>/delete/', views.CADDeleteView.as_view(), name='cad_delete'),
    path('cad/<int:pk>/versions/new/', views.CADVersionUploadView.as_view(), name='cad_version_upload'),
    path('cad/versions/<int:pk>/release/', views.CADVersionReleaseView.as_view(), name='cad_version_release'),
    path('cad/versions/<int:pk>/delete/', views.CADVersionDeleteView.as_view(), name='cad_version_delete'),

    # ---- Compliance ----
    path('compliance/', views.ComplianceListView.as_view(), name='compliance_list'),
    path('compliance/new/', views.ComplianceCreateView.as_view(), name='compliance_create'),
    path('compliance/<int:pk>/', views.ComplianceDetailView.as_view(), name='compliance_detail'),
    path('compliance/<int:pk>/edit/', views.ComplianceEditView.as_view(), name='compliance_edit'),
    path('compliance/<int:pk>/delete/', views.ComplianceDeleteView.as_view(), name='compliance_delete'),

    # ---- NPI ----
    path('npi/', views.NPIListView.as_view(), name='npi_list'),
    path('npi/new/', views.NPICreateView.as_view(), name='npi_create'),
    path('npi/<int:pk>/', views.NPIDetailView.as_view(), name='npi_detail'),
    path('npi/<int:pk>/edit/', views.NPIEditView.as_view(), name='npi_edit'),
    path('npi/<int:pk>/delete/', views.NPIDeleteView.as_view(), name='npi_delete'),
    path('npi/stages/<int:pk>/edit/', views.NPIStageEditView.as_view(), name='npi_stage_edit'),
    path('npi/stages/<int:stage_id>/deliverables/new/', views.NPIDeliverableAddView.as_view(), name='npi_deliverable_add'),
    path('npi/deliverables/<int:pk>/edit/', views.NPIDeliverableEditView.as_view(), name='npi_deliverable_edit'),
    path('npi/deliverables/<int:pk>/complete/', views.NPIDeliverableCompleteView.as_view(), name='npi_deliverable_complete'),
    path('npi/deliverables/<int:pk>/delete/', views.NPIDeliverableDeleteView.as_view(), name='npi_deliverable_delete'),
]
