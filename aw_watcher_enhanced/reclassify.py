"""
Retroactive reclassification for aw-watcher-enhanced.

Re-runs categorization on existing events to apply updated rules,
keywords, or RAG data retroactively.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from aw_client import ActivityWatchClient
from aw_core.models import Event

from .categorizer import categorize_event
from .config import load_config

logger = logging.getLogger(__name__)

WATCHER_NAME = "aw-watcher-enhanced"


class Reclassifier:
    """Re-classifies existing events with current rules."""

    def __init__(self, testing: bool = False):
        self.testing = testing
        self.config = load_config()
        # Use a different client name for CLI tools to avoid single-instance lock
        self.client = ActivityWatchClient(f"{WATCHER_NAME}-cli", testing=testing)
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"
        self.cat_config = self.config.get("categorization", {})

    def _clear_caches(self):
        """Clear categorizer caches to force fresh rule loading."""
        from . import categorizer
        categorizer._rules_cache = None
        categorizer._clients_cache = None

    def reclassify(
        self,
        start: datetime,
        end: datetime,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """Re-classify events in the given time range.

        Args:
            start: Start of time range.
            end: End of time range.
            dry_run: If True, don't modify events, just report changes.

        Returns:
            List of dicts with 'event_id', 'old_category', 'new_category'.
        """
        self._clear_caches()
        changes = []

        with self.client:
            # Fetch events in the range
            events = self.client.get_events(
                self.bucket_id,
                start=start,
                end=end,
                limit=-1,
            )

            if not events:
                logger.info("No events found in the specified range")
                return changes

            logger.info(f"Found {len(events)} events to reclassify")

            for event in events:
                old_category = event.data.get("category", "")
                new_category = categorize_event(event.data, self.cat_config) or ""

                if old_category != new_category:
                    changes.append({
                        "event_id": event.id,
                        "timestamp": event.timestamp.isoformat(),
                        "app": event.data.get("app", ""),
                        "title": event.data.get("title", "")[:60],
                        "old_category": old_category or "(none)",
                        "new_category": new_category or "(none)",
                    })

                    if not dry_run:
                        event.data["category"] = new_category
                        # Update by deleting and re-inserting
                        try:
                            self.client.delete_event(self.bucket_id, event.id)
                            self.client.insert_event(self.bucket_id, event)
                        except Exception as e:
                            logger.error(
                                f"Failed to update event {event.id}: {e}"
                            )

        return changes


def run_reclassify(
    start_str: str,
    end_str: str,
    dry_run: bool = False,
    testing: bool = False,
):
    """CLI entry point for reclassification.

    Args:
        start_str: Start date string (YYYY-MM-DD).
        end_str: End date string (YYYY-MM-DD).
        dry_run: If True, only report what would change.
        testing: Use testing server.
    """
    start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_str, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\nReclassifying events from {start_str} to {end_str} ({mode})")
    print("=" * 70)

    reclassifier = Reclassifier(testing=testing)
    changes = reclassifier.reclassify(start, end, dry_run=dry_run)

    if not changes:
        print("\nNo changes needed. All events already match current rules.")
        return

    # Print summary table
    print(f"\n{'Timestamp':<22} {'App':<20} {'Old Category':<25} {'New Category':<25}")
    print("-" * 92)
    for c in changes:
        ts = c["timestamp"][:19]
        app = c["app"][:19]
        old = c["old_category"][:24]
        new = c["new_category"][:24]
        print(f"{ts:<22} {app:<20} {old:<25} {new:<25}")

    print(f"\nTotal changes: {len(changes)}")
    if dry_run:
        print("(Dry run — no events were modified)")
