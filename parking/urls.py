from django.urls import path

from . import views

app_name = 'parking'

urlpatterns = [
    path('', views.zone_list, name='zone_list'),
]
