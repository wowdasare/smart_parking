from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('manage/users/', views.manage_users, name='manage_users'),
    path('manage/vehicles/', views.manage_vehicles, name='manage_vehicles'),
    path('manage/zones/', views.manage_zones, name='manage_zones'),
]
