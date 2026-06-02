"""
Authentication classes for the instances API.
"""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from instances.models import Instance


class ApiKeyAuthentication(BaseAuthentication):
    """
    API Key authentication for instance endpoints.

    Reads the Authorization header in the format: "Api-Key <instance.api_key>"
    Returns (instance, None) if valid.
    Raises AuthenticationFailed for invalid or missing keys.
    Only instances with status='active' are accepted.
    """

    def authenticate(self, request):
        """
        Authenticate the request using the API key from the Authorization header.

        Args:
            request: The HTTP request object

        Returns:
            tuple: (instance, None) if authentication is successful
            None: If no authentication credentials were provided

        Raises:
            AuthenticationFailed: If credentials are invalid
        """
        auth = request.META.get('HTTP_AUTHORIZATION', '')

        # Return None if no auth header (allows other auth methods to try)
        if not auth.startswith('Api-Key '):
            return None

        # Extract the key
        key = auth.split(' ', 1)[1].strip()

        # Look up the instance
        try:
            instance = Instance.objects.select_related(
                'customer', 'subscription__plan'
            ).get(api_key=key, status='active')
        except Instance.DoesNotExist:
            raise AuthenticationFailed('Ungültiger oder inaktiver API-Key.')

        # Check if customer is active
        if not instance.customer.is_active:
            raise AuthenticationFailed('Kunde ist gesperrt.')

        # Return the instance as the "user" (request.user will be the instance)
        return (instance, None)
