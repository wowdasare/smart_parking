from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'vehicle', 'slot', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'slot__zone')
    search_fields = ('reference', 'user__username', 'vehicle__registration_number')
    date_hierarchy = 'start_time'
    autocomplete_fields = ('user', 'vehicle', 'slot')
    readonly_fields = ('reference', 'checked_in_at', 'checked_out_at', 'cancelled_at', 'created_at', 'updated_at')
