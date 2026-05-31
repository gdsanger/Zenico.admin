"""
StripeImportService - Import products and prices from Stripe.

Provides methods to fetch Stripe products and prices for configuration UI.
"""

import logging
from typing import List, Dict, Optional

from core.services.stripe import get_stripe

logger = logging.getLogger(__name__)


class StripeImportService:
    """
    Service for importing Stripe products and prices.

    Used for the plan-wiring UI to populate dropdowns with available
    Stripe products and prices.
    """

    @staticmethod
    def fetch_products() -> List[Dict]:
        """
        Fetch all active Stripe products.

        Returns:
            List of dicts with product information:
            [
                {
                    "id": "prod_...",
                    "name": "Product Name",
                    "description": "Product description"
                },
                ...
            ]
        """
        try:
            stripe_api = get_stripe()
            products = stripe_api.Product.list(active=True, limit=100)

            result = []
            for product in products.auto_paging_iter():
                result.append({
                    'id': product.id,
                    'name': product.name,
                    'description': product.description or '',
                })

            logger.info(f'Fetched {len(result)} active products from Stripe')
            return result

        except Exception as e:
            logger.exception(f'Failed to fetch Stripe products: {e}')
            raise

    @staticmethod
    def fetch_prices(product_id: str) -> List[Dict]:
        """
        Fetch all active prices for a specific Stripe product.

        Args:
            product_id: Stripe product ID (prod_...)

        Returns:
            List of dicts with price information:
            [
                {
                    "id": "price_...",
                    "unit_amount": 1900,  # in cents
                    "currency": "eur",
                    "recurring": {
                        "interval": "month",
                        "usage_type": "licensed"
                    },
                    "nickname": "User License"
                },
                ...
            ]
        """
        try:
            stripe_api = get_stripe()
            prices = stripe_api.Price.list(
                product=product_id,
                active=True,
                limit=100
            )

            result = []
            for price in prices.auto_paging_iter():
                price_data = {
                    'id': price.id,
                    'unit_amount': price.unit_amount or 0,
                    'currency': price.currency,
                    'nickname': price.nickname or '',
                }

                # Include recurring information if present
                if price.recurring:
                    price_data['recurring'] = {
                        'interval': price.recurring.interval,
                        'usage_type': price.recurring.usage_type,
                    }

                result.append(price_data)

            logger.info(f'Fetched {len(result)} active prices for product {product_id}')
            return result

        except Exception as e:
            logger.exception(f'Failed to fetch Stripe prices for product {product_id}: {e}')
            raise

    @staticmethod
    def fetch_all_prices() -> List[Dict]:
        """
        Fetch all active prices across all products.

        Returns:
            List of dicts with price information including product details:
            [
                {
                    "id": "price_...",
                    "product_id": "prod_...",
                    "product_name": "Product Name",
                    "unit_amount": 1900,  # in cents
                    "currency": "eur",
                    "recurring": {
                        "interval": "month",
                        "usage_type": "licensed"
                    },
                    "nickname": "User License"
                },
                ...
            ]
        """
        try:
            stripe_api = get_stripe()
            prices = stripe_api.Price.list(active=True, limit=100)

            result = []
            for price in prices.auto_paging_iter():
                price_data = {
                    'id': price.id,
                    'product_id': price.product if isinstance(price.product, str) else price.product.id,
                    'unit_amount': price.unit_amount or 0,
                    'currency': price.currency,
                    'nickname': price.nickname or '',
                }

                # Include recurring information if present
                if price.recurring:
                    price_data['recurring'] = {
                        'interval': price.recurring.interval,
                        'usage_type': price.recurring.usage_type,
                    }

                # Fetch product name if product is expanded
                if not isinstance(price.product, str):
                    price_data['product_name'] = price.product.name
                else:
                    # Product is just an ID, need to fetch it
                    try:
                        product = stripe_api.Product.retrieve(price.product)
                        price_data['product_name'] = product.name
                    except Exception:
                        price_data['product_name'] = price.product

                result.append(price_data)

            logger.info(f'Fetched {len(result)} active prices from Stripe')
            return result

        except Exception as e:
            logger.exception(f'Failed to fetch all Stripe prices: {e}')
            raise

    @staticmethod
    def format_price_display(price: Dict) -> str:
        """
        Format a price dict for display in UI dropdowns.

        Args:
            price: Price dict from fetch_prices() or fetch_all_prices()

        Returns:
            Formatted string like: "User License — 19.00€/month (price_abc123)"
        """
        amount = price.get('unit_amount', 0) / 100
        currency = price.get('currency', 'eur').upper()
        nickname = price.get('nickname', '')
        price_id = price.get('id', '')

        # Format recurring interval
        interval = ''
        if price.get('recurring'):
            interval = f"/{price['recurring']['interval']}"

        # Build display string
        display = f"{nickname} — {amount:.2f}{currency}{interval} ({price_id})" if nickname else f"{amount:.2f}{currency}{interval} ({price_id})"

        return display

    @staticmethod
    def validate_price_product(price_id: str, product_id: str) -> bool:
        """
        Validate that a price belongs to a specific product.

        Args:
            price_id: Stripe price ID (price_...)
            product_id: Stripe product ID (prod_...)

        Returns:
            True if the price belongs to the product, False otherwise
        """
        try:
            stripe_api = get_stripe()
            price = stripe_api.Price.retrieve(price_id)

            # Get product ID from price (could be string or expanded object)
            price_product_id = price.product if isinstance(price.product, str) else price.product.id

            return price_product_id == product_id

        except Exception as e:
            logger.exception(f'Failed to validate price {price_id} for product {product_id}: {e}')
            return False
