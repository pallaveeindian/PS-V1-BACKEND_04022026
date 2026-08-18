# core/signals.py
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

@receiver(user_logged_in)
def track_successful_login(sender, request, user, **kwargs):
    """
    Increments the successful login counter in the cache.
    Triggered manually via JWT login views.
    """
    try:
        # Atomic increment
        cache.incr("successful_logins_count", 1)
    except ValueError:
        # If the key doesn't exist yet, cache.incr() throws a ValueError.
        # Initialize it to 1 with no expiration.
        cache.set("successful_logins_count", 1, timeout=None)
    except Exception as e:
        # Fail gracefully so auth doesn't break if Redis/Cache is temporarily down
        logger.error(f"Failed to update successful_logins_count: {e}")