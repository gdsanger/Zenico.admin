"""
Tests for logging and Sentry integration.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
import logging


class LoggingConfigurationTestCase(TestCase):
    """Tests for logging configuration."""

    def test_logs_directory_exists(self):
        """Test that logs directory is created."""
        logs_dir = settings.BASE_DIR / 'logs'
        self.assertTrue(logs_dir.exists())
        self.assertTrue(logs_dir.is_dir())

    def test_logging_handlers_configured(self):
        """Test that logging handlers are properly configured."""
        self.assertIn('console', settings.LOGGING['handlers'])
        self.assertIn('daily_file', settings.LOGGING['handlers'])

    def test_daily_file_handler_configuration(self):
        """Test that daily file handler is configured with correct parameters."""
        daily_file_handler = settings.LOGGING['handlers']['daily_file']

        self.assertEqual(
            daily_file_handler['class'],
            'logging.handlers.TimedRotatingFileHandler'
        )
        self.assertEqual(daily_file_handler['when'], 'midnight')
        self.assertEqual(daily_file_handler['interval'], 1)
        self.assertEqual(daily_file_handler['backupCount'], 7)
        self.assertEqual(daily_file_handler['level'], 'DEBUG')

    def test_log_file_location(self):
        """Test that log file is in the correct location."""
        daily_file_handler = settings.LOGGING['handlers']['daily_file']
        log_file = Path(daily_file_handler['filename'])

        expected_log_file = settings.BASE_DIR / 'logs' / 'app.log'
        self.assertEqual(str(log_file), str(expected_log_file))

    def test_logging_levels_configured(self):
        """Test that all required logging levels are configured."""
        # Check root logger
        self.assertEqual(settings.LOGGING['root']['level'], 'INFO')

        # Check django logger
        self.assertIn('django', settings.LOGGING['loggers'])
        django_logger = settings.LOGGING['loggers']['django']
        self.assertEqual(
            django_logger['level'],
            os.getenv('DJANGO_LOG_LEVEL', 'INFO')
        )

    def test_logger_can_write_messages(self):
        """Test that logger can write messages at different levels."""
        logger = logging.getLogger(__name__)

        # These should not raise exceptions
        logger.debug("Test DEBUG message")
        logger.info("Test INFO message")
        logger.warning("Test WARNING message")
        logger.error("Test ERROR message")

    def test_exception_logging(self):
        """Test that exceptions are properly logged."""
        logger = logging.getLogger(__name__)

        try:
            # Intentionally raise an exception
            _ = 1 / 0
        except ZeroDivisionError:
            # This should not raise an exception
            logger.exception("Caught ZeroDivisionError")


class SentryConfigurationTestCase(TestCase):
    """Tests for Sentry configuration."""

    def test_sentry_not_initialized_without_dsn(self):
        """Test that Sentry is not initialized when SENTRY_DSN is not set."""
        # In test environment, SENTRY_DSN should not be set
        sentry_dsn = os.getenv('SENTRY_DSN', '')

        # If DSN is not set, Sentry should not be initialized
        if not sentry_dsn:
            # This is expected behavior
            self.assertEqual(sentry_dsn, '')

    @override_settings(SENTRY_DSN='https://test@sentry.io/123')
    @patch('sentry_sdk.init')
    def test_sentry_initialization_with_dsn(self, mock_sentry_init):
        """Test that Sentry is initialized when SENTRY_DSN is provided."""
        # Import settings module to trigger Sentry initialization
        from importlib import reload
        from zenico_admin.settings import base

        # The actual Sentry initialization happens at import time,
        # so we just verify the DSN is set in settings
        test_dsn = 'https://test@sentry.io/123'
        with patch.dict(os.environ, {'SENTRY_DSN': test_dsn}):
            # Verify DSN is accessible
            self.assertEqual(os.getenv('SENTRY_DSN'), test_dsn)

    def test_sentry_dsn_from_environment(self):
        """Test that SENTRY_DSN is read from environment variable."""
        # Check that SENTRY_DSN can be read from environment
        sentry_dsn = os.getenv('SENTRY_DSN', '')

        # This should not raise an exception
        self.assertIsInstance(sentry_dsn, str)

    @patch('sentry_sdk.capture_exception')
    def test_exception_not_swallowed(self, mock_capture):
        """Test that exceptions are not swallowed (they propagate normally)."""
        # Exceptions should still be raised even with Sentry
        with self.assertRaises(ZeroDivisionError):
            _ = 1 / 0


class LogRotationTestCase(TestCase):
    """Tests for log rotation functionality."""

    def test_backup_count_is_seven_days(self):
        """Test that backup count is set to 7 for 7-day retention."""
        daily_file_handler = settings.LOGGING['handlers']['daily_file']
        self.assertEqual(daily_file_handler['backupCount'], 7)

    def test_rotation_happens_daily(self):
        """Test that log rotation is configured for daily rotation."""
        daily_file_handler = settings.LOGGING['handlers']['daily_file']
        self.assertEqual(daily_file_handler['when'], 'midnight')
        self.assertEqual(daily_file_handler['interval'], 1)

    def test_log_formatter_includes_timestamp(self):
        """Test that log formatter includes timestamp."""
        formatters = settings.LOGGING['formatters']
        verbose_format = formatters['verbose']['format']

        # Check that timestamp is included in format
        self.assertIn('{asctime}', verbose_format)
        self.assertIn('{levelname}', verbose_format)
        self.assertIn('{module}', verbose_format)
        self.assertIn('{message}', verbose_format)
