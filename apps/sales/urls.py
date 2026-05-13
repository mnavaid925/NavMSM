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
]
