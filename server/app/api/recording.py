from fastapi import APIRouter, Body, HTTPException, Depends
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, MediaStreamError
from aiortc.contrib.media import MediaRecorder
from ..api.compositing import AudioMixerTrack
import uuid
import os
import asyncio
import logging
from typing import Dict, Optional, Set, cast
from beanie import PydanticObjectId
import av
from av import AudioFrame, VideoFrame

from app.db_models.user import User
from app.db_models.academic import Section
from app.db_models.core import Role
from app.db_models.recording import RecordedVideo
from app.core.auth import authorize

router = APIRouter()
logger = logging.getLogger("recording_pipeline")
logging.basicConfig(level=logging.INFO)

sessions: Dict[str, "RecordingSession"] = {}


class WebMMediaRecorder:
    """
    Custom MediaRecorder for WebM format with proper codecs:
    - Video: VP8 (libvpx) - High quality, reliable codec
    - Audio: Opus (libopus) - High quality audio
    """
    
    class MediaRecorderContext:
        def __init__(self, stream):
            self.stream = stream
            self.task: Optional[asyncio.Task] = None
            self.started = False
    
    def __init__(self, file_path: str, options: Optional[dict] = None):
        self.file_path = file_path
        self.options = options or {}
        
        # Open WebM container with only format options
        # Filter out codec options that might confuse the container muxer
        container_options = {k: v for k, v in self.options.items() 
                           if k not in ["crf", "b:v", "maxrate", "bufsize", "b:a", "threads", "deadline", "cpu-used"]}
        
        self.__container = av.open(
            file=file_path,
            format="webm",
            mode="w",
            options=container_options
        )
        self.__tracks: Dict[MediaStreamTrack, WebMMediaRecorder.MediaRecorderContext] = {}
    
    def addTrack(self, track: MediaStreamTrack) -> None:
        """Add a track to be recorded with WebM-appropriate codecs."""
        if track.kind == "audio":
            # Use Opus codec for WebM audio - high quality
            codec_name = "libopus"
            stream = cast(av.AudioStream, self.__container.add_stream(codec_name))
            # Apply audio options
            if "b:a" in self.options:
                stream.options = {"b": self.options["b:a"]}
        else:
            # Use VP8 codec for WebM video
            codec_name = "libvpx"
            stream = cast(av.VideoStream, self.__container.add_stream(codec_name, rate=30))
            stream.pix_fmt = "yuv420p"
            # Apply video options
            video_opts = {}
            if "crf" in self.options: video_opts["crf"] = self.options["crf"]
            if "b:v" in self.options: video_opts["b"] = self.options["b:v"]
            if "maxrate" in self.options: video_opts["maxrate"] = self.options["maxrate"]
            if "bufsize" in self.options: video_opts["bufsize"] = self.options["bufsize"]
            if "threads" in self.options: video_opts["threads"] = self.options["threads"]
            if "deadline" in self.options: video_opts["deadline"] = self.options["deadline"]
            
            stream.options = video_opts
        
        self.__tracks[track] = self.MediaRecorderContext(stream)
        logger.info(f"Added {track.kind} track to WebM recorder with codec: {codec_name}")
    
    async def start(self) -> None:
        """Start recording."""
        for track, context in self.__tracks.items():
            if context.task is None:
                context.task = asyncio.ensure_future(self.__run_track(track, context))
        logger.info("WebM MediaRecorder started")
    
    async def stop(self) -> None:
        """Stop recording and finalize file."""
        if self.__container is None:
            logger.warning("WebM MediaRecorder container is already closed")
            return
            
        logger.info("Stopping WebM MediaRecorder and finalizing file...")
        
        # First, signal tracks to stop by canceling their tasks
        # But wait a bit for any in-flight frames to complete
        for track, context in list(self.__tracks.items()):
            if context.task is not None and not context.task.done():
                # Give tasks a moment to finish current frame processing
                await asyncio.sleep(0.1)
                context.task.cancel()
                try:
                    # Wait for task to finish cancellation
                    await asyncio.wait_for(context.task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                context.task = None
        
        # Now flush all remaining frames from each stream
        logger.info("Flushing remaining frames from all streams...")
        for track, context in list(self.__tracks.items()):
            try:
                # Flush encoder - encode(None) flushes all buffered frames
                flush_count = 0
                for packet in context.stream.encode(None):
                    self.__container.mux(packet)
                    flush_count += 1
                if flush_count > 0:
                    logger.info(f"Flushed {flush_count} packets from {track.kind} stream")
            except Exception as e:
                logger.error(f"Error flushing {track.kind} stream: {e}", exc_info=True)
        
        # Clear tracks
        self.__tracks = {}
        
        # Close container - this finalizes the file
        try:
            self.__container.close()
            logger.info(f"WebM MediaRecorder container closed. File should be saved to: {self.file_path}")
        except Exception as e:
            logger.error(f"Error closing container: {e}", exc_info=True)
        finally:
            self.__container = None
    
    async def __run_track(
        self, track: MediaStreamTrack, context: "WebMMediaRecorder.MediaRecorderContext"
    ) -> None:
        """Process frames from track and encode them."""
        try:
            while True:
                try:
                    frame = await track.recv()
                except MediaStreamError:
                    logger.info(f"Track {track.kind} ended")
                    return
                
                if not isinstance(frame, (AudioFrame, VideoFrame)):
                    logger.warning(f"Unexpected frame type: {type(frame)}")
                    continue
                
                if not context.started:
                    # Set output dimensions for video
                    if isinstance(context.stream, av.VideoStream) and isinstance(frame, VideoFrame):
                        context.stream.width = frame.width
                        context.stream.height = frame.height
                    context.started = True
                    logger.info(f"Started encoding {track.kind} track: {frame.width if isinstance(frame, VideoFrame) else 'audio'}x{frame.height if isinstance(frame, VideoFrame) else 'N/A'}")
                
                # Encode and mux frames
                try:
                    packets = context.stream.encode(frame)
                    for packet in packets:
                        try:
                            self.__container.mux(packet)
                        except Exception as mux_error:
                            logger.error(f"Error muxing {track.kind} packet: {mux_error}", exc_info=True)
                            # Continue processing other packets even if one fails
                except Exception as e:
                    logger.error(f"Error encoding {track.kind} frame: {e}", exc_info=True)
                    # Continue processing - don't stop on single frame error
        except Exception as e:
            logger.error(f"Error in track processing: {e}", exc_info=True)


class RecordingSession:
    def __init__(self, session_id: str, file_path: str, section_id: PydanticObjectId):
        self.session_id = session_id
        self.pc = RTCPeerConnection()
        self.recorder = None
        self.file_path = file_path
        self.section_id = section_id
        self.video_tracks: Dict[str, MediaStreamTrack] = {}
        self.audio_tracks: Set[MediaStreamTrack] = set()
        # self.compositor removed to reduce processing latency
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
                    # Use track directly without resizing to reduce latency
                    self.video_tracks["main"] = track
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

        # Use video track directly without compositing to reduce latency
        video_track = self.video_tracks.get("main")
        
        # Initialize audio mixer with existing tracks (could be empty initially)
        self.audio_mixer = AudioMixerTrack(tracks=self.audio_tracks.copy())

        # WebM encoding options for high quality VP8/Opus
        # VP8 quality: CRF 4-63 (lower = better, 10-20 is high quality range)
        # Using VP8 instead of VP9 for better reliability and compatibility
        options = {
            "crf": "30",  # Changed from 10 to 30 for smoother performance
            "b:v": "2500k",  # Changed from 8M to 2.5M (standard for 720p)
            "maxrate": "3000k",  # Cap spikes at 3M
            "bufsize": "6000k",  # Buffer 2x maxrate
            "b:a": "128k",  # 128k is sufficient for Opus voice
            "threads": "4",  # Use 4 threads explicitly
            "deadline": "realtime",  # VP8 encoding quality (good/best/realtime) - realtime reduces latency
            "cpu-used": "4", # Higher value = faster encoding (0-16 for VP8)
        }
        self.recorder = WebMMediaRecorder(self.file_path, options=options)

        self.recorder.addTrack(video_track)
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

        # Execute stop tasks sequentially to ensure proper order
        # Stop recorder first, then compositor, then close connection
        if self.recorder and (self.__recorder_started or hasattr(self, '_recorder_started')):
            logger.info(f"Stopping media recorder for session {self.session_id}...")
            try:
                await self.recorder.stop()
                logger.info(f"Recorder stopped for session {self.session_id}")
            except Exception as e:
                logger.error(f"Error stopping recorder: {e}", exc_info=True)
        
        # Compositor removed
        
        try:
            await self.pc.close()
            logger.info(f"Peer connection closed for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error closing peer connection: {e}", exc_info=True)
        
        # Wait longer for file to be fully written and flushed to disk
        await asyncio.sleep(1.0)
        
        # Save the recorded video to database after recording is stopped
        try:
            # Check if the file exists and has content before saving to database
            if os.path.exists(self.file_path):
                file_size = os.path.getsize(self.file_path)
                if file_size > 0:
                    filename = os.path.basename(self.file_path)
                    logger.info(f"Saving recorded video to database: {filename} (size: {file_size} bytes) for section {self.section_id}")
                    
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
                    logger.warning(f"Video file {self.file_path} exists but is empty (0 bytes), skipping database save.")
            else:
                logger.error(f"Video file {self.file_path} does not exist after recording stopped. Recording may have failed.")
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

        # Get videos directory path (same logic as in main.py and videos.py)
        # Try project root first (same level as server folder)
        # From server/app/api/recording.py: go up 3 levels to get to server/, then 1 more to project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Goes to server/
        project_root = os.path.dirname(base_dir)  # Goes up to project root
        videos_dir = os.path.join(project_root, "videos_recorded")
        
        # Fallback: check current working directory
        if not os.path.exists(videos_dir):
            videos_dir_cwd = os.path.join(os.getcwd(), "videos_recorded")
            if os.path.exists(videos_dir_cwd):
                videos_dir = videos_dir_cwd
            else:
                # Use project root path and create it
                videos_dir = os.path.join(project_root, "videos_recorded")
        
        os.makedirs(videos_dir, exist_ok=True)

        session_id = str(uuid.uuid4())
        file_path = os.path.join(videos_dir, f"{session_id}.webm")

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