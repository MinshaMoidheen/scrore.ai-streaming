from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.meeting_manager import manager
import uuid

router = APIRouter()

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    participant_id = str(uuid.uuid4())
    await manager.handle_connect(room_id, participant_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_message(room_id, participant_id, data)
    except WebSocketDisconnect:
        await manager.handle_disconnect(room_id, participant_id)
