from django.core.management.base import BaseCommand
from accounts.models import AdminUser


class Command(BaseCommand):
    help = 'Create a test superadmin user'

    def handle(self, *args, **options):
        if not AdminUser.objects.filter(email='admin@zenico.app').exists():
            user = AdminUser.objects.create_superuser(
                email='admin@zenico.app',
                password='admin123',
                display_name='Admin User'
            )
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created superadmin: {user.email}')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Superadmin already exists')
            )
