from django.urls import path

from . import views

app_name = 'reservations'

urlpatterns = [
    path('', views.reservation_list, name='list'),
    path('new/', views.reservation_create, name='create'),
    path('<int:pk>/', views.reservation_detail, name='detail'),
    path('<int:pk>/cancel/', views.reservation_cancel, name='cancel'),
    path('gate/', views.gate_verify, name='gate_verify'),
    path('gate/<int:pk>/action/', views.gate_action, name='gate_action'),
]
