from fastapi import WebSocket
from typing import Dict
import json

class Room:
    def __init__(self, host_id: str):
        self.host_id = host_id
        self.participants: Dict[str, WebSocket] = {}

    async def add_participant(self, participant_id: str, websocket: WebSocket):
        self.participants[participant_id] = websocket
        await self.broadcast(json.dumps({
            "type": "new_participant",
            "participant_id": participant_id
        }), exclude_id=participant_id)

    async def remove_participant(self, participant_id: str):
        if participant_id in self.participants:
            del self.participants[participant_id]
            await self.broadcast(json.dumps({
                "type": "participant_left",
                "participant_id": participant_id
            }))

    async def broadcast(self, message: str, exclude_id: str = None):
        # Create a list of websockets to send to, to avoid issues with modification during iteration
        websockets_to_send = [
            ws for pid, ws in self.participants.items() if pid != exclude_id
        ]
        for websocket in websockets_to_send:
            try:
                await websocket.send_text(message)
            except Exception:
                # A client might have disconnected. They will be cleaned up by the disconnect handler.
                pass

class MeetingManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def get_or_create_room(self, room_id: str, host_id: str) -> Room:
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(host_id)
        return self.rooms[room_id]

    async def handle_connect(self, room_id: str, participant_id: str, websocket: WebSocket):
        room = self.get_or_create_room(room_id, host_id=participant_id)
        await websocket.accept()

        # Assign the participant their ID
        await websocket.send_text(json.dumps({
            "type": "assign_id",
            "id": participant_id
        }))

        await room.add_participant(participant_id, websocket)

        # Send list of existing participants to the new participant
        existing_participants = list(room.participants.keys())
        await websocket.send_text(json.dumps({
            "type": "existing_participants",
            "participant_ids": existing_participants
        }))

    async def handle_disconnect(self, room_id: str, participant_id: str):
        if room_id in self.rooms:
            room = self.rooms[room_id]
            await room.remove_participant(participant_id)
            if not room.participants:
                del self.rooms[room_id]

    async def handle_message(self, room_id: str, sender_id: str, message: str):
        if room_id in self.rooms:
            room = self.rooms[room_id]
            parsed_message = json.loads(message)
            target_id = parsed_message.get("target_id")
            if target_id and target_id in room.participants:
                parsed_message["sender_id"] = sender_id
                await room.participants[target_id].send_text(json.dumps(parsed_message))
            else:
                # Broadcast to all if no target
                await room.broadcast(message, exclude_id=sender_id)

manager = MeetingManager()
