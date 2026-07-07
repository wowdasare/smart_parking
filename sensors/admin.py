from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html

from .models import GateEvent, SensorDevice


class OnlineStatusFilter(admin.SimpleListFilter):
    title = 'online status'
    parameter_name = 'online'

    def lookups(self, request, model_admin):
        return (('online', 'Online'), ('offline', 'Offline'))

    def queryset(self, request, queryset):
        threshold = timezone.now() - timedelta(minutes=settings.SENSOR_OFFLINE_THRESHOLD_MINUTES)
        if self.value() == 'online':
            return queryset.filter(last_seen_at__gte=threshold)
        if self.value() == 'offline':
            return queryset.filter(Q(last_seen_at__lt=threshold) | Q(last_seen_at__isnull=True))
        return queryset


@admin.register(SensorDevice)
class SensorDeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'device_type', 'assigned_to', 'is_active', 'online_badge', 'last_seen_at')
    list_filter = ('device_type', 'is_active', OnlineStatusFilter)
    search_fields = ('device_id',)
    autocomplete_fields = ('slot', 'zone')
    readonly_fields = ('api_key', 'last_seen_at', 'created_at')

    @admin.display(description='Assigned to')
    def assigned_to(self, obj):
        if obj.slot_id:
            return f'Slot {obj.slot}'
        if obj.zone_id:
            return f'Zone {obj.zone}'
        return '—'

    @admin.display(description='Status')
    def online_badge(self, obj):
        color = '#1e8a5f' if obj.is_online else '#c8433d'
        label = 'Online' if obj.is_online else 'Offline'
        return format_html('<span style="color: {}; font-weight: 600;">● {}</span>', color, label)


@admin.register(GateEvent)
class GateEventAdmin(admin.ModelAdmin):
    list_display = ('zone', 'event_type', 'device', 'plate_number', 'recorded_at')
    list_filter = ('event_type', 'zone')
    search_fields = ('plate_number', 'zone__name', 'zone__code', 'device__device_id')
    autocomplete_fields = ('zone', 'device')

    def has_change_permission(self, request, obj=None):
        return False  # events are a log of what happened — not meant to be edited after the fact
