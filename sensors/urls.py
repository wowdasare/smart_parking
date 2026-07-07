from django.urls import path

from . import views

app_name = 'sensors'

urlpatterns = [
    path('slot/<int:slot_id>/status/', views.SlotStatusReportView.as_view(), name='slot-status-report'),
    path('zone/<int:zone_id>/event/', views.GateEventView.as_view(), name='zone-gate-event'),
]
