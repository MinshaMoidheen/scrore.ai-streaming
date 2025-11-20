# models/__init__.py

from .core import SoftDelete, Role, Access, AttendanceStatus
from .academic import CourseClass, Section, Subject
from .user import User
from .token import Token
from .attendance import Schedule, Attendance, AttendanceRecord
from .recording import RecordedVideo
from .student import Student
from .meeting import Meeting

# A list of all model classes for easier management
__all__ = [
    "User",
    "Token",
    "CourseClass",
    "Section",
    "Subject",
    "Schedule",
    "Attendance",
    "AttendanceRecord",
    "RecordedVideo",
    "Student",
    "Meeting",
    "SoftDelete",
    "Role",
    "Access",
    "AttendanceStatus",
]

# --- Crucial Step: Update all Forward References ---
# This allows Beanie to correctly resolve the relationships between models
# that are defined in different files.
SoftDelete.model_rebuild()
Token.model_rebuild()
CourseClass.model_rebuild()
Section.model_rebuild()
Subject.model_rebuild()
User.model_rebuild()
Schedule.model_rebuild()
Attendance.model_rebuild()
AttendanceRecord.model_rebuild()
RecordedVideo.model_rebuild()
Student.model_rebuild()
Meeting.model_rebuild()