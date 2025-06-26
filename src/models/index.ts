// API Request/Response models
export interface PlaceCallRequest {
  to: string;
}

export interface PlaceCallResponse {
  callSid: string;
  status: string;
}

// Twilio WebSocket message models
export interface MediaFormat {
  encoding: string;
  sampleRate: number;
  channels: number;
}

export interface StreamStart {
  streamSid: string;
  accountSid: string;
  callSid: string;
  tracks: string[];
  mediaFormat: MediaFormat;
  customParameters: Record<string, string>;
}

export interface MediaPayload {
  track: string;
  chunk: string;
  timestamp: string;
  payload: string;
}

export interface MarkPayload {
  name: string;
}

export interface TwilioMessage {
  event: string;
  sequenceNumber?: string;
  streamSid?: string;
  start?: StreamStart;
  media?: MediaPayload;
  stop?: any;
  mark?: MarkPayload;
}

// Gemini message models
export interface GeminiSetup {
  model?: string;
  generationConfig?: Record<string, any>;
  systemInstruction?: Record<string, any>;
  tools?: any[];
}

export interface GeminiSetupMessage {
  setup: GeminiSetup;
}

export interface MediaChunk {
  mimeType: string;
  data: string;
}

export interface RealtimeInput {
  mediaChunks: MediaChunk[];
}

export interface GeminiRealtimeMessage {
  realtimeInput?: RealtimeInput;
  clientContent?: Record<string, any>;
}

// Gemini response models
export interface InlineData {
  mimeType: string;
  data: string;
}

export interface Part {
  text?: string;
  inlineData?: InlineData;
}

export interface ModelTurn {
  parts: Part[];
}

export interface ServerContent {
  turnComplete: boolean;
  interrupted?: boolean;
  modelTurn?: ModelTurn;
}

export interface GeminiResponse {
  setupComplete?: any;
  serverContent?: ServerContent;
  toolCall?: any;
  toolCallCancellation?: any;
}

// Call Summary Models
export interface CallSummary {
  call_transcript: string;
  quote_obtained: boolean;
  quote?: string | null;
  visit_booked: boolean;
  visit_booked_date?: string | null;
  visit_time?: string | null;
  trade_sentiment_analysis: string;
} 