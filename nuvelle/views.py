import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def handler403(request, exception=None):
    """Friendly 403 Forbidden error page."""
    context = {
        'title': '403 - Access Forbidden',
        'message': str(exception) if exception else 'You do not have permission to access this resource.',
    }
    return render(request, '403.html', context, status=403)


def handler404(request, exception=None):
    """Friendly 404 Not Found error page."""
    context = {
        'title': '404 - Page Not Found',
        'message': 'The page or resource you are looking for does not exist or has been moved.',
    }
    return render(request, '404.html', context, status=404)


def handler500(request):
    """Friendly 500 Server Error page with logging."""
    logger.exception("Internal Server Error occurred at %s", request.path)
    context = {
        'title': '500 - Server Error',
        'message': 'An unexpected error occurred on our server. Our team has been notified.',
    }
    return render(request, '500.html', context, status=500)
