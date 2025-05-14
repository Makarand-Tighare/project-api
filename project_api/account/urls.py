from django.urls import path
from account.views import (
    UserRegistrationView, UserLoginView, UserProfileView, UserChangePasswordView,
    SendPasswordResetEmailView, UserPasswordResetView, VerifyOtpView, SendOTPView,
    UserProfileUpdateView, AdminLoginView, DepartmentListCreateView, DepartmentDetailView,
    DepartmentParticipantsView, AssignDepartmentAdminView, DepartmentAdminsView,
    AdminDashboardView, DepartmentAdminDashboardView, DepartmentListPublicView,
    get_public_stats, SendMobileOTPView, VerifyMobileOtpView
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # User authentication and profile
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('verify-otp/', VerifyOtpView.as_view(), name='verify-otp'),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('send-mobile-otp/', SendMobileOTPView.as_view(), name='send-mobile-otp'),
    path('verify-mobile-otp/', VerifyMobileOtpView.as_view(), name='verify-mobile-otp'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('admin-login/', AdminLoginView.as_view(), name='admin-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('update-profile/', UserProfileUpdateView.as_view(), name='update-profile'),
    path('changepassword/', UserChangePasswordView.as_view(), name='changepassword'),
    path('send-reset-password-email/', SendPasswordResetEmailView.as_view(), name='send-reset-password-email'),
    path('reset-password/<uid>/<token>/', UserPasswordResetView.as_view(), name='reset-password'),
    
    # Dashboard endpoints
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('department-admin/dashboard/', DepartmentAdminDashboardView.as_view(), name='department-admin-dashboard'),
    
    # Department management
    path('departments/', DepartmentListCreateView.as_view(), name='department-list'),
    path('departments-public/', DepartmentListPublicView.as_view(), name='departments-public'),
    path('departments/<int:pk>/', DepartmentDetailView.as_view(), name='department-detail'),
    path('departments/<int:department_id>/participants/', DepartmentParticipantsView.as_view(), name='department-participants'),
    
    # Department admin management
    path('assign-department-admin/', AssignDepartmentAdminView.as_view(), name='assign-department-admin'),
    path('department-admins/', DepartmentAdminsView.as_view(), name='department-admins'),
    
    # Public endpoints
    path('public-stats/', get_public_stats, name='public-stats'),
]