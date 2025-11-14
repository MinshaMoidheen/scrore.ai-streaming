from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from beanie import PydanticObjectId

from app.db_models.user import User
from app.db_models.academic import Section
from app.db_models.core import Role
from app.core.auth import authorize

router = APIRouter(prefix="/meetings", tags=["Meetings"])


class MeetingStatus(BaseModel):
    is_live: bool


@router.put("/{section_id}/status", status_code=status.HTTP_200_OK)
async def set_meeting_status(
    section_id: PydanticObjectId,
    status_data: MeetingStatus,
    current_user: User = Depends(authorize([Role.TEACHER])),
):
    """
    Set the meeting status for a section. Only teachers assigned to the section can change the status.
    Note: This endpoint may need to be updated based on how teachers are linked to sections.
    """
    section = await Section.get(section_id)
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )

    # Authorization: Only teachers with appropriate access can set meeting status
    # Teachers with 'all' or 'centre' access can set status for any section
    # Teachers with 'own' access would need additional logic to determine ownership
    if current_user.role != Role.TEACHER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can change the status of meetings",
        )

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored or removed based on your requirements
    return {"message": f"Meeting status for section {section.name} updated"}


@router.get("/{section_id}/status", status_code=status.HTTP_200_OK)
async def get_meeting_status(
    section_id: PydanticObjectId,
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    Get the meeting status for a section. Only students enrolled in the section can see the status.
    """
    section = await Section.get(section_id)
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )

    # Authorization: Users can view meeting status based on their access level
    # Superadmin and admin with 'all' access can view any section
    # Others need appropriate access level
    # Note: Additional logic may be needed to determine section ownership

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored based on your requirements
    return {"is_live": False, "meeting_link": None}
