from django.urls import path

from . import views

app_name = 'applications'

urlpatterns = [
    # Student Application Actions
    path('apply/<int:opp_pk>/', views.ApplyOpportunityView.as_view(), name='apply'),
    path('my/', views.StudentApplicationListView.as_view(), name='student_applications'),
    path('<int:pk>/withdraw/', views.WithdrawApplicationView.as_view(), name='withdraw'),

    # Recruiter Applicant Tracking & Management
    path('opportunity/<int:opp_pk>/', views.RecruiterApplicantListView.as_view(), name='applicant_list'),
    path('opportunity/<int:opp_pk>/bulk-status/', views.BulkStatusChangeView.as_view(), name='bulk_status'),
    path('opportunity/<int:opp_pk>/export-csv/', views.ExportApplicantsCSVView.as_view(), name='export_csv'),
    path('<int:pk>/status-change/', views.SingleStatusChangeView.as_view(), name='status_change'),
]
