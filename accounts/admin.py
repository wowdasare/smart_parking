from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UserRegistrationForm, UserProfileForm
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = UserRegistrationForm
    form = UserProfileForm
    model = User
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Parking profile', {'fields': ('role', 'phone_number')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Parking profile', {'fields': ('email', 'first_name', 'last_name', 'role', 'phone_number')}),
    )
