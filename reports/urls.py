from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('placement-statistics/', views.PlacementStatisticsView.as_view(), name='placement_statistics'),
    path('placement-statistics/pdf/', views.ExportPlacementReportPdfView.as_view(), name='export_pdf'),
    path('placement-statistics/csv/', views.ExportPlacementReportCsvView.as_view(), name='export_csv'),
]
