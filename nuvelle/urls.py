from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard_redirect')
    return redirect('accounts:login')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('orgs/', include('orgs.urls')),
    path('skills/', include('skills.urls')),
    path('profiles/', include('profiles.urls')),
    path('opportunities/', include('opportunities.urls')),
    path('applications/', include('applications.urls')),
    path('matching/', include('matching.urls')),
    path('notifications/', include('notifications.urls')),
    path('drives/', include('drives.urls')),
    path('reports/', include('reports.urls')),
    path('', home_redirect, name='home'),
]

handler403 = 'nuvelle.views.handler403'
handler404 = 'nuvelle.views.handler404'
handler500 = 'nuvelle.views.handler500'
