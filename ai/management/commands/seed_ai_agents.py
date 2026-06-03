"""
Management command to seed default AI agents.
"""

from django.core.management.base import BaseCommand
from ai.models import AIProvider, AIModel, AIAgent


class Command(BaseCommand):
    help = 'Seed default AI agents for Zenico task management'

    def handle(self, *args, **options):
        """Seed default agents."""

        # Get default provider and model
        try:
            provider = AIProvider.objects.filter(active=True).first()
            if not provider:
                self.stdout.write(self.style.ERROR(
                    'No active AI provider found. Please create one first.'
                ))
                return

            model = AIModel.objects.filter(provider=provider, active=True).first()
            if not model:
                self.stdout.write(self.style.ERROR(
                    f'No active model found for provider {provider.name}. Please create one first.'
                ))
                return

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error finding provider/model: {e}'))
            return

        # Define default agents
        agents = [
            {
                'name': 'task-title-generator',
                'description': 'Generiert einen kurzen Task-Titel aus der Beschreibung',
                'role': (
                    'Du bist ein Projektmanagement-Assistent, spezialisiert auf das Erstellen '
                    'prägnanter und aussagekräftiger Task-Titel.'
                ),
                'task': (
                    'Generiere einen kurzen, präzisen Task-Titel (maximal 8 Wörter) '
                    'basierend auf der folgenden Beschreibung. Der Titel soll klar und '
                    'handlungsorientiert sein.'
                ),
                'cache_ttl': 300,
                'max_tokens': 100,
                'temperature': 0.7,
            },
            {
                'name': 'task-description-improver',
                'description': 'Verbessert Task-Beschreibungen für bessere Klarheit',
                'role': (
                    'Du bist ein Projektmanagement-Experte, der Task-Beschreibungen optimiert, '
                    'um sie klarer, strukturierter und umsetzbarer zu machen.'
                ),
                'task': (
                    'Verbessere die folgende Task-Beschreibung. Mache sie klarer, strukturierter '
                    'und füge relevante Details hinzu, wenn nötig. Behalte den ursprünglichen '
                    'Intent bei.'
                ),
                'cache_ttl': 300,
                'max_tokens': 500,
                'temperature': 0.7,
            },
            {
                'name': 'task-subtask-suggester',
                'description': 'Schlägt sinnvolle Sub-Tasks vor',
                'role': (
                    'Du bist ein Projektmanagement-Assistent, der komplexe Tasks in kleinere, '
                    'umsetzbare Sub-Tasks aufteilt.'
                ),
                'task': (
                    'Analysiere den folgenden Task und schlage 3-5 sinnvolle Sub-Tasks vor. '
                    'Jeder Sub-Task sollte eine eigenständige, umsetzbare Einheit sein. '
                    'Formatiere die Ausgabe als nummerierte Liste.'
                ),
                'cache_ttl': 600,
                'max_tokens': 500,
                'temperature': 0.7,
            },
            {
                'name': 'task-checklist-suggester',
                'description': 'Schlägt Checklisten-Items für Tasks vor',
                'role': (
                    'Du bist ein Projektmanagement-Assistent, der Checklisten für Tasks erstellt.'
                ),
                'task': (
                    'Erstelle eine Checkliste mit 5-8 Items für den folgenden Task. '
                    'Jedes Item sollte eine konkrete Aktion oder Prüfung darstellen. '
                    'Formatiere als einfache Liste mit "- [ ]" Syntax.'
                ),
                'cache_ttl': 600,
                'max_tokens': 400,
                'temperature': 0.7,
            },
            {
                'name': 'task-summarizer',
                'description': 'Fasst Tasks und deren Kontext zusammen',
                'role': (
                    'Du bist ein Projektmanagement-Assistent, der Tasks prägnant zusammenfasst.'
                ),
                'task': (
                    'Fasse den folgenden Task in 2-3 kurzen Sätzen zusammen. '
                    'Fokussiere dich auf das Wesentliche: Was soll erreicht werden und warum.'
                ),
                'cache_ttl': 120,
                'max_tokens': 200,
                'temperature': 0.5,
            },
            {
                'name': 'task-priority-suggester',
                'description': 'Schlägt eine Task-Priorität vor',
                'role': (
                    'Du bist ein Projektmanagement-Experte, der Tasks nach Dringlichkeit '
                    'und Wichtigkeit priorisiert.'
                ),
                'task': (
                    'Analysiere den folgenden Task und schlage eine Priorität vor: '
                    'CRITICAL (sofort kritisch), HIGH (hoch), MEDIUM (mittel), oder LOW (niedrig). '
                    'Gib nur das Prioritätslevel und eine kurze Begründung (1 Satz) zurück.'
                ),
                'cache_ttl': 300,
                'max_tokens': 150,
                'temperature': 0.5,
            },
            {
                'name': 'task-sp-estimator',
                'description': 'Schätzt Story Points für Tasks',
                'role': (
                    'Du bist ein agiler Projektmanagement-Experte, der Story Points für Tasks schätzt. '
                    'Nutze die Fibonacci-Skala: 1, 2, 3, 5, 8, 13, 21.'
                ),
                'task': (
                    'Schätze die Story Points für den folgenden Task auf der Fibonacci-Skala '
                    '(1, 2, 3, 5, 8, 13, 21). Gib die Zahl und eine kurze Begründung (2-3 Sätze) zurück.'
                ),
                'cache_ttl': 600,
                'max_tokens': 200,
                'temperature': 0.5,
            },
            {
                'name': 'task-comment-suggester',
                'description': 'Schlägt hilfreiche Kommentare zu Tasks vor',
                'role': (
                    'Du bist ein Projektmanagement-Assistent, der konstruktive und hilfreiche '
                    'Kommentare zu Tasks schreibt.'
                ),
                'task': (
                    'Schreibe einen konstruktiven Kommentar zum folgenden Task. '
                    'Der Kommentar kann Fragen stellen, Verbesserungen vorschlagen, '
                    'oder zusätzliche Informationen anfordern.'
                ),
                'cache_ttl': 60,
                'max_tokens': 300,
                'temperature': 0.7,
            },
            {
                'name': 'project-status-report',
                'description': 'Erstellt einen vollständigen Projekt-Status-Report',
                'context_type': 'project',
                'display_name': 'Projekt-Status erstellen',
                'display_description': 'Erstellt einen vollständigen Status-Report mit Stand, Risiken und nächsten Schritten',
                'button_icon': 'bi-clipboard2-pulse',
                'sort_order': 10,
                'role': (
                    'Du bist ein erfahrener Projektmanager und Kommunikationsexperte. '
                    'Du erstellst präzise, sachliche Projekt-Status-Reports für das Management. '
                    'Deine Reports sind klar strukturiert, auf das Wesentliche fokussiert '
                    'und handlungsorientiert. Du schreibst in der Sprache des übergebenen '
                    'Projektkontexts (Deutsch oder Englisch).'
                ),
                'task': (
                    'Erstelle einen vollständigen Projekt-Status-Report basierend auf '
                    'den folgenden Projektdaten.\n\n'
                    'Der Report muss folgende Abschnitte enthalten:\n\n'
                    '## Aktueller Stand\n'
                    'Kurze Zusammenfassung wo das Projekt gerade steht (2-3 Sätze). '
                    'Fortschritt in Prozent nennen.\n\n'
                    '## Erledigte Aufgaben\n'
                    'Kurze Auflistung was bereits abgeschlossen wurde. '
                    'Maximal 5 wichtigste Punkte.\n\n'
                    '## Offene Aufgaben\n'
                    'Was ist noch zu tun? Nächste wichtige Deadlines nennen. '
                    'Maximal 5 wichtigste Punkte.\n\n'
                    '## Risiken\n'
                    'Gibt es Risiken? Überfällige Tasks, kritische Abhängigkeiten, '
                    'knappe Deadlines? Wenn keine Risiken vorhanden: "Keine kritischen '
                    'Risiken erkannt." schreiben.\n\n'
                    '## Nächste Schritte (Management)\n'
                    'Konkrete Handlungsempfehlungen aus Management-Sicht. '
                    'Was muss entschieden, freigegeben oder eskaliert werden? '
                    'Maximal 3 Punkte. Wenn keine Aktion nötig: "Kein Handlungsbedarf."\n\n'
                    'Regeln:\n'
                    '- Sachlich und präzise, keine Marketing-Sprache\n'
                    '- Keine Einleitung oder Schlussformel\n'
                    '- Nur die 5 Abschnitte, kein weiterer Text\n'
                    '- Wenn ein Abschnitt leer wäre, trotzdem kurz befüllen'
                ),
                'cache_ttl': 300,
                'max_tokens': 2000,
                'temperature': 0.4,
            },
        ]

        # Create agents
        created_count = 0
        updated_count = 0
        for agent_data in agents:
            # Build defaults dict with optional display fields
            defaults = {
                'description': agent_data['description'],
                'provider': provider,
                'model': model,
                'role': agent_data['role'],
                'task': agent_data['task'],
                'cache_ttl_seconds': agent_data['cache_ttl'],
                'max_tokens': agent_data['max_tokens'],
                'temperature': agent_data['temperature'],
                'cache_enabled': True,
                'active': True,
            }

            # Add optional display fields if present
            if 'context_type' in agent_data:
                defaults['context_type'] = agent_data['context_type']
            if 'display_name' in agent_data:
                defaults['display_name'] = agent_data['display_name']
            if 'display_description' in agent_data:
                defaults['display_description'] = agent_data['display_description']
            if 'button_icon' in agent_data:
                defaults['button_icon'] = agent_data['button_icon']
            if 'sort_order' in agent_data:
                defaults['sort_order'] = agent_data['sort_order']

            agent, created = AIAgent.objects.update_or_create(
                name=agent_data['name'],
                defaults=defaults
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Created agent: {agent.name}'
                ))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(
                    f'↻ Updated agent: {agent.name}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'\nSeeding complete: {created_count} created, {updated_count} updated'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'All agents are using provider: {provider.name} ({provider.provider_type})'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'All agents are using model: {model.name} ({model.model_id})'
        ))
