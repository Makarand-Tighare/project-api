from django.urls import path
from account.views import AdminDashboardView, AdminLoginView

urlpatterns = [
    # Important: The login endpoint should be accessible without authentication
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
] 