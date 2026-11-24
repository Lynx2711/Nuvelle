from django.urls import path

from . import views

app_name = 'profiles'

urlpatterns = [
    # Student Profile Management
    path('me/', views.StudentProfileEditView.as_view(), name='profile_edit'),
    path('skills/add/', views.StudentSkillAddView.as_view(), name='skill_add'),
    path('skills/<int:pk>/edit/', views.StudentSkillEditView.as_view(), name='skill_edit'),
    path('skills/<int:pk>/delete/', views.StudentSkillDeleteView.as_view(), name='skill_delete'),
    path('projects/add/', views.ProjectCreateView.as_view(), name='project_add'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('certifications/add/', views.CertificationCreateView.as_view(), name='certification_add'),
    path('certifications/<int:pk>/delete/', views.CertificationDeleteView.as_view(), name='certification_delete'),

    # Faculty & Officer Verification Queue
    path('verification-queue/', views.FacultyVerificationQueueView.as_view(), name='verification_queue'),
    path('skills/<int:pk>/approve/', views.ApproveSkillView.as_view(), name='approve_skill'),
    path('skills/<int:pk>/reject/', views.RejectSkillView.as_view(), name='reject_skill'),
    path('skills/<int:pk>/adjust/', views.AdjustSkillLevelView.as_view(), name='adjust_skill'),

    # Student Batches & CSV Import
    path('students/', views.StudentListView.as_view(), name='student_list'),
    path('students/<int:pk>/', views.StudentProfileDetailView.as_view(), name='student_detail'),
    path('students/import-csv/', views.StudentCSVImportView.as_view(), name='import_students'),
    path('students/import-report/', views.ImportReportView.as_view(), name='import_report'),
    path('students/import-report/download/', views.DownloadImportErrorReportView.as_view(), name='download_error_report'),
]
