from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import render


def role_required(*allowed_roles):
    """
    Decorator to restrict view access based on user role.

    Usage:
        @role_required('superadmin', 'support')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # login_required should handle this, but just in case
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if request.user.role not in allowed_roles:
                return render(request, '403.html', status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
