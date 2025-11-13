from datetime import datetime, timezone
from typing import ForwardRef
from beanie import Document, Link
from pydantic import Field

UserRef = ForwardRef("User")


class Token(Document):
    """Represents a user token."""

    token: str
    user_id: Link[UserRef]
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    class Settings:
        name = "tokens"
