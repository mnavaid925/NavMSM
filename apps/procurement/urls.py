"""URL patterns for Module 9 - Procurement & Supplier Portal."""
from django.urls import path

from . import views

app_name = 'procurement'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 9.1  Suppliers
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/new/', views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', views.SupplierEditView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),
    path('suppliers/<int:pk>/contacts/new/', views.SupplierContactCreateView.as_view(), name='supplier_contact_create'),
    path('contacts/<int:pk>/delete/', views.SupplierContactDeleteView.as_view(), name='supplier_contact_delete'),

    # 9.1  Purchase Orders
    path('po/', views.POListView.as_view(), name='po_list'),
    path('po/new/', views.POCreateView.as_view(), name='po_create'),
    path('po/<int:pk>/', views.PODetailView.as_view(), name='po_detail'),
    path('po/<int:pk>/edit/', views.POEditView.as_view(), name='po_edit'),
    path('po/<int:pk>/delete/', views.PODeleteView.as_view(), name='po_delete'),
    path('po/<int:pk>/lines/new/', views.POLineCreateView.as_view(), name='po_line_create'),
    path('po/lines/<int:pk>/delete/', views.POLineDeleteView.as_view(), name='po_line_delete'),
    path('po/<int:pk>/submit/', views.POSubmitView.as_view(), name='po_submit'),
    path('po/<int:pk>/approve/', views.POApproveView.as_view(), name='po_approve'),
    path('po/<int:pk>/reject/', views.PORejectView.as_view(), name='po_reject'),
    path('po/<int:pk>/acknowledge/', views.POAcknowledgeView.as_view(), name='po_acknowledge'),
    path('po/<int:pk>/close/', views.POCloseView.as_view(), name='po_close'),
    path('po/<int:pk>/cancel/', views.POCancelView.as_view(), name='po_cancel'),
    path('po/<int:pk>/revise/', views.POReviseView.as_view(), name='po_revise'),

    # 9.2  RFQs
    path('rfq/', views.RFQListView.as_view(), name='rfq_list'),
    path('rfq/new/', views.RFQCreateView.as_view(), name='rfq_create'),
    path('rfq/<int:pk>/', views.RFQDetailView.as_view(), name='rfq_detail'),
    path('rfq/<int:pk>/edit/', views.RFQEditView.as_view(), name='rfq_edit'),
    path('rfq/<int:pk>/delete/', views.RFQDeleteView.as_view(), name='rfq_delete'),
    path('rfq/<int:pk>/lines/new/', views.RFQLineCreateView.as_view(), name='rfq_line_create'),
    path('rfq/lines/<int:pk>/delete/', views.RFQLineDeleteView.as_view(), name='rfq_line_delete'),
    path('rfq/<int:pk>/invite/', views.RFQSupplierInviteView.as_view(), name='rfq_invite'),
    path('rfq/invited/<int:pk>/remove/', views.RFQSupplierRemoveView.as_view(), name='rfq_invite_remove'),
    path('rfq/<int:pk>/issue/', views.RFQIssueView.as_view(), name='rfq_issue'),
    path('rfq/<int:pk>/close/', views.RFQCloseView.as_view(), name='rfq_close'),
    path('rfq/<int:pk>/award/', views.RFQAwardView.as_view(), name='rfq_award'),
    path('rfq/<int:pk>/cancel/', views.RFQCancelView.as_view(), name='rfq_cancel'),
    path('rfq/<int:rfq_pk>/compare/', views.RFQQuotationCompareView.as_view(), name='rfq_compare'),

    # 9.2  Quotations
    path('quotations/', views.QuotationListView.as_view(), name='quotation_list'),
    path('quotations/new/', views.QuotationCreateView.as_view(), name='quotation_create'),
    path('quotations/<int:pk>/', views.QuotationDetailView.as_view(), name='quotation_detail'),
    path('quotations/<int:pk>/lines/new/', views.QuotationLineCreateView.as_view(), name='quotation_line_create'),
    path('quotations/lines/<int:pk>/delete/', views.QuotationLineDeleteView.as_view(), name='quotation_line_delete'),
    path('quotations/<int:pk>/delete/', views.QuotationDeleteView.as_view(), name='quotation_delete'),

    # 9.3  Scorecards
    path('scorecards/', views.ScorecardListView.as_view(), name='scorecard_list'),
    path('scorecards/<int:pk>/', views.ScorecardDetailView.as_view(), name='scorecard_detail'),
    path('scorecards/recompute/', views.ScorecardRecomputeView.as_view(), name='scorecard_recompute'),

    # 9.4  ASNs
    path('asn/', views.ASNListView.as_view(), name='asn_list'),
    path('asn/new/', views.ASNCreateView.as_view(), name='asn_create'),
    path('asn/<int:pk>/', views.ASNDetailView.as_view(), name='asn_detail'),
    path('asn/<int:pk>/lines/new/', views.ASNLineCreateView.as_view(), name='asn_line_create'),
    path('asn/lines/<int:pk>/delete/', views.ASNLineDeleteView.as_view(), name='asn_line_delete'),
    path('asn/<int:pk>/submit/', views.ASNSubmitView.as_view(), name='asn_submit'),
    path('asn/<int:pk>/receive/', views.ASNReceiveView.as_view(), name='asn_receive'),
    path('asn/<int:pk>/cancel/', views.ASNCancelView.as_view(), name='asn_cancel'),

    # 9.4  Supplier Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/new/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/review/', views.InvoiceReviewView.as_view(), name='invoice_review'),
    path('invoices/<int:pk>/approve/', views.InvoiceApproveView.as_view(), name='invoice_approve'),
    path('invoices/<int:pk>/pay/', views.InvoicePayView.as_view(), name='invoice_pay'),
    path('invoices/<int:pk>/reject/', views.InvoiceRejectView.as_view(), name='invoice_reject'),
    path('invoices/<int:pk>/dispute/', views.InvoiceDisputeView.as_view(), name='invoice_dispute'),
    path('invoices/<int:pk>/delete/', views.InvoiceDeleteView.as_view(), name='invoice_delete'),

    # 9.5  Blanket Orders
    path('blanket/', views.BlanketListView.as_view(), name='blanket_list'),
    path('blanket/new/', views.BlanketCreateView.as_view(), name='blanket_create'),
    path('blanket/<int:pk>/', views.BlanketDetailView.as_view(), name='blanket_detail'),
    path('blanket/<int:pk>/edit/', views.BlanketEditView.as_view(), name='blanket_edit'),
    path('blanket/<int:pk>/delete/', views.BlanketDeleteView.as_view(), name='blanket_delete'),
    path('blanket/<int:pk>/lines/new/', views.BlanketLineCreateView.as_view(), name='blanket_line_create'),
    path('blanket/lines/<int:pk>/delete/', views.BlanketLineDeleteView.as_view(), name='blanket_line_delete'),
    path('blanket/<int:pk>/activate/', views.BlanketActivateView.as_view(), name='blanket_activate'),
    path('blanket/<int:pk>/close/', views.BlanketCloseView.as_view(), name='blanket_close'),
    path('blanket/<int:pk>/cancel/', views.BlanketCancelView.as_view(), name='blanket_cancel'),

    # 9.5  Schedule Releases
    path('releases/', views.ReleaseListView.as_view(), name='release_list'),
    path('releases/new/', views.ReleaseCreateView.as_view(), name='release_create'),
    path('releases/<int:pk>/', views.ReleaseDetailView.as_view(), name='release_detail'),
    path('releases/<int:pk>/lines/new/', views.ReleaseLineCreateView.as_view(), name='release_line_create'),
    path('releases/lines/<int:pk>/delete/', views.ReleaseLineDeleteView.as_view(), name='release_line_delete'),
    path('releases/<int:pk>/release/', views.ReleaseReleaseView.as_view(), name='release_release'),
    path('releases/<int:pk>/receive/', views.ReleaseReceiveView.as_view(), name='release_receive'),
    path('releases/<int:pk>/cancel/', views.ReleaseCancelView.as_view(), name='release_cancel'),

    # Supplier Portal (external user)
    path('portal/', views.PortalDashboardView.as_view(), name='portal_dashboard'),
    path('portal/pos/', views.PortalPOListView.as_view(), name='portal_pos'),
    path('portal/asns/', views.PortalASNListView.as_view(), name='portal_asns'),
    path('portal/invoices/', views.PortalInvoiceListView.as_view(), name='portal_invoices'),
]
