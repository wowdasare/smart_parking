from django.contrib import admin
from django.utils import timezone

from .models import ParkingSlot, SlotStatusChangeLog, Zone
from .services import log_manual_status_change


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'current_occupancy', 'capacity', 'description')
    search_fields = ('name', 'code')
    readonly_fields = ('current_occupancy',)


@admin.register(ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'zone', 'slot_number', 'status', 'status_changed_at', 'manual_override_at', 'sensor')
    list_filter = ('zone', 'status')
    search_fields = ('slot_number', 'zone__name', 'zone__code')
    autocomplete_fields = ('zone',)
    readonly_fields = ('status_changed_at', 'manual_override_at', 'created_at')

    @admin.display(description='Sensor')
    def sensor(self, obj):
        device = getattr(obj, 'sensor_device', None)
        return device.device_id if device else '—'

    def save_model(self, request, obj, form, change):
        """A manual admin edit is a "manual override" for conflict-resolution
        purposes. Django's ModelForm already mutates `obj.status` to the new
        value before this runs, so update_slot_status's before/after
        comparison doesn't apply cleanly here — instead we stamp
        manual_override_at pre-save (so it's persisted in the same write as
        everything else the admin changed) and log it after, using
        form.initial for the pre-edit value.
        """
        if change and 'status' in form.changed_data:
            previous_status = form.initial['status']
            obj.manual_override_at = timezone.now()
            super().save_model(request, obj, form, change)
            log_manual_status_change(obj, previous_status, request.user)
        else:
            super().save_model(request, obj, form, change)


@admin.register(SlotStatusChangeLog)
class SlotStatusChangeLogAdmin(admin.ModelAdmin):
    list_display = ('slot', 'source', 'previous_status', 'attempted_status', 'applied', 'device_id', 'changed_by', 'changed_at')
    list_filter = ('source', 'applied')
    search_fields = ('slot__slot_number', 'device_id', 'changed_by__username')
    autocomplete_fields = ('slot', 'changed_by')

    def has_change_permission(self, request, obj=None):
        return False  # a log of what happened — not meant to be edited after the fact
