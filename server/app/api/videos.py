import os
from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.auth import authorize
from app.db_models.academic import Division
from app.db_models.core import Role
from app.db_models.recording import RecordedVideo
from app.db_models.user import User

router = APIRouter(prefix="/videos", tags=["Videos"])


@router.get("/{division_id}", response_model=List[RecordedVideo])
async def list_recorded_videos(
    division_id: PydanticObjectId,
    date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    List recorded videos for a specific division with date filtering and pagination.
    """
    division = await Division.get(division_id)
    if not division:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Division not found"
        )

    if current_user.division.id != division_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view recordings for this division",
        )

    query = RecordedVideo.find(RecordedVideo.division.id == division_id)
    if date:
        query = query.find(
            RecordedVideo.created_at >= date,
            RecordedVideo.created_at < date.replace(hour=23, minute=59, second=59),
        )
    videos = (
        await query.sort([("created_at", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )

    return videos


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

    if current_user.division.id != video.division.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this recording",
        )

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
