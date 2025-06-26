import twilio from 'twilio';
import { createLogger } from '../utils/logger';
import {
  TWILIO_ACCOUNT_SID,
  TWILIO_AUTH_TOKEN,
  TWILIO_PHONE_NUMBER,
  SERVER_BASE_URL
} from '../config';

const logger = createLogger('twilioService');

export class TwilioService {
  private client: twilio.Twilio;

  constructor() {
    if (!TWILIO_ACCOUNT_SID || !TWILIO_AUTH_TOKEN) {
      throw new Error('Twilio credentials not configured');
    }
    this.client = twilio(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN);
    logger.info('Twilio service initialized');
  }

  /**
   * Place a phone call with machine detection to avoid voicemail.
   */
  async placeCall(to: string): Promise<any> {
    logger.info(`Placing call to: ${to}`);
    
    const twimlUrl = `${SERVER_BASE_URL}/twiml/stream`;
    const statusCallbackUrl = `${SERVER_BASE_URL}/call-status`;
    
    logger.warn(`Telling Twilio to fetch TwiML from the static URL: ${twimlUrl}`);
    logger.warn('Ensure your ngrok tunnel is active with the command: ngrok http 8080 --domain=striking-iguana-amazingly.ngrok-free.app');
    
    logger.info(`Creating call with TwiML URL: ${twimlUrl}`);
    logger.info(`Status callback URL: ${statusCallbackUrl}`);
    logger.info(`From: ${TWILIO_PHONE_NUMBER}, To: ${to}`);
    
    try {
      const call = await this.client.calls.create({
        to,
        from: TWILIO_PHONE_NUMBER!,
        url: twimlUrl,
        method: 'POST',
        statusCallback: statusCallbackUrl,
        statusCallbackEvent: ['initiated', 'ringing', 'answered', 'completed', 'failed', 'busy', 'no-answer'],
        statusCallbackMethod: 'POST',
        machineDetection: 'Enable', // Options: Enable, DetectMessageEnd, or Disable
        machineDetectionTimeout: 3000, // 3 seconds timeout
        // With 'Enable' mode, AnsweredBy can be: human, machine_start, machine_end_beep, machine_end_silence, machine_end_other, fax, unknown
      });
      
      logger.info(`Call initiated with SID: ${call.sid}`);
      logger.info(`Call status: ${call.status}`);
      logger.info('Machine detection enabled - will end call if answering machine detected');
      
      return call;
    } catch (error) {
      logger.error(`Failed to place call: ${error}`);
      throw error;
    }
  }

  /**
   * Generate TwiML based on who answered (human or machine).
   * If machine answered, just hang up.
   */
  generateStreamTwiml(answeredBy?: string): string {
    // Hang up immediately for fax or answering machine
    if (answeredBy && ['fax', 'machine_start', 'machine_end_beep', 'machine_end_silence', 'machine_end_other'].includes(answeredBy)) {
      logger.info(`Call answered by ${answeredBy} - hanging up immediately (no voicemail)`);
      return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>`;
    }
    
    // Normal flow for human-answered calls
    const wsUrl = SERVER_BASE_URL!.replace('https://', 'wss://').replace('http://', 'ws://');
    const wsEndpoint = `${wsUrl}/media-stream`;
    
    logger.info(`Generating TwiML with WebSocket URL: ${wsEndpoint}`);
    logger.info(`Call answered by: ${answeredBy || 'unknown (treating as human)'}`);
    
    const twiml = `<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting you now, one moment please..</Say>
    <Connect>
        <Stream url="${wsEndpoint}">
        </Stream>
    </Connect>
</Response>`;
    
    logger.debug(`Generated TwiML: ${twiml}`);
    logger.info('TwiML generation complete');
    return twiml;
  }

  /**
   * Update a call to end it immediately.
   */
  async updateCall(callSid: string, status: string = 'completed'): Promise<boolean> {
    try {
      logger.info(`Updating call ${callSid} to status: ${status}`);
      await this.client.calls(callSid).update({ status: status as any });
      logger.info(`Call ${callSid} updated successfully`);
      return true;
    } catch (error) {
      logger.error(`Failed to update call ${callSid}: ${error}`);
      return false;
    }
  }
} 