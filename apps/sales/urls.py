"""URL configuration for Module 17 - Sales (17.1 portion).

17.2 / 17.3 / 17.4 / 17.5 patterns will be appended in their respective turns.
"""
from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    # Dashboard
    path('', views.index_view, name='index'),

    # 17.1 - Customer Master
    path('customers/', views.customer_list_view, name='customer_list'),
    path('customers/new/', views.customer_create_view, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail_view, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit_view, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete_view, name='customer_delete'),
    path('customers/<int:pk>/toggle-active/', views.customer_toggle_active_view, name='customer_toggle_active'),

    # 17.1 - Contacts (nested under a customer)
    path('customers/<int:customer_pk>/contacts/new/', views.contact_add_view, name='contact_add'),
    path('contacts/<int:pk>/edit/', views.contact_edit_view, name='contact_edit'),
    path('contacts/<int:pk>/delete/', views.contact_delete_view, name='contact_delete'),

    # 17.1 - Communication log
    path('communications/', views.comm_list_view, name='comm_list'),
    path('customers/<int:customer_pk>/communications/new/', views.comm_add_view, name='comm_add'),
    path('communications/<int:pk>/edit/', views.comm_edit_view, name='comm_edit'),
    path('communications/<int:pk>/delete/', views.comm_delete_view, name='comm_delete'),

    # 17.1 - Documents
    path('customers/<int:customer_pk>/documents/upload/', views.document_upload_view, name='document_upload'),
    path('documents/<int:pk>/delete/', views.document_delete_view, name='document_delete'),
    path('documents/<int:pk>/download/', views.document_download_view, name='document_download'),

    # 17.1 - Categories
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/new/', views.category_create_view, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_view, name='category_delete'),

    # 17.1 - Price lists
    path('pricelists/', views.pricelist_list_view, name='pricelist_list'),
    path('pricelists/new/', views.pricelist_create_view, name='pricelist_create'),
    path('pricelists/<int:pk>/', views.pricelist_detail_view, name='pricelist_detail'),
    path('pricelists/<int:pk>/edit/', views.pricelist_edit_view, name='pricelist_edit'),
    path('pricelists/<int:pk>/delete/', views.pricelist_delete_view, name='pricelist_delete'),

    # 17.1 - Price list items
    path('pricelists/<int:pricelist_pk>/items/new/', views.pricelist_item_add_view, name='pricelist_item_add'),
    path('pricelist-items/<int:pk>/edit/', views.pricelist_item_edit_view, name='pricelist_item_edit'),
    path('pricelist-items/<int:pk>/delete/', views.pricelist_item_delete_view, name='pricelist_item_delete'),

    # 17.2 - Sales orders
    path('orders/', views.order_list_view, name='order_list'),
    path('orders/new/', views.order_create_view, name='order_create'),
    path('orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('orders/<int:pk>/edit/', views.order_edit_view, name='order_edit'),
    path('orders/<int:pk>/delete/', views.order_delete_view, name='order_delete'),
    # SO line CRUD (nested)
    path('orders/<int:order_pk>/lines/new/', views.order_line_add_view, name='order_line_add'),
    path('order-lines/<int:pk>/edit/', views.order_line_edit_view, name='order_line_edit'),
    path('order-lines/<int:pk>/delete/', views.order_line_delete_view, name='order_line_delete'),
    # SO workflow (POST only)
    path('orders/<int:pk>/submit/', views.order_submit_view, name='order_submit'),
    path('orders/<int:pk>/confirm/', views.order_confirm_view, name='order_confirm'),
    path('orders/<int:pk>/release-credit-hold/', views.order_release_credit_hold_view, name='order_release_credit_hold'),
    path('orders/<int:pk>/cancel/', views.order_cancel_view, name='order_cancel'),
    path('orders/<int:pk>/hold/', views.order_hold_view, name='order_hold'),
    path('orders/<int:pk>/resume/', views.order_resume_view, name='order_resume'),
    path('orders/<int:pk>/revise/', views.order_revise_view, name='order_revise'),
    # Revision detail
    path('order-revisions/<int:pk>/', views.order_revision_detail_view, name='order_revision_detail'),

    # 17.3 - ATP / CTP
    path('atp/', views.atp_list_view, name='atp_list'),
    path('atp/new/', views.atp_request_view, name='atp_request'),
    path('atp/<int:pk>/', views.atp_detail_view, name='atp_detail'),
    path('ctp/', views.ctp_list_view, name='ctp_list'),
    path('ctp/new/', views.ctp_request_view, name='ctp_request'),
    path('ctp/<int:pk>/', views.ctp_detail_view, name='ctp_detail'),
    path('order-lines/<int:order_line_pk>/confirm-promise/', views.promise_confirm_view, name='promise_confirm'),

    # 17.4 - Delivery Routes
    path('routes/', views.route_list_view, name='route_list'),
    path('routes/new/', views.route_create_view, name='route_create'),
    path('routes/<int:pk>/', views.route_detail_view, name='route_detail'),
    path('routes/<int:pk>/edit/', views.route_edit_view, name='route_edit'),
    path('routes/<int:pk>/delete/', views.route_delete_view, name='route_delete'),

    # 17.4 - Shipments
    path('shipments/', views.shipment_list_view, name='shipment_list'),
    path('shipments/new/', views.shipment_create_view, name='shipment_create'),
    path('shipments/<int:pk>/', views.shipment_detail_view, name='shipment_detail'),
    path('shipments/<int:pk>/edit/', views.shipment_edit_view, name='shipment_edit'),
    path('shipments/<int:pk>/delete/', views.shipment_delete_view, name='shipment_delete'),
    # Shipment lines
    path('shipments/<int:shipment_pk>/lines/new/', views.shipment_line_add_view, name='shipment_line_add'),
    path('shipment-lines/<int:pk>/edit/', views.shipment_line_edit_view, name='shipment_line_edit'),
    path('shipment-lines/<int:pk>/delete/', views.shipment_line_delete_view, name='shipment_line_delete'),
    # Shipment workflow (POST)
    path('shipments/<int:pk>/pick/', views.shipment_pick_view, name='shipment_pick'),
    path('shipments/<int:pk>/pack/', views.shipment_pack_view, name='shipment_pack'),
    path('shipments/<int:pk>/dispatch/', views.shipment_dispatch_view, name='shipment_dispatch'),
    path('shipments/<int:pk>/deliver/', views.shipment_mark_delivered_view, name='shipment_mark_delivered'),
    path('shipments/<int:pk>/cancel-shipment/', views.shipment_cancel_view, name='shipment_cancel'),
    # POD
    path('shipments/<int:shipment_pk>/pod/', views.pod_record_view, name='pod_record'),

    # 17.4 - Sales invoices
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/new/', views.invoice_create_view, name='invoice_create'),
    path('invoices/from-shipment/<int:shipment_pk>/', views.invoice_create_from_shipment_view, name='invoice_from_shipment'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.invoice_edit_view, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.invoice_delete_view, name='invoice_delete'),
    path('invoices/<int:pk>/issue/', views.invoice_issue_view, name='invoice_issue'),
    path('invoices/<int:pk>/mark-paid/', views.invoice_mark_paid_view, name='invoice_mark_paid'),
    # Invoice lines
    path('invoices/<int:invoice_pk>/lines/new/', views.invoice_line_add_view, name='invoice_line_add'),
    path('invoice-lines/<int:pk>/delete/', views.invoice_line_delete_view, name='invoice_line_delete'),

    # 17.5 - Customer Portal (all scoped to request.user.customer_company)
    path('portal/', views.portal_dashboard_view, name='portal_dashboard'),
    path('portal/orders/', views.portal_order_list_view, name='portal_order_list'),
    path('portal/orders/<int:pk>/', views.portal_order_detail_view, name='portal_order_detail'),
    path('portal/shipments/<int:pk>/tracking/', views.portal_shipment_tracking_view, name='portal_shipment_tracking'),
    path('portal/invoices/', views.portal_invoice_list_view, name='portal_invoice_list'),
    path('portal/invoices/<int:pk>/', views.portal_invoice_detail_view, name='portal_invoice_detail'),
    path('portal/documents/<int:pk>/download/', views.portal_document_download_view, name='portal_document_download'),
]
