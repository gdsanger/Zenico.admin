"""
Public REST API endpoints for Newsletter.

These endpoints are called by zenico.web and do not require authentication.
Rate limiting and CORS are applied.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.utils import timezone
import os

from newsletter.models import Subscriber, AutomationSequence, SequenceEnrollment
from core.services.mail import MailService
from core.services.audit import AuditService, AuditAction


@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='dispatch')
class SubscribeAPIView(APIView):
    """
    POST /api/newsletter/subscribe/

    Newsletter subscription from zenico.web.
    """

    def post(self, request):
        """
        Handle newsletter subscription.

        Request body:
        {
            "email": "max@example.com",
            "first_name": "Max",
            "ip_address": "1.2.3.4"
        }
        """
        # Extract data
        data = request.data
        email = data.get('email', '').strip()
        first_name = data.get('first_name', '').strip()
        ip_address = data.get('ip_address', request.META.get('REMOTE_ADDR'))

        # Validate required fields
        if not email:
            return Response(
                {'error': 'email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create or get subscriber
        subscriber, created = Subscriber.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'source': 'web_form',
                'status': 'active',
                'ip_address': ip_address,
            }
        )

        # If already exists but unsubscribed, reactivate
        if not created and subscriber.status == 'unsubscribed':
            subscriber.status = 'active'
            subscriber.confirmed_at = None  # Reset confirmation
            subscriber.save()

        # Send double-opt-in email
        confirmation_url = f"https://zenico.app/api/newsletter/confirm/{subscriber.unsubscribe_token}/"
        MailService.send_template(
            to=email,
            template='newsletter_doi',
            context={
                'first_name': first_name,
                'confirmation_url': confirmation_url,
                'subject': 'Newsletter-Anmeldung bestätigen – Zenico'
            }
        )

        # Log audit
        AuditService.log(
            action=AuditAction.SUBSCRIBER_CREATED,
            resource_type='Subscriber',
            resource_id=str(subscriber.id),
            actor_email='system',
            actor_ip=ip_address,
            after={
                'email': email,
                'first_name': first_name,
                'source': 'web_form',
            },
            note=f'Subscriber created from web form: {email}'
        )

        # Always return 201 (even if already exists) to prevent email enumeration
        return Response(
            {'message': 'Subscription successful. Please check your email to confirm.'},
            status=status.HTTP_201_CREATED
        )


class ConfirmAPIView(APIView):
    """
    GET /api/newsletter/confirm/<token>/

    Double-opt-in confirmation.
    """

    def get(self, request, token):
        """
        Handle newsletter confirmation via double-opt-in token.
        """
        # Find subscriber by token
        try:
            subscriber = Subscriber.objects.get(unsubscribe_token=token)
        except Subscriber.DoesNotExist:
            return redirect('https://zenico.app/?error=invalid_token')

        # Set confirmed_at if not already confirmed
        if not subscriber.confirmed_at:
            subscriber.confirmed_at = timezone.now()
            subscriber.save()

            # Send confirmation email
            unsubscribe_url = f"https://zenico.app/api/newsletter/unsubscribe/{subscriber.unsubscribe_token}/"
            MailService.send_template(
                to=subscriber.email,
                template='newsletter_confirmed',
                context={
                    'first_name': subscriber.first_name,
                    'unsubscribe_url': unsubscribe_url,
                    'subject': 'Newsletter-Anmeldung bestätigt – Zenico'
                }
            )

            # Enroll in automation sequences with trigger=subscriber_confirmed
            sequences = AutomationSequence.objects.filter(
                trigger='subscriber_confirmed',
                is_active=True
            )

            for sequence in sequences:
                # Check if not already enrolled
                if not SequenceEnrollment.objects.filter(
                    sequence=sequence,
                    subscriber=subscriber
                ).exists():
                    enrollment = SequenceEnrollment.objects.create(
                        sequence=sequence,
                        subscriber=subscriber,
                        status='active',
                        current_step=0,
                        next_send_at=timezone.now(),  # Send first step immediately
                    )

                    # Log audit
                    AuditService.log(
                        action=AuditAction.SEQUENCE_ENROLLED,
                        resource_type='SequenceEnrollment',
                        resource_id=str(enrollment.id),
                        actor_email='system',
                        after={
                            'sequence': sequence.name,
                            'subscriber': subscriber.email,
                        },
                        note=f'Subscriber {subscriber.email} enrolled in sequence {sequence.name}'
                    )

            # Log audit
            AuditService.log(
                action=AuditAction.SUBSCRIBER_CONFIRMED,
                resource_type='Subscriber',
                resource_id=str(subscriber.id),
                actor_email='system',
                after={
                    'email': subscriber.email,
                    'confirmed_at': subscriber.confirmed_at.isoformat(),
                },
                note=f'Subscriber confirmed: {subscriber.email}'
            )

        # Redirect to thank you page
        return redirect('https://zenico.app/?confirmed=1')


class UnsubscribeAPIView(APIView):
    """
    GET /api/newsletter/unsubscribe/<token>/

    Unsubscribe from newsletter.
    """

    def get(self, request, token):
        """
        Handle newsletter unsubscription via token.
        """
        # Find subscriber by token
        try:
            subscriber = Subscriber.objects.get(unsubscribe_token=token)
        except Subscriber.DoesNotExist:
            return redirect('https://zenico.app/?error=invalid_token')

        # Set status to unsubscribed
        if subscriber.status != 'unsubscribed':
            subscriber.status = 'unsubscribed'
            subscriber.unsubscribed_at = timezone.now()
            subscriber.save()

            # Cancel all active sequence enrollments
            active_enrollments = SequenceEnrollment.objects.filter(
                subscriber=subscriber,
                status='active'
            )

            for enrollment in active_enrollments:
                enrollment.status = 'cancelled'
                enrollment.save()

            # Log audit
            AuditService.log(
                action=AuditAction.SUBSCRIBER_UNSUBSCRIBED,
                resource_type='Subscriber',
                resource_id=str(subscriber.id),
                actor_email='system',
                after={
                    'email': subscriber.email,
                    'unsubscribed_at': subscriber.unsubscribed_at.isoformat(),
                },
                note=f'Subscriber unsubscribed: {subscriber.email}'
            )

        # Redirect to unsubscribe confirmation page
        return redirect('https://zenico.app/?unsubscribed=1')
