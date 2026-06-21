"""
Permission class for the internal Provisioning Agent API.

The agent authenticates via a static bearer token configured in settings,
distinct from the instance API-key authentication used by Zenico.app instances.
"""

import hmac
from django.conf import settings
from rest_framework.permissions import BasePermission


class IsProvisioningAgent(BasePermission):
    """
    Validates the Authorization: Bearer <token> header against
    settings.PROVISIONING_AGENT_TOKEN using constant-time comparison.
    """

    def has_permission(self, request, view):
        expected = getattr(settings, 'PROVISIONING_AGENT_TOKEN', '')
        if not expected:
            return False

        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return False

        provided = auth.split(' ', 1)[1].strip()
        return hmac.compare_digest(provided.encode(), expected.encode())
