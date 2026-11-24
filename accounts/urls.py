from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    # Auth views
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify-email/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset/confirm/<str:token>/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # Role dashboards
    path('dashboard/', views.DashboardRedirectView.as_view(), name='dashboard_redirect'),
    path('dashboard/student/', views.StudentDashboardView.as_view(), name='student_dashboard'),
    path('dashboard/faculty/', views.FacultyDashboardView.as_view(), name='faculty_dashboard'),
    path('dashboard/recruiter/', views.RecruiterDashboardView.as_view(), name='recruiter_dashboard'),
    path('dashboard/officer/', views.OfficerDashboardView.as_view(), name='officer_dashboard'),
    path('dashboard/admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
]
