#!/usr/bin/env node
import axios from 'axios';
import { TEST_PHONE_NUMBER } from './config';

const BASE_URL = 'http://localhost:8080';

async function checkServerHealth(): Promise<boolean> {
  try {
    // Try root endpoint first
    const response = await axios.get(`${BASE_URL}/`, { timeout: 5000 });
    
    if (response.status === 200) {
      console.log('✓ Server is healthy and running');
      console.log(`  Server response: ${JSON.stringify(response.data)}`);
      
      // Also try health endpoint if available
      try {
        const healthResponse = await axios.get(`${BASE_URL}/health`, { timeout: 5000 });
        if (healthResponse.status === 200) {
          console.log(`  Health check: ${JSON.stringify(healthResponse.data)}`);
        }
      } catch {
        // Health endpoint might not be available
      }
      
      return true;
    } else {
      console.log(`✗ Server health check failed: ${response.status}`);
      return false;
    }
  } catch (error) {
    console.log(`✗ Cannot connect to server: ${error}`);
    return false;
  }
}

async function placeTestCall(): Promise<boolean> {
  if (!TEST_PHONE_NUMBER) {
    console.log('✗ No test phone number configured in .env file');
    console.log('  Please set TEST_PHONE_NUMBER in your .env file');
    return false;
  }
  
  console.log(`\n📞 Placing test call to ${TEST_PHONE_NUMBER}...`);
  
  const callData = {
    to: TEST_PHONE_NUMBER
  };
  
  try {
    const response = await axios.post(
      `${BASE_URL}/place-call`,
      callData,
      { timeout: 30000 }
    );
    
    console.log(`📊 Response Status: ${response.status}`);
    
    if (response.status === 200) {
      const result = response.data;
      console.log('✓ Call placed successfully!');
      console.log(`  Call SID: ${result.callSid}`);
      console.log(`  Status: ${result.status}`);
      return true;
    } else {
      console.log(`✗ Call failed with status ${response.status}`);
      console.log(`  Error: ${JSON.stringify(response.data)}`);
      return false;
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      console.log(`✗ Error placing call: ${error.message}`);
      if (error.response) {
        console.log(`  Response: ${JSON.stringify(error.response.data)}`);
      }
    } else {
      console.log(`✗ Error placing call: ${error}`);
    }
    return false;
  }
}

async function main() {
  console.log('🚀 Starting Test Call Process');
  console.log('=' .repeat(50));
  
  if (!await checkServerHealth()) {
    console.log('\n❌ Server is not ready. Please start the server first.');
    process.exit(1);
  }
  
  // Place the test call
  const success = await placeTestCall();
  
  if (success) {
    console.log('\n' + '='.repeat(50));
    console.log('✅ TEST CALL INITIATED SUCCESSFULLY');
    console.log('='.repeat(50));
    console.log('📱 Your phone should be ringing now!');
  } else {
    console.log('\n❌ Test call failed. Check the server logs for details.');
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
} 