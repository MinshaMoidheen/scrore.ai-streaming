import os
import logging
from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.auth import authorize
from app.db_models.academic import Section
from app.db_models.core import Role, Access
from app.db_models.recording import RecordedVideo
from app.db_models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["Videos"])


@router.get("/{section_id}", response_model=List[RecordedVideo])
async def list_recorded_videos(
    section_id: PydanticObjectId,
    date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    List recorded videos for a specific section with date filtering and pagination.
    The section_id parameter can be either a section ID or a video ID.
    If it's a video ID, the endpoint will find the section from that video.
    """
    # First try to find the section
    section = await Section.get(section_id)
    
    # If section not found, try to find a video with this ID and get its section
    if not section:
        video = await RecordedVideo.get(section_id, fetch_links=True)
        if video and video.section:
            section = await Section.get(video.section.id, fetch_links=True)
    
    # Check if section exists and is not soft-deleted
    if not section or section.is_deleted.status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Section not found"
        )
    
    # Use the section's ID for querying videos
    actual_section_id = section.id

    # Authorization based on role and access level
    # Superadmin and admin with 'all' access can view any section
    # Others need appropriate access level
    if current_user.role == Role.USER and current_user.access == Access.OWN:
        # Users with 'own' access can only view their own recordings
        # This would need additional logic to determine ownership
        pass

    query = RecordedVideo.find(RecordedVideo.section.id == actual_section_id)
    if date:
        query = query.find(
            RecordedVideo.created_at >= date,
            RecordedVideo.created_at < date.replace(hour=23, minute=59, second=59),
        )
    try:
        videos = (
            await query.sort([("created_at", -1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )
        
        # Fetch links for all videos to ensure section is properly loaded
        # This is important for proper serialization in the response
        for video in videos:
            try:
                # Try to fetch the section link
                if hasattr(video, 'section') and video.section:
                    await video.fetch_all_links()
            except Exception as e:
                # Log the error but continue with the video as-is
                # The Link might not be fetchable if the section was deleted
                logger.warning(f"Failed to fetch links for video {video.id}: {str(e)}")
                # If section link can't be fetched, we'll return it as a Link reference
                # Beanie/Pydantic should handle Link serialization automatically

        return videos
    except Exception as e:
        logger.error(f"Error fetching videos for section {actual_section_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DatabaseError", "message": f"Failed to fetch videos: {str(e)}"}
        )


@router.get("/stream/{video_id}")
async def stream_video(
    video_id: PydanticObjectId,
    request: Request,
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    Stream a recorded video.
    """
    video = await RecordedVideo.get(video_id, fetch_links=True)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    # Authorization based on role and access level
    # Superadmin and admin with 'all' access can view any video
    # Others need appropriate access level
    if current_user.role == Role.USER and current_user.access == Access.OWN:
        # Users with 'own' access can only view their own recordings
        # This would need additional logic to determine ownership
        pass

    video_path = os.path.join("videos_recorded", video.filename)
    if not os.path.exists(video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found"
        )

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("Range")

    async def aiter_file(path: str, start: int, end: int):
        with open(path, "rb") as f:
            f.seek(start)
            while (pos := f.tell()) <= end:
                read_size = min(1024 * 1024, end - pos + 1)
                yield f.read(read_size)

    if range_header:
        start_str, end_str = range_header.replace("bytes=", "").split("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": "video/mkv",
        }
        return StreamingResponse(
            aiter_file(video_path, start, end), status_code=206, headers=headers
        )
    else:
        headers = {
            "Content-Length": str(file_size),
            "Content-Type": "video/mkv",
        }
        return StreamingResponse(
            aiter_file(video_path, 0, file_size - 1), headers=headers
        )
