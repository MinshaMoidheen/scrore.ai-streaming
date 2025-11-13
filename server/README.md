# Score.AI Streaming Server

A comprehensive real-time video streaming and recording platform for educational meetings, built with FastAPI, WebRTC, and MongoDB.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Running the Application](#running-the-application)
- [Environment Variables](#environment-variables)
- [Architecture Overview](#architecture-overview)
- [API Endpoints](#api-endpoints)
  - [Health Check](#health-check)
  - [Authentication](#authentication)
  - [Meetings](#meetings)
  - [Videos](#videos)
  - [Recording](#recording)
  - [WebSocket](#websocket)
- [Streaming Features](#streaming-features)
- [Recording Features](#recording-features)
- [Database Models](#database-models)
- [User Roles & Permissions](#user-roles--permissions)
- [WebRTC Integration](#webrtc-integration)

## Features

### Core Features

1. **Real-time Video Recording**
   - WebRTC-based screen capture and recording
   - Support for multiple audio tracks with automatic mixing
   - Video compositing with Picture-in-Picture (PiP) support
   - Aspect ratio preservation for video tracks
   - High-quality recording with configurable encoding options

2. **Video Streaming**
   - HTTP Range request support for video seeking
   - Efficient streaming of recorded videos
   - Support for MKV video format
   - Chunked transfer encoding for large files

3. **Meeting Management**
   - Live meeting status tracking
   - Division-based meeting rooms
   - Meeting link management
   - Real-time participant tracking

4. **WebSocket Communication**
   - Real-time bidirectional communication
   - Room-based messaging
   - Participant join/leave notifications
   - Peer-to-peer message routing

5. **Authentication & Authorization**
   - JWT-based authentication
   - Access token and refresh token support
   - Role-based access control (RBAC)
   - Secure token management

6. **Video Library Management**
   - List recorded videos by division
   - Date-based filtering
   - Pagination support
   - Access control per division

## Prerequisites

- Python 3.9 or higher
- MongoDB instance (local or remote)
- FFmpeg (for video processing, typically installed with aiortc dependencies)

## Setup

1. **Clone the repository**
2. **Navigate to the `server` directory:**
    ```bash
    cd server
    ```
3. **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    ```
4. **Activate the virtual environment:**
    - On Windows:
      ```bash
      .\venv\Scripts\activate
      ```
    - On macOS/Linux:
      ```bash
      source venv/bin/activate
      ```
5. **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
6. **Create a `.env` file** in the `server/app` directory (see [Environment Variables](#environment-variables))

## Running the Application

To run the server, execute the following command from the `server` directory:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The server will be available at `http://localhost:8000`. API documentation will be available at `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc).

## Environment Variables

The application requires a `.env` file located in `server/app`. This file should contain the following variables:

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `MONGO_URI` | string | Yes | MongoDB connection string (e.g., `mongodb://localhost:27017/` or `mongodb+srv://...`) |
| `JWT_SECRET` | string | Yes | Secret key for encoding/decoding JWT access tokens |
| `JWT_REFRESH_SECRET` | string | Yes | Secret key for encoding/decoding JWT refresh tokens |
| `ENV` | string | No | Environment mode (`development` or `production`). Defaults to `development` |
| `database` | string | No | MongoDB database name. Defaults to `score-ai` |

Example `.env` file:

```env
MONGO_URI="mongodb://localhost:27017/"
JWT_SECRET="your-super-secret-access-token-key"
JWT_REFRESH_SECRET="your-super-secret-refresh-token-key"
ENV="development"
database="score-ai"
```

## Architecture Overview

The application is built with:
- **FastAPI**: Modern Python web framework for building APIs
- **aiortc**: WebRTC implementation for Python
- **Beanie**: MongoDB ODM built on top of Motor and Pydantic
- **PyAV**: Audio/video processing library
- **NumPy**: Numerical operations for audio mixing

### Key Components

- **Media Processing**: `CompositingTrack` for video compositing, `AudioMixerTrack` for audio mixing
- **Recording Pipeline**: `RecordingSession` manages WebRTC connections and media recording
- **Meeting Manager**: Handles WebSocket connections and room management
- **Authentication**: JWT-based auth with role-based authorization

## API Endpoints

All endpoints are relative to the base URL (e.g., `http://localhost:8000`).

### Health Check

#### GET `/api/health`

Checks the health status of the server.

**Authentication:** Not required

**Request:**
- Method: `GET`
- Path: `/api/health`

**Response:**
    ```json
    {
      "status": "ok"
    }
    ```

**Status Codes:**
- `200 OK`: Server is healthy

---

### Authentication

#### POST `/api/auth/token/refresh`

Refreshes an access token using a refresh token stored in cookies.

**Authentication:** Requires refresh token cookie

**Request:**
- Method: `POST`
- Path: `/api/auth/token/refresh`
- Cookies:
  - `refreshToken` (string, required): JWT refresh token

**Response:**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Status Codes:**
- `200 OK`: Token refreshed successfully
- `401 Unauthorized`: Invalid or expired refresh token

**Error Response:**
```json
{
  "detail": {
    "code": "AuthenticationError",
    "message": "Invalid refresh token"
  }
}
```

---

### Meetings

#### PUT `/api/meetings/{division_id}/status`

Sets the meeting status (live or not) for a specific division. Only the assigned teacher can change the status.

**Authentication:** Required (Teacher role)

**Request:**
- Method: `PUT`
- Path: `/api/meetings/{division_id}/status`
- Headers:
  - `Authorization: Bearer <access_token>` (required)
- Path Parameters:
  - `division_id` (ObjectId, required): MongoDB ObjectId of the division
- Body:
    ```json
    {
      "is_live": true
    }
    ```
  - `is_live` (boolean, required): Meeting status

**Response:**
```json
{
  "message": "Meeting status for division Class 10-A updated to true"
}
```

**Status Codes:**
- `200 OK`: Status updated successfully
- `403 Forbidden`: User is not authorized to change this meeting's status
- `404 Not Found`: Division not found

---

#### GET `/api/meetings/{division_id}/status`

Gets the meeting status for a division. Only students enrolled in the division can view the status.

**Authentication:** Required (All roles)

**Request:**
- Method: `GET`
- Path: `/api/meetings/{division_id}/status`
- Headers:
  - `Authorization: Bearer <access_token>` (required)
- Path Parameters:
  - `division_id` (ObjectId, required): MongoDB ObjectId of the division

**Response:**
    ```json
    {
      "is_live": true,
      "meeting_link": "http://example.com/meet"
    }
    ```

**Response Fields:**
- `is_live` (boolean): Whether the meeting is currently live
- `meeting_link` (string, nullable): URL link to join the meeting

**Status Codes:**
- `200 OK`: Status retrieved successfully
- `403 Forbidden`: User is not authorized to view this meeting's status
- `404 Not Found`: Division not found

---

### Videos

#### GET `/api/videos/{division_id}`

Lists recorded videos for a specific division with date filtering and pagination.

**Authentication:** Required (All roles)

**Request:**
- Method: `GET`
- Path: `/api/videos/{division_id}`
- Headers:
  - `Authorization: Bearer <access_token>` (required)
- Path Parameters:
  - `division_id` (ObjectId, required): MongoDB ObjectId of the division
- Query Parameters:
  - `date` (datetime, optional): Filter videos by date (format: `YYYY-MM-DD` or ISO 8601)
  - `page` (integer, optional, default: 1): Page number for pagination (minimum: 1)
  - `page_size` (integer, optional, default: 10): Number of videos per page (minimum: 1, maximum: 100)

**Example Request:**
```
GET /api/videos/507f1f77bcf86cd799439011?date=2024-01-15&page=1&page_size=20
```

**Response:**
```json
[
  {
    "id": "507f1f77bcf86cd799439011",
    "filename": "35f93150-5f2c-4260-8f7c-260ca8489ee7.mkv",
    "division": {
      "id": "507f1f77bcf86cd799439012",
      "name": "Class 10-A"
    },
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

**Response Fields:**
- `id` (ObjectId): Unique identifier for the video
- `filename` (string): Name of the video file
- `division` (object): Division information
- `created_at` (datetime): Timestamp when the video was recorded

**Status Codes:**
- `200 OK`: Videos retrieved successfully
- `403 Forbidden`: User is not authorized to view recordings for this division
- `404 Not Found`: Division not found

---

#### GET `/api/videos/stream/{video_id}`

Streams a recorded video file. Supports HTTP Range requests for video seeking, enabling users to jump to different parts of the video.

**Authentication:** Required (All roles)

**Request:**
- Method: `GET`
- Path: `/api/videos/stream/{video_id}`
- Headers:
  - `Authorization: Bearer <access_token>` (required)
  - `Range` (string, optional): HTTP Range header for partial content requests (e.g., `bytes=0-1023`)
- Path Parameters:
  - `video_id` (ObjectId, required): MongoDB ObjectId of the video

**Example Request:**
```
GET /api/videos/stream/507f1f77bcf86cd799439011
Range: bytes=0-1048575
```

**Response Headers:**
- `Content-Type: video/mkv`
- `Content-Length: <file_size>` (for full requests)
- `Content-Range: bytes <start>-<end>/<total>` (for partial requests)
- `Accept-Ranges: bytes`

**Response:**
- Streaming video data (binary)

**Status Codes:**
- `200 OK`: Full video stream
- `206 Partial Content`: Partial video stream (Range request)
- `403 Forbidden`: User is not authorized to view this recording
- `404 Not Found`: Video not found or video file not found on disk

**Usage Example (HTML):**
```html
<video controls>
  <source
    src="http://localhost:8000/api/videos/stream/507f1f77bcf86cd799439011"
    type="video/mkv"
  />
</video>
```

---

### Recording

#### POST `/start-recording`

Initiates a WebRTC recording session. The client sends an SDP offer, and the server responds with an SDP answer. This endpoint creates a new recording session and establishes a WebRTC peer connection.

**Authentication:** Required (Teacher role)

**Request:**
- Method: `POST`
- Path: `/start-recording`
- Headers:
  - `Authorization: Bearer <access_token>` (required)
  - `Content-Type: application/json`
- Body:
    ```json
    {
    "sdp": "v=0\r\no=- 1234567890 1234567890 IN IP4 127.0.0.1\r\n...",
      "type": "offer",
    "division_id": "507f1f77bcf86cd799439011"
    }
    ```
  - `sdp` (string, required): Session Description Protocol offer from WebRTC peer connection
  - `type` (string, required): Must be `"offer"`
  - `division_id` (string/ObjectId, required): MongoDB ObjectId of the division to record

**Response:**
    ```json
    {
  "sdp": "v=0\r\no=- 9876543210 9876543210 IN IP4 127.0.0.1\r\n...",
      "type": "answer",
  "session_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7"
    }
    ```

**Response Fields:**
- `sdp` (string): Session Description Protocol answer
- `type` (string): Always `"answer"`
- `session_id` (string): UUID of the recording session (use this to stop recording)

**Status Codes:**
- `200 OK`: Recording session started successfully
- `400 Bad Request`: Missing division_id or invalid SDP offer
- `403 Forbidden`: User is not authorized to record this division
- `404 Not Found`: Division not found

**Recording Process:**
1. Server creates a `RecordingSession` with a unique session ID
2. WebRTC peer connection is established
3. Media tracks (video and audio) are received from the client
4. Video is processed through `AspectRatioPreservingTrack` (resized to 1280x720)
5. Audio tracks are mixed using `AudioMixerTrack`
6. Composite video and mixed audio are recorded to an MKV file in `videos_recorded/` directory
7. Recording starts automatically when WebRTC connection is established

**Media Format:**
- Video: Resized to 1280x720, YUV420P format
- Audio: Mixed from multiple tracks, 48kHz sample rate, stereo, S16 format
- Recording: MKV container with H.264 video and AAC audio (CRF 18, ultrafast preset)

---

#### POST `/stop-recording`

Stops the recording session and saves the video metadata to the database.

**Authentication:** Not required (but session_id must be valid)

**Request:**
- Method: `POST`
- Path: `/stop-recording`
- Headers:
  - `Content-Type: application/json`
- Body:
  ```json
  {
    "session_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7"
  }
  ```
  - `session_id` (string, required): UUID of the recording session (returned from `/start-recording`)

**Response:**
    ```json
    {
  "message": "Recording session 35f93150-5f2c-4260-8f7c-260ca8489ee7 stopped."
    }
    ```

**Status Codes:**
- `200 OK`: Recording stopped successfully
- `404 Not Found`: Recording session not found

**Stop Process:**
1. Media recorder stops and finalizes the video file
2. WebRTC peer connection is closed
3. Compositing and audio mixing tracks are stopped
4. A `RecordedVideo` document is created in the database
5. Session is removed from active sessions

---

### WebSocket

#### WS `/ws/{room_id}`

WebSocket endpoint for real-time bidirectional communication within a meeting room. Enables participants to send messages, join/leave notifications, and peer-to-peer communication.

**Authentication:** Not required (but may be implemented in client)

**Request:**
- Protocol: `WebSocket`
- Path: `/ws/{room_id}`
- Path Parameters:
  - `room_id` (string, required): Unique identifier for the meeting room

**Connection Flow:**
1. Client connects to `/ws/{room_id}`
2. Server assigns a unique `participant_id` (UUID)
3. Server sends `assign_id` message with participant ID
4. Server sends `existing_participants` message with list of current participants
5. Server broadcasts `new_participant` to all other participants

**Message Format:**
All messages are JSON strings.

**Outgoing Messages (Server → Client):**

1. **Assign ID:**
   ```json
   {
     "type": "assign_id",
     "id": "35f93150-5f2c-4260-8f7c-260ca8489ee7"
   }
   ```

2. **Existing Participants:**
   ```json
   {
     "type": "existing_participants",
     "participant_ids": ["uuid1", "uuid2", "uuid3"]
   }
   ```

3. **New Participant:**
   ```json
   {
     "type": "new_participant",
     "participant_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7"
   }
   ```

4. **Participant Left:**
   ```json
   {
     "type": "participant_left",
     "participant_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7"
   }
   ```

5. **Broadcast Message:**
   ```json
   {
     "type": "<any_type>",
     "sender_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7",
     "data": { ... }
   }
   ```

**Incoming Messages (Client → Server):**

1. **Targeted Message (Peer-to-Peer):**
   ```json
   {
     "type": "<message_type>",
     "target_id": "35f93150-5f2c-4260-8f7c-260ca8489ee7",
     "data": { ... }
   }
   ```
   - If `target_id` is provided, message is sent only to that participant
   - Server adds `sender_id` before forwarding

2. **Broadcast Message:**
   ```json
   {
     "type": "<message_type>",
     "data": { ... }
   }
   ```
   - If no `target_id` is provided, message is broadcast to all participants except sender

**Example Usage (JavaScript):**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/room-123');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

// Send a broadcast message
ws.send(JSON.stringify({
  type: 'chat',
  data: { text: 'Hello everyone!' }
}));

// Send a targeted message
ws.send(JSON.stringify({
  type: 'private_message',
  target_id: 'recipient-uuid',
  data: { text: 'Hello!' }
}));
```

**Disconnection:**
- When a client disconnects, server broadcasts `participant_left` to all remaining participants
- If room becomes empty, it is removed from memory

---

## Streaming Features

### Video Streaming

The application supports efficient video streaming with the following features:

1. **HTTP Range Requests**
   - Supports partial content requests (HTTP 206)
   - Enables video seeking in HTML5 video players
   - Efficient bandwidth usage by streaming only requested chunks

2. **Chunked Transfer**
   - Streams video in 1MB chunks
   - Prevents memory issues with large files
   - Supports progressive download

3. **Video Format**
   - Container: MKV (Matroska)
   - Video Codec: H.264 (libx264)
   - Audio Codec: AAC
   - Resolution: 1280x720 (configurable)
   - Encoding: CRF 18 (high quality), ultrafast preset

4. **Streaming Endpoint**
   - Endpoint: `GET /api/videos/stream/{video_id}`
   - Supports standard HTML5 video players
   - Automatic range request handling

**Usage Example:**
    ```html
<video controls preload="metadata">
      <source
    src="http://localhost:8000/api/videos/stream/507f1f77bcf86cd799439011"
        type="video/mkv"
      />
  Your browser does not support the video tag.
    </video>
    ```

---

## Recording Features

### WebRTC Recording

The application provides comprehensive WebRTC-based recording capabilities:

1. **Screen Capture Recording**
   - Records screen share from teacher's browser
   - Supports full screen or window capture
   - High-quality video recording

2. **Audio Mixing**
   - Mixes audio from multiple participants
   - Automatic resampling to 48kHz stereo
   - Prevents audio clipping through averaging
   - Handles variable audio track availability

3. **Video Processing**
   - Aspect ratio preservation
   - Automatic resizing to target resolution (1280x720)
   - Picture-in-Picture (PiP) support (compositing multiple video tracks)
   - Frame synchronization

4. **Recording Session Management**
   - Unique session IDs for each recording
   - Automatic file naming with UUIDs
   - Session state tracking
   - Graceful cleanup on disconnect

### Recording Pipeline

1. **Session Creation**
   - Teacher initiates recording with `/start-recording`
   - Server creates `RecordingSession` with unique ID
   - WebRTC peer connection established

2. **Media Reception**
   - Video tracks received and processed
   - Audio tracks received and added to mixer
   - Tracks processed through custom media pipelines

3. **Compositing & Mixing**
   - Video: `AspectRatioPreservingTrack` resizes to 1280x720
   - Video: `CompositingTrack` composites multiple video tracks (if available)
   - Audio: `AudioMixerTrack` mixes multiple audio tracks
   - Pacemaker-driven audio mixing (20ms frames)

4. **Encoding & Storage**
   - Media encoded to MKV container
   - H.264 video (CRF 18, ultrafast preset)
   - AAC audio
   - Saved to `videos_recorded/` directory

5. **Session Completion**
   - Recording stopped via `/stop-recording`
   - Video metadata saved to database
   - Session cleaned up

### Audio Mixing Details

- **Sample Rate:** 48kHz
- **Channels:** Stereo (2 channels)
- **Format:** S16 (16-bit signed integer)
- **Frame Size:** 960 samples per frame (20ms)
- **Mix Strategy:** Averaging to prevent clipping
- **Resampling:** Automatic conversion from source formats

### Video Processing Details

- **Target Resolution:** 1280x720
- **Format:** YUV420P
- **PiP Support:** 
  - Picture-in-Picture width: 25% of main video
  - Padding: 10 pixels
  - Position: Bottom-right corner
  - Aspect ratio preserved

---

## Database Models

### User

Represents a user in the system with role-based access.

**Fields:**
- `name` (string, max 50 chars): User's full name
- `email` (string, optional, indexed, unique): User's email address
- `password` (string): Hashed password
- `role` (Role enum): User role (SUPERADMIN, ADMIN, TEACHER, USER)
- `phone` (string, optional, max 15 chars): User's phone number
- `division` (Link[Division], optional): User's division (for students)
- `class_id` (Link[Class], optional): User's class
- `roll_number` (string, optional, max 20 chars): Roll number (for students)
- `parent_name` (string, optional, max 50 chars): Parent's name (for students)
- `parent_phone` (string, optional, max 15 chars): Parent's phone (for students)
- `address` (string, optional, max 200 chars): User's address
- `is_deleted` (SoftDelete): Soft delete status
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

**Validation:**
- Students (USER role) require: `roll_number`, `class_id`, `division`
- Admins and Teachers require: `class_id`, `division`

### Division

Represents a division within a class (e.g., Class 10-A).

**Fields:**
- `name` (string, max 20 chars): Division name
- `class_id` (Link[Class]): Parent class
- `teacher` (Link[User], optional): Assigned teacher
- `description` (string, optional, max 200 chars): Division description
- `meeting_link` (string, optional, max 255 chars): Meeting URL
- `is_live` (boolean, default: false): Whether meeting is currently live
- `is_deleted` (SoftDelete): Soft delete status
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

**Indexes:**
- Unique constraint on `(name, class_id)` combination

### Class

Represents a class or grade level.

**Fields:**
- `name` (string, indexed, unique, max 50 chars): Class name
- `description` (string, optional, max 200 chars): Class description
- `is_deleted` (SoftDelete): Soft delete status
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp

### RecordedVideo

Represents a recorded video of a class session.

**Fields:**
- `filename` (string, max 255 chars): Video filename (UUID.mkv)
- `division` (Link[Division]): Division the video belongs to
- `created_at` (datetime): Recording timestamp

### Token

Represents a refresh token for user authentication.

**Fields:**
- `token` (string): Refresh token string
- `user_id` (Link[User]): Associated user
- `created_at` (datetime): Token creation timestamp
- `updated_at` (datetime): Last update timestamp

---

## User Roles & Permissions

### Role Hierarchy

1. **SUPERADMIN**
   - Full system access
   - Can perform all operations

2. **ADMIN**
   - Administrative access
   - Can manage classes and divisions

3. **TEACHER**
   - Can start/stop recordings
   - Can manage meeting status for assigned divisions
   - Can view recordings for their divisions

4. **USER** (Student)
   - Can view meeting status
   - Can view and stream recordings for their division
   - Limited to their own division

### Endpoint Permissions

| Endpoint | SUPERADMIN | ADMIN | TEACHER | USER |
|----------|-----------|-------|---------|------|
| `/api/health` | ✅ | ✅ | ✅ | ✅ |
| `/api/auth/token/refresh` | ✅ | ✅ | ✅ | ✅ |
| `PUT /api/meetings/{id}/status` | ✅ | ✅ | ✅ (own division) | ❌ |
| `GET /api/meetings/{id}/status` | ✅ | ✅ | ✅ | ✅ (own division) |
| `GET /api/videos/{id}` | ✅ | ✅ | ✅ | ✅ (own division) |
| `GET /api/videos/stream/{id}` | ✅ | ✅ | ✅ | ✅ (own division) |
| `POST /start-recording` | ✅ | ✅ | ✅ (own division) | ❌ |
| `POST /stop-recording` | ✅ | ✅ | ✅ | ✅ |
| `WS /ws/{room_id}` | ✅ | ✅ | ✅ | ✅ |

---

## WebRTC Integration

### Client Requirements

To integrate with the recording endpoints, clients need:

1. **WebRTC Peer Connection**
   - Create `RTCPeerConnection`
   - Add screen share track: `getDisplayMedia({ video: true, audio: true })`
   - Create SDP offer: `createOffer()`
   - Set local description: `setLocalDescription(offer)`

2. **SDP Exchange**
   - Send SDP offer to `/start-recording` with `division_id`
   - Receive SDP answer from server
   - Set remote description: `setRemoteDescription(answer)`
   - ICE candidates handled automatically

3. **Recording Control**
   - Store `session_id` from `/start-recording` response
   - Send `session_id` to `/stop-recording` when done

### Example Client Code (JavaScript)

```javascript
// Start recording
async function startRecording(divisionId) {
  const pc = new RTCPeerConnection();
  
  // Get screen share
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: true
  });
  
  // Add tracks to peer connection
  stream.getTracks().forEach(track => {
    pc.addTrack(track, stream);
  });
  
  // Create offer
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  
  // Send to server
  const response = await fetch('http://localhost:8000/start-recording', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({
      sdp: offer.sdp,
      type: offer.type,
      division_id: divisionId
    })
  });
  
  const { sdp, type, session_id } = await response.json();
  
  // Set remote description
  await pc.setRemoteDescription({ sdp, type });
  
  // Store session_id for stopping
  window.recordingSessionId = session_id;
}

// Stop recording
async function stopRecording() {
  await fetch('http://localhost:8000/stop-recording', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      session_id: window.recordingSessionId
    })
  });
}
```

---

## Error Handling

### Common Error Responses

**401 Unauthorized:**
```json
{
  "detail": {
    "code": "AuthenticationError",
    "message": "Access denied, no token provided"
  }
}
```

**403 Forbidden:**
```json
{
  "detail": "You are not authorized to view this recording"
}
```

**404 Not Found:**
```json
{
  "detail": "Division not found"
}
```

**400 Bad Request:**
```json
{
  "detail": "Division ID is required."
}
```

---

## Development Notes

### File Structure

```
server/
├── app/
│   ├── api/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── compositing.py   # Video compositing and audio mixing
│   │   ├── meetings.py      # Meeting management
│   │   ├── recording.py     # Recording endpoints
│   │   ├── resizing.py      # Video resizing
│   │   ├── videos.py        # Video listing and streaming
│   │   └── websocket.py     # WebSocket endpoint
│   ├── config/
│   │   ├── db.py            # Database configuration
│   │   ├── env_settings.py  # Environment variables
│   │   ├── lifespan.py      # Application lifespan
│   │   └── origins.py       # CORS origins
│   ├── core/
│   │   ├── auth.py          # Authentication logic
│   │   └── meeting_manager.py # WebSocket room management
│   ├── db_models/
│   │   ├── academic.py      # Class and Division models
│   │   ├── core.py          # Core models and enums
│   │   ├── recording.py     # RecordedVideo model
│   │   ├── token.py         # Token model
│   │   └── user.py          # User model
│   └── main.py              # FastAPI application
├── videos_recorded/         # Recorded video files
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

### Key Dependencies

- **fastapi**: Web framework
- **aiortc**: WebRTC implementation
- **beanie**: MongoDB ODM
- **av** (PyAV): Audio/video processing
- **numpy**: Numerical operations
- **python-jose**: JWT handling
- **uvicorn**: ASGI server

---

## License

This project is part of the Score.AI streaming application.

---

## Support

For issues, questions, or contributions, please refer to the project repository.
