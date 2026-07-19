from decimal import Decimal

from django.db import migrations


def zero_price_per_instance(apps, schema_editor):
    """
    Instance pricing was retired from the business model (user-seat + optional
    AI addon only). Zero out the now-unused reporting field on all plans.
    """
    Plan = apps.get_model('customers', 'Plan')
    Plan.objects.update(price_per_instance=Decimal('0.00'))


def reverse_noop(apps, schema_editor):
    """No-op: the original per-plan instance prices are not worth restoring."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0009_migrate_plan_data'),
    ]

    operations = [
        migrations.RunPython(zero_price_per_instance, reverse_noop),
    ]
