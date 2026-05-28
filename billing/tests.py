from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from decimal import Decimal
from .models import StripeEvent, Invoice
from customers.models import Customer, Plan, Subscription


class StripeEventModelTest(TestCase):
    """Test cases for the StripeEvent model."""

    def setUp(self):
        """Set up test data."""
        # Use existing plan from data migration
        self.plan = Plan.objects.filter(name='starter').first()

        # Create a customer
        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='John Doe',
            contact_email='john@testco.com',
            billing_email='billing@testco.com',
            billing_address='123 Main St',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE'
        )

        # Create a subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=5
        )

        # Basic event data
        self.event_data = {
            'stripe_event_id': 'evt_test123',
            'event_type': 'customer.subscription.created',
            'payload': {
                'id': 'evt_test123',
                'object': 'event',
                'data': {
                    'object': {
                        'id': 'sub_test123',
                        'status': 'active'
                    }
                }
            }
        }

    def test_stripe_event_creation(self):
        """Test creating a StripeEvent with valid data."""
        event = StripeEvent.objects.create(**self.event_data)
        self.assertIsNotNone(event.id)
        self.assertEqual(event.stripe_event_id, 'evt_test123')
        self.assertEqual(event.event_type, 'customer.subscription.created')
        self.assertFalse(event.processed)
        self.assertIsNone(event.customer)
        self.assertIsNotNone(event.received_at)
        self.assertIsNone(event.processed_at)
        self.assertEqual(event.error_message, '')

    def test_stripe_event_with_customer(self):
        """Test creating a StripeEvent with associated customer."""
        event = StripeEvent.objects.create(
            customer=self.customer,
            **self.event_data
        )
        self.assertEqual(event.customer, self.customer)
        self.assertEqual(event.customer.company_name, 'Test Company')

    def test_stripe_event_id_unique_constraint(self):
        """Test that stripe_event_id must be unique."""
        StripeEvent.objects.create(**self.event_data)
        with self.assertRaises(IntegrityError):
            StripeEvent.objects.create(**self.event_data)

    def test_stripe_event_default_values(self):
        """Test default values for StripeEvent fields."""
        event = StripeEvent.objects.create(**self.event_data)
        self.assertFalse(event.processed)
        self.assertEqual(event.error_message, '')
        self.assertIsNone(event.customer)
        self.assertIsNone(event.processed_at)

    def test_stripe_event_str_method_unprocessed(self):
        """Test the __str__ method for unprocessed event."""
        event = StripeEvent.objects.create(**self.event_data)
        str_repr = str(event)
        self.assertIn('⏳', str_repr)
        self.assertIn('customer.subscription.created', str_repr)
        self.assertIn('evt_test123', str_repr)

    def test_stripe_event_str_method_processed(self):
        """Test the __str__ method for processed event."""
        event = StripeEvent.objects.create(**self.event_data)
        event.processed = True
        event.processed_at = timezone.now()
        event.save()
        str_repr = str(event)
        self.assertIn('✓', str_repr)
        self.assertIn('customer.subscription.created', str_repr)
        self.assertIn('evt_test123', str_repr)

    def test_stripe_event_processed_workflow(self):
        """Test the typical event processing workflow."""
        # Create event (unprocessed)
        event = StripeEvent.objects.create(**self.event_data)
        self.assertFalse(event.processed)
        self.assertIsNone(event.processed_at)

        # Process event
        event.processed = True
        event.processed_at = timezone.now()
        event.customer = self.customer
        event.save()

        # Verify processed state
        event.refresh_from_db()
        self.assertTrue(event.processed)
        self.assertIsNotNone(event.processed_at)
        self.assertEqual(event.customer, self.customer)

    def test_stripe_event_error_handling(self):
        """Test recording error messages for failed processing."""
        event = StripeEvent.objects.create(**self.event_data)
        error_msg = "Failed to process event: Invalid subscription ID"
        event.error_message = error_msg
        event.save()

        event.refresh_from_db()
        self.assertEqual(event.error_message, error_msg)
        self.assertFalse(event.processed)

    def test_stripe_event_customer_set_null(self):
        """Test that deleting customer sets event.customer to NULL."""
        event = StripeEvent.objects.create(
            customer=self.customer,
            **self.event_data
        )
        self.assertEqual(event.customer, self.customer)

        # Delete subscription first (PROTECT constraint), then customer
        self.subscription.delete()
        self.customer.delete()

        # Verify event still exists with NULL customer
        event.refresh_from_db()
        self.assertIsNone(event.customer)
        self.assertEqual(event.stripe_event_id, 'evt_test123')

    def test_stripe_event_uuid_primary_key(self):
        """Test that StripeEvent uses UUID as primary key."""
        event = StripeEvent.objects.create(**self.event_data)
        self.assertIsNotNone(event.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(event.id)), 36)

    def test_stripe_event_timestamps(self):
        """Test that received_at is automatically set."""
        event = StripeEvent.objects.create(**self.event_data)
        self.assertIsNotNone(event.received_at)
        # received_at should be close to now
        time_diff = timezone.now() - event.received_at
        self.assertLess(time_diff.total_seconds(), 2)

    def test_stripe_event_ordering(self):
        """Test that events are ordered by received_at descending."""
        event1 = StripeEvent.objects.create(
            stripe_event_id='evt_001',
            event_type='customer.created',
            payload={}
        )
        event2 = StripeEvent.objects.create(
            stripe_event_id='evt_002',
            event_type='customer.updated',
            payload={}
        )
        event3 = StripeEvent.objects.create(
            stripe_event_id='evt_003',
            event_type='customer.deleted',
            payload={}
        )

        events = list(StripeEvent.objects.all())
        # Most recent first (descending order)
        self.assertEqual(events[0].stripe_event_id, 'evt_003')
        self.assertEqual(events[1].stripe_event_id, 'evt_002')
        self.assertEqual(events[2].stripe_event_id, 'evt_001')

    def test_stripe_event_queue_query(self):
        """Test efficient queue query using processed + received_at index."""
        # Create multiple events with different states
        StripeEvent.objects.create(
            stripe_event_id='evt_processed',
            event_type='test.event',
            payload={},
            processed=True,
            processed_at=timezone.now()
        )
        unprocessed1 = StripeEvent.objects.create(
            stripe_event_id='evt_unprocessed1',
            event_type='test.event',
            payload={},
            processed=False
        )
        unprocessed2 = StripeEvent.objects.create(
            stripe_event_id='evt_unprocessed2',
            event_type='test.event',
            payload={},
            processed=False
        )

        # Query unprocessed events (should use index)
        unprocessed_events = StripeEvent.objects.filter(
            processed=False
        ).order_by('received_at')

        self.assertEqual(unprocessed_events.count(), 2)
        # Verify order (oldest first for queue processing)
        events_list = list(unprocessed_events)
        self.assertEqual(events_list[0].stripe_event_id, 'evt_unprocessed1')
        self.assertEqual(events_list[1].stripe_event_id, 'evt_unprocessed2')

    def test_stripe_event_event_type_filter(self):
        """Test filtering by event_type using index."""
        StripeEvent.objects.create(
            stripe_event_id='evt_sub_created',
            event_type='customer.subscription.created',
            payload={}
        )
        StripeEvent.objects.create(
            stripe_event_id='evt_sub_updated',
            event_type='customer.subscription.updated',
            payload={}
        )
        StripeEvent.objects.create(
            stripe_event_id='evt_cust_created',
            event_type='customer.created',
            payload={}
        )

        # Filter by event type (should use index)
        sub_events = StripeEvent.objects.filter(
            event_type__startswith='customer.subscription'
        )
        self.assertEqual(sub_events.count(), 2)

    def test_stripe_event_payload_json_field(self):
        """Test that payload correctly stores and retrieves JSON data."""
        complex_payload = {
            'id': 'evt_test',
            'object': 'event',
            'api_version': '2023-10-16',
            'data': {
                'object': {
                    'id': 'sub_123',
                    'items': [1, 2, 3],
                    'metadata': {
                        'key': 'value'
                    }
                }
            }
        }
        event = StripeEvent.objects.create(
            stripe_event_id='evt_json_test',
            event_type='test.event',
            payload=complex_payload
        )

        event.refresh_from_db()
        self.assertEqual(event.payload['id'], 'evt_test')
        self.assertEqual(event.payload['data']['object']['items'], [1, 2, 3])
        self.assertEqual(event.payload['data']['object']['metadata']['key'], 'value')

    def test_stripe_event_related_name(self):
        """Test that customer.stripe_events reverse relationship works."""
        event1 = StripeEvent.objects.create(
            customer=self.customer,
            stripe_event_id='evt_rel1',
            event_type='test.event',
            payload={}
        )
        event2 = StripeEvent.objects.create(
            customer=self.customer,
            stripe_event_id='evt_rel2',
            event_type='test.event',
            payload={}
        )

        # Access events through customer
        customer_events = self.customer.stripe_events.all()
        self.assertEqual(customer_events.count(), 2)
        event_ids = [e.stripe_event_id for e in customer_events]
        self.assertIn('evt_rel1', event_ids)
        self.assertIn('evt_rel2', event_ids)


class InvoiceModelTest(TestCase):
    """Test cases for the Invoice model."""

    def setUp(self):
        """Set up test data."""
        # Use existing plan from data migration
        self.plan = Plan.objects.filter(name='starter').first()

        # Create a customer
        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='John Doe',
            contact_email='john@testco.com',
            billing_email='billing@testco.com',
            billing_address='123 Main St',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE'
        )

        # Create a subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=5
        )

        # Basic invoice data
        self.invoice_data = {
            'customer': self.customer,
            'subscription': self.subscription,
            'stripe_invoice_id': 'in_test123',
            'amount_due': Decimal('100.00'),
            'amount_paid': Decimal('0.00'),
            'currency': 'EUR',
            'status': 'open'
        }

    def test_invoice_creation(self):
        """Test creating an Invoice with valid data."""
        invoice = Invoice.objects.create(**self.invoice_data)
        self.assertIsNotNone(invoice.id)
        self.assertEqual(invoice.stripe_invoice_id, 'in_test123')
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.subscription, self.subscription)
        self.assertEqual(invoice.amount_due, Decimal('100.00'))
        self.assertEqual(invoice.amount_paid, Decimal('0.00'))
        self.assertEqual(invoice.currency, 'EUR')
        self.assertEqual(invoice.status, 'open')
        self.assertIsNotNone(invoice.created_at)
        self.assertIsNotNone(invoice.updated_at)

    def test_invoice_without_subscription(self):
        """Test creating an Invoice without a subscription."""
        invoice_data = self.invoice_data.copy()
        invoice_data['subscription'] = None
        invoice = Invoice.objects.create(**invoice_data)
        self.assertEqual(invoice.customer, self.customer)
        self.assertIsNone(invoice.subscription)

    def test_stripe_invoice_id_unique_constraint(self):
        """Test that stripe_invoice_id must be unique."""
        Invoice.objects.create(**self.invoice_data)
        with self.assertRaises(IntegrityError):
            Invoice.objects.create(**self.invoice_data)

    def test_invoice_default_values(self):
        """Test default values for Invoice fields."""
        invoice_data = {
            'customer': self.customer,
            'stripe_invoice_id': 'in_default_test',
            'amount_due': Decimal('50.00'),
            'status': 'draft'
        }
        invoice = Invoice.objects.create(**invoice_data)
        self.assertEqual(invoice.amount_paid, Decimal('0.00'))
        self.assertEqual(invoice.currency, 'EUR')
        self.assertIsNone(invoice.subscription)
        self.assertEqual(invoice.stripe_hosted_url, '')
        self.assertEqual(invoice.stripe_pdf_url, '')
        self.assertIsNone(invoice.period_start)
        self.assertIsNone(invoice.period_end)
        self.assertIsNone(invoice.due_date)
        self.assertIsNone(invoice.paid_at)

    def test_invoice_status_choices(self):
        """Test all valid status choices."""
        statuses = ['draft', 'open', 'paid', 'void', 'uncollectible']
        for i, status in enumerate(statuses):
            invoice_data = self.invoice_data.copy()
            invoice_data['stripe_invoice_id'] = f'in_status_{i}'
            invoice_data['status'] = status
            invoice = Invoice.objects.create(**invoice_data)
            self.assertEqual(invoice.status, status)

    def test_invoice_str_method(self):
        """Test the __str__ method."""
        invoice = Invoice.objects.create(**self.invoice_data)
        str_repr = str(invoice)
        self.assertIn('in_test123', str_repr)
        self.assertIn('Test Company', str_repr)
        self.assertIn('open', str_repr)

    def test_invoice_uuid_primary_key(self):
        """Test that Invoice uses UUID as primary key."""
        invoice = Invoice.objects.create(**self.invoice_data)
        self.assertIsNotNone(invoice.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(invoice.id)), 36)

    def test_invoice_timestamps(self):
        """Test that created_at and updated_at are automatically set."""
        invoice = Invoice.objects.create(**self.invoice_data)
        self.assertIsNotNone(invoice.created_at)
        self.assertIsNotNone(invoice.updated_at)
        # created_at should be close to now
        time_diff = timezone.now() - invoice.created_at
        self.assertLess(time_diff.total_seconds(), 2)

    def test_invoice_ordering(self):
        """Test that invoices are ordered by created_at descending."""
        invoice1 = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_001',
            amount_due=Decimal('100.00'),
            status='paid'
        )
        invoice2 = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_002',
            amount_due=Decimal('200.00'),
            status='open'
        )
        invoice3 = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_003',
            amount_due=Decimal('300.00'),
            status='draft'
        )

        invoices = list(Invoice.objects.all())
        # Most recent first (descending order)
        self.assertEqual(invoices[0].stripe_invoice_id, 'in_003')
        self.assertEqual(invoices[1].stripe_invoice_id, 'in_002')
        self.assertEqual(invoices[2].stripe_invoice_id, 'in_001')

    def test_invoice_customer_protect(self):
        """Test that deleting customer is prevented when invoices exist."""
        Invoice.objects.create(**self.invoice_data)
        # Delete subscription first (PROTECT constraint)
        self.subscription.delete()
        # Try to delete customer - should raise ProtectedError
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.customer.delete()

    def test_invoice_subscription_set_null(self):
        """Test that deleting subscription sets invoice.subscription to NULL."""
        invoice = Invoice.objects.create(**self.invoice_data)
        self.assertEqual(invoice.subscription, self.subscription)

        # Delete subscription
        self.subscription.delete()

        # Verify invoice still exists with NULL subscription
        invoice.refresh_from_db()
        self.assertIsNone(invoice.subscription)
        self.assertEqual(invoice.stripe_invoice_id, 'in_test123')
        self.assertEqual(invoice.customer, self.customer)

    def test_invoice_related_name(self):
        """Test that customer.invoices reverse relationship works."""
        invoice1 = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_rel1',
            amount_due=Decimal('100.00'),
            status='paid'
        )
        invoice2 = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_rel2',
            amount_due=Decimal('200.00'),
            status='open'
        )

        # Access invoices through customer
        customer_invoices = self.customer.invoices.all()
        self.assertEqual(customer_invoices.count(), 2)
        invoice_ids = [inv.stripe_invoice_id for inv in customer_invoices]
        self.assertIn('in_rel1', invoice_ids)
        self.assertIn('in_rel2', invoice_ids)

    def test_invoice_subscription_related_name(self):
        """Test that subscription.invoices reverse relationship works."""
        invoice1 = Invoice.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            stripe_invoice_id='in_sub1',
            amount_due=Decimal('100.00'),
            status='paid'
        )
        invoice2 = Invoice.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            stripe_invoice_id='in_sub2',
            amount_due=Decimal('200.00'),
            status='open'
        )

        # Access invoices through subscription
        subscription_invoices = self.subscription.invoices.all()
        self.assertEqual(subscription_invoices.count(), 2)
        invoice_ids = [inv.stripe_invoice_id for inv in subscription_invoices]
        self.assertIn('in_sub1', invoice_ids)
        self.assertIn('in_sub2', invoice_ids)

    def test_invoice_customer_status_query(self):
        """Test efficient query using customer + status index."""
        # Create invoices with different statuses for this customer
        Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_paid1',
            amount_due=Decimal('100.00'),
            status='paid'
        )
        Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_paid2',
            amount_due=Decimal('200.00'),
            status='paid'
        )
        Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_open1',
            amount_due=Decimal('300.00'),
            status='open'
        )

        # Query by customer and status (should use index)
        paid_invoices = Invoice.objects.filter(
            customer=self.customer,
            status='paid'
        )
        self.assertEqual(paid_invoices.count(), 2)

        open_invoices = Invoice.objects.filter(
            customer=self.customer,
            status='open'
        )
        self.assertEqual(open_invoices.count(), 1)

    def test_invoice_decimal_precision(self):
        """Test that decimal fields maintain proper precision."""
        invoice = Invoice.objects.create(
            customer=self.customer,
            stripe_invoice_id='in_decimal_test',
            amount_due=Decimal('123.45'),
            amount_paid=Decimal('50.67'),
            status='open'
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_due, Decimal('123.45'))
        self.assertEqual(invoice.amount_paid, Decimal('50.67'))

    def test_invoice_with_all_fields(self):
        """Test creating an Invoice with all optional fields populated."""
        now = timezone.now()
        invoice = Invoice.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            stripe_invoice_id='in_complete',
            stripe_hosted_url='https://invoice.stripe.com/i/test123',
            stripe_pdf_url='https://invoice.stripe.com/i/test123/pdf',
            amount_due=Decimal('500.00'),
            amount_paid=Decimal('500.00'),
            currency='USD',
            status='paid',
            period_start=now,
            period_end=now,
            due_date=now,
            paid_at=now
        )
        self.assertEqual(invoice.stripe_hosted_url, 'https://invoice.stripe.com/i/test123')
        self.assertEqual(invoice.stripe_pdf_url, 'https://invoice.stripe.com/i/test123/pdf')
        self.assertEqual(invoice.currency, 'USD')
        self.assertEqual(invoice.status, 'paid')
        self.assertIsNotNone(invoice.period_start)
        self.assertIsNotNone(invoice.period_end)
        self.assertIsNotNone(invoice.due_date)
        self.assertIsNotNone(invoice.paid_at)

    def test_invoice_amount_validation(self):
        """Test that amount fields have minimum value validators."""
        invoice_data = self.invoice_data.copy()
        invoice_data['stripe_invoice_id'] = 'in_valid_amount'
        invoice_data['amount_due'] = Decimal('0.00')
        invoice_data['amount_paid'] = Decimal('0.00')
        # This should work (0.00 is valid)
        invoice = Invoice.objects.create(**invoice_data)
        self.assertEqual(invoice.amount_due, Decimal('0.00'))
        self.assertEqual(invoice.amount_paid, Decimal('0.00'))

    def test_invoice_currency_field(self):
        """Test that currency field accepts different currency codes."""
        currencies = ['EUR', 'USD', 'GBP', 'CHF']
        for i, currency in enumerate(currencies):
            invoice_data = self.invoice_data.copy()
            invoice_data['stripe_invoice_id'] = f'in_curr_{i}'
            invoice_data['currency'] = currency
            invoice = Invoice.objects.create(**invoice_data)
            self.assertEqual(invoice.currency, currency)


class StripeWebhookHandlerTests(TestCase):
    """Test suite for StripeWebhookHandler."""

    def setUp(self):
        """Set up test data."""
        import os
        os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test_secret'

        self.customer = Customer.objects.create(
            slug='webhooktest',
            company_name='Webhook Test Co',
            contact_name='Test User',
            contact_email='test@webhook.com',
            billing_email='billing@webhook.com',
            stripe_customer_id='cus_webhook123',
        )

    def test_webhook_signature_verification_failure(self):
        """Test that invalid signature raises error."""
        from core.services.webhook import StripeWebhookHandler
        
        payload = b'{"id": "evt_test", "type": "test"}'
        bad_signature = 'invalid_signature'

        with self.assertRaises(Exception):
            StripeWebhookHandler.handle(payload, bad_signature)

    def test_webhook_idempotency(self):
        """Test that processing same event twice is idempotent."""
        from core.services.webhook import StripeWebhookHandler
        from billing.models import StripeEvent
        from unittest.mock import patch, MagicMock

        # Create a mock event
        mock_event = {
            'id': 'evt_idempotent_test',
            'type': 'customer.updated',
            'data': {
                'object': {
                    'id': self.customer.stripe_customer_id,
                    'email': 'new@webhook.com',
                }
            }
        }

        # Mock the signature verification
        with patch('stripe.Webhook.construct_event', return_value=mock_event):
            # First call - should process
            StripeWebhookHandler.handle(b'payload', 'sig')

            # Check event was created
            db_event = StripeEvent.objects.get(stripe_event_id='evt_idempotent_test')
            self.assertTrue(db_event.processed)

            # Second call - should skip (idempotent)
            StripeWebhookHandler.handle(b'payload', 'sig')

            # Event should still be processed exactly once
            self.assertEqual(StripeEvent.objects.filter(stripe_event_id='evt_idempotent_test').count(), 1)

    def test_webhook_subscription_deleted_suspends_instances(self):
        """Test that subscription.deleted suspends all instances."""
        from core.services.webhook import StripeWebhookHandler
        from customers.models import Subscription, Plan
        from instances.models import Instance
        from unittest.mock import patch

        # Get or create plan
        plan, _ = Plan.objects.get_or_create(
            name='starter',
            defaults={'display_name': 'Starter Plan'}
        )

        # Create subscription
        subscription = Subscription.objects.create(
            customer=self.customer,
            plan=plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=2,
        )

        # Create active instances
        instance1 = Instance.objects.create_master(
            customer=self.customer,
            subscription=subscription,
            display_name='Test Instance 1',
            user_seats=10,
            status='active',
        )
        instance2 = Instance.objects.create(
            customer=self.customer,
            slug='test2',
            display_name='Test Instance 2',
            subscription=subscription,
            user_seats=5,
            is_master=False,
            status='active',
        )

        # Mock event
        mock_event = {
            'id': 'evt_sub_deleted',
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': self.customer.stripe_customer_id,
                    'status': 'canceled',
                }
            }
        }

        with patch('stripe.Webhook.construct_event', return_value=mock_event):
            StripeWebhookHandler.handle(b'payload', 'sig')

        # Check instances are suspended
        instance1.refresh_from_db()
        instance2.refresh_from_db()
        self.assertEqual(instance1.status, 'suspended')
        self.assertEqual(instance2.status, 'suspended')

    def test_webhook_invoice_payment_failed_sends_email(self):
        """Test that invoice.payment_failed sends email."""
        from core.services.webhook import StripeWebhookHandler
        from unittest.mock import patch, MagicMock

        mock_event = {
            'id': 'evt_payment_failed',
            'type': 'invoice.payment_failed',
            'data': {
                'object': {
                    'id': 'in_test123',
                    'customer': self.customer.stripe_customer_id,
                    'amount_due': 19900,  # $199 in cents
                    'currency': 'usd',
                    'status': 'open',
                    'hosted_invoice_url': 'https://stripe.com/invoice/test',
                }
            }
        }

        with patch('stripe.Webhook.construct_event', return_value=mock_event):
            with patch('core.services.webhook.MailService.send_template') as mock_send:
                with patch('core.services.webhook.StripeService.sync_invoice') as mock_sync:
                    mock_send.return_value = True
                    mock_sync.return_value = None

                    StripeWebhookHandler.handle(b'payload', 'sig')

                    # Verify email was sent
                    mock_send.assert_called_once()
                    call_kwargs = mock_send.call_args.kwargs if hasattr(mock_send.call_args, 'kwargs') else mock_send.call_args[1]
                    self.assertEqual(call_kwargs['to'], self.customer.billing_email)
                    self.assertEqual(call_kwargs['template'], 'payment_failed')
