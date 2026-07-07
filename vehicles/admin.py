from django.contrib import admin

from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'owner', 'vehicle_type', 'make', 'model', 'created_at')
    list_filter = ('vehicle_type',)
    search_fields = ('registration_number', 'owner__username', 'owner__email', 'make', 'model')
    autocomplete_fields = ('owner',)
