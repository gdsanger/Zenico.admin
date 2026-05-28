from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.views.generic import FormView
from django.contrib import messages


class LoginView(FormView):
    """
    Login view for admin users.
    """
    template_name = 'ui/login.html'
    form_class = AuthenticationForm

    def form_valid(self, form):
        user = form.get_user()
        auth_login(self.request, user)
        messages.success(self.request, f'Willkommen zurück, {user.display_name}!')

        # Redirect to next URL or dashboard
        next_url = self.request.GET.get('next', '/')
        return redirect(next_url)

    def form_invalid(self, form):
        messages.error(self.request, 'Ungültige E-Mail oder Passwort.')
        return super().form_invalid(form)

    def get(self, request, *args, **kwargs):
        # Redirect to dashboard if already authenticated
        if request.user.is_authenticated:
            return redirect('/')
        return super().get(request, *args, **kwargs)


def logout_view(request):
    """
    Logout view.
    """
    auth_logout(request)
    messages.info(request, 'Sie wurden erfolgreich abgemeldet.')
    return redirect('login')
