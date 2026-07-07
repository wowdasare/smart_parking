from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def reservation_list(request):
    return render(request, 'reservations/reservation_list.html')
