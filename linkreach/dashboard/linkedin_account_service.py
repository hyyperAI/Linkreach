from datetime import timedelta
from django.utils import timezone
from linkreach.linkedin.models import ActionLog, LinkedInProfile


def verification_in_progress(profile_id: int) -> bool:
    """Application boundary for the browser-backed verification worker."""
    from linkreach.linkedin.browser.verify import verification_in_progress as check

    return check(profile_id)


def request_verification(profile_id: int) -> bool:
    """Queue one background verification without exposing browser code to views."""
    from linkreach.linkedin.browser.verify import start_verification

    return start_verification(profile_id)

def account_context(user):
    try: profile = user.linkedin_profile
    except LinkedInProfile.DoesNotExist: return {"profile": None, "status": "not_connected", "connect_used": 0, "follow_used": 0, "activities": [], "campaigns": []}
    since = timezone.now() - timedelta(days=1)
    logs = profile.action_logs.filter(created_at__gte=since).select_related("campaign").order_by("-created_at")[:8]
    return {"profile": profile, "status": profile.connection_status, "connect_used": profile.action_logs.filter(action_type=ActionLog.ActionType.CONNECT, created_at__gte=since).count(), "follow_used": profile.action_logs.filter(action_type=ActionLog.ActionType.FOLLOW_UP, created_at__gte=since).count(), "activities": logs, "campaigns": user.campaigns.order_by("name")}
