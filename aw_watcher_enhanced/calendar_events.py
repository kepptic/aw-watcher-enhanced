"""
Calendar context for aw-watcher-enhanced.

Queries EventKit on macOS to correlate current time with calendar events.
Polls every 5 minutes (calendar data changes infrequently).
"""

import logging
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CalendarMonitor:
    """Monitors calendar events to provide context about what meeting/event
    the user is currently in.

    On macOS, uses EventKit (pyobjc-framework-EventKit).
    Caches today's events and refreshes every 5 minutes.
    """

    def __init__(self, refresh_interval: float = 300.0):
        self._refresh_interval = refresh_interval
        self._events: List[Dict] = []
        self._events_lock = threading.Lock()
        self._last_refresh = 0.0
        self._available = False
        self._store = None
        self._thread = None
        self._running = False

        if sys.platform != "darwin":
            logger.info("Calendar monitoring only supported on macOS")
            return

        try:
            import EventKit

            self._store = EventKit.EKEventStore.alloc().init()
            self._available = True
            logger.info("Calendar monitoring available (EventKit)")
        except ImportError:
            logger.info(
                "EventKit not available. Install: "
                "pip install pyobjc-framework-EventKit"
            )

    def start(self):
        """Start background calendar refresh thread."""
        if not self._available:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._refresh_loop, name="calendar", daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop the calendar refresh thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_current_event(self) -> Optional[Dict[str, str]]:
        """Get the calendar event happening right now, if any.

        Returns:
            Dict with calendar_event, calendar_event_location,
            calendar_event_attendees, or None if no current event.
        """
        if not self._available:
            return None

        now = datetime.now(timezone.utc)

        with self._events_lock:
            for event in self._events:
                start = event.get("start")
                end = event.get("end")
                if start and end and start <= now <= end:
                    result = {
                        "calendar_event": event.get("title", ""),
                    }
                    if event.get("location"):
                        result["calendar_event_location"] = event[
                            "location"
                        ]
                    if event.get("attendee_count", 0) > 0:
                        result["calendar_event_attendees"] = event[
                            "attendee_count"
                        ]
                    return result

        return None

    def _refresh_loop(self):
        """Periodically refresh today's calendar events."""
        while self._running:
            try:
                self._fetch_today_events()
            except Exception as e:
                logger.debug(f"Calendar refresh error: {e}")

            time.sleep(self._refresh_interval)

    def _fetch_today_events(self):
        """Fetch today's events from EventKit."""
        if not self._store:
            return

        try:
            import EventKit
            from Foundation import NSAutoreleasePool, NSDate

            # Autorelease pool for EventKit objects in background thread
            pool = NSAutoreleasePool.alloc().init()

            # Request access (user will be prompted on first use)
            granted = [None]
            semaphore = threading.Event()

            def callback(success, error):
                granted[0] = success
                semaphore.set()

            self._store.requestFullAccessToEventsWithCompletion_(callback)
            semaphore.wait(timeout=10.0)

            if not granted[0]:
                logger.debug("Calendar access not granted")
                self._available = False
                return

            # Get today's events
            now = NSDate.date()
            start_of_day = NSDate.dateWithTimeIntervalSinceNow_(
                -86400.0
            )  # 24h ago
            end_of_day = NSDate.dateWithTimeIntervalSinceNow_(
                86400.0
            )  # 24h from now

            calendars = self._store.calendarsForEntityType_(
                EventKit.EKEntityTypeEvent
            )
            predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
                start_of_day, end_of_day, calendars
            )
            ek_events = self._store.eventsMatchingPredicate_(predicate)

            events = []
            for ek_event in ek_events or []:
                try:
                    start_date = ek_event.startDate()
                    end_date = ek_event.endDate()

                    # Convert NSDate to datetime
                    start_ts = start_date.timeIntervalSince1970()
                    end_ts = end_date.timeIntervalSince1970()

                    start_dt = datetime.fromtimestamp(
                        start_ts, tz=timezone.utc
                    )
                    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)

                    attendees = ek_event.attendees() or []

                    events.append(
                        {
                            "title": str(ek_event.title() or ""),
                            "location": str(ek_event.location() or ""),
                            "start": start_dt,
                            "end": end_dt,
                            "attendee_count": len(attendees),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Error parsing calendar event: {e}")

            with self._events_lock:
                self._events = events

            logger.debug(f"Loaded {len(events)} calendar events")

            del pool

        except Exception as e:
            logger.debug(f"EventKit fetch error: {e}")
