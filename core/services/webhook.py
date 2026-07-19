"""
StripeWebhookHandler - Processes Stripe webhook events with idempotency.

Handles incoming Stripe webhooks, verifies signatures, ensures idempotent processing
via StripeEvent model, and dispatches to appropriate handler methods.
"""

import logging
from typing import Optional
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

import stripe

from billing.models import StripeEvent
from customers.models import Customer, Subscription
from customers.services import CustomerService
from instances.models import Instance
from orders.models import Order
from core.services.audit import AuditService, AuditAction
from core.services.stripe import StripeService
from core.services.mail import MailService

logger = logging.getLogger(__name__)


class StripeWebhookHandler:
    """
    Handler for Stripe webhook events.

    Provides idempotent webhook processing with signature verification.
    All events are logged and stored for audit purposes.
    """

    @classmethod
    def handle(cls, payload: bytes, sig_header: str) -> None:
        """
        Main entry point for webhook processing.

        Args:
            payload: Raw request body bytes
            sig_header: Stripe signature header value

        Raises:
            ValueError: If signature verification fails
            Exception: If event processing fails

        Side effects:
            - Creates StripeEvent record
            - Processes event
            - Updates StripeEvent status
            - Creates audit logs
            - May send emails
            - May update customer/subscription/instance status
        """
        from billing.models import StripeConfig

        # Get webhook secret from StripeConfig
        config = StripeConfig.get()
        webhook_secret = config.active_webhook_secret

        if not webhook_secret:
            # Fallback to environment variable for initial setup
            import os
            webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')
            logger.warning('Using STRIPE_WEBHOOK_SECRET from environment (StripeConfig not configured)')

        if not webhook_secret:
            raise ValueError('STRIPE_WEBHOOK_SECRET not configured in StripeConfig or environment')

        try:
            # Verify signature and construct event
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError as e:
            # Invalid payload
            logger.error(f'Invalid webhook payload: {e}')
            raise
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f'Invalid webhook signature: {e}')
            raise

        # Get or create StripeEvent for idempotency
        stripe_event_id = event['id']
        event_type = event['type']

        # Check if event already processed
        db_event, created = StripeEvent.objects.get_or_create(
            stripe_event_id=stripe_event_id,
            defaults={
                'event_type': event_type,
                'payload': event.to_dict_recursive(),
            }
        )

        if not created and db_event.processed:
            # Event already processed, return early (idempotency)
            logger.info(f'Event {stripe_event_id} already processed, skipping')
            AuditService.log(
                action=AuditAction.STRIPE_WEBHOOK_RECEIVED,
                resource_type='StripeWebhook',
                resource_id=stripe_event_id,
                note=f'Duplicate webhook event {event_type} (already processed)',
            )
            return

        # Log receipt
        AuditService.log(
            action=AuditAction.STRIPE_WEBHOOK_RECEIVED,
            resource_type='StripeWebhook',
            resource_id=stripe_event_id,
            customer=db_event.customer,
            after={'event_type': event_type},
            note=f'Webhook event received: {event_type}',
        )

        try:
            # Dispatch to handler
            cls._dispatch(event, db_event)

            # Mark as processed
            db_event.processed = True
            db_event.processed_at = timezone.now()
            db_event.save()

            # Log success
            AuditService.log(
                action=AuditAction.STRIPE_WEBHOOK_PROCESSED,
                resource_type='StripeWebhook',
                resource_id=stripe_event_id,
                customer=db_event.customer,
                after={'event_type': event_type},
                note=f'Webhook event processed successfully: {event_type}',
            )

            logger.info(f'Successfully processed webhook event {stripe_event_id} ({event_type})')

        except Exception as e:
            # Log failure but don't raise (return 200 to Stripe to prevent retries)
            error_msg = str(e)
            db_event.error_message = error_msg
            db_event.save()

            AuditService.log(
                action=AuditAction.STRIPE_WEBHOOK_FAILED,
                resource_type='StripeWebhook',
                resource_id=stripe_event_id,
                customer=db_event.customer,
                after={
                    'event_type': event_type,
                    'error': error_msg,
                },
                note=f'Webhook event processing failed: {event_type} - {error_msg}',
            )

            logger.exception(f'Failed to process webhook event {stripe_event_id} ({event_type}): {e}')

    @classmethod
    def _dispatch(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """
        Route event to appropriate handler method.

        Args:
            event: Stripe event object
            db_event: Local StripeEvent record
        """
        event_type = event['type']

        # Map event types to handler methods
        handlers = {
            'checkout.session.completed': cls._handle_checkout_session_completed,
            'checkout.session.expired': cls._handle_checkout_session_expired,
            'customer.subscription.created': cls._handle_subscription_created,
            'customer.subscription.updated': cls._handle_subscription_updated,
            'customer.subscription.deleted': cls._handle_subscription_deleted,
            'invoice.paid': cls._handle_invoice_paid,
            'invoice.payment_failed': cls._handle_invoice_payment_failed,
            'invoice.payment_action_required': cls._handle_invoice_payment_action_required,
            'customer.updated': cls._handle_customer_updated,
            'customer.discount.created': cls._handle_discount_created,
            'customer.discount.deleted': cls._handle_discount_deleted,
        }

        handler = handlers.get(event_type)

        if handler:
            logger.info(f'Dispatching {event_type} to {handler.__name__}')
            handler(event, db_event)
        else:
            logger.info(f'No handler for event type {event_type}, skipping')

    @staticmethod
    def _find_order(session: dict) -> Optional[Order]:
        """
        Locate the local Order for a Stripe Checkout Session.

        Sucht zuerst über die `metadata.order_id`, dann als Fallback über die
        gespeicherte `stripe_checkout_session_id`. Gibt None zurück, wenn keine
        Order gefunden wird — die Session gehört dann zu einem anderen Flow
        (z. B. Seat-Add-ons aus der Instance-Subscription-API).
        """
        metadata = session.get('metadata') or {}
        order_id = metadata.get('order_id')

        order = None
        if order_id:
            order = Order.objects.filter(id=order_id).first()

        if order is None and session.get('id'):
            order = Order.objects.filter(
                stripe_checkout_session_id=session['id']
            ).first()

        return order

    @classmethod
    def _handle_checkout_session_completed(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """
        Handle checkout.session.completed - Kunde nach erfolgreicher Zahlung anlegen.

        Legt Customer + Subscription + Master-Instanz (`status='provisioning'`)
        über CustomerService.create_customer() an; die Master-Instanz wird
        dadurch vom Provisioner beim nächsten Poll abgeholt. Idempotent gegen
        Mehrfachzustellung; fremde Checkout-Sessions werden ignoriert.
        """
        session = event['data']['object']

        order = cls._find_order(session)
        if order is None:
            logger.warning(
                f'No order found for checkout session {session.get("id")}, ignoring '
                f'(likely a foreign checkout session, e.g. seat add-on)'
            )
            return

        # Idempotenz: bereits abgeschlossene Order nicht erneut verarbeiten.
        if order.status == 'completed':
            logger.info(f'Order {order.id} already completed, skipping duplicate checkout.session.completed')
            return

        stripe_customer_id = session.get('customer') or None
        stripe_subscription_id = session.get('subscription') or None

        # Slug-Kollision zum Zahlungszeitpunkt (Race seit Bestellung): Geld ist
        # bereits geflossen — Order als failed markieren und Admin informieren,
        # statt still einen halben Kunden anzulegen.
        if Customer.objects.filter(slug=order.slug).exists():
            cls._fail_order(
                order,
                db_event,
                reason=f'Slug "{order.slug}" ist zum Zahlungszeitpunkt bereits vergeben (Race).',
            )
            return

        try:
            customer, subscription, master_instance = CustomerService.create_customer(
                slug=order.slug,
                company_name=order.company_name,
                contact_name=order.contact_name,
                contact_email=order.contact_email,
                billing_email=order.billing_email,
                plan=order.plan,
                user_seats=order.user_seats,
                instance_seats=1,
                stripe_subscription_id=stripe_subscription_id or '',
                ai_addon=order.ai_addon,
                contact_phone=order.contact_phone,
                billing_address=order.billing_address,
                billing_city=order.billing_city,
                billing_postal_code=order.billing_postal_code,
                billing_country=order.billing_country,
                vat_id=order.vat_id,
                stripe_customer_id=stripe_customer_id,
            )
        except (IntegrityError, ValidationError) as exc:
            # Kollision/Validierung schlug erst beim Anlegen zu (enger Race) —
            # create_customer läuft in einer Transaktion, es bleibt kein
            # halber Kunde zurück.
            logger.exception(f'Failed to create customer for order {order.id}: {exc}')
            cls._fail_order(
                order,
                db_event,
                reason=f'Kundenanlage fehlgeschlagen (Slug "{order.slug}"): {exc}',
            )
            return

        db_event.customer = customer
        db_event.save()

        order.status = 'completed'
        order.save(update_fields=['status', 'updated_at'])

        AuditService.log(
            action='order.completed',
            resource_type='Order',
            resource_id=str(order.id),
            customer=customer,
            after={
                'slug': customer.slug,
                'stripe_customer_id': stripe_customer_id,
                'stripe_subscription_id': stripe_subscription_id,
            },
            note=f'Order {order.id} completed via checkout.session.completed; customer and master instance provisioning',
        )

        logger.info(
            f'Order {order.id} completed: created customer {customer.slug} '
            f'with master instance {master_instance.slug} (provisioning)'
        )

        # Bestätigungsmail an den Kunden — Instanz wird bereitgestellt, URL folgt.
        MailService.send_template(
            to=order.contact_email,
            template='order_confirmed',
            context={
                'contact_name': order.contact_name,
                'company_name': order.company_name,
                'slug': customer.slug,
                'instance_url': f'https://{customer.slug}.zenico.app',
            },
            subject_override='Ihre Zenico-Bestellung ist bestätigt',
        )

    @classmethod
    def _handle_checkout_session_expired(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle checkout.session.expired - Order auf 'expired' setzen."""
        session = event['data']['object']

        order = cls._find_order(session)
        if order is None:
            logger.warning(
                f'No order found for expired checkout session {session.get("id")}, ignoring'
            )
            return

        # Nur offene Bestellungen ablaufen lassen (Idempotenz / kein Rückschritt
        # aus einem Endzustand).
        if order.status not in Order.OPEN_STATUSES:
            logger.info(f'Order {order.id} in status {order.status}, ignoring checkout.session.expired')
            return

        order.status = 'expired'
        order.save(update_fields=['status', 'updated_at'])

        AuditService.log(
            action='order.expired',
            resource_type='Order',
            resource_id=str(order.id),
            after={'slug': order.slug, 'status': 'expired'},
            note=f'Order {order.id} expired (checkout.session.expired)',
        )

        logger.info(f'Order {order.id} marked as expired')

    @classmethod
    def _fail_order(cls, order: Order, db_event: StripeEvent, reason: str) -> None:
        """
        Order auf 'failed' setzen und Admin benachrichtigen.

        Wird gerufen, wenn nach erfolgreicher Zahlung kein Kunde angelegt werden
        kann (z. B. Slug-Kollision). Das Geld ist bereits geflossen — der Fall
        muss auffallen, nicht verschluckt werden.
        """
        order.status = 'failed'
        order.save(update_fields=['status', 'updated_at'])

        AuditService.log(
            action='order.failed',
            resource_type='Order',
            resource_id=str(order.id),
            after={'slug': order.slug, 'status': 'failed', 'reason': reason},
            note=f'Order {order.id} failed after payment: {reason}',
        )

        logger.error(f'Order {order.id} failed after payment: {reason}')

        MailService.send_template(
            to=settings.ADMIN_NOTIFICATION_EMAIL,
            template='admin_order_failed',
            context={
                'order': order,
                'reason': reason,
            },
            subject_override=f'Bestellung fehlgeschlagen nach Zahlung: {order.company_name} ({order.slug})',
        )

    @classmethod
    def _handle_subscription_created(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.subscription.created event."""
        subscription_data = event['data']['object']
        stripe_customer_id = subscription_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Subscription creation is usually done during signup, so just log it
        logger.info(f'Subscription {subscription_data["id"]} created for customer {customer.slug}')

    @classmethod
    def _handle_subscription_updated(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.subscription.updated event."""
        subscription_data = event['data']['object']
        stripe_subscription_id = subscription_data['id']

        # Find local subscription
        subscription = Subscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first()
        if not subscription:
            logger.warning(f'Subscription not found for stripe_subscription_id {stripe_subscription_id}')
            return

        # Link event to customer
        db_event.customer = subscription.customer
        db_event.save()

        # Update subscription status
        old_status = subscription.stripe_status
        new_status = subscription_data['status']

        if old_status != new_status:
            subscription.stripe_status = new_status
            subscription.save()

            logger.info(f'Subscription {stripe_subscription_id} status changed: {old_status} -> {new_status}')

            # If subscription becomes active after being in another state, send email
            if new_status == 'active' and old_status != 'active':
                MailService.send_template(
                    to=subscription.customer.billing_email,
                    template='subscription_updated',
                    context={
                        'contact_name': subscription.customer.contact_name,
                        'user_seats': subscription.user_seats_total,
                        'instance_seats': subscription.instance_seats_total,
                        'changes': ['Subscription status updated to active'],
                    },
                    subject_override='Ihr Abonnement wurde aktualisiert',
                )

    @classmethod
    def _handle_subscription_deleted(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.subscription.deleted event - suspend all instances."""
        subscription_data = event['data']['object']
        stripe_subscription_id = subscription_data['id']

        # Find local subscription
        subscription = Subscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first()
        if not subscription:
            logger.warning(f'Subscription not found for stripe_subscription_id {stripe_subscription_id}')
            return

        # Link event to customer
        db_event.customer = subscription.customer
        db_event.save()

        # Update subscription status
        subscription.stripe_status = 'canceled'
        subscription.save()

        # Suspend all active instances
        active_instances = Instance.objects.filter(
            customer=subscription.customer,
            status='active'
        )

        for instance in active_instances:
            instance.status = 'suspended'
            instance.save()

            AuditService.log(
                action=AuditAction.INSTANCE_SUSPENDED,
                resource_type='Instance',
                resource_id=str(instance.id),
                customer=subscription.customer,
                instance_id=instance.id,
                before={'status': 'active'},
                after={'status': 'suspended'},
                note=f'Instance suspended due to subscription cancellation',
            )

            logger.info(f'Suspended instance {instance.slug} due to subscription cancellation')

        logger.info(f'Subscription {stripe_subscription_id} cancelled, suspended {active_instances.count()} instances')

    @classmethod
    def _handle_invoice_paid(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle invoice.paid event - sync invoice and reactivate instances if needed."""
        invoice_data = event['data']['object']
        stripe_customer_id = invoice_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Sync invoice
        StripeService.sync_invoice(invoice_data, customer)

        # If customer was suspended, reactivate instances
        if customer.status == 'suspended':
            suspended_instances = Instance.objects.filter(
                customer=customer,
                status='suspended'
            )

            for instance in suspended_instances:
                instance.status = 'active'
                instance.save()

                AuditService.log(
                    action=AuditAction.INSTANCE_REACTIVATED,
                    resource_type='Instance',
                    resource_id=str(instance.id),
                    customer=customer,
                    instance_id=instance.id,
                    before={'status': 'suspended'},
                    after={'status': 'active'},
                    note=f'Instance reactivated after invoice payment',
                )

                # Send reactivation email
                MailService.send_template(
                    to=customer.billing_email,
                    template='instance_reactivated',
                    context={
                        'contact_name': customer.contact_name,
                        'instance_name': instance.display_name,
                        'instance_url': f'https://{instance.slug}.zenico.app',  # Adjust URL pattern
                    },
                    subject_override='Ihre Zenico-Instanz ist wieder aktiv',
                )

            logger.info(f'Reactivated {suspended_instances.count()} instances for customer {customer.slug} after payment')

    @classmethod
    def _handle_invoice_payment_failed(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle invoice.payment_failed event - send warning email."""
        invoice_data = event['data']['object']
        stripe_customer_id = invoice_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Sync invoice
        StripeService.sync_invoice(invoice_data, customer)

        # Send payment failed email
        amount = invoice_data.get('amount_due', 0) / 100  # Convert cents to currency
        currency = invoice_data.get('currency', 'EUR').upper()

        MailService.send_template(
            to=customer.billing_email,
            template='payment_failed',
            context={
                'contact_name': customer.contact_name,
                'invoice_id': invoice_data['id'],
                'amount': f'{amount:.2f}',
                'currency': currency,
                'due_date': 'within 7 days',  # Could parse from invoice
                'payment_url': invoice_data.get('hosted_invoice_url', 'https://billing.stripe.com'),
            },
            subject_override='Zahlungsproblem bei Ihrem Zenico-Abonnement',
        )

        logger.info(f'Sent payment failed email to {customer.billing_email} for invoice {invoice_data["id"]}')

    @classmethod
    def _handle_invoice_payment_action_required(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle invoice.payment_action_required event - send action required email."""
        invoice_data = event['data']['object']
        stripe_customer_id = invoice_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Send payment action required email (similar to payment_failed)
        amount = invoice_data.get('amount_due', 0) / 100
        currency = invoice_data.get('currency', 'EUR').upper()

        MailService.send_template(
            to=customer.billing_email,
            template='payment_failed',  # Reuse payment_failed template
            context={
                'contact_name': customer.contact_name,
                'invoice_id': invoice_data['id'],
                'amount': f'{amount:.2f}',
                'currency': currency,
                'due_date': 'as soon as possible',
                'payment_url': invoice_data.get('hosted_invoice_url', 'https://billing.stripe.com'),
            },
            subject_override='Aktion erforderlich für Ihre Zenico-Rechnung',
        )

        logger.info(f'Sent payment action required email to {customer.billing_email}')

    @classmethod
    def _handle_customer_updated(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.updated event - sync customer data."""
        customer_data = event['data']['object']
        stripe_customer_id = customer_data['id']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Sync customer data
        updated = False

        if customer_data.get('email') and customer_data['email'] != customer.billing_email:
            customer.billing_email = customer_data['email']
            updated = True

        if customer_data.get('name') and customer_data['name'] != customer.company_name:
            customer.company_name = customer_data['name']
            updated = True

        if updated:
            customer.save()
            logger.info(f'Updated customer {customer.slug} from Stripe data')

    @classmethod
    def _handle_discount_created(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.discount.created event - track coupon redemption if not already tracked."""
        from billing.models import Coupon, CouponRedemption

        discount_data = event['data']['object']
        stripe_customer_id = discount_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Extract coupon information
        coupon_data = discount_data.get('coupon')
        if not coupon_data:
            logger.warning(f'No coupon data in discount.created event for customer {customer.slug}')
            return

        stripe_coupon_id = coupon_data['id']

        # Find local coupon
        coupon = Coupon.objects.filter(stripe_coupon_id=stripe_coupon_id).first()
        if not coupon:
            logger.warning(f'Coupon not found for stripe_coupon_id {stripe_coupon_id}')
            return

        # Check if redemption already exists
        redemption_exists = CouponRedemption.objects.filter(
            coupon=coupon,
            customer=customer
        ).exists()

        if redemption_exists:
            logger.info(f'Coupon {coupon.code} already redeemed by customer {customer.slug}, skipping')
            return

        # Find active subscription
        subscription = customer.active_subscription
        if not subscription:
            logger.warning(f'No active subscription for customer {customer.slug}')
            return

        # Create redemption record
        discount_id = discount_data.get('id', '')
        redemption = CouponRedemption.objects.create(
            coupon=coupon,
            customer=customer,
            subscription=subscription,
            stripe_discount_id=discount_id,
        )

        # Increment redemption count
        coupon.redemptions_count += 1
        coupon.save()

        # Update subscription coupon reference
        subscription.coupon = coupon
        subscription.save()

        # Log action
        AuditService.log(
            action='coupon.redeemed',
            resource_type='CouponRedemption',
            resource_id=str(redemption.id),
            customer=customer,
            after={
                'coupon_code': coupon.code,
                'source': 'webhook',
            },
            note=f'Coupon {coupon.code} applied via Stripe webhook',
        )

        logger.info(f'Tracked coupon redemption {coupon.code} for customer {customer.slug} from webhook')

    @classmethod
    def _handle_discount_deleted(cls, event: stripe.Event, db_event: StripeEvent) -> None:
        """Handle customer.discount.deleted event - clear coupon from subscription."""
        discount_data = event['data']['object']
        stripe_customer_id = discount_data['customer']

        # Find customer
        customer = Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if not customer:
            logger.warning(f'Customer not found for stripe_customer_id {stripe_customer_id}')
            return

        # Link event to customer
        db_event.customer = customer
        db_event.save()

        # Find active subscription
        subscription = customer.active_subscription
        if not subscription:
            logger.warning(f'No active subscription for customer {customer.slug}')
            return

        if subscription.coupon:
            coupon_code = subscription.coupon.code
            subscription.coupon = None
            subscription.save()

            # Log action
            AuditService.log(
                action='coupon.removed',
                resource_type='Subscription',
                resource_id=str(subscription.id),
                customer=customer,
                after={
                    'coupon_code': coupon_code,
                    'source': 'webhook',
                },
                note=f'Coupon {coupon_code} removed via Stripe webhook',
            )

            logger.info(f'Removed coupon {coupon_code} from subscription for customer {customer.slug} via webhook')
        else:
            logger.info(f'No coupon to remove for customer {customer.slug}')

