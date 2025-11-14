# models/user.py

from datetime import datetime, timezone
from typing import Optional

from beanie import Document, Link, Indexed, PydanticObjectId
from pydantic import EmailStr, Field, model_validator

from .core import Role, Access, SoftDelete

# --- Type Forward References ---
# (Removed SectionRef and CourseClassRef as they're no longer used)

# --- Beanie Document Models ---


class User(Document):
    """Represents a user in the system."""
    username: str = Field(max_length=20)
    email: Indexed(EmailStr, unique=True) = Field(max_length=50)
    password: str
    role: Role
    access: Access = Field(default=Access.CENTRE)
    collaboratingCentreId: Optional[PydanticObjectId] = None
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_access_for_role(self):
        """Validate that access level is appropriate for the user's role."""
        if self.role == Role.SUPERADMIN:
            if self.access != Access.ALL:
                raise ValueError('Superadmin role can only have "all" access')
        elif self.role == Role.ADMIN:
            if self.access not in (Access.ALL, Access.CENTRE):
                raise ValueError('Admin role can only have "all" or "centre" access')
        elif self.role == Role.USER:
            if self.access not in (Access.ALL, Access.CENTRE, Access.OWN):
                raise ValueError('User role can have "all", "centre", or "own" access')
        elif self.role == Role.TEACHER:
            if self.access not in (Access.ALL, Access.CENTRE, Access.OWN):
                raise ValueError('Teacher role can have "all", "centre", or "own" access')
        return self

    async def soft_delete(self, deleted_by: "User"):
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    class Settings:
        name = "users"
        indexes = []