// @ts-ignore - Package may not have proper TypeScript definitions
import { createLogger } from '../utils/logger';
import { VERTEX_PROJECT_ID, VERTEX_LOCATION, GEMINI_MODEL } from '../config';

const logger = createLogger('geminiClient');

// Use require for @google/genai to avoid ESM issues
const { GoogleGenAI } = require('@google/genai');

export class GeminiLiveClient {
  private modelName: string;
  private ai: any = null;
  private session: any = null;
  private connected = false;
  private functionCallHandler?: (functionCall: any) => Promise<void>;
  private conversationState = {
    quote_mentioned: false,
    visit_scheduled: false,
    goodbyes_exchanged: false
  };
  private responseQueue: any[] = [];
  private summaryTriggered = false;

  constructor(modelName?: string, functionCallHandler?: (functionCall: any) => Promise<void>) {
    this.modelName = modelName || GEMINI_MODEL || '';
    if (!this.modelName) {
      throw new Error('GEMINI_MODEL not set in environment variables');
    }
    this.functionCallHandler = functionCallHandler;
  }

  async connect(systemInstruction?: string): Promise<boolean> {
    try {
      logger.info(`Connecting to Gemini model: ${this.modelName}`);

      // Initialize Google GenAI with Vertex AI support
      // The SDK should automatically use Application Default Credentials
      this.ai = new GoogleGenAI({
        vertexai: true,
        project: VERTEX_PROJECT_ID,
        location: VERTEX_LOCATION
      });

      const config: any = {
        responseModalities: ['AUDIO'],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        speechConfig: {
          voiceConfig: {
            prebuiltVoiceConfig: {
              voiceName: 'Kore'
            }
          }
        },
        enableAffectiveDialog: true,
        proactivity: {
          proactiveAudio: false
        },
        realtimeInputConfig: {
          automaticActivityDetection: {
            disabled: false,
            startOfSpeechSensitivity: 'START_SENSITIVITY_LOW',
            endOfSpeechSensitivity: 'END_SENSITIVITY_LOW',
            prefixPaddingMs: 20,
            silenceDurationMs: 250
          }
        },
        tools: [
          {
            functionDeclarations: [
              {
                name: 'summarize_call_outcome',
                description: 'Summarize the outcome of the call with the tradesperson',
                parameters: {
                  type: 'object',
                  properties: {
                    call_transcript: {
                      type: 'string',
                      description: 'A brief summary of the conversation that took place'
                    },
                    quote_obtained: {
                      type: 'boolean',
                      description: 'True if a quote or price estimate was obtained'
                    },
                    quote: {
                      type: 'string',
                      description: 'The actual quote amount/range if obtained, null if not'
                    },
                    visit_booked: {
                      type: 'boolean',
                      description: 'True if an appointment or visit was scheduled'
                    },
                    visit_booked_date: {
                      type: 'string',
                      description: 'The date of the visit if booked (format: YYYY-MM-DD), null if not'
                    },
                    visit_time: {
                      type: 'string',
                      description: 'The time of the visit if specified (format: HH:MM), null if not'
                    },
                    trade_sentiment_analysis: {
                      type: 'string',
                      description: 'Assessment of the tradesperson\'s attitude and sentiment during the call'
                    }
                  },
                  required: ['call_transcript', 'quote_obtained', 'visit_booked', 'trade_sentiment_analysis']
                }
              }
            ]
          }
        ]
      };

      if (systemInstruction) {
        config.systemInstruction = systemInstruction;
      }

      // Create callbacks object
      const callbacks = {
        onopen: () => {
          logger.info('✅ WebSocket connected to Gemini');
          this.connected = true;
        },
        onmessage: (message: any) => {
          this.responseQueue.push(message);
          this.handleMessage(message);
        },
        onerror: (error: any) => {
          logger.error(`WebSocket error: ${error.message || error}`);
        },
        onclose: (event: any) => {
          logger.info(`WebSocket closed: ${event.reason || 'No reason provided'}`);
          this.connected = false;
        }
      };

      // Connect to the live session
      this.session = await this.ai.live.connect({
        model: this.modelName,
        config: config,
        callbacks: callbacks
      });

      // Wait a bit to ensure connection is established
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Log available methods on the session object for debugging
      if (this.session) {
        const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(this.session))
          .filter(m => typeof this.session[m] === 'function');
        logger.debug(`Available session methods: ${methods.join(', ')}`);
      }
      
      return this.connected;
    } catch (error) {
      logger.error(`Failed to connect to Gemini: ${error}`);
      logger.error(`Error details: ${JSON.stringify(error, null, 2)}`);
      this.connected = false;
      return false;
    }
  }

  private handleMessage(message: any): void {
    try {
      // Handle setup completion
      if (message.setupComplete) {
        logger.info(`✅ Setup complete.`);
        return;
      }

      // Handle server content
      if (message.serverContent) {
        this.handleServerContent(message.serverContent);
      }

      // Handle tool calls
      if (message.toolCall && this.functionCallHandler) {
        this.handleToolCall(message.toolCall);
      }
    } catch (error) {
      logger.error(`Error handling message: ${error}`);
    }
  }

  private async handleToolCall(toolCall: any): Promise<void> {
    logger.info('🔧 Tool call received');
    try {
      if (toolCall.functionCalls) {
        for (const fc of toolCall.functionCalls) {
          logger.info(`🔧 Function call: ${fc.name}`);
          if (this.functionCallHandler) {
            await this.functionCallHandler(fc);
          }
        }
      }
    } catch (error) {
      logger.error(`Error handling tool call: ${error}`);
    }
  }

  private handleServerContent(serverContent: any): void {
    // Handle interruptions
    if (serverContent.interrupted) {
      logger.info('🛑 Gemini response was interrupted by user');
      return;
    }

    // Log transcriptions
    if (serverContent.inputTranscription?.text) {
      const userText = serverContent.inputTranscription.text;
      logger.info(`🎤 User said: ${userText}`);
      
      // Check for goodbye patterns
      const goodbyePatterns = ['bye', 'goodbye', 'thanks', 'thank you', 'see you'];
      if (goodbyePatterns.some(pattern => userText.toLowerCase().includes(pattern))) {
        this.conversationState.goodbyes_exchanged = true;
      }
    }

    if (serverContent.outputTranscription?.text) {
      const aiText = serverContent.outputTranscription.text;
      logger.info(`🤖 Gemini says: ${aiText}`);
      
      // Monitor for quote mentions
      if (['quote', 'pound', '£', 'cost', 'price'].some(word => aiText.toLowerCase().includes(word))) {
        this.conversationState.quote_mentioned = true;
      }
      
      // Monitor for visit scheduling
      if (['scheduled', 'appointment', 'visit', 'saturday', 'thursday'].some(word => aiText.toLowerCase().includes(word))) {
        this.conversationState.visit_scheduled = true;
      }
    }

    // Log turn completion
    if (serverContent.turnComplete) {
      logger.info('Gemini turn complete');
      
      // Check if we should trigger the summary based on conversation state
      if (this.conversationState.goodbyes_exchanged && !this.summaryTriggered) {
        this.triggerSummaryBasedOnState();
      }
    }
  }

  private async triggerSummaryBasedOnState(): Promise<void> {
    if (this.summaryTriggered) return;
    this.summaryTriggered = true;
    
    logger.info('📞 Goodbyes exchanged - triggering call summary');
    
    // Since we can't send text in Vertex AI, we'll need to rely on the natural flow
    // The system prompt should instruct Gemini to summarize when goodbyes are exchanged
    // This is a limitation of Vertex AI's Live API
    logger.info('⚠️ Note: Vertex AI Live sessions do not support programmatic text triggers.');
    logger.info('💡 Relying on system instructions to trigger summary after goodbyes.');
  }

  getConversationState() {
    return { ...this.conversationState };
  }

  async sendAudioChunk(audioData: Buffer, sampleRate: number = 8000): Promise<boolean> {
    if (!this.connected || !this.session) {
      logger.error('Not connected to Gemini');
      return false;
    }

    try {
      // Convert audio data to base64 as per Google sample code
      const base64Audio = audioData.toString('base64');
      
      // Use sendRealtimeInput with media parameter (like Python implementation)
      await this.session.sendRealtimeInput({
        media: {
          data: base64Audio,
          mimeType: `audio/pcm;rate=${sampleRate}`
        }
      });
      
      return true;
    } catch (error) {
      logger.error(`Failed to send audio to Gemini: ${error}`);
      return false;
    }
  }

  async *receiveAudioResponses(): AsyncGenerator<Buffer, void, unknown> {
    if (!this.connected || !this.session) {
      logger.error('Not connected to Gemini');
      return;
    }

    while (this.connected) {
      // Wait for messages in the queue
      while (this.responseQueue.length === 0 && this.connected) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }

      if (!this.connected) break;

      const message = this.responseQueue.shift();
      if (!message) continue;

      // Skip if no server content
      if (!message.serverContent) {
        continue;
      }

      const serverContent = message.serverContent;

      // Process model turns
      if (serverContent.model_turn?.parts) {
        for (const part of serverContent.model_turn.parts) {
          if (part.inline_data?.data) {
            // The data is likely already bytes, not base64
            const audioChunk = part.inline_data.data;
            yield audioChunk;
          }
        }
      }

      // Also check for data directly on the message
      if (message.data) {
        // Audio data might come directly in the data field
        const audioChunk = Buffer.from(message.data, 'base64');
        yield audioChunk;
      }
    }
  }

  async sendToolResponse(functionResponse: any): Promise<void> {
    if (!this.connected || !this.session) {
      logger.error('Not connected to Gemini');
      return;
    }

    try {
      // Try different formats based on what the SDK might expect
      if (typeof this.session.sendToolResponse === 'function') {
        try {
          // First try as a list (matching Python)
          await this.session.sendToolResponse([functionResponse]);
        } catch (e1) {
          try {
            // If that fails, try with functionResponses wrapper
            await this.session.sendToolResponse({
              functionResponses: [functionResponse]
            });
          } catch (e2) {
            try {
              // If that fails, try sending directly
              await this.session.sendToolResponse(functionResponse);
            } catch (e3) {
              logger.error(`All tool response formats failed. Errors: ${e1}, ${e2}, ${e3}`);
              throw e3;
            }
          }
        }
      } else {
        logger.error('sendToolResponse method not found on session');
      }
      logger.info('Tool response sent to Gemini');
    } catch (error) {
      logger.error(`Error sending tool response: ${error}`);
    }
  }

  async sendClientContent(content: any): Promise<void> {
    if (!this.connected || !this.session) {
      logger.error('Not connected to Gemini');
      return;
    }

    try {
      // Vertex AI Live sessions don't support text input - only audio
      // Log a warning and skip text messages
      if (content.turns?.parts?.[0]?.text) {
        logger.warn('Vertex AI Live sessions do not support text input. Skipping text message.');
        logger.debug(`Attempted to send text: ${content.turns.parts[0].text}`);
        return;
      }

      // For other content types, try available methods
      if (typeof this.session.send === 'function') {
        await this.session.send(content);
      } else if (typeof this.session.sendMessage === 'function') {
        await this.session.sendMessage(content);
      } else {
        logger.error(`No suitable method found to send client content. Available methods: ${Object.getOwnPropertyNames(Object.getPrototypeOf(this.session)).filter(m => typeof this.session[m] === 'function').join(', ')}`);
      }
    } catch (error) {
      logger.error(`Error sending client content: ${error}`);
    }
  }

  async close(): Promise<void> {
    if (this.session) {
      try {
        this.session.close();
      } catch (error) {
        logger.error(`Error closing session: ${error}`);
      }
      this.session = null;
    }
    this.connected = false;
  }
} 