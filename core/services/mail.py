"""
MailService - Email sending via Microsoft Graph API.

Sends emails using Azure AD Client Credentials Flow with a shared mailbox.
All email operations are logged via AuditService.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Union
from django.template.loader import render_to_string
from django.conf import settings
import msal
import requests

from core.services.audit import AuditService, AuditAction

logger = logging.getLogger(__name__)


class MailService:
    """
    Service for sending emails via Microsoft Graph API using MSAL.

    Configuration (environment variables):
        AZURE_TENANT_ID: Azure AD tenant ID
        AZURE_CLIENT_ID: Application (client) ID
        AZURE_CLIENT_SECRET: Client secret
        MAIL_FROM_ADDRESS: Email address to send from (e.g., admin@zenico.app)
        MAIL_FROM_NAME: Display name for sender (e.g., Zenico Admin)
    """

    _msal_app: Optional[msal.ConfidentialClientApplication] = None

    @classmethod
    def _get_msal_app(cls) -> msal.ConfidentialClientApplication:
        """Get or create MSAL confidential client application."""
        if cls._msal_app is None:
            tenant_id = os.getenv('AZURE_TENANT_ID')
            client_id = os.getenv('AZURE_CLIENT_ID')
            client_secret = os.getenv('AZURE_CLIENT_SECRET')

            if not all([tenant_id, client_id, client_secret]):
                missing_keys = [
                    key
                    for key, value in {
                        'AZURE_TENANT_ID': tenant_id,
                        'AZURE_CLIENT_ID': client_id,
                        'AZURE_CLIENT_SECRET': client_secret,
                    }.items()
                    if not value
                ]
                logger.error(
                    'Missing required Azure AD configuration for Graph email sending: %s',
                    ', '.join(missing_keys) if missing_keys else '(unknown)',
                )
                raise ValueError(
                    'Missing required Azure AD configuration. '
                    'Ensure AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET are set.'
                )

            authority = f'https://login.microsoftonline.com/{tenant_id}'
            cls._msal_app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret,
            )

        return cls._msal_app

    @classmethod
    def _get_access_token(cls) -> str:
        """Acquire access token for Microsoft Graph API."""
        app = cls._get_msal_app()
        scopes = ['https://graph.microsoft.com/.default']

        result = app.acquire_token_for_client(scopes=scopes)

        if 'access_token' in result:
            return result['access_token']
        else:
            error = result.get('error', 'unknown_error')
            error_description = result.get('error_description', 'No description available')
            correlation_id = result.get('correlation_id') or result.get('correlationId')
            trace_id = result.get('trace_id') or result.get('traceId')
            logger.error(
                'Failed to acquire Graph access token via MSAL: error=%s correlation_id=%s trace_id=%s description=%s',
                error,
                correlation_id,
                trace_id,
                error_description,
            )
            raise Exception(f'Failed to acquire access token: {error} - {error_description}')

    @classmethod
    def send(
        cls,
        to: Union[str, list[str]],
        subject: str,
        html_body: str,
        text_body: str = "",
        cc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """
        Send an email via Microsoft Graph API.

        Args:
            to: Recipient email address or list of addresses
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
            cc: List of CC recipients (optional)
            reply_to: Reply-to email address (optional)

        Returns:
            bool: True if email was sent successfully, False otherwise

        Side effects:
            Creates an AuditLog entry (mail.sent or mail.failed)
        """
        from_address = settings.MAIL_FROM_ADDRESS
        from_name = settings.MAIL_FROM_NAME

        # Normalize to list
        if isinstance(to, str):
            to = [to]

        # Build recipient list
        recipients = [{'emailAddress': {'address': addr}} for addr in to]
        cc_recipients = [{'emailAddress': {'address': addr}} for addr in (cc or [])]

        # Build message
        message = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'HTML',
                    'content': html_body,
                },
                'toRecipients': recipients,
            },
            'saveToSentItems': True,
        }

        if cc_recipients:
            message['message']['ccRecipients'] = cc_recipients

        if reply_to:
            message['message']['replyTo'] = [{'emailAddress': {'address': reply_to}}]

        try:
            # Get access token
            token = cls._get_access_token()

            # Send email via Graph API
            url = f'https://graph.microsoft.com/v1.0/users/{from_address}/sendMail'
            client_request_id = str(uuid.uuid4())
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'client-request-id': client_request_id,
                'return-client-request-id': 'true',
            }

            response = requests.post(url, json=message, headers=headers, timeout=30)

            if response.status_code == 202:
                # Success
                AuditService.log(
                    action=AuditAction.MAIL_SENT,
                    resource_type='Email',
                    resource_id=subject,
                    after={
                        'to': to,
                        'cc': cc,
                        'subject': subject,
                    },
                    note=f'Email sent to {", ".join(to)}',
                )
                logger.info(f'Email sent successfully to {", ".join(to)}: {subject}')
                return True
            else:
                # Failure
                def _header(name: str) -> Optional[str]:
                    try:
                        value = response.headers.get(name)
                    except Exception:
                        return None
                    if value is None:
                        return None
                    return str(value)

                request_id = _header('request-id') or _header('x-ms-request-id') or _header('client-request-id')
                error_msg = (
                    f'HTTP {response.status_code} (request_id={request_id}, client_request_id={client_request_id}): '
                    f'{response.text}'
                )
                AuditService.log(
                    action=AuditAction.MAIL_FAILED,
                    resource_type='Email',
                    resource_id=subject,
                    after={
                        'to': to,
                        'cc': cc,
                        'subject': subject,
                        'error': error_msg,
                        'request_id': request_id,
                        'client_request_id': client_request_id,
                    },
                    note=f'Failed to send email to {", ".join(to)}: {error_msg}',
                )
                logger.error(f'Failed to send email: {error_msg}')
                return False

        except Exception as e:
            # Exception during send
            error_msg = str(e)
            AuditService.log(
                action=AuditAction.MAIL_FAILED,
                resource_type='Email',
                resource_id=subject,
                after={
                    'to': to,
                    'cc': cc,
                    'subject': subject,
                    'error': error_msg,
                },
                note=f'Exception while sending email to {", ".join(to)}: {error_msg}',
            )
            logger.exception(f'Exception while sending email: {error_msg}')
            return False

    @classmethod
    def send_template(
        cls,
        to: Union[str, list[str]],
        template: str,
        context: dict,
        subject_override: Optional[str] = None,
    ) -> bool:
        """
        Render a Django template and send it as an email.

        Templates should be located in templates/mail/<template>.html and .txt
        The template can define a subject variable or use subject_override.

        Args:
            to: Recipient email address or list of addresses
            template: Template name (without path or extension, e.g., 'welcome')
            context: Context dict for template rendering
            subject_override: Override the subject from template (optional)

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        # Add base context that's available to all templates
        base_context = {
            'admin_base_url': settings.ADMIN_BASE_URL,
            'frontend_base_url': settings.FRONTEND_BASE_URL,
            'mail_from_name': settings.MAIL_FROM_NAME,
            'current_year': datetime.now().year,
        }

        # Merge user context with base context (user context takes precedence)
        full_context = {**base_context, **context}

        html_template_path = f'mail/{template}.html'
        text_template_path = f'mail/{template}.txt'

        try:
            # Render HTML template
            html_body = render_to_string(html_template_path, full_context)

            # Try to render text template, fallback to empty string if not found
            try:
                text_body = render_to_string(text_template_path, full_context)
            except Exception:
                text_body = ""

            # Extract subject from context or use override
            subject = subject_override or full_context.get('subject', 'Zenico Admin Notification')

            # Send email with both HTML and text
            return cls.send(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )

        except Exception as e:
            logger.exception(f'Failed to render template {html_template_path}: {e}')
            AuditService.log(
                action=AuditAction.MAIL_FAILED,
                resource_type='Email',
                resource_id=template,
                after={
                    'to': to if isinstance(to, list) else [to],
                    'template': template,
                    'error': str(e),
                },
                note=f'Failed to render email template {template}: {str(e)}',
            )
            return False
