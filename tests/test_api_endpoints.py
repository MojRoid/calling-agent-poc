"""
Test API Endpoints
"""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app import app

@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)

def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get('/')
    assert response.status_code == 200
    data = response.json()
    assert "message" in data

def test_health_check(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"

def test_twiml_generation(client):
    """Test TwiML generation endpoint"""
    # Test default TwiML (human answered)
    response = client.post('/twiml/stream')
    assert response.status_code == 200
    twiml = response.text
    assert "<Response>" in twiml
    assert "<Connect>" in twiml
    assert "<Say>" in twiml
    
    # Test machine detection
    response = client.post('/twiml/stream', data={"AnsweredBy": "machine_start"})
    assert response.status_code == 200
    twiml = response.text
    assert "<Hangup/>" in twiml

@patch('services.twilio_service.TwilioService.place_call')
def test_place_call(mock_place_call, client):
    """Test place call endpoint"""
    # Mock successful call placement
    mock_call = Mock()
    mock_call.sid = "CA123456789"
    mock_call.status = "queued"
    mock_place_call.return_value = mock_call
    
    call_data = {
        "to": "+1234567890"
    }
    
    response = client.post('/place-call', json=call_data)
    assert response.status_code == 200
    data = response.json()
    assert "callSid" in data
    assert "status" in data
    assert data["callSid"] == "CA123456789"
    assert data["status"] == "queued"

def test_call_status_endpoint(client):
    """Test call status callback endpoint"""
    statuses = ["answered", "busy", "no-answer", "failed", "completed"]
    
    for status in statuses:
        data = {
            "CallSid": f"CAtest{status}",
            "CallStatus": status
        }
        
        response = client.post('/call-status', data=data)
        assert response.status_code == 200 
