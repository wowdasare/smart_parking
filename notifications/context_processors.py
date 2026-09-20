from .models import Notification


def unread_count(request):
    """Makes the navbar's unread badge available on every page.

    A context processor rather than a template tag because the badge appears
    in base.html, so every single view would otherwise have to remember to
    put the count in its own context.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'unread_notification_count': 0}

    return {
        'unread_notification_count': Notification.objects.filter(
            recipient=user, is_read=False
        ).count(),
    }
