from django.core.exceptions import PermissionDenied

def require_researcher(user):
    if not user.is_authenticated or not getattr(user, "is_researcher", False):
        raise PermissionDenied("Researcher permissions required.")