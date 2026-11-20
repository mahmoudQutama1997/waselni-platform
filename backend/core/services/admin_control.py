"""Admin staff roles, permission checks and the administrative audit trail.

The console hides sections a role cannot use, but that is convenience only:
every admin endpoint calls :func:`has_permission` (or ``control_views._guard``)
so a crafted request is refused in the backend as well.
"""
from ..models import AuditLog

SUPER_ADMIN = "super_admin"

ADMIN_ROLE_LABELS = {
    "super_admin": "Super admin",
    "operations": "Operations manager",
    "services": "Services manager",
    "merchants": "Merchants manager",
    "captains": "Captains manager",
    "regions": "Regions manager",
    "support": "Support agent",
    "finance": "Finance officer",
    "review": "Review & approval officer",
}

# Section -> roles allowed to use it. ``dashboard`` is the shared landing page.
PERMISSION_ROLES = {
    "dashboard": set(ADMIN_ROLE_LABELS),
    "services": {"super_admin", "services"},
    "catalog": {"super_admin", "services"},
    "providers": {"super_admin", "merchants", "review"},
    "branches": {"super_admin", "regions", "merchants"},
    "regions": {"super_admin", "regions"},
    "captains": {"super_admin", "captains", "review"},
    "operations": {"super_admin", "operations", "support"},
    "map": {"super_admin", "operations", "regions"},
    "analytics": {"super_admin", "operations", "finance"},
    "finance": {"super_admin", "finance"},
    "staff": {"super_admin"},
    "support": {"super_admin", "support"},
    "audit": {"super_admin", "review"},
    "notifications": set(ADMIN_ROLE_LABELS),
    "settings": {"super_admin"},
}

ALL_PERMISSIONS = list(PERMISSION_ROLES)


def admin_role(user):
    """Return the effective admin role, or '' for a non-admin account."""
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    if user.is_superuser:
        return SUPER_ADMIN
    if getattr(user, "role", "") != "admin":
        return ""
    return getattr(user, "admin_role", "") or SUPER_ADMIN


def permissions_for(user):
    role = admin_role(user)
    if not role:
        return []
    return [name for name, roles in PERMISSION_ROLES.items() if role in roles]


def has_permission(user, permission):
    role = admin_role(user)
    if not role:
        return False
    if role == SUPER_ADMIN:
        return True
    return role in PERMISSION_ROLES.get(permission, set())


def record_audit(actor, action, target_type, target_id="", summary="", before=None, after=None):
    """Write one immutable audit row; never raises to the caller's transaction."""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=(actor.get_full_name() or actor.username) if actor else "system",
        action=str(action)[:60],
        target_type=str(target_type)[:40],
        target_id=str(target_id or "")[:40],
        summary=str(summary)[:255],
        before=before or {},
        after=after or {},
    )
