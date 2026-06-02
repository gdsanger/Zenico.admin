"""
Tests for AI Agent System
"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from customers.models import Customer, Plan, Subscription
from instances.models import Instance
from ai.models import (
    AIProvider,
    AIModel,
    AIAgent,
    AIJobsHistory,
    AITokenBudget,
    AIJobStatus,
)
from ai.router import AIRouter
from ai.agent_service import AgentService
from ai.providers.schemas import ProviderResponse, AIResponse


class AIProviderModelTest(TestCase):
    """Tests for AIProvider model."""

    def setUp(self):
        """Set up test data."""
        self.provider = AIProvider.objects.create(
            name='Test OpenAI',
            provider_type='OpenAI',
            active=True
        )

    def test_provider_creation(self):
        """Test provider can be created."""
        self.assertEqual(self.provider.name, 'Test OpenAI')
        self.assertEqual(self.provider.provider_type, 'OpenAI')
        self.assertTrue(self.provider.active)

    def test_provider_encryption(self):
        """Test API key encryption."""
        plaintext_key = 'sk-test-1234567890'
        self.provider.set_api_key(plaintext_key)
        self.provider.save()

        # Encrypted key should not match plaintext
        self.assertNotEqual(self.provider.api_key, plaintext_key)

        # Decrypted key should match plaintext
        decrypted = self.provider.get_api_key()
        self.assertEqual(decrypted, plaintext_key)


class AIModelModelTest(TestCase):
    """Tests for AIModel model."""

    def setUp(self):
        """Set up test data."""
        self.provider = AIProvider.objects.create(
            name='Test Provider',
            provider_type='OpenAI',
            active=True
        )
        self.model = AIModel.objects.create(
            provider=self.provider,
            name='GPT-4',
            model_id='gpt-4',
            input_price_per_1m_tokens=Decimal('30.00'),
            output_price_per_1m_tokens=Decimal('60.00'),
            active=True,
            is_default=True
        )

    def test_model_creation(self):
        """Test model can be created."""
        self.assertEqual(self.model.name, 'GPT-4')
        self.assertEqual(self.model.model_id, 'gpt-4')
        self.assertTrue(self.model.active)
        self.assertTrue(self.model.is_default)

    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = self.model.calculate_cost(1000, 500)
        # 1000 input tokens = 0.03 USD, 500 output tokens = 0.03 USD
        expected = Decimal('0.06')
        self.assertEqual(cost, expected)


class AIAgentModelTest(TestCase):
    """Tests for AIAgent model."""

    def setUp(self):
        """Set up test data."""
        self.provider = AIProvider.objects.create(
            name='Test Provider',
            provider_type='Anthropic',
            active=True
        )
        self.model = AIModel.objects.create(
            provider=self.provider,
            name='Claude',
            model_id='claude-sonnet-4-5',
            active=True
        )
        self.agent = AIAgent.objects.create(
            name='test-agent',
            description='Test agent',
            provider=self.provider,
            model=self.model,
            role='You are a test assistant.',
            task='Test the input.',
            cache_enabled=True,
            cache_ttl_seconds=300,
            max_tokens=100,
            temperature=0.7,
            active=True
        )

    def test_agent_creation(self):
        """Test agent can be created."""
        self.assertEqual(self.agent.name, 'test-agent')
        self.assertTrue(self.agent.active)
        self.assertTrue(self.agent.cache_enabled)

    def test_to_yaml_dict(self):
        """Test agent export to YAML dict."""
        yaml_dict = self.agent.to_yaml_dict()
        self.assertEqual(yaml_dict['name'], 'test-agent')
        self.assertEqual(yaml_dict['provider'], 'Anthropic')
        self.assertEqual(yaml_dict['model'], 'claude-sonnet-4-5')
        self.assertTrue(yaml_dict['cache']['enabled'])


class AITokenBudgetTest(TestCase):
    """Tests for AITokenBudget model."""

    def setUp(self):
        """Set up test data."""
        plan = Plan.objects.filter(name='starter').first()
        self.customer = Customer.objects.create(
            company_name='Test Company',
            slug='testco',
            contact_name='Test User',
            contact_email='test@example.com'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=plan,
            user_seats_total=5,
            instance_seats_total=1,
            ai_addon_active=True
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Instance',
            is_master=True,
            status='active'
        )

    def test_budget_creation(self):
        """Test budget can be created."""
        budget = AITokenBudget.objects.create(
            instance=self.instance,
            weekly_limit=200000,
            tokens_used_week=50000
        )
        self.assertEqual(budget.weekly_limit, 200000)
        self.assertEqual(budget.tokens_used_week, 50000)

    def test_tokens_remaining(self):
        """Test tokens remaining calculation."""
        budget = AITokenBudget.objects.create(
            instance=self.instance,
            weekly_limit=200000,
            tokens_used_week=50000
        )
        self.assertEqual(budget.tokens_remaining, 150000)

    def test_is_exhausted(self):
        """Test budget exhaustion check."""
        budget = AITokenBudget.objects.create(
            instance=self.instance,
            weekly_limit=200000,
            tokens_used_week=200000
        )
        self.assertTrue(budget.is_exhausted)

    def test_add_tokens(self):
        """Test adding tokens to budget."""
        budget = AITokenBudget.objects.create(
            instance=self.instance,
            weekly_limit=200000,
            tokens_used_week=50000
        )
        budget.add_tokens(1000, 500)
        self.assertEqual(budget.tokens_used_week, 51500)


class AICompleteAPITest(TestCase):
    """Tests for AI Complete API endpoint."""

    def setUp(self):
        """Set up test data."""
        plan = Plan.objects.filter(name='starter').first()
        self.customer = Customer.objects.create(
            company_name='Test Company',
            slug='testco',
            contact_name='Test User',
            contact_email='test@example.com'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=plan,
            user_seats_total=5,
            instance_seats_total=1,
            ai_addon_active=True
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Instance',
            is_master=True,
            status='active'
        )

        # Create provider, model, and agent
        self.provider = AIProvider.objects.create(
            name='Test Provider',
            provider_type='Anthropic',
            active=True
        )
        self.provider.set_api_key('test-key')
        self.provider.save()

        self.model = AIModel.objects.create(
            provider=self.provider,
            name='Test Model',
            model_id='test-model',
            active=True,
            is_default=True
        )

        self.agent = AIAgent.objects.create(
            name='test-summarizer',
            description='Test summarizer',
            provider=self.provider,
            model=self.model,
            role='You are a summarizer.',
            task='Summarize the input.',
            active=True
        )

        self.client = APIClient()

    def test_ai_addon_not_active(self):
        """Test API rejects when AI addon is not active."""
        self.subscription.ai_addon_active = False
        self.subscription.save()

        response = self.client.post(
            '/api/ai/complete/',
            {
                'agent': 'test-summarizer',
                'input': 'Test input'
            },
            HTTP_AUTHORIZATION=f'Api-Key {self.instance.api_key}',
            format='json'
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.data)

    def test_missing_agent(self):
        """Test API rejects when agent is missing."""
        response = self.client.post(
            '/api/ai/complete/',
            {'input': 'Test input'},
            HTTP_AUTHORIZATION=f'Api-Key {self.instance.api_key}',
            format='json'
        )

        self.assertEqual(response.status_code, 400)

    def test_token_budget_exhausted(self):
        """Test API rejects when token budget is exhausted."""
        budget = AITokenBudget.objects.create(
            instance=self.instance,
            weekly_limit=100,
            tokens_used_week=100
        )

        response = self.client.post(
            '/api/ai/complete/',
            {
                'agent': 'test-summarizer',
                'input': 'Test input'
            },
            HTTP_AUTHORIZATION=f'Api-Key {self.instance.api_key}',
            format='json'
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn('token_limit_exceeded', response.data.get('error', ''))

    @patch('ai.agent_service.AgentService.execute')
    def test_successful_agent_execution(self, mock_execute):
        """Test successful agent execution."""
        mock_execute.return_value = ('Test response', False)

        response = self.client.post(
            '/api/ai/complete/',
            {
                'agent': 'test-summarizer',
                'input': 'Test input'
            },
            HTTP_AUTHORIZATION=f'Api-Key {self.instance.api_key}',
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['text'], 'Test response')
        self.assertFalse(response.data['from_cache'])
        self.assertIn('tokens_remaining', response.data)


class AIRouterTest(TestCase):
    """Tests for AIRouter."""

    def setUp(self):
        """Set up test data."""
        plan = Plan.objects.filter(name='starter').first()
        self.customer = Customer.objects.create(
            company_name='Test Company',
            slug='testco',
            contact_name='Test User',
            contact_email='test@example.com'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=plan,
            user_seats_total=5,
            instance_seats_total=1,
            ai_addon_active=True
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Instance',
            is_master=True,
            status='active'
        )

        self.provider = AIProvider.objects.create(
            name='Test Provider',
            provider_type='OpenAI',
            active=True
        )
        self.provider.set_api_key('test-key')
        self.provider.save()

        self.model = AIModel.objects.create(
            provider=self.provider,
            name='Test Model',
            model_id='gpt-4',
            active=True,
            is_default=True,
            input_price_per_1m_tokens=Decimal('30.00'),
            output_price_per_1m_tokens=Decimal('60.00')
        )

        self.router = AIRouter()

    def test_select_default_model(self):
        """Test selecting default model."""
        provider, model = self.router._select_model(None, None)
        self.assertEqual(model.model_id, 'gpt-4')
        self.assertTrue(model.is_default)

    def test_select_model_by_id(self):
        """Test selecting model by ID."""
        provider, model = self.router._select_model(None, 'gpt-4')
        self.assertEqual(model.model_id, 'gpt-4')

    def test_select_model_by_provider(self):
        """Test selecting model by provider type."""
        provider, model = self.router._select_model('OpenAI', None)
        self.assertEqual(provider.provider_type, 'OpenAI')


class AgentServiceTest(TestCase):
    """Tests for AgentService."""

    def setUp(self):
        """Set up test data."""
        plan = Plan.objects.filter(name='starter').first()
        self.customer = Customer.objects.create(
            company_name='Test Company',
            slug='testco',
            contact_name='Test User',
            contact_email='test@example.com'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=plan,
            user_seats_total=5,
            instance_seats_total=1,
            ai_addon_active=True
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Instance',
            is_master=True,
            status='active'
        )

        self.provider = AIProvider.objects.create(
            name='Test Provider',
            provider_type='Anthropic',
            active=True
        )
        self.provider.set_api_key('test-key')
        self.provider.save()

        self.model = AIModel.objects.create(
            provider=self.provider,
            name='Test Model',
            model_id='test-model',
            active=True
        )

        self.agent = AIAgent.objects.create(
            name='test-agent',
            provider=self.provider,
            model=self.model,
            role='Test role',
            task='Test task',
            active=True,
            cache_enabled=False
        )

        self.service = AgentService()

    def test_agent_not_found(self):
        """Test error when agent not found."""
        with self.assertRaises(AIAgent.DoesNotExist):
            self.service.execute('nonexistent-agent', 'input', self.instance)

    @patch('ai.router.AIRouter.chat')
    def test_agent_execution_without_cache(self, mock_chat):
        """Test agent execution without cache."""
        mock_response = AIResponse(
            text='Test response',
            input_tokens=10,
            output_tokens=20
        )
        mock_chat.return_value = mock_response

        text, from_cache = self.service.execute(
            'test-agent',
            'Test input',
            self.instance
        )

        self.assertEqual(text, 'Test response')
        self.assertFalse(from_cache)
        mock_chat.assert_called_once()
