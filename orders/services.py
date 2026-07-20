"""
OrderService — Bestellungen anlegen und Stripe-Checkout-Session erstellen.

Ablauf (Stripe Checkout zuerst): Order speichern (`pending_payment`) →
Stripe-Checkout-Session erstellen (mit `metadata.order_id`) → Checkout-URL
zurückgeben. Kunde und Instanz entstehen erst nach Zahlung im Webhook.
"""

import logging

from django.conf import settings
from django.db import transaction

from core.services.audit import AuditService, AuditAction
from core.services.stripe import get_stripe
from .models import Order

logger = logging.getLogger(__name__)


class OrderService:
    """Service-Klasse für Bestellungen."""

    @staticmethod
    def create_order_with_checkout(
        *,
        plan,
        user_seats: int,
        ai_addon: bool,
        slug: str,
        company_name: str,
        contact_name: str,
        contact_email: str,
        billing_email: str,
        contact_phone: str = '',
        billing_address: str = '',
        billing_city: str = '',
        billing_postal_code: str = '',
        billing_country: str = 'DE',
        vat_id: str = '',
        terms_accepted: bool = False,
        actor_ip: str = None,
    ) -> tuple[Order, str]:
        """
        Order anlegen und Stripe-Checkout-Session erstellen.

        Returns:
            tuple[Order, str]: Die erstellte Order und die Checkout-URL.

        Raises:
            Exception: Wenn die Stripe-Checkout-Session nicht erstellt werden
                kann. Die Order wird in diesem Fall zurückgerollt (atomic).
        """
        with transaction.atomic():
            order = Order.objects.create(
                plan=plan,
                user_seats=user_seats,
                ai_addon=ai_addon,
                slug=slug,
                company_name=company_name,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                billing_email=billing_email,
                billing_address=billing_address,
                billing_city=billing_city,
                billing_postal_code=billing_postal_code,
                billing_country=billing_country,
                vat_id=vat_id,
                terms_accepted=terms_accepted,
                status='pending_payment',
            )

            checkout_url = OrderService._create_checkout_session(order)

            AuditService.log(
                action=AuditAction.ORDER_CREATED,
                resource_type='Order',
                resource_id=str(order.id),
                actor_email='system',
                actor_ip=actor_ip,
                after={
                    'slug': order.slug,
                    'company_name': order.company_name,
                    'contact_email': order.contact_email,
                    'plan': plan.name,
                    'user_seats': user_seats,
                    'ai_addon': ai_addon,
                    'stripe_checkout_session_id': order.stripe_checkout_session_id,
                },
                note=f'Order created from web form: {company_name} ({slug}), plan {plan.name}',
            )

            return order, checkout_url

    @staticmethod
    def _create_checkout_session(order: Order) -> str:
        """
        Stripe-Checkout-Session (mode=subscription) für eine Order erstellen.

        Line Items ergeben sich aus dem Plan: User-Seats (× user_seats)
        und optional das KI-Addon (× 1). Es gibt keine Instanzgebühr mehr
        (vgl. #893/#896) — ein evtl. am Plan hinterlegtes
        `stripe_price_id_instance` fließt bewusst nicht ein.
        Setzt `metadata.order_id`, den der Webhook zum Anlegen von Kunde und
        Instanz benötigt. Speichert die Session-ID auf der Order.

        `automatic_tax` aktiviert Stripe Tax für diese Session (greift NICHT
        automatisch bei per API erstellten Sessions, vgl. #918); dafür
        braucht Stripe die Rechnungsadresse (`billing_address_collection`)
        und optional die USt-IdNr für EU-B2B-Reverse-Charge
        (`tax_id_collection`). Ein `customer_update` entfällt hier bewusst,
        da die Session keinen bestehenden `customer` referenziert, sondern
        nur `customer_email` — Stripe legt den Customer erst im Webhook an.

        `subscription_data.trial_period_days` gibt jeder neuen Bestellung
        einen Trial (vgl. #920) — mit Kreditkarte, da Checkout eine
        Zahlungsmethode ohnehin abfragt und die Instanz sofort provisioniert
        wird (echte Docker-Ressourcen, kein kartenloser Trial).
        """
        plan = order.plan
        stripe_api = get_stripe()

        line_items = []
        if plan.stripe_price_id_user:
            line_items.append({
                'price': plan.stripe_price_id_user,
                'quantity': order.user_seats,
            })
        if order.ai_addon and plan.stripe_price_id_ai:
            line_items.append({
                'price': plan.stripe_price_id_ai,
                'quantity': 1,
            })

        if not line_items:
            raise ValueError(
                f'Plan {plan.name} has no Stripe price IDs configured; cannot create checkout session'
            )

        metadata = {
            'order_id': str(order.id),
            'slug': order.slug,
            'plan_name': plan.name,
        }

        session_params = {
            'mode': 'subscription',
            'line_items': line_items,
            'customer_email': order.billing_email,
            'success_url': settings.ORDER_SUCCESS_URL,
            'cancel_url': settings.ORDER_CANCEL_URL,
            'metadata': metadata,
            'subscription_data': {
                'metadata': metadata,
                'trial_period_days': settings.TRIAL_PERIOD_DAYS,
            },
            'client_reference_id': str(order.id),
            'automatic_tax': {'enabled': True},
            'billing_address_collection': 'required',
            'tax_id_collection': {'enabled': True},
        }

        session = stripe_api.checkout.Session.create(**session_params)

        order.stripe_checkout_session_id = session.id
        order.save(update_fields=['stripe_checkout_session_id', 'updated_at'])

        logger.info(f'Created Stripe checkout session {session.id} for order {order.id}')
        return session.url
