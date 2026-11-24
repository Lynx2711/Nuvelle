from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(AccessMixin):
    """Verify that the current user is authenticated and belongs to an allowed role."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if self.allowed_roles and request.user.role not in self.allowed_roles and not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to access this resource.")

        return super().dispatch(request, *args, **kwargs)


class VerifiedRequiredMixin(AccessMixin):
    """Verify that the current user has verified their email."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.is_verified and not request.user.is_superuser:
            raise PermissionDenied("Please verify your email address to access this feature.")

        return super().dispatch(request, *args, **kwargs)


def role_required(*allowed_roles):
    """Decorator for views that checks whether a user has one of the allowed roles."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if allowed_roles and request.user.role not in allowed_roles and not request.user.is_superuser:
                raise PermissionDenied("You do not have permission to access this resource.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def verified_required(view_func):
    """Decorator that checks whether a user is verified."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        if not request.user.is_verified and not request.user.is_superuser:
            raise PermissionDenied("Please verify your email address to access this feature.")

        return view_func(request, *args, **kwargs)
    return _wrapped_view
