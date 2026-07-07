"""
URL configuration for atuparking project.

Each app owns its own urls.py, included below under a namespace matching the
app name (e.g. {% url 'reservations:list' %}). The home page is the only
route that doesn't belong to a specific app.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    path('accounts/', include('accounts.urls')),
    path('vehicles/', include('vehicles.urls')),
    path('reservations/', include('reservations.urls')),
    path('parking/', include('parking.urls')),
    path('notifications/', include('notifications.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('permits/', include('permits.urls')),

    path('api/sensors/', include('sensors.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
