from django.db import transaction
from django.utils import timezone
from .models import Customer, Subscription, Plan
from instances.models import Instance
from audit.models import AuditLog


class CustomerService:
    """
    Service class for customer-related operations.
    Provides atomic operations for creating customers with related resources.
    """

    @staticmethod
    def create_customer(
        slug: str,
        company_name: str,
        contact_name: str,
        contact_email: str,
        billing_email: str,
        plan: Plan,
        user_seats: int,
        instance_seats: int,
        stripe_subscription_id: str,
        ai_addon: bool = False,
        **kwargs
    ) -> tuple[Customer, Subscription, Instance]:
        """
        Atomically create a Customer, Subscription, and Master Instance.

        All operations are wrapped in a database transaction. If any step fails,
        all changes are rolled back, ensuring no partial customer creation.

        Args:
            slug: Customer slug (2-10 lowercase alphanumeric characters)
            company_name: Company name
            contact_name: Contact person name
            contact_email: Contact email address
            billing_email: Billing email address
            plan: Plan instance for the subscription
            user_seats: Total user seats for the subscription
            instance_seats: Total instance seats for the subscription
            stripe_subscription_id: Stripe subscription ID
            ai_addon: Whether AI addon is active (default: False)
            **kwargs: Additional optional fields for Customer (billing_address,
                     billing_city, billing_postal_code, billing_country, vat_id,
                     stripe_customer_id, contact_phone, notes, status)

        Returns:
            tuple[Customer, Subscription, Instance]: The created customer, subscription,
                                                     and master instance

        Raises:
            ValidationError: If any of the created objects fail validation
            IntegrityError: If unique constraints are violated (e.g., slug already exists)
            Exception: If any step in the transaction fails, triggering a complete rollback
        """
        with transaction.atomic():
            # Step 1: Create Customer
            customer = Customer(
                slug=slug,
                company_name=company_name,
                contact_name=contact_name,
                contact_email=contact_email,
                billing_email=billing_email,
                **kwargs
            )
            customer.full_clean()  # Validate before saving
            customer.save()

            # Step 2: Create Subscription
            subscription = Subscription(
                customer=customer,
                plan=plan,
                stripe_subscription_id=stripe_subscription_id,
                stripe_status='active',  # New subscriptions start as active
                user_seats_total=user_seats,
                instance_seats_total=instance_seats,
                ai_addon_active=ai_addon,
                current_period_start=timezone.now(),
            )
            subscription.full_clean()  # Validate before saving
            subscription.save()

            # Step 3: Create Master Instance using the manager method
            master_instance = Instance.objects.create_master(
                customer=customer,
                subscription=subscription,
                display_name=f"{company_name} Master",
                user_seats=user_seats,
                ai_addon_active=ai_addon,
                status='provisioning',
            )

            # Step 4: Create AuditLog entry
            AuditLog.objects.create(
                customer=customer,
                actor_email='system',
                action='customer.created',
                resource_type='Customer',
                resource_id=str(customer.id),
                after={
                    'slug': customer.slug,
                    'company_name': customer.company_name,
                    'plan': plan.name,
                    'user_seats': user_seats,
                    'instance_seats': instance_seats,
                },
                note=f'Customer created with master instance and subscription to {plan.display_name} plan'
            )

            return customer, subscription, master_instance
