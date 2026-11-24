from django.urls import path

from . import views

app_name = 'orgs'

urlpatterns = [
    path('manage/', views.ManageOrgsView.as_view(), name='manage_orgs'),
    path('institutions/create/', views.InstitutionCreateView.as_view(), name='institution_create'),
    path('institutions/<int:pk>/toggle-approval/', views.ToggleInstitutionApprovalView.as_view(), name='toggle_institution_approval'),
    path('companies/create/', views.CompanyCreateView.as_view(), name='company_create'),
    path('companies/<int:pk>/toggle-approval/', views.ToggleCompanyApprovalView.as_view(), name='toggle_company_approval'),
]
