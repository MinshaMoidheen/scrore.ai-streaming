from fastapi import APIRouter, Body, HTTPException, Depends
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRecorder
from ..api.resizing import AspectRatioPreservingTrack
from ..api.compositing import CompositingTrack, AudioMixerTrack
import uuid
import os
import asyncio
import logging
from typing import Dict, Optional, Set
from beanie import PydanticObjectId

from app.db_models.user import User
from app.db_models.academic import Section
from app.db_models.core import Role
from app.db_models.recording import RecordedVideo
from app.core.auth import authorize

router = APIRouter()
logger = logging.getLogger("recording_pipeline")
logging.basicConfig(level=logging.INFO)

sessions: Dict[str, "RecordingSession"] = {}


class RecordingSession:
    def __init__(self, session_id: str, file_path: str, section_id: PydanticObjectId):
        self.session_id = session_id
        self.pc = RTCPeerConnection()
        self.recorder = None
        self.file_path = file_path
        self.section_id = section_id
        self.video_tracks: Dict[str, MediaStreamTrack] = {}
        self.audio_tracks: Set[MediaStreamTrack] = set()
        self.compositor: Optional[CompositingTrack] = None
        self.audio_mixer: Optional[AudioMixerTrack] = None
        self.__recorder_started = False
        self.__stopped = False

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(
                f"Recording PC state for session {self.session_id} is {self.pc.connectionState}"
            )
            if self.pc.connectionState == "connected":
                logger.info(f"WebRTC connection established for session {self.session_id}. Starting recorder now...")
                # Start the recorder now that WebRTC connection is established
                if self.recorder and not hasattr(self, '_recorder_started'):
                    try:
                        # Wait a bit more for media to start flowing after connection
                        await asyncio.sleep(1.0)
                        
                        # Reinitialize audio mixer with current tracks to ensure proper setup
                        if self.audio_tracks and self.audio_mixer:
                            logger.info(f"Reinitializing audio mixer with {len(self.audio_tracks)} tracks after connection established")
                            self.audio_mixer.tracks = set(self.audio_tracks)
                            self.audio_mixer._resamplers.clear()  # Clear old resamplers
                        
                        await self.recorder.start()
                        self._recorder_started = True
                        logger.info(f"MediaRecorder started after WebRTC connection established and media stabilized.")
                    except Exception as e:
                        logger.error(f"Failed to start recorder after connection: {e}")
            elif self.pc.connectionState in ["failed", "closed", "disconnected"]:
                logger.info(
                    f"Recording session {self.session_id} disconnected. Stopping gracefully."
                )
                await self.stop()

        @self.pc.on("track")
        async def on_track(track):
            logger.info(
                f"Track '{track.kind}' received for recording session {self.session_id}."
            )
            if track.kind == "video":
                if not self.video_tracks.get("main"):
                    logger.info("Received video track for recording (screen share).")
                    self.video_tracks["main"] = AspectRatioPreservingTrack(track)
                else:
                    logger.warning(
                        "A second video track was received for recording. It will be ignored."
                    )
            elif track.kind == "audio":
                logger.info(f"Received audio track. Track enabled: {hasattr(track, 'enabled') and track.enabled if hasattr(track, 'enabled') else 'N/A'}")
                self.audio_tracks.add(track)
                if self.audio_mixer is not None:
                    logger.info(f"Adding audio track to existing mixer. Mixer now has {len(self.audio_mixer.tracks)} tracks.")
                    self.audio_mixer.tracks.add(track)
                else:
                    logger.info("Audio track received but mixer not yet created - will be added when recorder starts.")

            await self._maybe_start_recorder()

    async def _maybe_start_recorder(self):
        # Start recording as soon as we have video tracks, even if no audio yet
        if self.__recorder_started or not self.video_tracks:
            return

        logger.info(
            f"Video track received for session {self.session_id}. Initializing recorder."
        )
        self.__recorder_started = True

        self.compositor = CompositingTrack(
            main_track=self.video_tracks.get("main"),
        )
        
        # Initialize audio mixer with existing tracks (could be empty initially)
        self.audio_mixer = AudioMixerTrack(tracks=self.audio_tracks.copy())

        options = {"crf": "18", "preset": "ultrafast", "tune": "zerolatency"}
        self.recorder = MediaRecorder(self.file_path, options=options)

        self.recorder.addTrack(self.compositor)
        self.recorder.addTrack(self.audio_mixer)

        # Don't start recorder immediately - wait for WebRTC connection
        logger.info(f"Recorder initialized but not started - waiting for WebRTC connection...")
        
        if self.audio_tracks:
            logger.info(f"Recorder for session {self.session_id} started with {len(self.audio_tracks)} audio track(s).")
        else:
            logger.info(f"Recorder for session {self.session_id} started with video only. Audio tracks will be added when received.")

    async def start(self, offer):
        logger.info(f"Received SDP offer for session {self.session_id}")
        logger.info(f"Offer contains audio: {'m=audio' in offer['sdp']}")
        logger.info(f"Offer contains video: {'m=video' in offer['sdp']}")
        
        # Log audio codecs in offer
        audio_lines = [line for line in offer["sdp"].split('\n') if 'audio' in line or 'a=rtpmap' in line]
        logger.info(f"Audio-related SDP lines: {audio_lines[:5]}")  # First 5 lines
        
        offer_desc = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        await self.pc.setRemoteDescription(offer_desc)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        
        logger.info(f"Generated SDP answer for session {self.session_id}")
        logger.info(f"Answer contains audio: {'m=audio' in self.pc.localDescription.sdp}")
        
        return {
            "sdp": self.pc.localDescription.sdp,
            "type": self.pc.localDescription.type,
        }

    async def stop(self):
        # Prevent duplicate stops
        if self.__stopped:
            logger.info(f"Session {self.session_id} already stopped, skipping.")
            return
        
        self.__stopped = True

        # Remove from sessions dictionary first to prevent race conditions
        if self.session_id in sessions:
            del sessions[self.session_id]

        tasks = []
        if self.recorder and (self.__recorder_started or hasattr(self, '_recorder_started')):
            logger.info(f"Stopping media recorder for session {self.session_id}...")
            tasks.append(self.recorder.stop())

        if self.compositor:
            tasks.append(self.compositor.stop())

        logger.info(f"Closing peer connection for session {self.session_id}...")
        tasks.append(self.pc.close())

        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Save the recorded video to database after recording is stopped
        try:
            # Check if the file exists before saving to database
            if os.path.exists(self.file_path):
                filename = os.path.basename(self.file_path)
                logger.info(f"Saving recorded video to database: {filename} for section {self.section_id}")
                
                # Create a Link from the section_id
                section_link = Section.link_from_id(self.section_id)
                
                # Create and save RecordedVideo document
                video_doc = RecordedVideo(
                    filename=filename,
                    section=section_link,
                )
                await video_doc.insert()
                logger.info(f"Successfully saved recorded video {filename} to database.")
            else:
                logger.warning(f"Video file {self.file_path} does not exist, skipping database save.")
        except Exception as e:
            logger.error(f"Error saving recorded video to database: {str(e)}", exc_info=True)
        
        logger.info(
            f"Recording session {self.session_id} stopped and cleaned up."
        )


@router.post("/start-recording")
async def start_recording_endpoint(
    offer: dict = Body(...),
    current_user: User = Depends(authorize([Role.TEACHER])),
):
    try:
        section_id = offer.get("section_id") or offer.get("division_id")  # Support both for backward compatibility
        if not section_id:
            raise HTTPException(
                status_code=400, 
                detail={"code": "ValidationError", "message": "Section ID is required."}
            )

        # Try to fetch section, but don't fail if it doesn't exist
        # The section might not be in the streaming server's database
        section = None
        
        try:
            section = await Section.get(PydanticObjectId(section_id))
        except ValueError as e:
            logger.error(f"Invalid section_id format {section_id}: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail={"code": "ValidationError", "message": f"Invalid section ID format: {str(e)}"}
            )
        except Exception as e:
            logger.warning(f"Section {section_id} not found in database or error fetching: {str(e)}")
            # Don't fail if section doesn't exist - allow recording to proceed
            # The section might not be synced to the streaming server's database
            section = None

        # Authorization: Only teachers with appropriate access can record
        # Teachers with 'all' or 'centre' access can record any section
        # Teachers with 'own' access would need additional logic to determine ownership
        if current_user.role != Role.TEACHER:
            raise HTTPException(
                status_code=403,
                detail={"code": "AuthorizationError", "message": "Only teachers can record classes."}
            )
        
        # If section doesn't exist, log a warning but allow recording
        if not section:
            logger.info(f"Recording allowed for section {section_id} without section validation (section may not exist in streaming server DB)")

        videos_dir = "videos_recorded"
        os.makedirs(videos_dir, exist_ok=True)

        session_id = str(uuid.uuid4())
        file_path = os.path.join(videos_dir, f"{session_id}.mkv")

        logger.info(
            f"Starting new recording session {session_id}. File will be saved to {file_path}"
        )
        try:
            session = RecordingSession(
                session_id, file_path, section_id=PydanticObjectId(section_id)
            )
            sessions[session_id] = session

            answer = await session.start(offer)
            return {"sdp": answer["sdp"], "type": answer["type"], "session_id": session_id}
        except Exception as session_error:
            logger.error(f"Error in RecordingSession.start for session {session_id}: {str(session_error)}", exc_info=True)
            # Clean up session if it was created
            if session_id in sessions:
                try:
                    await sessions[session_id].stop()
                except:
                    pass
                del sessions[session_id]
            raise HTTPException(
                status_code=500,
                detail={"code": "RecordingError", "message": f"Failed to start recording session: {str(session_error)}"}
            )
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any other unhandled exceptions
        logger.error(f"Unhandled error in start_recording_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/stop-recording")
async def stop_recording_endpoint(data: dict = Body(...)):
    session_id = data.get("session_id")
    session = sessions.get(session_id)

    if not session:
        # Session might have already been stopped automatically (e.g., on disconnect)
        logger.warning(f"Recording session {session_id} not found. It may have already been stopped.")
        raise HTTPException(status_code=404, detail="Recording session not found.")

    logger.info(f"Request to stop recording session {session_id}")
    await session.stop()
    # Note: RecordedVideo is now saved in the stop() method

    return {"message": f"Recording session {session_id} stopped."}