import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Twilio Configuration (required from .env)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Vertex AI Configuration (required from .env)
VERTEX_PROJECT_ID = os.getenv('VERTEX_PROJECT_ID')
VERTEX_LOCATION = os.getenv('VERTEX_LOCATION')

# Server Configuration (required from .env)
SERVER_BASE_URL = os.getenv('SERVER_BASE_URL')
SERVER_PORT = int(os.getenv('SERVER_PORT', '8080'))

# Gemini Model Configuration (required from .env)
GEMINI_MODEL = os.getenv('GEMINI_MODEL')

# Test Configuration (optional from .env)
TEST_PHONE_NUMBER = os.getenv('TEST_PHONE_NUMBER')

# Load system prompt from fixed file
def load_system_prompt():
    """Load system prompt from gemini_system_prompt.txt (required)"""
    file_path = 'gemini_system_prompt.txt'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
            if prompt:
                return prompt
            else:
                raise ValueError(f"System prompt file '{file_path}' is empty.")
    except FileNotFoundError:
        raise FileNotFoundError(f"System prompt file '{file_path}' not found. Please create this file with the desired system prompt.")
    except Exception as e:
        raise Exception(f"Error reading system prompt file '{file_path}': {e}")

# Load system prompt once at startup
try:
    DEFAULT_SYSTEM_INSTRUCTIONS = load_system_prompt()
except Exception as e:
    print(f"ERROR: {e}")
    print("The application cannot start without a valid system prompt.")
    print("Please ensure 'gemini_system_prompt.txt' exists and contains the system prompt.")
    DEFAULT_SYSTEM_INSTRUCTIONS = None

# Validate required configuration
required_configs = {
    'TWILIO_ACCOUNT_SID': TWILIO_ACCOUNT_SID,
    'TWILIO_AUTH_TOKEN': TWILIO_AUTH_TOKEN,
    'TWILIO_PHONE_NUMBER': TWILIO_PHONE_NUMBER,
    'VERTEX_PROJECT_ID': VERTEX_PROJECT_ID,
    'VERTEX_LOCATION': VERTEX_LOCATION,
    'SERVER_BASE_URL': SERVER_BASE_URL,
    'GEMINI_MODEL': GEMINI_MODEL
}

missing_configs = [key for key, value in required_configs.items() if not value]
if missing_configs:
    print("ERROR: Missing required configuration values in .env file:")
    for config in missing_configs:
        print(f"  - {config}")
    print("\nPlease create a .env file with all required configuration values.") 