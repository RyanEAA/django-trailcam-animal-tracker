from django.core.exceptions import PermissionDenied
from django.utils import timezone

LOCK_TTL_SECONDS = 60

def require_researcher(user):
    if not user.is_authenticated or not getattr(user, "is_researcher", False):
        raise PermissionDenied("Researcher permissions required.")
    
def _lock_is_active(opened_at):
    if not opened_at:
        return False
    return opened_at >= timezone.now() - timezone.timedelta(seconds=LOCK_TTL_SECONDS)

def _lock_status(obj):
    """
    Returns a lock payload the frontend can display.
    """
    if obj.opened_by_id and _lock_is_active(obj.opened_at):
        expires_in = max(
            0,
            int((obj.opened_at + timezone.timedelta(seconds=LOCK_TTL_SECONDS) - timezone.now()).total_seconds())
        )
        return {
            "active": True,
            "opened_by": obj.opened_by.username if obj.opened_by else "",
            "expires_in": expires_in,
            "ttl_seconds": LOCK_TTL_SECONDS,
            "is_mine": False,
        }

    return {
        "active": False,
        "opened_by": "",
        "expires_in": 0,
        "ttl_seconds": 0,
        "is_mine": False,
    }

def _require_my_lock(obj, user):
    """
    True only if:
      - lock exists
      - lock is active
      - lock belongs to this user
    """
    return (
        obj.opened_by_id is not None
        and _lock_is_active(obj.opened_at)
        and obj.opened_by_id == user.id
    )