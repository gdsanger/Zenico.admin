"""
Test the custom DailyRotatingFileHandler to verify filename format.
"""
import os
import tempfile
import time
from pathlib import Path
from core.logging_utils import DailyRotatingFileHandler


def test_custom_filename_format():
    """Test that the custom handler creates files with app-YYYY-MM-DD.log format."""
    print("=" * 60)
    print("TESTING CUSTOM DAILY ROTATING FILE HANDLER")
    print("=" * 60)

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / 'app.log'

        # Create the handler
        handler = DailyRotatingFileHandler(
            filename=str(log_file),
            when='midnight',
            interval=1,
            backupCount=7
        )

        print(f"\n1. Handler created")
        print(f"   Base filename: {handler.baseFilename}")
        print(f"   Base name: {handler.base_name}")
        print(f"   Log directory: {handler.log_dir}")
        print(f"   Suffix format: {handler.suffix}")

        # Test the custom namer
        test_default_name = str(log_file) + ".2026-05-30"
        custom_name = handler._custom_namer(test_default_name)

        print(f"\n2. Testing custom namer:")
        print(f"   Default name: {test_default_name}")
        print(f"   Custom name: {custom_name}")
        print(f"   Expected format: {temp_dir}/app-2026-05-30.log")

        # Verify the format
        expected_name = os.path.join(temp_dir, "app-2026-05-30.log")
        assert custom_name == expected_name, f"Expected {expected_name}, got {custom_name}"
        print(f"   ✓ Custom name matches expected format!")

        # Test with different dates
        test_dates = ["2026-05-29", "2026-05-28", "2026-05-27"]
        print(f"\n3. Testing with multiple dates:")
        for date in test_dates:
            test_name = str(log_file) + f".{date}"
            custom_name = handler._custom_namer(test_name)
            expected = os.path.join(temp_dir, f"app-{date}.log")
            assert custom_name == expected, f"Expected {expected}, got {custom_name}"
            print(f"   ✓ {date} -> app-{date}.log")

        handler.close()

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    print("\nThe custom handler will create log files with the format:")
    print("  - app.log (current log file)")
    print("  - app-YYYY-MM-DD.log (rotated log files)")
    print("\nOlder files beyond backupCount (7) will be automatically deleted.")


if __name__ == '__main__':
    test_custom_filename_format()
