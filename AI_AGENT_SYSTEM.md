# KI-Agentensystem + Token-Tracking

**Complete AI Agent System for Zenico.Admin**

## Overview

Zenico.Admin now includes a full-featured AI Agent System based on the Agira architecture. All Zenico instances route their AI requests through this central proxy, providing:

- ✅ No API keys stored in instances
- ✅ Complete token tracking and cost calculation
- ✅ Budget enforcement (weekly token limits)
- ✅ Multi-provider support (OpenAI, Anthropic)
- ✅ DB-based agent configuration (no YAML files)
- ✅ Redis-based response caching
- ✅ Comprehensive job history and audit trail

## Architecture

```
Zenico.app → POST /api/ai/complete/
                 ↓
          Zenico.Admin:
          ├── Instance authentifizieren (API-Key)
          ├── Budget prüfen (tokens_this_week)
          ├── Agent laden (aus DB)
          ├── Cache prüfen (Redis)
          ├── KI-Call (OpenAI / Anthropic)
          ├── Token-Tracking + Kostenberechnung
          └── Response zurück
```

## Database Models

### AIProvider
Stores AI provider configurations (OpenAI, Anthropic) with encrypted API keys.

**Fields:**
- `name`: Provider name (e.g., "Production OpenAI")
- `provider_type`: OpenAI | Anthropic
- `api_key`: Encrypted API key (Fernet encryption)
- `organization_id`: Optional organization ID
- `active`: Enable/disable provider

**Methods:**
- `set_api_key(plaintext)`: Encrypt and store API key
- `get_api_key()`: Decrypt and return API key

### AIModel
AI models with pricing information for cost calculation.

**Fields:**
- `provider`: ForeignKey to AIProvider
- `name`: Model display name
- `model_id`: API model identifier (e.g., "gpt-4o", "claude-sonnet-4-5")
- `input_price_per_1m_tokens`: USD per 1M input tokens
- `output_price_per_1m_tokens`: USD per 1M output tokens
- `is_default`: Default model for provider
- `active`: Enable/disable model

**Methods:**
- `calculate_cost(input_tokens, output_tokens)`: Calculate USD cost

### AIAgent
DB-based agent configuration (replaces YAML files from Agira).

**Fields:**
- `name`: Unique agent identifier
- `description`: Agent purpose
- `provider`: ForeignKey to AIProvider
- `model`: ForeignKey to AIModel
- `role`: System prompt (defines agent's role and context)
- `task`: User prompt template (defines the task)
- `cache_enabled`: Enable response caching
- `cache_ttl_seconds`: Cache TTL
- `cache_version`: Cache version (increment to invalidate)
- `max_tokens`: Maximum response tokens
- `temperature`: Sampling temperature
- `active`: Enable/disable agent

**Methods:**
- `to_yaml_dict()`: Export as YAML-compatible dict

### AIJobsHistory
Complete history of all AI API calls (instance-aware).

**Fields:**
- `agent`: Agent name
- `instance`: ForeignKey to Instance
- `provider`: ForeignKey to AIProvider
- `model`: ForeignKey to AIModel
- `status`: Pending | Completed | Error | Cached
- `input_tokens`: Input tokens used
- `output_tokens`: Output tokens used
- `costs`: Cost in USD
- `duration_ms`: Request duration
- `error_message`: Error details (if any)
- `from_cache`: Whether response was from cache
- `timestamp`: Request timestamp

### AITokenBudget
Weekly token budget per instance.

**Fields:**
- `instance`: OneToOneField to Instance
- `weekly_limit`: Maximum tokens per week
- `tokens_used_week`: Tokens used this week
- `week_start`: Monday of current week
- `updated_at`: Last update timestamp

**Properties:**
- `tokens_remaining`: Remaining tokens for week
- `is_exhausted`: Whether budget is exhausted

**Methods:**
- `add_tokens(input_tokens, output_tokens)`: Add token usage
- `_reset_week_if_needed()`: Reset on new week (Monday)

## Provider Implementations

### Base Provider
Abstract base class for AI providers.

```python
class BaseProvider(ABC):
    def chat(self, messages, model_id, temperature=None, max_tokens=None, **kwargs):
        """Perform chat completion."""
        pass
```

### OpenAI Provider
OpenAI API provider with max_completion_tokens fix.

**Fix for new models:** Newer OpenAI models (o1, o3, gpt-4o, gpt-4-turbo) use `max_completion_tokens` instead of `max_tokens`.

### Anthropic Provider
Anthropic Claude API provider.

**System message handling:** Anthropic requires system messages in separate `system` parameter, not in messages array.

## Core Services

### AIRouter
Central router for AI requests with provider management.

**Features:**
- Automatic provider and model selection
- Job tracking (create pending → complete)
- Token budget updates
- Cost calculation
- Error handling

**Usage:**
```python
router = AIRouter()
response = router.chat(
    messages=[{'role': 'user', 'content': 'Hello'}],
    instance=instance,
    agent='test-agent',
    provider_type='OpenAI',
    model_id='gpt-4o',
    temperature=0.7,
    max_tokens=1000
)
```

### AgentService
Execute DB-based agents with caching.

**Features:**
- Load agent from database
- Cache response checking
- Message building (system + user prompts)
- Router integration
- Response caching

**Usage:**
```python
service = AgentService()
text, from_cache = service.execute(
    agent_name='task-summarizer',
    input_text='Task description...',
    instance=instance
)
```

### AgentCacheService
Redis-based caching for agent responses.

**Cache key strategy:** `agent:{name}:v{version}:{content_hash}`

**Features:**
- Content-based hashing for consistent keys
- Configurable TTL per agent
- Version-based cache invalidation

## API Endpoints

### POST /api/ai/complete/
Agent-based AI completion endpoint.

**Authentication:** API Key (from Instance)

**Request:**
```json
{
  "agent": "task-summarizer",
  "input": "Task text to summarize..."
}
```

**Response:**
```json
{
  "text": "AI response...",
  "from_cache": false,
  "tokens_remaining": 156800
}
```

**Error Responses:**
- `403`: AI addon not active
- `404`: Agent not found
- `429`: Token budget exhausted
- `500`: Agent execution failed

### POST /api/instance/register/
Phone-home endpoint (updated with budget data).

**Response includes:**
```json
{
  "plan": "standard",
  "user_seats": 5,
  "instance_status": "active",
  "ai_addon": true,
  "ai_weekly_limit": 200000,
  "ai_tokens_used_this_week": 43200,
  "ai_tokens_remaining_this_week": 156800,
  "week_resets_at": "2026-06-09T00:00:00Z"
}
```

## Admin Interface

### Provider Management
`/admin/ai/aiprovider/`

- List providers with type and status
- Create/edit providers
- API keys managed via model methods (encrypted)

### Model Management
`/admin/ai/aimodel/`

- List models with pricing
- Set default model per provider
- Pricing in USD per 1M tokens

### Agent Management
`/admin/ai/aiagent/`

- List agents with provider/model
- Edit system prompt (role) and user prompt (task)
- Configure caching (enable, TTL, version)
- Set generation parameters (temperature, max_tokens)

### Job History
`/admin/ai/aijobshistory/`

**Read-only** interface with filters:

- Filter by status, provider, from_cache, timestamp
- Search by agent, instance, error message
- Display tokens, costs, duration
- Color-coded status badges

### Token Budget
`/admin/ai/aitokenbudget/`

- View budgets per instance
- Edit weekly limits
- Display usage percentage with color coding
- Shows exhausted budgets in red

## Management Commands

### seed_ai_agents
Create default agents for Zenico task management.

```bash
python manage.py seed_ai_agents
```

**Creates 8 default agents:**
1. `task-title-generator`: Generate task titles
2. `task-description-improver`: Improve task descriptions
3. `task-subtask-suggester`: Suggest sub-tasks
4. `task-checklist-suggester`: Suggest checklist items
5. `task-summarizer`: Summarize tasks
6. `task-priority-suggester`: Suggest priority
7. `task-sp-estimator`: Estimate story points
8. `task-comment-suggester`: Suggest comments

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**New dependencies:**
- `anthropic>=0.18`
- `openai>=1.0`
- `cryptography>=41.0`

### 2. Configure Encryption Key

Add to `.env`:

```env
FIELD_ENCRYPTION_KEY=<32-byte Fernet key>
```

Generate key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 3. Run Migrations

```bash
python manage.py migrate ai
```

### 4. Create Provider and Model

Via Django admin or shell:

```python
from ai.models import AIProvider, AIModel
from decimal import Decimal

# Create provider
provider = AIProvider.objects.create(
    name='Production Anthropic',
    provider_type='Anthropic',
    active=True
)
provider.set_api_key('your-api-key')
provider.save()

# Create model
model = AIModel.objects.create(
    provider=provider,
    name='Claude Sonnet 4.5',
    model_id='claude-sonnet-4-5-20250929',
    input_price_per_1m_tokens=Decimal('3.00'),
    output_price_per_1m_tokens=Decimal('15.00'),
    active=True,
    is_default=True
)
```

### 5. Seed Default Agents

```bash
python manage.py seed_ai_agents
```

### 6. Configure Redis Cache

Ensure Redis is configured in settings:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

## Testing

Run tests:

```bash
python manage.py test ai
```

Test coverage includes:
- Model creation and encryption
- Cost calculation
- Token budget management
- API endpoint authentication and validation
- Router model selection
- Agent service execution
- Cache integration

## Token Budget Workflow

1. **Instance registration:** Budget created on first phone-home
2. **Agent execution:** Tokens deducted from budget
3. **Weekly reset:** Budget resets every Monday 00:00 UTC
4. **Budget enforcement:** Requests rejected when exhausted (HTTP 429)
5. **Budget display:** Remaining tokens shown in API responses

## Pricing and Costs

### Cost Calculation
```python
cost = (input_tokens / 1_000_000) * input_price +
       (output_tokens / 1_000_000) * output_price
```

### Example Pricing (as of 2025)

**Anthropic Claude:**
- Claude Sonnet 4.5: $3/1M in, $15/1M out
- Claude Opus 4.5: $15/1M in, $75/1M out

**OpenAI:**
- GPT-4o: $5/1M in, $15/1M out
- GPT-4 Turbo: $10/1M in, $30/1M out

## Caching Strategy

### Cache Key Format
```
agent:{agent_name}:v{cache_version}:{content_hash}
```

### Cache Invalidation
1. Increment `cache_version` on agent
2. All cached responses invalidated
3. New cache keys used going forward

### Cache TTL
- Configure per agent
- Default: 300 seconds (5 minutes)
- Adjust based on agent purpose

## Monitoring and Observability

### Job History
- All API calls logged to AIJobsHistory
- Track success/failure rates
- Monitor costs per instance
- Analyze response times

### Token Budget
- Weekly usage tracking
- Budget exhaustion alerts
- Usage trends per instance

### Admin Dashboard
- Stats on jobs, tokens, costs
- Top instances by usage
- Provider performance metrics

## Security

### API Key Encryption
- All provider API keys encrypted with Fernet
- Encryption key stored in environment variable
- Keys never exposed in API responses

### Instance Authentication
- API key required for all requests
- Keys auto-generated per instance
- Validated against database

### Budget Enforcement
- Hard limits on token usage
- Prevents budget overruns
- Resets automatically weekly

## Future Enhancements

### Planned Features
- [ ] Stats dashboard in UI
- [ ] Cost alerts and notifications
- [ ] Budget overrides per instance
- [ ] Model auto-selection based on task complexity
- [ ] Agent versioning and A/B testing
- [ ] Custom agent templates
- [ ] Batch request processing
- [ ] Streaming response support

## Troubleshooting

### "FIELD_ENCRYPTION_KEY not configured"
Add encryption key to `.env` file.

### "No active model found"
Create at least one active AIModel with `is_default=True`.

### "Token budget exhausted"
- Check AITokenBudget for instance
- Increase `weekly_limit` if needed
- Wait for Monday reset

### Cache not working
- Verify Redis is running and configured
- Check `cache_enabled` on agent
- Ensure Redis connection in settings

## References

- Agira Architecture: Provider-based AI routing with job tracking
- Django Encryption: Fernet symmetric encryption
- Redis Caching: Django cache framework
- Token Tracking: Instance-aware budget management
