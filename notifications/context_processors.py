from .services import get_unread_notifications_count


def unread_notifications(request):
    """
    Injects `unread_notifications_count` into template context for all views.
    """
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return {
            'unread_notifications_count': get_unread_notifications_count(request.user),
        }
    return {
        'unread_notifications_count': 0,
    }
