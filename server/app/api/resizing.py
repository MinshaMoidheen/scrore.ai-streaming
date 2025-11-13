import asyncio
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame

class AspectRatioPreservingTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, track, target_width=1280, target_height=720):
        super().__init__()
        self.track = track
        self.target_width = target_width
        self.target_height = target_height

    async def recv(self):
        try:
            frame = await self.track.recv()
        except MediaStreamError:
            self.stop()
            raise
        
        # For simplicity, we'll just resize to a fixed resolution.
        # A more advanced implementation would handle aspect ratio.
        new_frame = frame.reformat(
            width=self.target_width,
            height=self.target_height,
        )
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame