# Logging and Sentry Integration

This document describes the logging and Sentry error tracking configuration for the Zenico Admin application.

## Local Logging Configuration

### Overview

The application uses Python's built-in logging with a custom daily rotating file handler. Logs are written to both the console and a file that rotates daily at midnight.

### Configuration

- **Log Directory**: `logs/` (relative to project root)
- **Current Log File**: `logs/app.log`
- **Rotated Log Files**: `logs/app-YYYY-MM-DD.log` (e.g., `logs/app-2026-05-30.log`)
- **Retention**: 7 days (automatically deletes logs older than 7 days)
- **Rotation**: Daily at midnight
- **Log Levels**: DEBUG, INFO, WARNING, ERROR

### Log Format

Logs are formatted with the following information:

```
{levelname} {timestamp} {module} {process_id} {thread_id} {message}
```

Example:
```
INFO 2026-05-30 19:23:27,208 mail 20966 140704458641536 Email sent successfully
ERROR 2026-05-30 19:23:27,208 webhook 20966 140704458641536 Failed to process webhook
```

### Usage in Code

```python
import logging

logger = logging.getLogger(__name__)

# Log at different levels
logger.debug("Detailed debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message")

# Log exceptions with traceback
try:
    # some code
    pass
except Exception as e:
    logger.exception("An error occurred")
```

### Log File Management

- The current day's logs are written to `logs/app.log`
- At midnight, the current log file is rotated to `logs/app-YYYY-MM-DD.log`
- The system keeps 7 days of rotated logs
- Logs older than 7 days are automatically deleted

Example log directory after a week:
```
logs/
├── app.log                 # Current day
├── app-2026-05-30.log      # Yesterday
├── app-2026-05-29.log      # 2 days ago
├── app-2026-05-28.log      # 3 days ago
├── app-2026-05-27.log      # 4 days ago
├── app-2026-05-26.log      # 5 days ago
├── app-2026-05-25.log      # 6 days ago
└── app-2026-05-24.log      # 7 days ago (will be deleted tomorrow)
```

### Custom Handler

The application uses a custom `DailyRotatingFileHandler` (in `core/logging_utils.py`) to achieve the exact filename format required: `app-YYYY-MM-DD.log`.

This custom handler extends Python's `TimedRotatingFileHandler` and overrides the filename generation to match the specification.

## Sentry Integration

### Overview

Sentry provides real-time error tracking and monitoring for production environments. The integration is **conditional** and only activates when the `SENTRY_DSN` environment variable is set.

### Configuration

Sentry is configured in `zenico_admin/settings/base.py` with the following features:

- **Django Integration**: Automatically captures Django errors and exceptions
- **Celery Integration**: Monitors background tasks and Celery workers
- **User Context**: Captures user information with errors (PII enabled)
- **Environment Detection**: Automatically sets environment (production/development)
- **Performance Monitoring**: Configurable trace sampling rate

### Environment Variables

Add these to your `.env` file to enable Sentry:

```bash
# Required: Your Sentry DSN from https://sentry.io/
SENTRY_DSN=https://your-key@sentry.io/your-project-id

# Optional: Environment name (defaults to 'production' or 'development' based on DEBUG)
SENTRY_ENVIRONMENT=production

# Optional: Percentage of transactions to send to Sentry (0.0 to 1.0, default: 0.1)
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Getting Your Sentry DSN

1. Sign up at https://sentry.io/
2. Create a new project for your Django application
3. Copy the DSN from your project settings
4. Add it to your `.env` file

### Behavior

**With SENTRY_DSN set:**
- Sentry SDK is initialized on application startup
- All unhandled exceptions are automatically sent to Sentry
- Django request errors are captured
- Celery task errors are captured
- User context is included with errors (if user is authenticated)

**Without SENTRY_DSN:**
- Sentry is completely disabled
- Application runs normally without Sentry
- No errors or warnings about missing Sentry configuration

### Testing Sentry

To test that Sentry is working:

```python
# In Django shell or a view
import sentry_sdk

# Send a test message
sentry_sdk.capture_message("Test message from Zenico Admin", level="info")

# Or trigger a test exception
raise Exception("Test exception for Sentry")
```

Check your Sentry dashboard to verify the events were received.

### What Gets Sent to Sentry

- **Exceptions**: All unhandled exceptions with full stack traces
- **User Context**: User ID, email, and username (if authenticated)
- **Request Context**: URL, method, headers, query parameters
- **Environment**: Server name, release version, environment name
- **Breadcrumbs**: Recent log messages and events leading up to the error

### Privacy Considerations

The integration has `send_default_pii=True` enabled, which means:
- User email addresses are sent to Sentry
- Request data (including POST data) is sent to Sentry
- IP addresses are captured

If you need to disable PII (Personally Identifiable Information), set `send_default_pii=False` in the Sentry configuration in `zenico_admin/settings/base.py`.

## Testing

### Running Tests

The logging and Sentry configuration includes comprehensive tests:

```bash
# Run all logging tests
python manage.py test core.tests_logging

# Run specific test class
python manage.py test core.tests_logging.LoggingConfigurationTestCase

# Run all tests
python manage.py test
```

### Manual Testing

Use the included test scripts:

```bash
# Test logging and Sentry configuration
python test_logging_sentry.py

# Test custom handler filename format
python test_custom_handler.py
```

## Troubleshooting

### Logs directory not created

The logs directory is automatically created when Django settings are loaded. If you encounter issues:

```python
# In Django shell
from django.conf import settings
print(settings.LOGS_DIR)
print(settings.LOGS_DIR.exists())
```

### Sentry not capturing errors

1. Verify SENTRY_DSN is set: `echo $SENTRY_DSN`
2. Check Django logs for Sentry initialization messages
3. Test with a manual capture: `sentry_sdk.capture_message("Test")`
4. Verify your DSN is correct in your Sentry project settings

### Log files not rotating

The rotation happens at midnight. To test rotation:

1. Check the handler configuration in settings
2. Verify the `when='midnight'` setting
3. Check system time is correct

### Permission errors

Ensure the application has write permissions to the `logs/` directory:

```bash
chmod 755 logs/
```

## Implementation Details

### File Locations

- **Settings Configuration**: `zenico_admin/settings/base.py` (lines 209-292)
- **Custom Handler**: `core/logging_utils.py`
- **Tests**: `core/tests_logging.py`
- **Environment Variables**: `.env.example` (lines 41-45)

### Dependencies

- `sentry-sdk>=2.0`: Sentry Python SDK with Django integration

### Architecture Decisions

1. **Centralized Configuration**: All logging configuration is in `base.py` (not `production.py`) to ensure consistency across environments
2. **Custom Handler**: Created custom `DailyRotatingFileHandler` to match exact filename requirement (`app-YYYY-MM-DD.log`)
3. **Conditional Sentry**: Sentry only initializes if DSN is provided, making it optional for development/testing
4. **No Exception Swallowing**: Exceptions propagate normally; Sentry only captures them, doesn't suppress them
5. **7-Day Retention**: Balances disk space with debugging needs

## Future Enhancements

Potential improvements for future implementation:

1. **Request-ID Middleware**: Add unique request IDs to track requests across services
2. **Structured Logging**: Consider JSON-formatted logs for easier parsing
3. **Log Aggregation**: Integration with ELK stack or similar for centralized log management
4. **Alert Configuration**: Set up Sentry alerts for critical errors
5. **Performance Monitoring**: Enable Sentry performance tracking for slow endpoints
