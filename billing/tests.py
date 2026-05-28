from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from decimal import Decimal
from .models import StripeEvent
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
