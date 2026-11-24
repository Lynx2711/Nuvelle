from django.urls import path

from . import views

app_name = 'drives'

urlpatterns = [
    # Placement Drives
    path('', views.PlacementDriveListView.as_view(), name='drive_list'),
    path('create/', views.PlacementDriveCreateView.as_view(), name='drive_create'),
    path('<int:pk>/', views.PlacementDriveDetailView.as_view(), name='drive_detail'),
    path('<int:drive_pk>/rounds/create/', views.DriveRoundCreateView.as_view(), name='round_create'),
    path('<int:drive_pk>/eligible-students/', views.EligibleStudentsView.as_view(), name='eligible_students'),

    # Offers
    path('application/<int:app_pk>/offer/', views.CreateOfferForApplicationView.as_view(), name='create_offer'),
    path('my-offers/', views.StudentOfferListView.as_view(), name='student_offers'),
    path('offer/<int:pk>/', views.OfferDetailView.as_view(), name='offer_detail'),
    path('offer/<int:pk>/<str:action>/', views.OfferRespondView.as_view(), name='offer_respond'),
]
