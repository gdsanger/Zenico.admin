"""
Öffentlicher REST-API-Endpoint für Bestellungen.

Wird von Zenico.web aufgerufen (keine Authentifizierung — Rate-Limiting pro IP
und CORS). Legt eine Order an und erstellt eine Stripe-Checkout-Session.
"""

import logging
import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from customers.models import Plan, Customer
from .models import Order
from .services import OrderService

logger = logging.getLogger(__name__)

SLUG_RE = re.compile(r'^[a-z0-9]{2,10}$')


@method_decorator(ratelimit(key='ip', rate='5/h', method='POST', block=True), name='dispatch')
class OrderCreateAPIView(APIView):
    """
    POST /api/orders/

    Bestellung von der Homepage entgegennehmen, Order anlegen und
    Stripe-Checkout-Session erstellen.

    Request body:
    {
        "plan": "standard",              // Plan-Name (Pflicht)
        "user_seats": 5,                // positive Ganzzahl (Pflicht)
        "ai_addon": true,               // optional, Default false
        "billing_interval": "monthly",   // optional, "monthly" (Default) oder "yearly"
        "slug": "acme",                 // 2-10 lowercase alphanumerisch (Pflicht)
        "company_name": "Acme GmbH",    // Pflicht
        "contact_name": "Max Muster",   // Pflicht
        "contact_email": "max@acme.de", // Pflicht
        "contact_phone": "",
        "billing_email": "rechnung@acme.de",
        "billing_address": "Hauptstr. 1",
        "billing_city": "München",
        "billing_postal_code": "80331",
        "billing_country": "DE",
        "vat_id": "",
        "terms_accepted": true          // AGB-Zustimmung (Pflicht, muss true sein)
    }

    Response 201: {"order_id": "...", "checkout_url": "https://checkout.stripe.com/..."}
    Response 400: {"errors": {"<feld>": "<meldung>"}}
    """

    def post(self, request):
        data = request.data
        errors = {}

        # Plan
        plan_identifier = str(data.get('plan', '')).strip()
        plan = None
        if not plan_identifier:
            errors['plan'] = 'Plan ist erforderlich.'
        else:
            plan = Plan.objects.filter(name=plan_identifier, is_active=True).first()
            if plan is None:
                errors['plan'] = 'Unbekannter oder inaktiver Plan.'

        # user_seats
        user_seats = data.get('user_seats')
        try:
            user_seats = int(user_seats)
            if user_seats <= 0:
                errors['user_seats'] = 'user_seats muss eine positive Ganzzahl sein.'
        except (TypeError, ValueError):
            errors['user_seats'] = 'user_seats muss eine positive Ganzzahl sein.'
            user_seats = None

        ai_addon = bool(data.get('ai_addon', False))
        if ai_addon and plan is not None and not plan.ai_addon_available:
            errors['ai_addon'] = 'Für diesen Plan ist kein KI-Addon verfügbar.'

        # billing_interval
        billing_interval = str(data.get('billing_interval', 'monthly')).strip().lower() or 'monthly'
        if billing_interval not in ('monthly', 'yearly'):
            errors['billing_interval'] = 'Ungültiges Abrechnungsintervall (monthly oder yearly).'
        elif billing_interval == 'yearly' and plan is not None and not plan.stripe_price_id_user_yearly:
            errors['billing_interval'] = 'Für diesen Plan ist kein Jahrespreis verfügbar.'

        # Slug
        slug = str(data.get('slug', '')).strip().lower()
        if not slug:
            errors['slug'] = 'Slug ist erforderlich.'
        elif not SLUG_RE.match(slug):
            errors['slug'] = 'Slug muss 2-10 Zeichen lang sein (nur a-z und 0-9).'
        elif Customer.objects.filter(slug=slug).exists():
            errors['slug'] = 'Dieser Slug ist bereits vergeben.'
        elif Order.objects.filter(slug=slug, status__in=Order.OPEN_STATUSES).exists():
            errors['slug'] = 'Dieser Slug ist bereits vergeben.'

        # Pflichtfelder
        company_name = str(data.get('company_name', '')).strip()
        if not company_name:
            errors['company_name'] = 'Firmenname ist erforderlich.'

        contact_name = str(data.get('contact_name', '')).strip()
        if not contact_name:
            errors['contact_name'] = 'Kontaktname ist erforderlich.'

        contact_email = str(data.get('contact_email', '')).strip()
        if not contact_email:
            errors['contact_email'] = 'Kontakt-E-Mail ist erforderlich.'

        terms_accepted = bool(data.get('terms_accepted', False))
        if not terms_accepted:
            errors['terms_accepted'] = 'Die AGB müssen akzeptiert werden.'

        # Rechnungs-E-Mail: fällt auf Kontakt-E-Mail zurück
        billing_email = str(data.get('billing_email', '')).strip() or contact_email

        if errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        actor_ip = request.META.get('REMOTE_ADDR')

        try:
            order, checkout_url = OrderService.create_order_with_checkout(
                plan=plan,
                user_seats=user_seats,
                ai_addon=ai_addon,
                billing_interval=billing_interval,
                slug=slug,
                company_name=company_name,
                contact_name=contact_name,
                contact_email=contact_email,
                billing_email=billing_email,
                contact_phone=str(data.get('contact_phone', '')).strip(),
                billing_address=str(data.get('billing_address', '')).strip(),
                billing_city=str(data.get('billing_city', '')).strip(),
                billing_postal_code=str(data.get('billing_postal_code', '')).strip(),
                billing_country=(str(data.get('billing_country', '')).strip() or 'DE')[:2].upper(),
                vat_id=str(data.get('vat_id', '')).strip(),
                terms_accepted=terms_accepted,
                actor_ip=actor_ip,
            )
        except Exception as exc:
            logger.exception(f'Failed to create order/checkout for slug {slug}: {exc}')
            return Response(
                {'errors': {'non_field': 'Die Bestellung konnte nicht verarbeitet werden. Bitte später erneut versuchen.'}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {'order_id': str(order.id), 'checkout_url': checkout_url},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ratelimit(key='ip', rate='30/m', method='GET', block=True), name='dispatch')
class CheckSlugAPIView(APIView):
    """
    GET /api/orders/check-slug/?slug=acme

    Öffentliche Live-Prüfung für die Bestellstrecke auf der Homepage: Ist der
    Wunsch-Slug (= künftige Subdomain ``{slug}.zenico.app``) frei?

    Ein Slug gilt als vergeben, wenn ein ``Customer`` ihn nutzt oder eine offene
    Order (``pending_payment``/``paid``) ihn reserviert. Beim Tippen gepollt,
    daher großzügigeres Rate-Limit (30/min pro IP).

    Response 200: {"available": true|false, "message": "<deutsche Meldung>"}

    Die Antwort ist bewusst knapp — sie verrät nur frei/nicht frei, nicht, ob
    ein Kunde oder eine Order den Slug hält.
    """

    def get(self, request):
        slug = str(request.GET.get('slug', '')).strip().lower()

        if not slug:
            return Response({
                'available': False,
                'message': 'Bitte gib einen Slug ein.',
            })

        if not SLUG_RE.match(slug):
            return Response({
                'available': False,
                'message': 'Slug muss 2-10 Zeichen lang sein (nur a-z und 0-9).',
            })

        taken = (
            Customer.objects.filter(slug=slug).exists()
            or Order.objects.filter(slug=slug, status__in=Order.OPEN_STATUSES).exists()
        )

        if taken:
            return Response({
                'available': False,
                'message': 'Dieser Slug ist bereits vergeben.',
            })

        return Response({
            'available': True,
            'message': 'Slug verfügbar ✓',
        })
