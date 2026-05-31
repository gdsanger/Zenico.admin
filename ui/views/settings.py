"""
Stripe Configuration Views

Views for managing Stripe configuration and plan wiring.
"""

import logging
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render

from billing.models import StripeConfig
from billing.stripe_import import StripeImportService
from customers.models import Plan
from ui.decorators import role_required

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class StripeConfigView(TemplateView):
    """
    Main Stripe configuration view.

    Displays and manages:
    - API keys (test and live)
    - Webhook secrets
    - Mode toggle (test/live)
    - Connection testing
    """
    template_name = 'ui/settings/stripe.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = StripeConfig.get()

        # Mask keys for display
        context['config'] = config
        context['test_secret_key_masked'] = config.mask_key(config.get_test_secret_key())
        context['test_publishable_key'] = config.test_publishable_key
        context['test_webhook_secret_masked'] = config.mask_key(config.get_test_webhook_secret())

        context['live_secret_key_masked'] = config.mask_key(config.get_live_secret_key())
        context['live_publishable_key'] = config.live_publishable_key
        context['live_webhook_secret_masked'] = config.mask_key(config.get_live_webhook_secret())

        context['mode'] = config.mode
        context['is_configured'] = config.is_configured

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class StripePlanWiringView(TemplateView):
    """
    Plan wiring view for mapping Zenico plans to Stripe products/prices.
    """
    template_name = 'ui/settings/stripe_plans.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all plans
        plans = Plan.objects.all().order_by('name')
        context['plans'] = plans

        # Get Stripe products and prices
        try:
            products = StripeImportService.fetch_products()
            all_prices = StripeImportService.fetch_all_prices()

            context['products'] = products
            context['all_prices'] = all_prices

            # Organize prices by product
            prices_by_product = {}
            for price in all_prices:
                product_id = price['product_id']
                if product_id not in prices_by_product:
                    prices_by_product[product_id] = []
                prices_by_product[product_id].append(price)

            context['prices_by_product'] = prices_by_product

        except Exception as e:
            logger.exception(f'Failed to fetch Stripe data: {e}')
            context['error'] = str(e)
            context['products'] = []
            context['all_prices'] = []
            context['prices_by_product'] = {}

        return context


@login_required
@role_required('superadmin')
@require_http_methods(['POST'])
def stripe_config_save(request):
    """
    Save Stripe configuration (keys, mode, etc).
    """
    try:
        config = StripeConfig.get()

        # Get form data
        mode = request.POST.get('mode', 'test')

        # Update mode
        if mode in ['test', 'live']:
            config.mode = mode

        # Update test keys if provided
        test_secret = request.POST.get('test_secret_key', '').strip()
        if test_secret:
            config.set_test_secret_key(test_secret)

        test_publishable = request.POST.get('test_publishable_key', '').strip()
        if test_publishable:
            config.test_publishable_key = test_publishable

        test_webhook = request.POST.get('test_webhook_secret', '').strip()
        if test_webhook:
            config.set_test_webhook_secret(test_webhook)

        # Update live keys if provided
        live_secret = request.POST.get('live_secret_key', '').strip()
        if live_secret:
            config.set_live_secret_key(live_secret)

        live_publishable = request.POST.get('live_publishable_key', '').strip()
        if live_publishable:
            config.live_publishable_key = live_publishable

        live_webhook = request.POST.get('live_webhook_secret', '').strip()
        if live_webhook:
            config.set_live_webhook_secret(live_webhook)

        # Set updated_by
        config.updated_by = request.user
        config.save()

        return JsonResponse({
            'success': True,
            'message': 'Konfiguration gespeichert'
        })

    except Exception as e:
        logger.exception(f'Failed to save Stripe config: {e}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@role_required('superadmin')
@require_http_methods(['POST'])
def stripe_connection_test(request):
    """
    Test connection to Stripe with current configuration.
    """
    try:
        import stripe as stripe_lib
        from core.services.stripe import get_stripe

        get_stripe()  # setzt stripe.api_key, sonst nichts

        account = stripe_lib.Account.retrieve()
        account_dict = account.to_dict()

        logger.info("Stripe account data: %s", account_dict)

        account_name = (
            account_dict.get('business_profile', {}).get('name')
            or account_dict.get('settings', {}).get('dashboard', {}).get('display_name')
            or account_dict.get('id')
        )

        mode = 'live' if account_dict.get('livemode') else 'test'


        return JsonResponse({
            'success': True,
            'account_name': account_name,
            'mode': mode,
            'account_id': account.id
        })

    except Exception as e:
        logger.exception(f'Stripe connection test failed: {e}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@role_required('superadmin')
@require_http_methods(['GET'])
def stripe_fetch_prices(request):
    """
    Fetch all Stripe prices for populating dropdowns.
    """
    try:
        all_prices = StripeImportService.fetch_all_prices()

        # Format prices for dropdowns
        formatted_prices = []
        for price in all_prices:
            formatted_prices.append({
                'id': price['id'],
                'product_id': price['product_id'],
                'display': StripeImportService.format_price_display(price),
                'amount': price.get('unit_amount', 0) / 100,
                'currency': price.get('currency', 'eur'),
                'interval': price.get('recurring', {}).get('interval', ''),
            })

        return JsonResponse({
            'success': True,
            'prices': formatted_prices
        })

    except Exception as e:
        logger.exception(f'Failed to fetch Stripe prices: {e}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@role_required('superadmin')
@require_http_methods(['POST'])
def stripe_plan_save(request):
    """
    Save plan-to-Stripe mapping.
    """
    try:
        plan_id = request.POST.get('plan_id')
        if not plan_id:
            return JsonResponse({
                'success': False,
                'error': 'Plan ID is required'
            }, status=400)

        plan = Plan.objects.get(pk=plan_id)

        # Get Stripe IDs from form
        stripe_product_id = request.POST.get('stripe_product_id', '').strip()
        stripe_price_id_user = request.POST.get('stripe_price_id_user', '').strip()
        stripe_price_id_instance = request.POST.get('stripe_price_id_instance', '').strip()
        stripe_price_id_ai = request.POST.get('stripe_price_id_ai', '').strip()

        # Validate that prices belong to the product
        if stripe_product_id:
            if stripe_price_id_user:
                if not StripeImportService.validate_price_product(stripe_price_id_user, stripe_product_id):
                    return JsonResponse({
                        'success': False,
                        'error': 'User price does not belong to selected product'
                    }, status=400)

            if stripe_price_id_instance:
                if not StripeImportService.validate_price_product(stripe_price_id_instance, stripe_product_id):
                    return JsonResponse({
                        'success': False,
                        'error': 'Instance price does not belong to selected product'
                    }, status=400)

            if stripe_price_id_ai:
                if not StripeImportService.validate_price_product(stripe_price_id_ai, stripe_product_id):
                    return JsonResponse({
                        'success': False,
                        'error': 'AI addon price does not belong to selected product'
                    }, status=400)

        # Update plan
        plan.stripe_product_id = stripe_product_id
        plan.stripe_price_id_user = stripe_price_id_user
        plan.stripe_price_id_instance = stripe_price_id_instance
        plan.stripe_price_id_ai = stripe_price_id_ai
        plan.save()

        return JsonResponse({
            'success': True,
            'message': f'{plan.display_name} gespeichert'
        })

    except Plan.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Plan not found'
        }, status=404)
    except Exception as e:
        logger.exception(f'Failed to save plan mapping: {e}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
