#!/usr/bin/env python3
"""
Windows Service wrapper for aw-watcher-enhanced.

This module allows aw-watcher-enhanced to run as a Windows Service,
starting automatically at system boot and running in the background.

Usage:
    # Install service
    python windows_service.py install

    # Start service
    python windows_service.py start

    # Stop service
    python windows_service.py stop

    # Remove service
    python windows_service.py remove

    # Debug (run in console)
    python windows_service.py debug

Requirements:
    pip install pywin32
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import socket

    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:
    print("Error: pywin32 is required for Windows service support.")
    print("Install it with: pip install pywin32")
    sys.exit(1)

# Service configuration
SERVICE_NAME = "AWWatcherEnhanced"
SERVICE_DISPLAY_NAME = "ActivityWatch Enhanced Watcher"
SERVICE_DESCRIPTION = "Enhanced ActivityWatch watcher with OCR and categorization"


class AWWatcherEnhancedService(win32serviceutil.ServiceFramework):
    """Windows Service class for aw-watcher-enhanced."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.watcher = None
        socket.setdefaulttimeout(60)

        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the service."""
        log_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "activitywatch" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "aw-watcher-enhanced-service.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )
        self.logger = logging.getLogger("aw-watcher-enhanced-service")

    def SvcStop(self):
        """Called when the service is asked to stop."""
        self.logger.info("Service stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

        if self.watcher:
            self.watcher.stop()

    def SvcDoRun(self):
        """Called when the service is asked to start."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.logger.info("Service starting")
        self.main()

    def main(self):
        """Main service loop."""
        try:
            # Import watcher here to avoid import errors during service registration
            from aw_watcher_enhanced.main import EnhancedWatcher

            self.logger.info("Initializing watcher")
            self.watcher = EnhancedWatcher(testing=False, enable_ocr=True)
            self.watcher.setup()

            self.logger.info("Starting watcher loop")

            # Run watcher in a separate thread so we can check for stop events
            import threading

            watcher_thread = threading.Thread(target=self.watcher.run)
            watcher_thread.daemon = True
            watcher_thread.start()

            # Wait for stop event
            while True:
                result = win32event.WaitForSingleObject(self.stop_event, 5000)
                if result == win32event.WAIT_OBJECT_0:
                    # Stop event was set
                    break

                # Check if watcher thread is still alive
                if not watcher_thread.is_alive():
                    self.logger.error("Watcher thread died unexpectedly")
                    break

            self.logger.info("Service stopped")

        except Exception as e:
            self.logger.error(f"Service error: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Service error: {e}")


def install_service():
    """Install the Windows service."""
    print(f"Installing {SERVICE_DISPLAY_NAME}...")

    try:
        # Get the path to this script
        script_path = os.path.abspath(__file__)

        # Install the service
        win32serviceutil.InstallService(
            AWWatcherEnhancedService._svc_reg_class_,
            SERVICE_NAME,
            SERVICE_DISPLAY_NAME,
            startType=win32service.SERVICE_AUTO_START,
            description=SERVICE_DESCRIPTION,
        )

        print(f"Service '{SERVICE_NAME}' installed successfully.")
        print(f"Start with: python {script_path} start")
        print(f"Or use: sc start {SERVICE_NAME}")

    except Exception as e:
        print(f"Failed to install service: {e}")
        sys.exit(1)


def uninstall_service():
    """Uninstall the Windows service."""
    print(f"Removing {SERVICE_DISPLAY_NAME}...")

    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
        print(f"Service '{SERVICE_NAME}' removed successfully.")
    except Exception as e:
        print(f"Failed to remove service: {e}")
        sys.exit(1)


def start_service():
    """Start the Windows service."""
    print(f"Starting {SERVICE_DISPLAY_NAME}...")

    try:
        win32serviceutil.StartService(SERVICE_NAME)
        print(f"Service '{SERVICE_NAME}' started.")
    except Exception as e:
        print(f"Failed to start service: {e}")
        sys.exit(1)


def stop_service():
    """Stop the Windows service."""
    print(f"Stopping {SERVICE_DISPLAY_NAME}...")

    try:
        win32serviceutil.StopService(SERVICE_NAME)
        print(f"Service '{SERVICE_NAME}' stopped.")
    except Exception as e:
        print(f"Failed to stop service: {e}")
        sys.exit(1)


def service_status():
    """Get the status of the Windows service."""
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        state = status[1]

        states = {
            win32service.SERVICE_STOPPED: "Stopped",
            win32service.SERVICE_START_PENDING: "Starting",
            win32service.SERVICE_STOP_PENDING: "Stopping",
            win32service.SERVICE_RUNNING: "Running",
            win32service.SERVICE_CONTINUE_PENDING: "Continuing",
            win32service.SERVICE_PAUSE_PENDING: "Pausing",
            win32service.SERVICE_PAUSED: "Paused",
        }

        print(f"Service '{SERVICE_NAME}' status: {states.get(state, 'Unknown')}")

    except Exception as e:
        print(f"Service not found or error: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Running as service
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AWWatcherEnhancedService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Command line handling
        if sys.argv[1] == "install":
            install_service()
        elif sys.argv[1] == "remove" or sys.argv[1] == "uninstall":
            uninstall_service()
        elif sys.argv[1] == "start":
            start_service()
        elif sys.argv[1] == "stop":
            stop_service()
        elif sys.argv[1] == "status":
            service_status()
        elif sys.argv[1] == "restart":
            stop_service()
            time.sleep(2)
            start_service()
        elif sys.argv[1] == "debug":
            # Run in debug mode (console)
            print("Running in debug mode (Ctrl+C to stop)...")
            from aw_watcher_enhanced.main import main

            main()
        else:
            # Use win32serviceutil's built-in command handling
            win32serviceutil.HandleCommandLine(AWWatcherEnhancedService)
