from django.urls import path

from . import views

app_name = 'permits'

urlpatterns = [
    path('', views.permit_list, name='list'),
    path('apply/', views.permit_apply, name='apply'),
    path('check/', views.plate_check, name='plate_check'),
    path('<int:pk>/', views.permit_detail, name='detail'),
    path('<int:pk>/document/', views.permit_document, name='document'),
    path('<int:pk>/review/', views.permit_review, name='review'),
    path('<int:pk>/withdraw/', views.permit_withdraw, name='withdraw'),
]
