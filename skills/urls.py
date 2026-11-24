from django.urls import path

from . import views

app_name = 'skills'

urlpatterns = [
    # Skills CRUD
    path('', views.SkillListView.as_view(), name='skill_list'),
    path('create/', views.SkillCreateView.as_view(), name='skill_create'),
    path('<int:pk>/edit/', views.SkillUpdateView.as_view(), name='skill_edit'),
    path('<int:pk>/toggle-active/', views.SkillToggleActiveView.as_view(), name='skill_toggle_active'),

    # Categories CRUD
    path('categories/', views.SkillCategoryListView.as_view(), name='category_list'),
    path('categories/create/', views.SkillCategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/edit/', views.SkillCategoryUpdateView.as_view(), name='category_edit'),

    # Role Profiles CRUD
    path('role-profiles/', views.RoleProfileListView.as_view(), name='role_profile_list'),
    path('role-profiles/create/', views.RoleProfileCreateView.as_view(), name='role_profile_create'),
    path('role-profiles/<int:pk>/', views.RoleProfileDetailView.as_view(), name='role_profile_detail'),
    path('role-profiles/<int:pk>/edit/', views.RoleProfileUpdateView.as_view(), name='role_profile_edit'),
    path('role-profiles/<int:pk>/skills/add/', views.RoleSkillAddView.as_view(), name='role_skill_add'),
    path('role-profiles/<int:role_pk>/skills/<int:pk>/delete/', views.RoleSkillDeleteView.as_view(), name='role_skill_delete'),
]
