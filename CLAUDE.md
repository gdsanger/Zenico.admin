# CLAUDE.md — Zenico Admin

Django-basierte Admin-Plattform für das Zenico Multi-Tenant-SaaS-System.

## Projektstruktur

```
zenico_admin/        # Django-Projektkonfiguration (settings/, urls.py, celery.py)
accounts/            # Benutzerverwaltung (AdminUser-Modell)
customers/           # Kundenverwaltung
instances/           # Instanzverwaltung (Mandanten)
billing/             # Abrechnung & Stripe-Integration
crm/                 # Kontaktverwaltung
newsletter/          # Newsletter & Marketing-Automatisierung
audit/               # Audit-Logging
ai/                  # AI-Proxy-Endpunkte (Anthropic, OpenAI)
api/                 # REST-API-Endpunkte
ui/                  # Django-Templates & UI-Views
core/                # Shared Services, Logging-Utilities
```

## Tech Stack

- **Framework:** Django 5+ mit Django REST Framework
- **Datenbank:** PostgreSQL (Produktion), SQLite (Entwicklung)
- **Task Queue:** Celery + Redis
- **Zahlungen:** Stripe
- **AI:** Anthropic (Claude), OpenAI
- **Frontend:** HTMX + Bootstrap 5 (Server-Side Rendering)
- **Error Tracking:** Sentry
- **Auth:** Eigenes `AdminUser`-Modell + Microsoft MSAL

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # .env befüllen
python manage.py migrate
python manage.py runserver
```

Settings werden per `DJANGO_SETTINGS_MODULE` gesteuert:
- `zenico_admin.settings.development` (Standard lokal)
- `zenico_admin.settings.production`

## Tests ausführen

```bash
python manage.py test
# oder gezielt:
python manage.py test billing.tests
python manage.py test customers.tests
```

## Git Workflow

**Niemals direkt auf `main` committen.**

1. Vor jeder Änderung neuen Branch von `main` erstellen:
   ```bash
   git checkout main && git pull
   git checkout -b feature/<kurzbeschreibung>
   # oder: fix/<kurzbeschreibung>
   ```

2. Commits auf dem Branch, aussagekräftige Nachrichten auf Englisch.

3. Nach Abschluss Pull Request als Draft erstellen:
   ```bash
   gh pr create --draft --title "..." --body "..."
   ```

4. `main` bleibt geschützt — nur via Review-PR mergen.

**Branch-Namensschema:**
- `feature/<kurzbeschreibung>` — neue Funktionalität
- `fix/<kurzbeschreibung>` — Bugfixes

## Umgebungsvariablen

Sensible Werte leben in `.env` (nicht im Repo). Referenz: [`.env.example`](.env.example).

Wichtige Variablen:
- `SECRET_KEY`, `DEBUG`, `DATABASE_URL`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- `FIELD_ENCRYPTION_KEY` — für verschlüsselte Felder (Fernet)
- `SENTRY_DSN` — optional, nur für Produktion

## Migrations

```bash
python manage.py makemigrations <app>
python manage.py migrate
```

Migrations immer zusammen mit dem zugehörigen Model-/Code-Change committen. Keine leeren Migrations erstellen.

## Coding-Konventionen

- Python: PEP 8, keine unnötigen Kommentare
- API-Endpunkte: DRF-Views in `api/` oder app-eigenem `views.py`
- Stripe-Logik gehört in `billing/stripe_helpers.py` oder `billing/services`
- AI-Logik gehört in `ai/`
- Logging über `core/logging_utils.py` (strukturiertes Logging mit Sentry-Integration)
- Keine Secrets oder `.env`-Inhalte in den Code schreiben
