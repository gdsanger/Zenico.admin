from django.contrib.auth.models import AbstractUser
from django.db import models


class AdminUser(AbstractUser):
    """
    Custom user model for Zenico Admin users.
    Extends Django's AbstractUser to allow for future customizations.
    """

    class Meta:
        verbose_name = 'Admin User'
        verbose_name_plural = 'Admin Users'

    def __str__(self):
        return self.username
