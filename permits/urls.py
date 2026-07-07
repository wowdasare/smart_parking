from django.urls import path

from . import views

app_name = 'permits'

urlpatterns = [
    path('', views.permit_list, name='list'),
]
