from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import Notification
from .services import mark_all_read


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    context = {
        'notifications': notifications,
        'unread_count': notifications.filter(is_read=False).count(),
    }
    return render(request, 'notifications/notification_list.html', context)


@login_required
def notification_mark_read(request):
    """Marks everything read. POST only — this mutates state."""
    if request.method != 'POST':
        return redirect('notifications:list')

    updated = mark_all_read(request.user)
    if updated:
        messages.success(request, f'{updated} alert{"s" if updated != 1 else ""} marked as read.')
    return redirect('notifications:list')
