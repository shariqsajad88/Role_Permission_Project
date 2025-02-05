from django.urls import path
from .views import ExportRolesPermissionsView, AdminDashboardView 

urlpatterns = [
    path('export/', ExportRolesPermissionsView.as_view(), name='export-roles-permissions'),  
    path('dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
]