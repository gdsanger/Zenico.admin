#!/usr/bin/env python
"""
Test script for logging and Sentry configuration.
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zenico_admin.settings.development')
django.setup()

import logging
from django.conf import settings

def test_logging_configuration():
    """Test that logging is properly configured."""
    print("=" * 60)
    print("LOGGING CONFIGURATION TEST")
    print("=" * 60)

    # Check logs directory exists
    logs_dir = settings.BASE_DIR / 'logs'
    print(f"\n1. Logs directory: {logs_dir}")
    print(f"   Exists: {logs_dir.exists()}")
    print(f"   Is directory: {logs_dir.is_dir()}")

    # Check log file exists
    log_file = logs_dir / 'app.log'
    print(f"\n2. Log file: {log_file}")
    print(f"   Exists: {log_file.exists()}")

    # Test logger at different levels
    print("\n3. Testing logger at different levels:")
    logger = logging.getLogger(__name__)

    logger.debug("DEBUG: This is a debug message")
    logger.info("INFO: This is an info message")
    logger.warning("WARNING: This is a warning message")
    logger.error("ERROR: This is an error message")

    print("   ✓ Logged messages at DEBUG, INFO, WARNING, ERROR levels")

    # Check logging configuration
    print("\n4. Logging handlers:")
    for handler_name, handler_config in settings.LOGGING['handlers'].items():
        print(f"   - {handler_name}: {handler_config['class']}")
        if handler_name == 'daily_file':
            print(f"     * Filename: {handler_config.get('filename', 'N/A')}")
            print(f"     * When: {handler_config.get('when', 'N/A')}")
            print(f"     * Backup Count: {handler_config.get('backupCount', 'N/A')}")

    # Read and display log file content
    if log_file.exists():
        print(f"\n5. Log file content (last 10 lines):")
        with open(log_file, 'r') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(f"   {line.rstrip()}")

    print("\n✅ Logging configuration test completed successfully!")
    return True


def test_sentry_configuration():
    """Test Sentry configuration."""
    print("\n" + "=" * 60)
    print("SENTRY CONFIGURATION TEST")
    print("=" * 60)

    sentry_dsn = os.getenv('SENTRY_DSN', '')

    print(f"\n1. SENTRY_DSN environment variable: {'Set' if sentry_dsn else 'Not set'}")

    if not sentry_dsn:
        print("   ℹ️  Sentry is disabled (no DSN provided)")
        print("\n✅ Sentry configuration test completed successfully!")
        print("   To enable Sentry, set the SENTRY_DSN environment variable")
        return True

    print(f"   DSN: {sentry_dsn[:20]}...{sentry_dsn[-10:]}")

    # Check if sentry_sdk was imported and initialized
    try:
        import sentry_sdk
        print("\n2. Sentry SDK imported successfully")

        # Try to capture a test message
        print("\n3. Testing Sentry integration:")
        print("   Sending test message to Sentry...")
        event_id = sentry_sdk.capture_message("Test message from logging test script", level="info")
        print(f"   ✓ Message sent (Event ID: {event_id})")

        print("\n✅ Sentry configuration test completed successfully!")
        print("   Check your Sentry dashboard to verify the test message was received")
        return True
    except ImportError:
        print("\n❌ ERROR: sentry_sdk not installed")
        print("   Run: pip install sentry-sdk")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: Sentry test failed: {e}")
        return False


def test_exception_handling():
    """Test that exceptions are properly logged and sent to Sentry."""
    print("\n" + "=" * 60)
    print("EXCEPTION HANDLING TEST")
    print("=" * 60)

    logger = logging.getLogger(__name__)

    print("\n1. Testing exception logging (will be caught):")
    try:
        # Intentionally raise an exception
        result = 1 / 0
    except ZeroDivisionError as e:
        logger.exception("Caught ZeroDivisionError")
        print("   ✓ Exception logged with traceback")

    print("\n✅ Exception handling test completed successfully!")
    return True


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("ZENICO ADMIN - LOGGING AND SENTRY TEST")
    print("=" * 60)

    success = True

    try:
        success &= test_logging_configuration()
        success &= test_sentry_configuration()
        success &= test_exception_handling()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False

    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if success else 1)
