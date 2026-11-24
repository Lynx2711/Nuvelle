from django.urls import path

from . import views

app_name = 'opportunities'

urlpatterns = [
    # Public & Student Browsing
    path('', views.OpportunityBrowseView.as_view(), name='opportunity_list'),
    path('<int:pk>/', views.OpportunityPublicDetailView.as_view(), name='opportunity_detail'),

    # Recruiter Opportunity Management
    path('manage/', views.RecruiterOpportunityListView.as_view(), name='recruiter_list'),
    path('create/', views.OpportunityCreateView.as_view(), name='opportunity_create'),
    path('<int:pk>/edit/', views.OpportunityUpdateView.as_view(), name='opportunity_edit'),
    path('<int:pk>/manage/', views.RecruiterOpportunityDetailView.as_view(), name='recruiter_detail'),
    path('<int:pk>/skills/add/', views.OpportunitySkillAddView.as_view(), name='skill_add'),
    path('<int:opp_pk>/skills/<int:pk>/delete/', views.OpportunitySkillDeleteView.as_view(), name='skill_delete'),
    path('<int:pk>/publish/', views.OpportunityPublishView.as_view(), name='opportunity_publish'),
    path('<int:pk>/close/', views.OpportunityCloseView.as_view(), name='opportunity_close'),
]
