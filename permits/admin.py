from django.contrib import admin

from .models import Permit


@admin.register(Permit)
class PermitAdmin(admin.ModelAdmin):
    list_display = ('permit_number', 'holder', 'vehicle', 'permit_type', 'status',
                    'valid_from', 'valid_until', 'is_paid')
    list_filter = ('status', 'permit_type', 'is_paid', 'zone')
    search_fields = ('permit_number', 'holder__username', 'vehicle__registration_number')
    date_hierarchy = 'valid_from'
    autocomplete_fields = ('holder', 'vehicle', 'zone')
    readonly_fields = ('permit_number', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at')
