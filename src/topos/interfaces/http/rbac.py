"""Role-based access control guard.

Usage::

    from topos.interfaces.http.auth import get_current_user, require_role
    from topos.domain.auth import Role

    @router.get("/items")
    async def list_items(user: User = Depends(get_current_user)):
        require_role(user, Role.ANALYST)
        ...
"""

from __future__ import annotations

from fastapi import HTTPException, status

from topos.domain.auth import Role, User


def require_role(user: User, minimum: Role) -> None:
    """Check that the user has at least the given role.

    Role hierarchy: viewer < reviewer < analyst < admin
    """
    hierarchy = [Role.VIEWER, Role.REVIEWER, Role.ANALYST, Role.ADMIN]
    user_max = max((hierarchy.index(r) for r in user.roles if r in hierarchy), default=-1)
    required = hierarchy.index(minimum)

    if user_max < required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {minimum.value} or higher required",
        )
