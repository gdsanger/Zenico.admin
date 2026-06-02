"""
AI Agent System Models

Based on Agira architecture, adapted for Zenico.admin with instance-aware tracking.
"""

import uuid
import logging
from datetime import date, timedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from decimal import Decimal

logger = logging.getLogger(__name__)


class AIProviderType(models.TextChoices):
    OPENAI = 'OpenAI', 'OpenAI'
    ANTHROPIC = 'Anthropic', 'Anthropic'


class AIJobStatus(models.TextChoices):
    PENDING = 'Pending', 'Pending'
    COMPLETED = 'Completed', 'Completed'
    ERROR = 'Error', 'Error'
    CACHED = 'Cached', 'Cached'


class AIProvider(models.Model):
    """KI-Provider Konfiguration (OpenAI, Anthropic)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name='name')
    provider_type = models.CharField(
        max_length=20,
        choices=AIProviderType.choices,
        verbose_name='provider type'
    )
    api_key = models.CharField(
        max_length=500,
        verbose_name='API key (encrypted)',
        help_text='Encrypted API key'
    )
    organization_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='organization ID'
    )
    active = models.BooleanField(default=True, verbose_name='active')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        ordering = ['provider_type', 'name']
        verbose_name = 'AI Provider'
        verbose_name_plural = 'AI Providers'

    def __str__(self):
        return f'{self.name} ({self.provider_type})'

    def set_api_key(self, plaintext: str):
        """Encrypt and store API key."""
        self.api_key = self._encrypt(plaintext) if plaintext else ''

    def get_api_key(self) -> str:
        """Decrypt and return API key."""
        return self._decrypt(self.api_key) if self.api_key else ''

    @staticmethod
    def _get_cipher():
        """Get Fernet cipher instance."""
        key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
        if not key:
            raise ValueError('FIELD_ENCRYPTION_KEY not configured in settings')
        return Fernet(key.encode() if isinstance(key, str) else key)

    @staticmethod
    def _encrypt(plaintext: str) -> str:
        """Encrypt plaintext string."""
        if not plaintext:
            return ''
        cipher = AIProvider._get_cipher()
        encrypted_bytes = cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()

    @staticmethod
    def _decrypt(encrypted: str) -> str:
        """Decrypt encrypted string."""
        if not encrypted:
            return ''
        try:
            cipher = AIProvider._get_cipher()
            decrypted_bytes = cipher.decrypt(encrypted.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f'Failed to decrypt API key: {e}')
            return ''


class AIModel(models.Model):
    """KI-Modell mit Preisinformation"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        AIProvider,
        on_delete=models.CASCADE,
        related_name='models',
        verbose_name='provider'
    )
    name = models.CharField(max_length=255, verbose_name='name')
    model_id = models.CharField(
        max_length=255,
        verbose_name='model ID',
        help_text='Model identifier used in API calls'
    )
    input_price_per_1m_tokens = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='input price per 1M tokens (USD)',
        help_text='Price in USD per 1 million input tokens'
    )
    output_price_per_1m_tokens = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='output price per 1M tokens (USD)',
        help_text='Price in USD per 1 million output tokens'
    )
    active = models.BooleanField(default=True, verbose_name='active')
    is_default = models.BooleanField(default=False, verbose_name='is default')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        ordering = ['provider', 'name']
        verbose_name = 'AI Model'
        verbose_name_plural = 'AI Models'
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'model_id'],
                name='unique_provider_model',
                violation_error_message='This model ID already exists for this provider.'
            )
        ]

    def __str__(self):
        return f'{self.provider.provider_type} — {self.name}'

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate cost in USD for given token usage."""
        cost = Decimal('0.00')

        if self.input_price_per_1m_tokens and input_tokens:
            cost += (Decimal(input_tokens) / Decimal('1000000')) * self.input_price_per_1m_tokens

        if self.output_price_per_1m_tokens and output_tokens:
            cost += (Decimal(output_tokens) / Decimal('1000000')) * self.output_price_per_1m_tokens

        return cost.quantize(Decimal('0.000001'))


class AIAgent(models.Model):
    """
    KI-Agent Konfiguration — in DB gespeichert, UI-editierbar.
    Entspricht den YAML-Agents aus Agira, aber vollständig in DB.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='name',
        help_text='Unique agent identifier'
    )
    description = models.TextField(blank=True, verbose_name='description')
    provider = models.ForeignKey(
        AIProvider,
        on_delete=models.SET_NULL,
        null=True,
        related_name='agents',
        verbose_name='provider'
    )
    model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='agents',
        verbose_name='model'
    )
    role = models.TextField(
        verbose_name='role (system prompt)',
        help_text='System Prompt — Rolle und Kontext des Agenten'
    )
    task = models.TextField(
        verbose_name='task (user prompt template)',
        help_text='User Prompt Template — Aufgabenbeschreibung'
    )

    # Cache Konfiguration
    cache_enabled = models.BooleanField(default=True, verbose_name='cache enabled')
    cache_ttl_seconds = models.IntegerField(
        default=300,
        verbose_name='cache TTL (seconds)',
        help_text='Cache time-to-live in seconds'
    )
    cache_version = models.IntegerField(
        default=1,
        verbose_name='cache version',
        help_text='Increment to invalidate all cached responses for this agent'
    )

    # Einstellungen
    max_tokens = models.IntegerField(
        default=1000,
        verbose_name='max tokens',
        help_text='Maximum tokens in response'
    )
    temperature = models.FloatField(
        default=0.7,
        verbose_name='temperature',
        help_text='Sampling temperature (0.0-1.0)'
    )
    active = models.BooleanField(default=True, verbose_name='active')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        ordering = ['name']
        verbose_name = 'AI Agent'
        verbose_name_plural = 'AI Agents'

    def __str__(self):
        return self.name

    def to_yaml_dict(self) -> dict:
        """Export als YAML-kompatibles Dict."""
        return {
            'name': self.name,
            'description': self.description,
            'provider': self.provider.provider_type if self.provider else '',
            'model': self.model.model_id if self.model else '',
            'role': self.role,
            'task': self.task,
            'cache': {
                'enabled': self.cache_enabled,
                'ttl_seconds': self.cache_ttl_seconds,
                'key_strategy': 'content_hash',
                'agent_version': self.cache_version,
            },
        }


class AIJobsHistory(models.Model):
    """
    History aller KI-API-Calls — instance-aware.
    Basis für Token-Tracking und Kostenberechnung.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.CharField(
        max_length=255,
        default='zenico.ai',
        verbose_name='agent name'
    )
    instance = models.ForeignKey(
        'instances.Instance',
        on_delete=models.SET_NULL,
        null=True,
        related_name='ai_jobs',
        verbose_name='instance'
    )
    provider = models.ForeignKey(
        AIProvider,
        on_delete=models.SET_NULL,
        null=True,
        related_name='jobs',
        verbose_name='provider'
    )
    model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='jobs',
        verbose_name='model'
    )
    status = models.CharField(
        max_length=20,
        choices=AIJobStatus.choices,
        default=AIJobStatus.PENDING,
        verbose_name='status'
    )
    input_tokens = models.IntegerField(null=True, blank=True, verbose_name='input tokens')
    output_tokens = models.IntegerField(null=True, blank=True, verbose_name='output tokens')
    costs = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='costs (USD)',
        help_text='Kosten in USD'
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='duration (ms)'
    )
    error_message = models.TextField(blank=True, verbose_name='error message')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='timestamp')
    from_cache = models.BooleanField(default=False, verbose_name='from cache')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'AI Job History'
        verbose_name_plural = 'AI Job History'
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['instance', '-timestamp']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.agent} ({self.status}) @ {self.timestamp}'


class AITokenBudget(models.Model):
    """
    Wöchentliches Token-Budget pro Instance.
    Wird bei Phone Home in der License Response zurückgegeben.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.OneToOneField(
        'instances.Instance',
        on_delete=models.CASCADE,
        related_name='token_budget',
        verbose_name='instance'
    )
    weekly_limit = models.IntegerField(
        default=200_000,
        verbose_name='weekly limit',
        help_text='Maximale Tokens pro Woche'
    )
    tokens_used_week = models.IntegerField(
        default=0,
        verbose_name='tokens used this week'
    )
    week_start = models.DateField(
        auto_now_add=True,
        verbose_name='week start'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'AI Token Budget'
        verbose_name_plural = 'AI Token Budgets'

    def __str__(self):
        return f'{self.instance.display_name} — {self.tokens_used_week}/{self.weekly_limit}'

    @property
    def tokens_remaining(self) -> int:
        """Calculate remaining tokens for this week."""
        return max(0, self.weekly_limit - self.tokens_used_week)

    @property
    def is_exhausted(self) -> bool:
        """Check if weekly budget is exhausted."""
        return self.tokens_used_week >= self.weekly_limit

    def add_tokens(self, input_tokens: int, output_tokens: int):
        """Token-Verbrauch addieren und Budget aktualisieren."""
        self._reset_week_if_needed()
        total = (input_tokens or 0) + (output_tokens or 0)
        AITokenBudget.objects.filter(pk=self.pk).update(
            tokens_used_week=models.F('tokens_used_week') + total
        )
        self.refresh_from_db()

    def _reset_week_if_needed(self):
        """Wöchentliches Budget zurücksetzen wenn neue Woche."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Montag

        if self.week_start < week_start:
            AITokenBudget.objects.filter(pk=self.pk).update(
                tokens_used_week=0,
                week_start=week_start,
            )
            self.refresh_from_db()
