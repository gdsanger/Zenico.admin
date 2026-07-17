from django.test import TestCase

from billing.stripe_import import StripeImportService


class FormatPriceDisplayTestCase(TestCase):
    """Test StripeImportService.format_price_display, in particular cents-to-euro
    conversion and tiered-price handling (see #893)."""

    def test_flat_price_converts_cents_to_euros(self):
        price = {
            'id': 'price_ai_addon',
            'nickname': 'KI Add-On',
            'currency': 'eur',
            'unit_amount': 750,
            'billing_scheme': 'per_unit',
            'recurring': {'interval': 'month'},
        }
        display = StripeImportService.format_price_display(price)
        self.assertIn('7.50EUR', display)
        self.assertNotIn('750.00EUR', display)

    def test_tiered_price_shows_minimum_tier_amount_instead_of_zero(self):
        price = {
            'id': 'price_user_license',
            'nickname': 'User Lizenz',
            'currency': 'eur',
            'unit_amount': 0,
            'billing_scheme': 'tiered',
            'tiers': [
                {'unit_amount': 1900, 'up_to': 5},
                {'unit_amount': 1500, 'up_to': 20},
                {'unit_amount': 1200, 'up_to': None},
            ],
            'recurring': {'interval': 'month'},
        }
        display = StripeImportService.format_price_display(price)
        self.assertIn('Staffelpreis', display)
        self.assertIn('12.00EUR', display)
        self.assertNotIn('0.00EUR', display)

    def test_tiered_price_without_tier_data_falls_back_gracefully(self):
        price = {
            'id': 'price_user_license',
            'nickname': 'User Lizenz',
            'currency': 'eur',
            'unit_amount': 0,
            'billing_scheme': 'tiered',
            'tiers': None,
            'recurring': {'interval': 'month'},
        }
        display = StripeImportService.format_price_display(price)
        self.assertIn('Staffelpreis', display)
        self.assertNotIn('0.00EUR', display)
