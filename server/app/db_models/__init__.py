# models/__init__.py

from .core import SoftDelete, Role, AttendanceStatus
from .academic import Class, Division
from .user import User
from .token import Token
from .attendance import Schedule, Attendance, AttendanceRecord
from .recording import RecordedVideo

# A list of all model classes for easier management
__all__ = [
    "User",
    "Token",
    "Class",
    "Division",
    "Schedule",
    "Attendance",
    "AttendanceRecord",
    "RecordedVideo",
    "SoftDelete",
    "Role",
    "AttendanceStatus",
]

# --- Crucial Step: Update all Forward References ---
# This allows Beanie to correctly resolve the relationships between models
# that are defined in different files.
SoftDelete.model_rebuild()
Token.model_rebuild()
Class.model_rebuild()
Division.model_rebuild()
User.model_rebuild()
Schedule.model_rebuild()
Attendance.model_rebuild()
AttendanceRecord.model_rebuild()
RecordedVideo.model_rebuild()