"""
Public REST API endpoints for CRM.

These endpoints are called by zenico.web and do not require authentication.
Rate limiting and CORS are applied.
"""

import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.conf import settings

from crm.models import Contact
from newsletter.models import Subscriber
from core.services.mail import MailService
from core.services.audit import AuditService, AuditAction

logger = logging.getLogger(__name__)


@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='dispatch')
class ContactCreateAPIView(APIView):
    """
    POST /api/contacts/

    Create a new contact from the zenico.web contact form.
    """

    def post(self, request):
        """
        Handle incoming contact request.

        Request body:
        {
            "first_name": "Max",
            "last_name": "Mustermann",
            "email": "max@example.com",
            "phone": "",
            "company": "Muster GmbH",
            "message": "Ich hätte Interesse an Zenico...",
            "newsletter_consent": true,
            "ip_address": "1.2.3.4"
        }
        """
        # Extract data
        data = request.data
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        company = data.get('company', '').strip()
        message = data.get('message', '').strip()
        newsletter_consent = data.get('newsletter_consent', False)
        ip_address = data.get('ip_address', request.META.get('REMOTE_ADDR'))

        # Validate required fields
        if not all([first_name, last_name, email]):
            return Response(
                {'error': 'first_name, last_name, and email are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create contact
        contact = Contact.objects.create(
            source='web_contact',
            status='new',
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            company=company,
            message=message,
            newsletter_consent=newsletter_consent,
            ip_address=ip_address,
        )

        # Track email sending results
        email_results = {
            'contact_confirmation': False,
            'admin_notification': False,
            'newsletter_doi': False
        }

        # If newsletter consent, create or reactivate subscriber
        if newsletter_consent:
            subscriber, created = Subscriber.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'source': 'contact_form',
                    'status': 'active',
                    'ip_address': ip_address,
                    'contact': contact,
                }
            )

            # If already exists but unsubscribed, reactivate
            if not created and subscriber.status == 'unsubscribed':
                subscriber.status = 'active'
                subscriber.contact = contact
                subscriber.save()

            # Send double-opt-in email
            confirmation_url = f"{settings.ADMIN_BASE_URL}/api/newsletter/confirm/{subscriber.unsubscribe_token}/"
            email_results['newsletter_doi'] = MailService.send_template(
                to=email,
                template='newsletter_doi',
                context={
                    'first_name': first_name,
                    'confirmation_url': confirmation_url,
                    'subject': 'Newsletter-Anmeldung bestätigen – Zenico'
                }
            )

        # Send confirmation email to contact
        email_results['contact_confirmation'] = MailService.send_template(
            to=email,
            template='contact_confirmation',
            context={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'company': company,
                'message': message,
                'subject': 'Ihre Anfrage bei Zenico – Bestätigung'
            }
        )

        # Send notification email to admin
        admin_url = f"{settings.ADMIN_BASE_URL}/crm/contacts/{contact.id}/"
        email_results['admin_notification'] = MailService.send_template(
            to=settings.ADMIN_NOTIFICATION_EMAIL,
            template='contact_notification',
            context={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'company': company,
                'message': message,
                'newsletter_consent': newsletter_consent,
                'ip_address': ip_address,
                'admin_url': admin_url,
                'subject': 'Neue Kontaktanfrage über zenico.web'
            }
        )

        # Log audit with email results
        AuditService.log(
            action=AuditAction.CONTACT_CREATED,
            resource_type='Contact',
            resource_id=str(contact.id),
            actor_email='system',
            actor_ip=ip_address,
            after={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'company': company,
                'newsletter_consent': newsletter_consent,
                'email_results': email_results,
            },
            note=f'Contact created from web form: {email}. Emails sent: {sum(email_results.values())}/{"3" if newsletter_consent else "2"}'
        )

        # Log warning if any emails failed
        failed_emails = [k for k, v in email_results.items() if not v]
        if failed_emails:
            logger.warning(
                f'Failed to send emails for contact {contact.id} ({email}): {", ".join(failed_emails)}'
            )

        return Response(
            {
                'message': 'Contact created successfully',
                'email_status': email_results
            },
            status=status.HTTP_201_CREATED
        )
