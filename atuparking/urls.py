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

from sensors import views as sensor_views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    # Phone-friendly sensor simulator (drives the /api/sensors/ endpoints with
    # no hardware). Short top-level path so it's easy to type on a phone.
    path('simulator/', sensor_views.simulator, name='sensor_simulator'),

    # --- PWA (installable "Add to Home Screen" app) ---------------------------
    # Both files are rendered as templates so {% static %}/{% url %} resolve,
    # and both must be served from the site root: a service worker can only
    # control pages at or below its own path, so /sw.js gives it the whole app.
    path(
        'manifest.webmanifest',
        TemplateView.as_view(
            template_name='manifest.webmanifest',
            content_type='application/manifest+json',
        ),
        name='manifest',
    ),
    path(
        'sw.js',
        TemplateView.as_view(
            template_name='sw.js',
            content_type='text/javascript',
        ),
        name='service_worker',
    ),
    path(
        'offline/',
        TemplateView.as_view(template_name='offline.html'),
        name='offline',
    ),

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
