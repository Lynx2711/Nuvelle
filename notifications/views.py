from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from .models import Notification
from .services import mark_all_notifications_as_read, mark_notification_as_read


class NotificationListView(LoginRequiredMixin, ListView):
    """
    Renders user's in-app notification center with read/unread filtering.
    """
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 25

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        filter_type = self.request.GET.get('filter', '').strip()
        if filter_type == 'unread':
            qs = qs.filter(is_read=False)
        elif filter_type == 'read':
            qs = qs.filter(is_read=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['total_count'] = Notification.objects.filter(user=user).count()
        ctx['unread_count'] = Notification.objects.filter(user=user, is_read=False).count()
        ctx['selected_filter'] = self.request.GET.get('filter', 'all')
        return ctx


class MarkNotificationReadView(LoginRequiredMixin, View):
    """
    Marks a single notification as read. Supports both standard POST and HTMX requests.
    """
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        mark_notification_as_read(notification.pk, request.user)

        if request.headers.get('HX-Request'):
            return HttpResponse('<span class="badge bg-light text-muted border">Read</span>')

        messages.success(request, "Notification marked as read.")
        next_url = request.POST.get('next') or request.GET.get('next') or 'notifications:notification_list'
        return redirect(next_url)


class MarkAllNotificationsReadView(LoginRequiredMixin, View):
    """
    Marks all notifications for current user as read.
    """
    def post(self, request):
        count = mark_all_notifications_as_read(request.user)
        messages.success(request, f"Marked {count} notification(s) as read.")
        return redirect('notifications:notification_list')
