import asyncio
import logging
from typing import Dict, Optional, Set
import numpy as np
from fractions import Fraction
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame, VideoFrame
from av.audio.resampler import AudioResampler

logger = logging.getLogger("recording_pipeline")

class CompositingTrack(MediaStreamTrack):
    """
    A video track that composites a main track and a picture-in-picture (PiP) track.
    It can also pass through a single track if only one is provided.
    """
    kind = "video"

    def __init__(self, main_track: Optional[MediaStreamTrack] = None, pip_track: Optional[MediaStreamTrack] = None):
        super().__init__()
        if not main_track:
            raise ValueError("Main track must be provided for compositing.")

        self.main_track = main_track
        self.pip_track = pip_track
        
        # PiP settings
        self.pip_width_ratio = 0.25
        self.padding = 10
        
        self._queue = asyncio.Queue()
        self._consumer_task = asyncio.create_task(self._consume_tracks())
        
        self._last_main_frame: Optional[VideoFrame] = None
        self._last_pip_frame: Optional[VideoFrame] = None

    async def _consume_tracks(self):
        while True:
            try:
                tasks = {
                    "main": asyncio.create_task(self.main_track.recv()),
                }
                if self.pip_track:
                    tasks["pip"] = asyncio.create_task(self.pip_track.recv())

                done, pending = await asyncio.wait(
                    tasks.values(), return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel any pending tasks to keep frames synchronized
                for task in pending:
                    task.cancel()

                if tasks.get("main") in done:
                    self._last_main_frame = await tasks["main"]
                if tasks.get("pip") in done:
                    self._last_pip_frame = await tasks["pip"]

                if self._last_main_frame:
                    if self.pip_track and self._last_pip_frame:
                        # Both tracks are available, composite them
                        composited_frame = self._composite_frames(self._last_main_frame, self._last_pip_frame)
                        await self._queue.put(composited_frame)
                    else:
                        # Only main track is available, pass it through
                        yuv_frame = self._last_main_frame.reformat(format="yuv420p")
                        await self._queue.put(yuv_frame)
                        
            except (asyncio.CancelledError, MediaStreamError):
                return
            except Exception as e:
                logger.error(f"Error in video consumer: {e}")
                return

    def _composite_frames(self, main_frame: VideoFrame, pip_frame: VideoFrame) -> VideoFrame:
        main_yuv = main_frame.to_ndarray(format="yuv420p")
        main_height, main_width = main_yuv.shape[0] * 2 // 3, main_yuv.shape[1]

        # Calculate PiP dimensions
        target_pip_width = int(main_width * self.pip_width_ratio)
        if target_pip_width % 2 != 0:
             target_pip_width += 1 # Ensure even width for yuv420p

        # Preserve aspect ratio for PiP height
        pip_aspect_ratio = pip_frame.width / pip_frame.height
        target_pip_height = int(target_pip_width / pip_aspect_ratio)
        if target_pip_height % 2 != 0:
             target_pip_height += 1 # Ensure even height

        pip_resized_frame = pip_frame.reformat(
            width=target_pip_width,
            height=target_pip_height,
            format="yuv420p",
        )
        pip_yuv = pip_resized_frame.to_ndarray()

        # Calculate offsets
        x_offset = main_width - target_pip_width - self.padding
        y_offset = main_height - target_pip_height - self.padding
        
        # Simple overlay (for yuv420p, this requires careful plane manipulation)
        # For simplicity and correctness, we convert to RGBA for compositing
        main_rgba = main_frame.to_ndarray(format="rgba")
        pip_rgba = pip_frame.reformat(width=target_pip_width, height=target_pip_height, format="rgba").to_ndarray()

        main_rgba[
            y_offset : y_offset + target_pip_height,
            x_offset : x_offset + target_pip_width,
        ] = pip_rgba

        final_frame_rgba = VideoFrame.from_ndarray(main_rgba, format="rgba")
        final_frame_yuv = final_frame_rgba.reformat(format="yuv420p")

        final_frame_yuv.pts = main_frame.pts
        final_frame_yuv.time_base = main_frame.time_base
        
        return final_frame_yuv

    async def recv(self):
        return await self._queue.get()

    async def stop(self):
        if self._consumer_task:
            self._consumer_task.cancel()
            await self._consumer_task
            self._consumer_task = None

class AudioMixerTrack(MediaStreamTrack):
    """
    An audio track that mixes audio from multiple source tracks using a
    self-driving pacemaker model within the recv() method.
    """
    kind = "audio"

    # Audio properties
    SAMPLES_PER_FRAME = 960
    SAMPLE_RATE = 48000
    TIME_BASE = Fraction(1, SAMPLE_RATE)
    FRAME_DURATION = SAMPLES_PER_FRAME / SAMPLE_RATE  # 0.02 seconds

    def __init__(self, tracks: Set[MediaStreamTrack]):
        super().__init__()
        self.tracks = set(tracks)
        self._resamplers: Dict[MediaStreamTrack, AudioResampler] = {}
        self._next_pts = 0

    async def recv(self) -> AudioFrame:
        # This recv method IS the pacemaker. It will block for FRAME_DURATION.
        start_time = asyncio.get_event_loop().time()

        # 1. Check track states before attempting to receive
        live_tracks = []
        for track in self.tracks:
            if hasattr(track, 'readyState'):
                logger.info(f"Audio track readyState: {track.readyState}")
                if track.readyState == "live":
                    live_tracks.append(track)
                else:
                    logger.warning(f"Audio track not live: readyState={track.readyState}")
            else:
                # Assume track is live if readyState not available
                live_tracks.append(track)
        
        if not live_tracks:
            logger.warning(f"No live audio tracks available out of {len(self.tracks)} total tracks")
            # Generate silence and return early
            final_frame_s16 = np.zeros((2, self.SAMPLES_PER_FRAME), dtype=np.int16)
            output_frame = AudioFrame.from_ndarray(final_frame_s16, format="s16", layout="stereo")
            output_frame.pts = self._next_pts
            output_frame.sample_rate = self.SAMPLE_RATE
            output_frame.time_base = self.TIME_BASE
            self._next_pts += self.SAMPLES_PER_FRAME
            elapsed = asyncio.get_event_loop().time() - start_time
            await asyncio.sleep(max(0, self.FRAME_DURATION - elapsed))
            return output_frame

        # 2. Fetch frames from live tracks only
        logger.info(f"Attempting to receive frames from {len(live_tracks)} live audio tracks")
        tasks = {
            asyncio.create_task(track.recv()): track for track in live_tracks
        }
        
        # Wait for frames with a longer timeout for debugging
        done, pending = await asyncio.wait(
            tasks.keys(),
            timeout=self.FRAME_DURATION * 3,  # Increase timeout to 60ms
            return_when=asyncio.FIRST_COMPLETED  # Return as soon as any task completes
        )

        logger.info(f"Audio frame reception: {len(done)} completed, {len(pending)} pending/timeout")
        
        for task in pending:
            task.cancel()

        # 3. Collect and mix the frames that arrived
        mixed_frame_i32: Optional[np.ndarray] = None
        contributors = 0
        ended_tracks = set()

        for task in done:
            track = tasks[task]
            try:
                frame = task.result()
                logger.info(f"Successfully received audio frame: samples={frame.samples}, rate={frame.sample_rate}, format={frame.format}, layout={frame.layout}")
                
                # Try to handle different audio formats more flexibly
                try:
                    resampler = self._resamplers.setdefault(
                        track, AudioResampler(format="s16", layout="stereo", rate=self.SAMPLE_RATE)
                    )
                    resampled_frames = resampler.resample(frame)
                except Exception as resample_error:
                    logger.error(f"Resampling failed: {resample_error}. Trying different format...")
                    # Try with original format first, then convert
                    try:
                        resampler = self._resamplers.setdefault(
                            track, AudioResampler(format=frame.format, layout=frame.layout, rate=self.SAMPLE_RATE)
                        )
                        resampled_frames = resampler.resample(frame)
                    except Exception as fallback_error:
                        logger.error(f"Fallback resampling also failed: {fallback_error}")
                        continue

                for resampled_frame in resampled_frames:
                    frame_data_i32 = resampled_frame.to_ndarray().astype(np.int32)
                    if mixed_frame_i32 is None:
                        mixed_frame_i32 = frame_data_i32
                    else:
                        min_len = min(mixed_frame_i32.shape[1], frame_data_i32.shape[1])
                        mixed_frame_i32 = mixed_frame_i32[:, :min_len] + frame_data_i32[:, :min_len]
                contributors += 1

            except (MediaStreamError, asyncio.CancelledError) as e:
                logger.warning(f"Audio track ended or cancelled: {e}")
                ended_tracks.add(track)
            except Exception as e:
                logger.error(f"Error processing audio frame: {e}")
                ended_tracks.add(track)

        # Clean up any tracks that have ended
        for track in ended_tracks:
            self.tracks.discard(track)
            self._resamplers.pop(track, None)

        # 4. Create the final output frame (or silence)
        if mixed_frame_i32 is None or contributors == 0:
            # Generate silence if no audio was received
            final_frame_s16 = np.zeros((2, self.SAMPLES_PER_FRAME), dtype=np.int16)
            if len(live_tracks) > 0:
                logger.warning(f"Generating silence despite having {len(live_tracks)} live audio tracks available")
        else:
            # Average the signal to prevent clipping
            if contributors > 1:
                mixed_frame_i32 //= contributors
            # Clip to 16-bit range
            final_frame_s16 = np.clip(mixed_frame_i32, -32768, 32767).astype(np.int16)
            logger.info(f"Successfully mixed audio from {contributors} contributors")

        output_frame = AudioFrame.from_ndarray(final_frame_s16, format="s16", layout="stereo")

        # 5. Set a reliable timestamp and enforce the pacemaker rhythm
        output_frame.pts = self._next_pts
        output_frame.sample_rate = self.SAMPLE_RATE
        output_frame.time_base = self.TIME_BASE
        self._next_pts += self.SAMPLES_PER_FRAME

        elapsed = asyncio.get_event_loop().time() - start_time
        await asyncio.sleep(max(0, self.FRAME_DURATION - elapsed))
        
        return output_frame

    async def stop(self):
        # The new design doesn't have persistent tasks, so stop is simpler.
        self.tracks.clear()
        self._resamplers.clear()