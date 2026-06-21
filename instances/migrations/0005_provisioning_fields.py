from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0004_subscription_api_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='claimed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='claimed at',
                help_text='Zeitpunkt, an dem der Provisioning-Agent diese Instanz übernommen hat',
            ),
        ),
        migrations.AddField(
            model_name='instance',
            name='provisioning_error',
            field=models.TextField(
                blank=True,
                verbose_name='provisioning error',
                help_text='Letzte Fehlermeldung, falls status=failed',
            ),
        ),
        migrations.AddField(
            model_name='instance',
            name='image_tag',
            field=models.CharField(
                blank=True,
                default='latest',
                max_length=50,
                verbose_name='image tag',
                help_text='Ziel-Docker-Image-Tag, der bei der Bereitstellung deployed werden soll',
            ),
        ),
        migrations.AlterField(
            model_name='instance',
            name='status',
            field=models.CharField(
                choices=[
                    ('provisioning', 'Provisioning'),
                    ('active', 'Active'),
                    ('suspended', 'Suspended'),
                    ('deprovisioned', 'Deprovisioned'),
                    ('failed', 'Failed'),
                ],
                default='provisioning',
                max_length=20,
                verbose_name='status',
            ),
        ),
    ]
