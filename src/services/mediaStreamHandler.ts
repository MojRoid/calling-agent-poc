import WebSocket from 'ws';
import * as fs from 'fs';
import * as path from 'path';
import { createLogger } from '../utils/logger';
import { encodeWav } from '../utils/wavFile';
import { GeminiLiveClient } from './geminiClient';
import { SimpleAudioConverter } from './audioConverter';
import { TwilioMessage, CallSummary } from '../models';
import { DEFAULT_SYSTEM_INSTRUCTIONS } from '../config';

const logger = createLogger('mediaStreamHandler');

export class MediaStreamHandler {
  private ws: WebSocket;
  private geminiClient: GeminiLiveClient | null = null;
  private audioConverter: SimpleAudioConverter;
  private streamSid: string | null = null;
  private _callSid: string | null = null;
  private recordingEnabled = true;
  private inputAudioBuffers: Buffer[] = [];
  private outputAudioBuffers: Buffer[] = [];
  private inputRecordingFilePath: string | null = null;
  private outputRecordingFilePath: string | null = null;
  private geminiAudioChunksReceived = 0;
  private totalGeminiAudioBytes = 0;
  private isGeminiSpeaking = false;
  private callSummary: CallSummary | null = null;

  constructor(ws: WebSocket) {
    this.ws = ws;
    this.audioConverter = new SimpleAudioConverter();
  }

  async handleFunctionCall(functionCall: any): Promise<void> {
    try {
      const functionName = functionCall.name;
      const args = functionCall.args || {};
      
      logger.info(`📞 Handling function call: ${functionName}`);
      logger.info(`📋 Function arguments: ${JSON.stringify(args)}`);
      
      if (functionName === 'summarize_call_outcome') {
        // Extract and validate the call summary data
        const callSummaryData: CallSummary = {
          call_transcript: args.call_transcript || '',
          quote_obtained: args.quote_obtained || false,
          quote: args.quote || null,
          visit_booked: args.visit_booked || false,
          visit_booked_date: args.visit_booked_date || null,
          visit_time: args.visit_time || null,
          trade_sentiment_analysis: args.trade_sentiment_analysis || 'neutral'
        };
        
        this.callSummary = callSummaryData;
        
        logger.info('✅ Call summary captured:');
        logger.info(`   📝 Transcript: ${this.callSummary.call_transcript}`);
        logger.info(`   💰 Quote obtained: ${this.callSummary.quote_obtained}`);
        if (this.callSummary.quote) {
          logger.info(`   💷 Quote: ${this.callSummary.quote}`);
        }
        logger.info(`   📅 Visit booked: ${this.callSummary.visit_booked}`);
        if (this.callSummary.visit_booked_date) {
          logger.info(`   📆 Visit date: ${this.callSummary.visit_booked_date}`);
        }
        if (this.callSummary.visit_time) {
          logger.info(`   ⏰ Visit time: ${this.callSummary.visit_time}`);
        }
        logger.info(`   😊 Sentiment: ${this.callSummary.trade_sentiment_analysis}`);
        
        // Send function response back to Gemini
        if (this.geminiClient) {
          const functionResponse = {
            id: functionCall.id || null,
            name: functionName,
            response: {
              status: 'success',
              message: 'Call summary recorded successfully'
            }
          };
          
          try {
            await this.geminiClient.sendToolResponse(functionResponse);
            logger.info('📤 Function response sent to Gemini');
          } catch (error) {
            logger.error(`Error sending function response to Gemini: ${error}`);
          }
        }
      } else {
        logger.warn(`Unknown function call: ${functionName}`);
      }
    } catch (error) {
      logger.error(`Error handling function call: ${error}`, { stack: error });
    }
  }

  async handleStream(): Promise<void> {
    logger.info('📞 Starting media stream handler');
    
    try {
      let connectedReceived = false;
      let startReceived = false;
      
      // Set up message handler to process initial handshake
      await new Promise<void>((resolve, reject) => {
        const messageHandler = (data: WebSocket.Data) => {
          try {
            const message = JSON.parse(data.toString());
            logger.debug(`Received message with event: ${message.event}`);
            
            if (!connectedReceived && message.event === 'connected') {
              logger.debug(`Connected event received - Protocol: ${message.protocol}, Version: ${message.version}`);
              connectedReceived = true;
            } else if (connectedReceived && !startReceived && message.event === 'start') {
              const twilioMessage = message as TwilioMessage;
              if (twilioMessage.start) {
                logger.info(`📞 Call started - SID: ${twilioMessage.start.callSid}`);
                this._callSid = twilioMessage.start.callSid;
                this.streamSid = twilioMessage.start.streamSid;
                startReceived = true;
                
                // Remove this handler and resolve
                this.ws.removeListener('message', messageHandler);
                resolve();
              }
            } else if (!connectedReceived) {
              logger.error(`Expected 'connected' event first, but received '${message.event}'`);
              this.ws.removeListener('message', messageHandler);
              reject(new Error(`Unexpected first message: ${message.event}`));
            } else if (connectedReceived && !startReceived) {
              logger.error(`Expected 'start' event after 'connected', but received '${message.event}'`);
              this.ws.removeListener('message', messageHandler);
              reject(new Error(`Unexpected message after connected: ${message.event}`));
            }
          } catch (error) {
            logger.error(`Error parsing message: ${error}`);
            this.ws.removeListener('message', messageHandler);
            reject(error);
          }
        };
        
        this.ws.on('message', messageHandler);
        
        // Set a timeout for the handshake
        setTimeout(() => {
          this.ws.removeListener('message', messageHandler);
          reject(new Error('Timeout waiting for WebSocket handshake'));
        }, 10000);
      });
      
      // Initialize audio recording if enabled
      if (this.recordingEnabled) {
        await this.setupAudioRecording();
      }
      
      // Establish connection to Gemini
      if (!await this.connectToGemini()) {
        logger.error('Failed to establish Gemini connection. Closing stream.');
        return;
      }
      
      // Start receiving from Gemini
      this.receiveFromGemini();
      
      // Handle Twilio messages
      await this.receiveFromTwilio();
      
      // Trigger call summary before closing
      logger.info('📞 Call ending - triggering summary');
      await this.triggerCallSummary();
      
      // Wait a bit for the summary to be processed
      await new Promise(resolve => setTimeout(resolve, 2000));
      
    } catch (error) {
      logger.error(`Error in handle_stream: ${error}`, { stack: error });
    } finally {
      await this.cleanup();
      logger.info('📞 Call ended');
    }
  }



  private async setupAudioRecording(): Promise<void> {
    try {
      // Create recordings directory if it doesn't exist
      const recordingsDir = path.join(process.cwd(), 'recordings');
      if (!fs.existsSync(recordingsDir)) {
        fs.mkdirSync(recordingsDir, { recursive: true });
      }
      
      // Generate filename with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
      
      this.inputRecordingFilePath = path.join(recordingsDir, `twilio_input_${timestamp}.wav`);
      this.outputRecordingFilePath = path.join(recordingsDir, `gemini_output_${timestamp}.wav`);
      
      logger.debug(`📼 Recording enabled: ${timestamp}`);
    } catch (error) {
      logger.error(`Failed to setup audio recording: ${error}`);
      this.recordingEnabled = false;
    }
  }

  private async connectToGemini(): Promise<boolean> {
    try {
      logger.info('Creating new Gemini client...');
      
      // Create a new GeminiLiveClient with function call handler
      this.geminiClient = new GeminiLiveClient(undefined, this.handleFunctionCall.bind(this));
      
      // Connect with system instructions
      const success = await this.geminiClient.connect(DEFAULT_SYSTEM_INSTRUCTIONS || undefined);
      
      if (success) {
        return true;
      } else {
        logger.error('❌ Failed to connect to Gemini');
        return false;
      }
    } catch (error) {
      logger.error(`❌ Failed to connect to Gemini: ${error}`, { stack: error });
      return false;
    }
  }

  private async receiveFromTwilio(): Promise<void> {
    let audioChunksReceived = 0;
    let totalAudioBytes = 0;
    
    return new Promise((resolve) => {
      this.ws.on('message', async (data) => {
        try {
          const message: TwilioMessage = JSON.parse(data.toString());
          
          if (message.event === 'media' && message.media) {
            // Check if user is speaking while Gemini is speaking (interruption)
            if (this.isGeminiSpeaking) {
              this.isGeminiSpeaking = false;
            }
            
            // Decode the mulaw audio from Twilio
            const audioMulaw = Buffer.from(message.media.payload, 'base64');
            audioChunksReceived++;
            totalAudioBytes += audioMulaw.length;
            
            // Convert mulaw to PCM
            const audioPcm = this.audioConverter.mulawToPcm(audioMulaw);
            
            // Record the original audio
            if (this.recordingEnabled) {
              this.inputAudioBuffers.push(audioPcm);
            }
            
            // Simple upsampling from 8kHz to 16kHz
            const upsampledAudio = this.audioConverter.resampleAudio(audioPcm, 8000, 16000);
            
            // Forward the upsampled audio to Gemini
            if (this.geminiClient) {
              const success = await this.geminiClient.sendAudioChunk(upsampledAudio, 16000);
              if (!success) {
                logger.warn('Failed to send audio chunk to Gemini');
              }
            }
          } else if (message.event === 'stop') {
            logger.info("Received 'stop' from Twilio. Closing stream.");
            resolve();
          }
        } catch (error) {
          if (error instanceof SyntaxError) {
            logger.warn(`Ignoring non-JSON message from Twilio: ${error}`);
          } else {
            logger.error(`Error processing Twilio message: ${error}`);
          }
        }
      });
      
      this.ws.on('close', () => {
        logger.info('Twilio WebSocket connection closed.');
        resolve();
      });
      
      this.ws.on('error', (error) => {
        logger.error(`Twilio WebSocket error: ${error}`);
        resolve();
      });
    });
  }

  private async receiveFromGemini(): Promise<void> {
    if (!this.geminiClient) return;
    
    try {
      for await (const audioChunk of this.geminiClient.receiveAudioResponses()) {
        // Mark that Gemini is speaking
        this.isGeminiSpeaking = true;
        
        logger.debug(`Received audio from Gemini: ${audioChunk.length} bytes`);
        
        // Record output audio from Gemini if enabled
        if (this.recordingEnabled) {
          this.outputAudioBuffers.push(audioChunk);
          this.geminiAudioChunksReceived++;
          this.totalGeminiAudioBytes += audioChunk.length;
        }
        
        // Convert Gemini's 24kHz audio to 8kHz for Twilio
        const downsampledAudio = this.audioConverter.resampleAudio(audioChunk, 24000, 8000);
        
        // Convert PCM to mulaw for Twilio
        const mulawAudio = this.audioConverter.pcmToMulaw(downsampledAudio);
        
        // Send audio back to Twilio
        const mediaMessage = {
          event: 'media',
          streamSid: this.streamSid,
          media: {
            payload: mulawAudio.toString('base64')
          }
        };
        
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify(mediaMessage));
        }
      }
      
      // Gemini finished speaking
      this.isGeminiSpeaking = false;
    } catch (error) {
      logger.error(`Error in Gemini receiver: ${error}`);
      this.isGeminiSpeaking = false;
    }
  }

  private async triggerCallSummary(): Promise<void> {
    if (!this.geminiClient) return;
    
    try {
      await this.geminiClient.sendClientContent({
        turns: {
          parts: [{
            text: 'The call is ending. Please summarize the call outcome now using the summarize_call_outcome function.'
          }]
        }
      });
      logger.info('📤 Sent trigger message for call summary');
      
      // Wait for the function call and response
      const timeout = 5000;
      const startTime = Date.now();
      
      while ((Date.now() - startTime) < timeout) {
        if (this.callSummary !== null) {
          logger.info('✅ Call summary received');
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      if (this.callSummary === null) {
        logger.warn('⚠️ Timeout waiting for call summary');
      }
    } catch (error) {
      logger.error(`Error triggering call summary: ${error}`);
    }
  }

  private async cleanup(): Promise<void> {
    // Log final call summary if available
    if (this.callSummary) {
      logger.info('=== FINAL CALL SUMMARY ===');
      logger.info(`Transcript: ${this.callSummary.call_transcript}`);
      logger.info(`Quote obtained: ${this.callSummary.quote_obtained}`);
      if (this.callSummary.quote) {
        logger.info(`Quote: ${this.callSummary.quote}`);
      }
      logger.info(`Visit booked: ${this.callSummary.visit_booked}`);
      if (this.callSummary.visit_booked_date) {
        logger.info(`Visit date: ${this.callSummary.visit_booked_date}`);
      }
      if (this.callSummary.visit_time) {
        logger.info(`Visit time: ${this.callSummary.visit_time}`);
      }
      logger.info(`Trade sentiment: ${this.callSummary.trade_sentiment_analysis}`);
      logger.info('=========================');
    }
    
    // Save audio recordings
    if (this.recordingEnabled) {
      // Save input recording
      if (this.inputAudioBuffers.length > 0 && this.inputRecordingFilePath) {
        try {
          const combinedInput = Buffer.concat(this.inputAudioBuffers);
          const inputWavData = encodeWav(combinedInput, 8000, 16);
          fs.writeFileSync(this.inputRecordingFilePath, inputWavData);
          const duration = combinedInput.length / (8000 * 2);
          logger.debug(`📼 Input recording: ${duration.toFixed(1)}s - ${this.inputRecordingFilePath}`);
        } catch (error) {
          logger.error(`Error saving input recording: ${error}`);
        }
      }
      
      // Save output recording
      if (this.outputAudioBuffers.length > 0 && this.outputRecordingFilePath) {
        try {
          const combinedOutput = Buffer.concat(this.outputAudioBuffers);
          const outputWavData = encodeWav(combinedOutput, 24000, 16);
          fs.writeFileSync(this.outputRecordingFilePath, outputWavData);
          const duration = combinedOutput.length / (24000 * 2);
          logger.debug(`📼 Output recording: ${duration.toFixed(1)}s - ${this.outputRecordingFilePath}`);
        } catch (error) {
          logger.error(`Error saving output recording: ${error}`);
        }
      }
    }
    
    // Close Gemini connection
    if (this.geminiClient) {
      try {
        await this.geminiClient.close();
      } catch (error) {
        logger.error(`Error closing Gemini connection: ${error}`);
      }
    }
    
    // Close WebSocket
    try {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.close(1000);
      }
    } catch (error) {
      logger.error(`Error closing WebSocket: ${error}`);
    }
  }
} 