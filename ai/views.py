"""
AI Administration Views

UI for managing AI providers, models, agents, and viewing usage statistics.
"""

import logging
from django.views.generic import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, F
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.db.models.functions import TruncDate
from datetime import timedelta

from ai.models import AIProvider, AIModel, AIAgent, AIJobsHistory, AIProviderType, AIJobStatus
from instances.models import Instance
from ui.decorators import role_required

logger = logging.getLogger(__name__)


# ── Dashboard ──────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIDashboardView(View):
    def get(self, request):
        # KPIs letzte 7 Tage
        since = timezone.now() - timedelta(days=7)
        jobs = AIJobsHistory.objects.filter(timestamp__gte=since)

        ctx = {
            'total_jobs': jobs.count(),
            'total_tokens': jobs.aggregate(
                t=Sum('input_tokens') + Sum('output_tokens')
            )['t'] or 0,
            'total_cost': jobs.aggregate(
                c=Sum('costs')
            )['c'] or 0,
            'cache_hit_rate': _cache_hit_rate(jobs),
            'provider_count': AIProvider.objects.filter(active=True).count(),
            'agent_count': AIAgent.objects.filter(active=True).count(),
            'recent_jobs': jobs.select_related(
                'provider', 'model', 'instance'
            ).order_by('-timestamp')[:10],
            'top_agents': jobs.values('agent').annotate(
                count=Count('id'),
                tokens=Sum('input_tokens') + Sum('output_tokens'),
            ).order_by('-count')[:5],
        }
        return render(request, 'ai/dashboard.html', ctx)


# ── Provider ──────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIProviderListView(View):
    def get(self, request):
        providers = AIProvider.objects.prefetch_related(
            'models'
        ).order_by('provider_type', 'name')
        return render(request, 'ai/provider_list.html', {
            'providers': providers,
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIProviderCreateView(View):
    def get(self, request):
        return render(request, 'ai/provider_form.html', {
            'provider_types': AIProviderType.choices,
            'is_create': True,
            'form_data': {
                'name': '',
                'provider_type': '',
                'organization_id': '',
            },
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        provider_type = request.POST.get('provider_type', '')
        api_key = request.POST.get('api_key', '').strip()
        org_id = request.POST.get('organization_id', '').strip()

        errors = {}
        if not name:
            errors['name'] = 'Name ist erforderlich.'
        if not provider_type:
            errors['provider_type'] = 'Provider-Typ erforderlich.'
        if not api_key:
            errors['api_key'] = 'API-Key ist erforderlich.'

        if errors:
            return render(request, 'ai/provider_form.html', {
                'provider_types': AIProviderType.choices,
                'is_create': True,
                'errors': errors,
                'form_data': request.POST,
            })

        provider = AIProvider(
            name=name,
            provider_type=provider_type,
            organization_id=org_id,
        )
        provider.set_api_key(api_key)
        provider.save()

        messages.success(request, f'Provider "{provider.name}" angelegt.')
        return redirect('ai:provider-detail', pk=provider.pk)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIProviderDetailView(View):
    def get(self, request, pk):
        provider = get_object_or_404(AIProvider, pk=pk)
        models = provider.models.order_by('name')
        return render(request, 'ai/provider_detail.html', {
            'provider': provider,
            'models': models,
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIProviderEditView(View):
    def get(self, request, pk):
        provider = get_object_or_404(AIProvider, pk=pk)
        return render(request, 'ai/provider_form.html', {
            'provider': provider,
            'provider_types': AIProviderType.choices,
            'is_create': False,
            'form_data': {
                'name': '',
                'provider_type': '',
                'organization_id': '',
            },
        })

    def post(self, request, pk):
        provider = get_object_or_404(AIProvider, pk=pk)
        provider.name = request.POST.get('name', provider.name).strip()
        provider.organization_id = request.POST.get(
            'organization_id', ''
        ).strip()
        provider.active = 'active' in request.POST

        # API-Key nur aktualisieren wenn neu eingegeben
        new_key = request.POST.get('api_key', '').strip()
        if new_key and new_key != '••••••••':
            provider.set_api_key(new_key)

        provider.save()
        messages.success(request, 'Provider aktualisiert.')
        return redirect('ai:provider-detail', pk=provider.pk)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIProviderDeleteView(View):
    def post(self, request, pk):
        provider = get_object_or_404(AIProvider, pk=pk)
        name = provider.name
        provider.delete()
        messages.success(request, f'Provider "{name}" gelöscht.')
        return redirect('ai:provider-list')


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class FetchModelsView(View):
    """
    Modelle vom Provider abrufen und in DB speichern.
    Unterstützt OpenAI und Anthropic.
    """
    def post(self, request, pk):
        provider = get_object_or_404(AIProvider, pk=pk)

        try:
            fetched = _fetch_models_from_api(provider)
            created = 0
            for model_id, model_name in fetched:
                _, is_new = AIModel.objects.get_or_create(
                    provider=provider,
                    model_id=model_id,
                    defaults={'name': model_name},
                )
                if is_new:
                    created += 1

            messages.success(
                request,
                f'{len(fetched)} Modelle abgerufen, {created} neu angelegt.'
            )
        except Exception as e:
            logger.exception('Error fetching models from provider API')
            messages.error(request, f'Fehler beim Abrufen: {e}')

        return redirect('ai:provider-detail', pk=provider.pk)


def _fetch_models_from_api(provider: AIProvider) -> list[tuple[str, str]]:
    """Modelle vom Provider API abrufen."""
    if provider.provider_type == 'OpenAI':
        import openai
        client = openai.OpenAI(api_key=provider.get_api_key())
        models = client.models.list()
        return [
            (m.id, m.id)
            for m in models.data
            if 'gpt' in m.id or 'o1' in m.id or 'o3' in m.id
        ]

    elif provider.provider_type == 'Anthropic':
        # Anthropic hat keine Model-List API — bekannte Modelle hardcoded
        return [
            ('claude-opus-4-5', 'Claude Opus 4.5'),
            ('claude-sonnet-4-5', 'Claude Sonnet 4.5'),
            ('claude-haiku-4-5', 'Claude Haiku 4.5'),
            ('claude-opus-4-0', 'Claude Opus 4'),
            ('claude-sonnet-4-0', 'Claude Sonnet 4'),
        ]

    return []


# ── Agenten ───────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentListView(View):
    def get(self, request):
        agents = AIAgent.objects.select_related(
            'provider', 'model'
        ).order_by('name')
        return render(request, 'ai/agent_list.html', {'agents': agents})


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentCreateView(View):
    def get(self, request):
        providers = AIProvider.objects.filter(
            active=True
        ).prefetch_related('models')
        return render(request, 'ai/agent_form.html', {
            'providers': providers,
            'is_create': True,
            'form_data': {
                'name': '',
                'description': '',
                'provider_id': '',
                'role': '',
                'task': '',
                'max_tokens': '1000',
                'temperature': '0.7',
                'cache_ttl_seconds': '300',
                'cache_version': '1',
            },
        })

    def post(self, request):
        errors = _validate_agent_form(request.POST)
        if errors:
            providers = AIProvider.objects.filter(
                active=True
            ).prefetch_related('models')
            return render(request, 'ai/agent_form.html', {
                'providers': providers,
                'is_create': True,
                'errors': errors,
                'form_data': request.POST,
            })

        agent = AIAgent.objects.create(
            name=request.POST['name'].strip(),
            description=request.POST.get('description', '').strip(),
            provider_id=request.POST['provider_id'],
            model_id=request.POST['model_id'],
            role=request.POST.get('role', '').strip(),
            task=request.POST.get('task', '').strip(),
            cache_enabled=('cache_enabled' in request.POST),
            cache_ttl_seconds=int(request.POST.get('cache_ttl_seconds', 300)),
            cache_version=int(request.POST.get('cache_version', 1)),
            max_tokens=int(request.POST.get('max_tokens', 1000)),
            temperature=float(request.POST.get('temperature', 0.7)),
        )
        messages.success(request, f'Agent "{agent.name}" angelegt.')
        return redirect('ai:agent-detail', pk=agent.pk)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentDetailView(View):
    def get(self, request, pk):
        agent = get_object_or_404(
            AIAgent.objects.select_related('provider', 'model'), pk=pk
        )
        recent_jobs = AIJobsHistory.objects.filter(
            agent=agent.name
        ).select_related('provider', 'model', 'instance').order_by('-timestamp')[:20]
        return render(request, 'ai/agent_detail.html', {
            'agent': agent,
            'recent_jobs': recent_jobs,
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentEditView(View):
    def get(self, request, pk):
        agent = get_object_or_404(AIAgent, pk=pk)
        providers = AIProvider.objects.filter(
            active=True
        ).prefetch_related('models')
        return render(request, 'ai/agent_form.html', {
            'agent': agent,
            'providers': providers,
            'is_create': False,
            'form_data': {
                'name': '',
                'description': '',
                'provider_id': '',
                'role': '',
                'task': '',
                'max_tokens': '1000',
                'temperature': '0.7',
                'cache_ttl_seconds': '300',
                'cache_version': '1',
            },
        })

    def post(self, request, pk):
        agent = get_object_or_404(AIAgent, pk=pk)
        errors = _validate_agent_form(request.POST, is_edit=True)

        if errors:
            providers = AIProvider.objects.filter(
                active=True
            ).prefetch_related('models')
            return render(request, 'ai/agent_form.html', {
                'agent': agent,
                'providers': providers,
                'is_create': False,
                'errors': errors,
                'form_data': request.POST,
            })

        agent.description = request.POST.get('description', '').strip()
        agent.provider_id = request.POST['provider_id']
        agent.model_id = request.POST['model_id']
        agent.role = request.POST.get('role', '').strip()
        agent.task = request.POST.get('task', '').strip()
        agent.cache_enabled = ('cache_enabled' in request.POST)
        agent.cache_ttl_seconds = int(
            request.POST.get('cache_ttl_seconds', 300)
        )
        agent.cache_version = int(
            request.POST.get('cache_version', agent.cache_version)
        )
        agent.max_tokens = int(request.POST.get('max_tokens', 1000))
        agent.temperature = float(request.POST.get('temperature', 0.7))
        agent.active = ('active' in request.POST)
        agent.save()

        messages.success(request, f'Agent "{agent.name}" gespeichert.')
        return redirect('ai:agent-detail', pk=agent.pk)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentDeleteView(View):
    def post(self, request, pk):
        agent = get_object_or_404(AIAgent, pk=pk)
        name = agent.name
        agent.delete()
        messages.success(request, f'Agent "{name}" gelöscht.')
        return redirect('ai:agent-list')


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIAgentTestView(View):
    """Agent mit Test-Input ausführen."""
    def post(self, request, pk):
        agent = get_object_or_404(AIAgent, pk=pk)
        input_text = request.POST.get('test_input', '').strip()

        if not input_text:
            return render(request, 'ai/partials/agent_test_result.html', {
                'error': 'Bitte Test-Input eingeben.'
            })

        try:
            from ai.agent_service import AgentService
            service = AgentService()
            # Test ohne Instance-Budget-Check
            text, from_cache = service.execute(
                agent_name=agent.name,
                input_text=input_text,
                instance=None,  # Admin-Test ohne Instance
            )
            return render(request, 'ai/partials/agent_test_result.html', {
                'result': text,
                'from_cache': from_cache,
            })
        except Exception as e:
            logger.exception('Error testing agent')
            return render(request, 'ai/partials/agent_test_result.html', {
                'error': str(e),
            })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class ModelsForProviderView(View):
    """HTMX — Modell-Dropdown für gewählten Provider."""
    def get(self, request):
        provider_id = request.GET.get('provider_id')
        models = AIModel.objects.filter(
            provider_id=provider_id, active=True
        ).order_by('name') if provider_id else []
        return render(request, 'ai/partials/model_options.html', {
            'models': models,
            'selected_model': request.GET.get('selected_model'),
        })


# ── Jobs + Stats ──────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIJobListView(View):
    def get(self, request):
        jobs = AIJobsHistory.objects.select_related(
            'provider', 'model', 'instance'
        ).order_by('-timestamp')

        # Filter
        if instance_id := request.GET.get('instance'):
            jobs = jobs.filter(instance_id=instance_id)
        if agent := request.GET.get('agent'):
            jobs = jobs.filter(agent__icontains=agent)
        if status := request.GET.get('status'):
            jobs = jobs.filter(status=status)
        if provider_id := request.GET.get('provider'):
            jobs = jobs.filter(provider_id=provider_id)

        paginator = Paginator(jobs, 50)
        page = paginator.get_page(request.GET.get('page', 1))

        return render(request, 'ai/job_list.html', {
            'page': page,
            'providers': AIProvider.objects.all(),
            'instances': Instance.objects.all().order_by('slug'),
            'statuses': AIJobStatus.choices,
            'filters': {
                'instance': request.GET.get('instance', ''),
                'agent': request.GET.get('agent', ''),
                'status': request.GET.get('status', ''),
                'provider': request.GET.get('provider', ''),
            },
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class AIStatsView(View):
    def get(self, request):
        # Zeitraum
        days = int(request.GET.get('days', 7))
        since = timezone.now() - timedelta(days=days)
        jobs = AIJobsHistory.objects.filter(
            timestamp__gte=since, status=AIJobStatus.COMPLETED
        )

        # Gesamt KPIs
        totals = jobs.aggregate(
            total_jobs=Count('id'),
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            total_cost=Sum('costs'),
            avg_duration=Avg('duration_ms'),
        )

        # Top Instanzen
        top_instances = jobs.values(
            'instance__id', 'instance__slug', 'instance__customer__slug', 'instance__is_master'
        ).annotate(
            jobs=Count('id'),
            tokens=Sum('input_tokens') + Sum('output_tokens'),
            cost=Sum('costs'),
        ).order_by('-tokens')[:10]

        # Top Agenten
        top_agents = jobs.values('agent').annotate(
            jobs=Count('id'),
            tokens=Sum('input_tokens') + Sum('output_tokens'),
            cost=Sum('costs'),
            cache_hits=Count('id', filter=Q(from_cache=True)),
        ).order_by('-jobs')[:10]

        # Tagesweise Entwicklung
        daily = jobs.annotate(
            date=TruncDate('timestamp')
        ).values('date').annotate(
            jobs=Count('id'),
            tokens=Sum('input_tokens') + Sum('output_tokens'),
            cost=Sum('costs'),
        ).order_by('date')

        # Kosten pro Provider
        per_provider = jobs.values(
            'provider__name', 'provider__provider_type'
        ).annotate(
            jobs=Count('id'),
            cost=Sum('costs'),
            tokens=Sum('input_tokens') + Sum('output_tokens'),
        ).order_by('-cost')

        return render(request, 'ai/stats.html', {
            'totals': totals,
            'top_instances': top_instances,
            'top_agents': top_agents,
            'daily': list(daily),
            'per_provider': per_provider,
            'days': days,
            'cache_rate': _cache_hit_rate(
                AIJobsHistory.objects.filter(timestamp__gte=since)
            ),
        })


# ── Helpers ───────────────────────────────────────────────────

def _validate_agent_form(data: dict, is_edit: bool = False) -> dict:
    errors = {}
    if not is_edit and not data.get('name', '').strip():
        errors['name'] = 'Name ist erforderlich.'
    if not data.get('provider_id'):
        errors['provider_id'] = 'Provider ist erforderlich.'
    if not data.get('model_id'):
        errors['model_id'] = 'Modell ist erforderlich.'
    if not data.get('role', '').strip():
        errors['role'] = 'System Prompt (Role) ist erforderlich.'
    if not data.get('task', '').strip():
        errors['task'] = 'Task Prompt ist erforderlich.'
    return errors


def _cache_hit_rate(jobs) -> float:
    total = jobs.count()
    if not total:
        return 0.0
    cached = jobs.filter(from_cache=True).count()
    return round(cached / total * 100, 1)
