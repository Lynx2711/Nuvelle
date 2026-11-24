from django.urls import path

from . import views

app_name = 'matching'

urlpatterns = [
    # Gap Reports
    path('opportunity/<int:opp_pk>/gap-report/', views.OpportunityGapReportView.as_view(), name='opportunity_gap_report'),
    path('role/<int:role_pk>/gap-report/', views.RoleProfileGapReportView.as_view(), name='role_gap_report'),

    # Institutional Analytics & Market Insights
    path('batch-skill-map/', views.BatchSkillMapView.as_view(), name='batch_skill_map'),
    path('market-demand/', views.MarketDemandView.as_view(), name='market_demand'),
]
