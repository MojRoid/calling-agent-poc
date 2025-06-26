import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';

// Load environment variables from .env file
dotenv.config();

// Twilio Configuration (required from .env)
export const TWILIO_ACCOUNT_SID = process.env.TWILIO_ACCOUNT_SID;
export const TWILIO_AUTH_TOKEN = process.env.TWILIO_AUTH_TOKEN;
export const TWILIO_PHONE_NUMBER = process.env.TWILIO_PHONE_NUMBER;

// Vertex AI Configuration (required from .env)
export const VERTEX_PROJECT_ID = process.env.VERTEX_PROJECT_ID;
export const VERTEX_LOCATION = process.env.VERTEX_LOCATION;

// Server Configuration (required from .env)
export const SERVER_BASE_URL = process.env.SERVER_BASE_URL;
export const SERVER_PORT = parseInt(process.env.SERVER_PORT || '8080', 10);

// Gemini Model Configuration (required from .env)
export const GEMINI_MODEL = process.env.GEMINI_MODEL;

// Test Configuration (optional from .env)
export const TEST_PHONE_NUMBER = process.env.TEST_PHONE_NUMBER;

// Load system prompt from fixed file
function loadSystemPrompt(): string | null {
  const filePath = path.join(process.cwd(), 'gemini_system_prompt.txt');
  
  try {
    const prompt = fs.readFileSync(filePath, 'utf-8').trim();
    if (prompt) {
      return prompt;
    } else {
      throw new Error(`System prompt file '${filePath}' is empty.`);
    }
  } catch (error) {
    if (error instanceof Error) {
      if ((error as any).code === 'ENOENT') {
        console.error(`System prompt file '${filePath}' not found. Please create this file with the desired system prompt.`);
      } else {
        console.error(`Error reading system prompt file '${filePath}': ${error.message}`);
      }
    }
    console.error('The application cannot start without a valid system prompt.');
    console.error("Please ensure 'gemini_system_prompt.txt' exists and contains the system prompt.");
    return null;
  }
}

// Load system prompt once at startup
export const DEFAULT_SYSTEM_INSTRUCTIONS = loadSystemPrompt();

// Validate required configuration
const requiredConfigs: Record<string, string | undefined> = {
  TWILIO_ACCOUNT_SID,
  TWILIO_AUTH_TOKEN,
  TWILIO_PHONE_NUMBER,
  VERTEX_PROJECT_ID,
  VERTEX_LOCATION,
  SERVER_BASE_URL,
  GEMINI_MODEL
};

const missingConfigs = Object.entries(requiredConfigs)
  .filter(([_, value]) => !value)
  .map(([key]) => key);

if (missingConfigs.length > 0) {
  console.error('ERROR: Missing required configuration values in .env file:');
  missingConfigs.forEach(config => {
    console.error(`  - ${config}`);
  });
  console.error('\nPlease create a .env file with all required configuration values.');
} 