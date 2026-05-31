"""
Coupon management views for the admin UI.
Handles coupon listing, creation, detail view, validation, and application to subscriptions.
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.core.exceptions import ValidationError
from django.contrib import messages

from billing.models import Coupon, CouponRedemption
from billing.coupon_service import CouponService
from customers.models import Customer, Subscription
from ui.decorators import role_required

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class CouponListView(ListView):
    """
    List all coupons with filtering and search.
    Accessible by superadmin and billing roles.
    """
    model = Coupon
    template_name = 'ui/billing/coupons/list.html'
    context_object_name = 'coupons'
    paginate_by = 20

    def get_queryset(self):
        queryset = Coupon.objects.all().select_related('created_by')

        # Search by code or name
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) | Q(name__icontains=search)
            )

        # Filter by status
        status = self.request.GET.get('status', '')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        # Filter by type
        coupon_type = self.request.GET.get('type', '')
        if coupon_type in ['percent', 'fixed']:
            queryset = queryset.filter(type=coupon_type)

        return queryset.annotate(redemption_count=Count('redemptions'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['status'] = self.request.GET.get('status', '')
        context['type'] = self.request.GET.get('type', '')
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class CouponCreateView(CreateView):
    """
    Create new coupon with Stripe integration.
    Accessible by superadmin and billing roles.
    """
    model = Coupon
    template_name = 'ui/billing/coupons/new.html'
    fields = [
        'code', 'name', 'type', 'discount_percent', 'discount_amount',
        'duration', 'duration_in_months', 'max_redemptions',
        'valid_from', 'valid_until', 'is_active'
    ]

    def form_valid(self, form):
        coupon = form.save(commit=False)
        coupon.created_by = self.request.user

        try:
            # Validate before saving
            coupon.full_clean()
            coupon.save()

            # Create in Stripe
            CouponService.create_stripe_coupon(coupon)

            messages.success(
                self.request,
                f'Gutschein {coupon.code} wurde erfolgreich erstellt und mit Stripe synchronisiert.'
            )
            return redirect('ui:coupon_detail', pk=coupon.id)

        except ValidationError as e:
            # Add validation errors to form
            for field, errors in e.message_dict.items():
                form.add_error(field, errors)
            return self.form_invalid(form)

        except Exception as e:
            logger.exception(f'Failed to create coupon: {e}')
            form.add_error(None, f'Fehler beim Erstellen des Gutscheins: {str(e)}')
            # Delete the coupon if Stripe creation failed
            if coupon.pk:
                coupon.delete()
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Neuer Gutscheincode'
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class CouponDetailView(DetailView):
    """
    Show coupon details and redemption history.
    Accessible by superadmin and billing roles.
    """
    model = Coupon
    template_name = 'ui/billing/coupons/detail.html'
    context_object_name = 'coupon'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        coupon = self.get_object()

        # Get redemptions with related data
        redemptions = CouponRedemption.objects.filter(
            coupon=coupon
        ).select_related(
            'customer', 'subscription'
        ).order_by('-redeemed_at')

        context['redemptions'] = redemptions
        context['redemption_count'] = redemptions.count()
        return context


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['POST'])
def coupon_deactivate(request, pk):
    """
    Deactivate a coupon.
    Accessible by superadmin and billing roles.
    """
    coupon = get_object_or_404(Coupon, pk=pk)

    coupon.is_active = False
    coupon.save()

    messages.success(request, f'Gutschein {coupon.code} wurde deaktiviert.')
    return redirect('ui:coupon_detail', pk=pk)


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['POST'])
def coupon_activate(request, pk):
    """
    Activate a coupon.
    Accessible by superadmin and billing roles.
    """
    coupon = get_object_or_404(Coupon, pk=pk)

    coupon.is_active = True
    coupon.save()

    messages.success(request, f'Gutschein {coupon.code} wurde aktiviert.')
    return redirect('ui:coupon_detail', pk=pk)


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['GET'])
def coupon_validate(request):
    """
    HTMX endpoint to validate a coupon code without applying it.
    Returns JSON with validation result.
    """
    code = request.GET.get('code', '').strip().upper()

    if not code:
        return JsonResponse({
            'valid': False,
            'message': 'Bitte geben Sie einen Code ein.'
        })

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'message': f'Code "{code}" ist nicht gültig.'
        })

    if not coupon.is_valid:
        return JsonResponse({
            'valid': False,
            'message': f'Code "{code}" ist {coupon.status_text.lower()}.'
        })

    return JsonResponse({
        'valid': True,
        'message': f'Code "{code}" ist gültig.',
        'coupon': {
            'id': str(coupon.id),
            'code': coupon.code,
            'name': coupon.name,
            'discount': coupon.discount_display,
            'duration': coupon.duration_display,
        }
    })


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['POST'])
def coupon_apply(request):
    """
    HTMX endpoint to apply a coupon code to a subscription.
    Returns HTML fragment with result.
    """
    code = request.POST.get('code', '').strip().upper()
    subscription_id = request.POST.get('subscription_id', '').strip()

    if not code or not subscription_id:
        return HttpResponse(
            '<div class="alert alert-danger">Ungültige Anfrage.</div>',
            status=400
        )

    try:
        coupon = Coupon.objects.get(code=code)
        subscription = Subscription.objects.select_related('customer', 'coupon').get(pk=subscription_id)
    except Coupon.DoesNotExist:
        return HttpResponse(
            f'<div class="alert alert-danger">Code "{code}" ist nicht gültig.</div>',
            status=400
        )
    except Subscription.DoesNotExist:
        return HttpResponse(
            '<div class="alert alert-danger">Abonnement nicht gefunden.</div>',
            status=404
        )

    # Check if subscription already has a coupon
    if subscription.coupon:
        return HttpResponse(
            f'<div class="alert alert-warning">Dieses Abonnement hat bereits einen Gutschein ({subscription.coupon.code}). Bitte entfernen Sie ihn zuerst.</div>',
            status=400
        )

    try:
        # Apply coupon
        redemption = CouponService.apply_to_subscription(
            coupon=coupon,
            subscription=subscription,
            customer=subscription.customer,
        )

        return HttpResponse(
            f'''<div class="alert alert-success">
                Gutschein {coupon.code} wurde erfolgreich angewendet!<br>
                <strong>{coupon.discount_display}</strong> für <strong>{coupon.duration_display}</strong>
            </div>''',
            status=200
        )

    except ValidationError as e:
        return HttpResponse(
            f'<div class="alert alert-danger">{str(e)}</div>',
            status=400
        )
    except Exception as e:
        logger.exception(f'Failed to apply coupon {code} to subscription {subscription_id}: {e}')
        return HttpResponse(
            f'<div class="alert alert-danger">Fehler beim Anwenden des Gutscheins: {str(e)}</div>',
            status=500
        )


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['POST'])
def coupon_remove(request, subscription_id):
    """
    Remove coupon from a subscription.
    Accessible by superadmin and billing roles.
    """
    subscription = get_object_or_404(Subscription, pk=subscription_id)

    if not subscription.coupon:
        messages.warning(request, 'Dieses Abonnement hat keinen Gutschein.')
        return redirect('ui:customer_detail', pk=subscription.customer.pk)

    coupon_code = subscription.coupon.code

    try:
        CouponService.remove_from_subscription(subscription)
        messages.success(request, f'Gutschein {coupon_code} wurde entfernt.')
    except Exception as e:
        logger.exception(f'Failed to remove coupon from subscription {subscription_id}: {e}')
        messages.error(request, f'Fehler beim Entfernen des Gutscheins: {str(e)}')

    return redirect('ui:customer_detail', pk=subscription.customer.pk)


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['GET'])
def coupon_type_fields(request):
    """
    HTMX endpoint to return the appropriate field for coupon type.
    Used for dynamic form switching between percent and fixed discount types.
    """
    coupon_type = request.GET.get('type', 'percent')

    if coupon_type == 'percent':
        html = '''
        <div id="discount-field">
            <label for="id_discount_percent" class="form-label">Rabatt (%)</label>
            <input type="number" step="0.01" min="0.01" max="100"
                   name="discount_percent" class="form-control"
                   id="id_discount_percent" placeholder="z.B. 20.00">
            <div class="form-text">Prozentualer Rabatt (0.01 - 100.00)</div>
        </div>
        '''
    else:  # fixed
        html = '''
        <div id="discount-field">
            <label for="id_discount_amount" class="form-label">Rabatt (€)</label>
            <input type="number" step="0.01" min="0.01"
                   name="discount_amount" class="form-control"
                   id="id_discount_amount" placeholder="z.B. 50.00">
            <div class="form-text">Fixer Rabattbetrag in EUR</div>
        </div>
        '''

    return HttpResponse(html)


@login_required
@role_required('superadmin', 'billing')
@require_http_methods(['GET'])
def coupon_duration_fields(request):
    """
    HTMX endpoint to return the appropriate field for coupon duration.
    Used for dynamic form switching between repeating and forever duration.
    """
    duration = request.GET.get('duration', 'forever')

    if duration == 'repeating':
        html = '''
        <div id="duration-months-field">
            <label for="id_duration_in_months" class="form-label">Anzahl Monate</label>
            <input type="number" min="1" name="duration_in_months"
                   class="form-control" id="id_duration_in_months"
                   placeholder="z.B. 3">
            <div class="form-text">Anzahl der Monate für den wiederkehrenden Rabatt</div>
        </div>
        '''
    else:  # forever
        html = '<div id="duration-months-field"></div>'

    return HttpResponse(html)
