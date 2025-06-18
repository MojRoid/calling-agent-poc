from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# API Request/Response models
class PlaceCallRequest(BaseModel):
    to: str

class PlaceCallResponse(BaseModel):
    callSid: str
    status: str

# Twilio WebSocket message models
class MediaFormat(BaseModel):
    encoding: str
    sampleRate: int
    channels: int

class StreamStart(BaseModel):
    streamSid: str
    accountSid: str
    callSid: str
    tracks: List[str]
    mediaFormat: MediaFormat
    customParameters: Dict[str, str] = {}

class MediaPayload(BaseModel):
    track: str
    chunk: str
    timestamp: str
    payload: str

class MarkPayload(BaseModel):
    name: str

class TwilioMessage(BaseModel):
    event: str
    sequenceNumber: Optional[str] = None
    streamSid: Optional[str] = None
    start: Optional[StreamStart] = None
    media: Optional[MediaPayload] = None
    stop: Optional[Any] = None
    mark: Optional[MarkPayload] = None

# Gemini message models
class GeminiSetup(BaseModel):
    model: str = "gemini-live-2.5-flash-preview-native-audio"
    generationConfig: Optional[Dict[str, Any]] = None
    systemInstruction: Optional[Dict[str, Any]] = None
    tools: List[Any] = []

class GeminiSetupMessage(BaseModel):
    setup: GeminiSetup

class MediaChunk(BaseModel):
    mimeType: str
    data: str

class RealtimeInput(BaseModel):
    mediaChunks: List[MediaChunk]

class GeminiRealtimeMessage(BaseModel):
    realtimeInput: Optional[RealtimeInput] = None
    clientContent: Optional[Dict[str, Any]] = None

# Gemini response models
class InlineData(BaseModel):
    mimeType: str
    data: str

class Part(BaseModel):
    text: Optional[str] = None
    inlineData: Optional[InlineData] = None

class ModelTurn(BaseModel):
    parts: List[Part]

class ServerContent(BaseModel):
    turnComplete: bool
    interrupted: Optional[bool] = None
    modelTurn: Optional[ModelTurn] = None

class GeminiResponse(BaseModel):
    setupComplete: Optional[Any] = None
    serverContent: Optional[ServerContent] = None
    toolCall: Optional[Any] = None
    toolCallCancellation: Optional[Any] = None 