from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def notification_list(request):
    return render(request, 'notifications/notification_list.html')
