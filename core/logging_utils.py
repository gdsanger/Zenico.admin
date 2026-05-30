"""
Custom logging utilities for Zenico Admin.
"""
import logging.handlers
import os
import time


class DailyRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    Custom TimedRotatingFileHandler that uses app-YYYY-MM-DD.log naming format.

    This handler rotates log files daily at midnight and keeps 7 days of backups.
    The filename format matches the requirement: app-YYYY-MM-DD.log
    """

    def __init__(self, filename, **kwargs):
        # Extract directory and base name
        self.log_dir = os.path.dirname(filename)
        self.base_name = os.path.basename(filename).replace('.log', '')

        # Use a placeholder filename for the current day
        super().__init__(filename, **kwargs)

        # Override the namer to use our custom format
        self.namer = self._custom_namer

    def _custom_namer(self, default_name):
        """
        Custom namer that converts app.log.YYYY-MM-DD to app-YYYY-MM-DD.log
        """
        # default_name format: /path/to/app.log.YYYY-MM-DD
        # Extract the date suffix (last part after the last dot)
        if '.' in default_name:
            # Split and get the date part
            base_path = os.path.dirname(default_name)
            filename = os.path.basename(default_name)

            # filename is like: app.log.YYYY-MM-DD
            # We want: app-YYYY-MM-DD.log
            parts = filename.split('.')
            if len(parts) >= 3:  # ['app', 'log', 'YYYY-MM-DD']
                # Get the base name (without .log extension)
                base_name = parts[0]
                # Get the date suffix (last part)
                date_suffix = parts[-1]
                # Return custom format: /path/to/app-YYYY-MM-DD.log
                return os.path.join(base_path, f"{base_name}-{date_suffix}.log")

        # If we can't parse it, return the default
        return default_name

    def doRollover(self):
        """
        Override doRollover to ensure current log file is named with today's date.
        """
        # Close current file
        if self.stream:
            self.stream.close()
            self.stream = None

        # Get current time
        current_time = int(time.time())
        dst_now = time.localtime(current_time)[-1]

        # Rotate to dated filename
        t = self.rolloverAt - self.interval
        time_tuple = time.localtime(t)
        dst_then = time_tuple[-1]

        if dst_now != dst_then:
            if dst_now:
                addend = 3600
            else:
                addend = -3600
            time_tuple = time.localtime(t + addend)

        # Generate the dated filename
        dfn = self.rotation_filename(self.baseFilename + "." + time.strftime(self.suffix, time_tuple))

        # If the dated file exists, remove it
        if os.path.exists(dfn):
            os.remove(dfn)

        # Rename current log file to dated filename
        self.rotate(self.baseFilename, dfn)

        # Delete old backup files
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)

        # Open new log file
        if not self.delay:
            self.stream = self._open()

        # Calculate next rollover time
        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at = new_rollover_at + self.interval

        self.rolloverAt = new_rollover_at
