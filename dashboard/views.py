from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from accounts.models import User
from parking.models import ParkingSlot, Zone
from vehicles.models import Vehicle


@login_required
def home(request):
    if request.user.role == User.Role.ADMIN:
        context = {
            'total_users': User.objects.count(),
            'total_students': User.objects.filter(role=User.Role.STUDENT).count(),
            'total_staff': User.objects.filter(role=User.Role.STAFF).count(),
            'total_vehicles': Vehicle.objects.count(),
            'total_zones': Zone.objects.count(),
            'available_slots': ParkingSlot.objects.filter(status=ParkingSlot.Status.AVAILABLE).count(),
        }
        return render(request, 'dashboard/admin_dashboard.html', context)

    if request.user.role == User.Role.SECURITY:
        context = {
            'active_entries': Zone.objects.aggregate(total=Sum('current_occupancy'))['total'] or 0,
            'available_slots': ParkingSlot.objects.filter(status=ParkingSlot.Status.AVAILABLE).count(),
        }
        return render(request, 'dashboard/security_dashboard.html', context)

    context = {
        'vehicle_count': request.user.vehicles.count(),
        'available_slots': ParkingSlot.objects.filter(status=ParkingSlot.Status.AVAILABLE).count(),
    }
    return render(request, 'dashboard/user_dashboard.html', context)
