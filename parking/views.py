from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Zone


@login_required
def zone_list(request):
    zones = Zone.objects.prefetch_related('slots').all()
    return render(request, 'parking/zone_list.html', {'zones': zones})
