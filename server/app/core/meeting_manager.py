from fastapi import WebSocket
from typing import Dict, Optional, Literal
import json

ParticipantType = Literal["teacher", "student"]


class Room:
    def __init__(self, host_id: Optional[str] = None):
        self.host_id = host_id  # Only teachers can be hosts
        self.participants: Dict[str, WebSocket] = {}
        self.participant_types: Dict[str, ParticipantType] = {}  # Track participant types
        self.participant_usernames: Dict[str, str] = {}  # Track participant usernames

    async def add_participant(
        self, participant_id: str, websocket: WebSocket, participant_type: ParticipantType, username: str
    ):
        self.participants[participant_id] = websocket
        self.participant_types[participant_id] = participant_type
        self.participant_usernames[participant_id] = username
        
        # If this is the first teacher and no host is set, make them the host
        if participant_type == "teacher" and self.host_id is None:
            self.host_id = participant_id
        
        await self.broadcast(json.dumps({
            "type": "new_participant",
            "participant_id": participant_id,
            "participant_type": participant_type,
            "username": username,
            "is_host": participant_id == self.host_id
        }), exclude_id=participant_id)

    async def remove_participant(self, participant_id: str):
        if participant_id in self.participants:
            was_host = participant_id == self.host_id
            participant_type = self.participant_types.get(participant_id)
            username = self.participant_usernames.get(participant_id)
            del self.participants[participant_id]
            if participant_id in self.participant_types:
                del self.participant_types[participant_id]
            if participant_id in self.participant_usernames:
                del self.participant_usernames[participant_id]
            
            # If the host left, assign a new host from remaining teachers
            if was_host and self.host_id == participant_id:
                # Find first teacher participant to be the new host
                new_host = None
                for pid, ptype in self.participant_types.items():
                    if ptype == "teacher":
                        new_host = pid
                        break
                self.host_id = new_host
                
                # Notify new host if one was assigned
                if new_host and new_host in self.participants:
                    await self.participants[new_host].send_text(json.dumps({
                        "type": "host_assigned",
                        "participant_id": new_host
                    }))
            
            await self.broadcast(json.dumps({
                "type": "participant_left",
                "participant_id": participant_id,
                "participant_type": participant_type,
                "username": username,
                "was_host": was_host
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

    def get_or_create_room(self, room_id: str, host_id: Optional[str] = None) -> Room:
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(host_id=host_id)
        return self.rooms[room_id]

    async def handle_connect(
        self,
        room_id: str,
        participant_id: str,
        username: str,
        websocket: WebSocket,
        participant_type: ParticipantType,
    ):
        """
        Handle a new participant connecting to a room.
        
        Args:
            room_id: The room identifier
            participant_id: Unique identifier for the participant
            username: Username of the participant
            websocket: WebSocket connection (must be already accepted)
            participant_type: "teacher" or "student"
        """
        room = self.get_or_create_room(room_id)
        # Note: websocket.accept() is called in the endpoint before this method

        # Assign the participant their ID and type
        is_host = participant_type == "teacher" and (
            room.host_id is None or room.host_id == participant_id
        )
        await websocket.send_text(json.dumps({
            "type": "assign_id",
            "id": participant_id,
            "participant_type": participant_type,
            "username": username,
            "is_host": is_host
        }))

        await room.add_participant(participant_id, websocket, participant_type, username)

        # Send list of existing participants to the new participant
        # Exclude the newly joined participant from the list
        # Send both participant_ids (for client compatibility) and participants (for future use)
        participant_ids = [
            pid for pid in room.participants.keys() 
            if pid != participant_id
        ]
        existing_participants = [
            {
                "id": pid,
                "type": room.participant_types.get(pid, "unknown"),
                "username": room.participant_usernames.get(pid, ""),
                "is_host": pid == room.host_id
            }
            for pid in participant_ids
        ]
        await websocket.send_text(json.dumps({
            "type": "existing_participants",
            "participant_ids": participant_ids,  # Client expects this format
            "participants": existing_participants  # Additional info for future use
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
