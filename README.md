# Zenico Admin

Django-based administration platform for the Zenico multi-tenant SaaS system.

## Features

- Custom user authentication with `AdminUser` model
- Modular app structure:
  - `accounts` - User management
  - `customers` - Customer management
  - `instances` - Instance management
  - `billing` - Billing and invoicing
  - `audit` - Audit logging
- PostgreSQL database support
- Environment-based configuration (development/production)

## Prerequisites

- Python 3.8 or higher
- PostgreSQL (for production) or SQLite (for development)
- pip or virtualenv

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Zenico.admin
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file and update it with your settings:

```bash
cp .env.example .env
```

Edit `.env` and set the required variables:
- `SECRET_KEY`: Django secret key (generate a new one for production)
- `DEBUG`: Set to `False` in production
- `DATABASE_URL`: PostgreSQL connection string
- Other configuration as needed

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Run Development Server

```bash
python manage.py runserver
```

Visit http://localhost:8000/admin to access the admin interface.

## Project Structure

```
zenico_admin/
├── accounts/          # User authentication and management
├── customers/         # Customer management
├── instances/         # Instance management
├── billing/           # Billing and invoicing
├── audit/             # Audit logging
├── zenico_admin/      # Project settings
│   ├── settings/
│   │   ├── base.py           # Base settings
│   │   ├── development.py    # Development settings
│   │   └── production.py     # Production settings
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── manage.py
├── requirements.txt
└── .env.example
```

## Settings Configuration

The project uses a modular settings structure:

- **base.py**: Common settings for all environments
- **development.py**: Development-specific settings (DEBUG=True, console email backend)
- **production.py**: Production settings (security headers, logging, SMTP email)

By default, `manage.py` uses `development` settings. For production deployment, set:

```bash
export DJANGO_SETTINGS_MODULE=zenico_admin.settings.production
```

## Database Configuration

### Development (SQLite)

The default configuration uses SQLite:

```env
DATABASE_URL=sqlite:///db.sqlite3
```

### Production (PostgreSQL)

For production, use PostgreSQL:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/zenico_admin
```

## Running Tests

```bash
python manage.py test
```

## Deployment

1. Set `DJANGO_SETTINGS_MODULE=zenico_admin.settings.production`
2. Update `.env` with production values
3. Run `python manage.py collectstatic`
4. Run `python manage.py migrate`
5. Configure your WSGI/ASGI server (e.g., Gunicorn, uWSGI)

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]
