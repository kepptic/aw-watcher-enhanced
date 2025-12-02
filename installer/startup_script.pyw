#!/usr/bin/env pythonw
"""
Startup script for aw-watcher-enhanced.

This script is designed to run at Windows startup without showing a console window.
Use pythonw.exe to run this script silently.

Place a shortcut to this script in:
    %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

Or create a scheduled task with Task Scheduler.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Setup logging first
log_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'activitywatch' / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'aw-watcher-enhanced-startup.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(log_file)]
)
logger = logging.getLogger(__name__)


def wait_for_aw_server(timeout=60, interval=5):
    """Wait for ActivityWatch server to be available."""
    import urllib.request
    import urllib.error

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen('http://localhost:5600/api/0/info', timeout=5)
            if req.status == 200:
                logger.info("ActivityWatch server is available")
                return True
        except (urllib.error.URLError, ConnectionRefusedError):
            pass
        except Exception as e:
            logger.warning(f"Error checking server: {e}")

        logger.debug(f"Waiting for ActivityWatch server... ({interval}s)")
        time.sleep(interval)

    logger.warning(f"ActivityWatch server not available after {timeout}s")
    return False


def main():
    """Main entry point for startup script."""
    logger.info("aw-watcher-enhanced startup script starting")

    # Wait a bit for system to stabilize after login
    startup_delay = int(os.environ.get('AW_STARTUP_DELAY', '10'))
    logger.info(f"Waiting {startup_delay}s for system startup...")
    time.sleep(startup_delay)

    # Wait for ActivityWatch server
    if not wait_for_aw_server():
        logger.error("ActivityWatch server not available, exiting")
        sys.exit(1)

    # Import and run watcher
    try:
        # Add package to path if running from source
        script_dir = Path(__file__).parent.parent
        if (script_dir / 'aw_watcher_enhanced').exists():
            sys.path.insert(0, str(script_dir))

        from aw_watcher_enhanced.main import EnhancedWatcher

        logger.info("Starting aw-watcher-enhanced")
        watcher = EnhancedWatcher(testing=False, enable_ocr=True)
        watcher.setup()
        watcher.run()

    except ImportError as e:
        logger.error(f"Failed to import watcher: {e}")
        logger.error("Make sure aw-watcher-enhanced is installed: pip install aw-watcher-enhanced")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error running watcher: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
