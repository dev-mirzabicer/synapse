import pytest
import httpx
import asyncio
import uuid
import json
from contextlib import asynccontextmanager
import websockets

# --- Configuration ---
# This test assumes the docker-compose stack is running.
API_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"

# Generate unique user credentials for each test run to ensure isolation
TEST_EMAIL = f"testuser_{uuid.uuid4()}@example.com"
TEST_PASSWORD = "a_secure_password_123"

# Define the agent and group for the test scenario
RESEARCHER_AGENT = {
    "alias": "Researcher",
    "role_prompt": "You are a world-class researcher. Your job is to use the web_search tool to find information.",
    "tools": ["web_search"],
    "provider": "gemini",
    "model": "models/gemini-pro",
    "temperature": 0.0,
}

TEST_GROUP = {
    "name": "E2E Test Research Group",
    "members": [RESEARCHER_AGENT],
}

# The user's prompt, designed to trigger the researcher agent
TEST_PROMPT = "What is the current market cap of NVIDIA?"


@asynccontextmanager
async def websocket_listener(group_id: str, token: str):
    """A context manager to handle the WebSocket connection and message collection."""
    received_messages = []
    uri = f"{WS_BASE_URL}/ws/{group_id}?token={token}"

    async def listen(ws):
        try:
            while True:
                message_str = await ws.recv()
                message = json.loads(message_str)
                print(f"RECV: {message.get('sender_alias')}: {message.get('content')}")
                received_messages.append(message)
                # A robust way to end the test is to look for the completion signal
                if "TASK_COMPLETE" in message.get("content", ""):
                    break
        except asyncio.CancelledError:
            pass  # Task was cancelled, which is expected
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed.")
        except Exception as e:
            print(f"WebSocket listener error: {e}")

    try:
        async with websockets.connect(uri) as ws:
            listener_task = asyncio.create_task(listen(ws))
            yield received_messages
            # Wait a bit longer to ensure all final messages are captured
            await asyncio.sleep(5)
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass  # Expected cancellation
    except Exception as e:
        pytest.fail(f"WebSocket connection failed: {e}")


@pytest.mark.asyncio
async def test_full_e2e_workflow():
    """
    Tests the entire application flow:
    1. Register a new user.
    2. Log in to get a token.
    3. Create a new chat group with a tool-using agent.
    4. Establish a WebSocket connection to listen for real-time messages.
    5. Send a message that triggers the agent and its tool.
    6. Verify the entire sequence of events from the WebSocket feed.
    """
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
        # 1. Register User
        register_payload = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        response = await client.post("/auth/register", json=register_payload)
        assert response.status_code == 201, f"Registration failed: {response.text}"

        # 2. Log In
        login_payload = {"username": TEST_EMAIL, "password": TEST_PASSWORD}
        response = await client.post("/auth/login", data=login_payload)
        assert response.status_code == 200, f"Login failed: {response.text}"
        token_data = response.json()
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # 3. Create Group
        response = await client.post("/groups/", json=TEST_GROUP, headers=headers)
        assert response.status_code == 201, f"Group creation failed: {response.text}"
        group_data = response.json()
        group_id = group_data["id"]
        assert group_id

        # 4. & 5. Connect WebSocket and Send Message
        async with websocket_listener(group_id, access_token) as received_messages:
            message_payload = {"content": TEST_PROMPT}
            response = await client.post(
                f"/groups/{group_id}/messages", json=message_payload, headers=headers
            )
            assert response.status_code == 202, f"Sending message failed: {response.text}"

            # Wait for the listener to signal completion (or timeout)
            await asyncio.sleep(45) # Give ample time for the full flow

        # 6. Verify the conversation flow
        assert len(received_messages) > 4, "Expected at least 5 messages in the flow"

        aliases = [msg.get("sender_alias") for msg in received_messages]
        content = " ".join([str(msg.get("content", "")) for msg in received_messages])

        # Check for key participants
        assert "User" in aliases, "User message was not broadcast"
        assert "Orchestrator" in aliases, "Orchestrator did not participate"
        assert "Researcher" in aliases, "Researcher agent was not invoked"
        
        # Check for key events in the conversation content
        # Orchestrator should delegate to the researcher
        assert f"@{RESEARCHER_AGENT['alias']}" in content, "Orchestrator did not delegate to the Researcher"
        
        # The tool should have been called
        assert "tool_calls" in content, "Agent did not seem to make a tool call"
        
        # The final response should be present
        assert "TASK_COMPLETE" in content, "Orchestrator did not signal task completion"
        
        print("\n--- E2E Test Succeeded ---")
        print(f"Verified a full conversation flow with {len(received_messages)} messages.")