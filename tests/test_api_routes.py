import os
import sys
from pathlib import Path
import uuid
import pytest
from httpx import AsyncClient # For making HTTP requests in tests
from datetime import datetime, timezone, timedelta

# Ensure paths are set up correctly for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "api_gateway"))
sys.path.insert(0, str(ROOT / "backend" / "shared"))


# Set default environment variables for tests if not already set
# These should ideally be in conftest.py for broader application
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file:test_api_routes?mode=memory&cache=shared&uri=true")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1") # Use a different DB for tests
os.environ.setdefault("SECRET_KEY", "testsecretkeyforpytest")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("TAVILY_API_KEY", "dummy_tavily_key")
os.environ.setdefault("OPENAI_API_KEY", "dummy_openai_key") # For llm-options test
os.environ.setdefault("GEMINI_API_KEY", "dummy_gemini_key")   # For llm-options test
# CLAUDE_API_KEY can be None for testing filtering

from backend.api_gateway.app.main import app # Import the FastAPI app
from backend.shared.app.models.chat import User, ChatGroup, GroupMember, Message # For direct DB manipulation if needed
from backend.shared.app.schemas.auth import UserCreate
from backend.shared.app.schemas.groups import GroupCreate, AgentConfigCreate
from backend.api_gateway.app.core.security import get_password_hash, create_access_token
from backend.shared.app.db import AsyncSessionLocal, engine as app_engine, Base


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session_fixture():
    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
async def test_user(db_session_fixture: AsyncSessionLocal):
    user_email = f"testuser_{uuid.uuid4()}@example.com"
    user_password = "testpassword123"
    hashed_password = get_password_hash(user_password)
    user = User(email=user_email, hashed_password=hashed_password)
    db_session_fixture.add(user)
    await db_session_fixture.commit()
    await db_session_fixture.refresh(user)
    return {"id": user.id, "email": user_email, "password": user_password}

@pytest.fixture
async def authenticated_client(test_user):
    access_token = create_access_token(data={"sub": str(test_user["id"])})
    async with AsyncClient(app=app, base_url="http://test") as client:
        client.headers.update({"Authorization": f"Bearer {access_token}"})
        yield client

@pytest.mark.asyncio
async def test_register_user():
    user_email = f"register_{uuid.uuid4()}@example.com"
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/register", json={"email": user_email, "password": "password123"})
        assert response.status_code == 201
        assert response.json()["message"] == "User created successfully"

        # Try registering the same email again
        response = await client.post("/auth/register", json={"email": user_email, "password": "password123"})
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_for_access_token(test_user):
     async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/auth/login", data={"username": test_user["email"], "password": test_user["password"]})
        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_create_and_list_groups(authenticated_client: AsyncClient, test_user):
    group_name = f"Test Group {uuid.uuid4()}"
    group_payload = {
        "name": group_name,
        "members": [
            {"alias": "Researcher", "role_prompt": "Research things.", "tools": ["web_search"]}
        ]
    }
    response = await authenticated_client.post("/groups/", json=group_payload)
    assert response.status_code == 201
    created_group = response.json()
    assert created_group["name"] == group_name
    assert "id" in created_group

    response = await authenticated_client.get("/groups/")
    assert response.status_code == 200
    groups_list = response.json()
    assert isinstance(groups_list, list)
    assert any(g["id"] == created_group["id"] and g["name"] == group_name for g in groups_list)

@pytest.mark.asyncio
async def test_get_group_details(authenticated_client: AsyncClient, db_session_fixture: AsyncSessionLocal, test_user):
    # Create a group directly in DB for this test or use the API
    group = ChatGroup(name=f"Detail Test Group {uuid.uuid4()}", owner_id=test_user["id"])
    member1 = GroupMember(alias="Agent1", system_prompt="Prompt1", provider="openai", model="gpt-4o", temperature=0.1, group=group)
    # The Orchestrator is auto-added by the create_group endpoint, so we replicate that here for consistency
    orchestrator = GroupMember(alias="Orchestrator", system_prompt="Orchestrator Prompt", provider="gemini", model="gemini-2.5-pro", temperature=0.1, group=group)

    db_session_fixture.add_all([group, member1, orchestrator])
    await db_session_fixture.commit()
    await db_session_fixture.refresh(group)
    
    response = await authenticated_client.get(f"/groups/{group.id}")
    assert response.status_code == 200
    group_details = response.json()
    assert group_details["id"] == str(group.id)
    assert group_details["name"] == group.name
    assert group_details["owner_id"] == str(test_user["id"])
    assert len(group_details["members"]) == 2 # Agent1 + Orchestrator
    
    member_aliases = {m["alias"] for m in group_details["members"]}
    assert "Agent1" in member_aliases
    assert "Orchestrator" in member_aliases

    # Test not found
    non_existent_uuid = uuid.uuid4()
    response = await authenticated_client.get(f"/groups/{non_existent_uuid}")
    assert response.status_code == 404

    # Test forbidden (create another user and group)
    other_user_email = f"otheruser_{uuid.uuid4()}@example.com"
    other_user_password = "otherpassword"
    other_user = User(email=other_user_email, hashed_password=get_password_hash(other_user_password))
    db_session_fixture.add(other_user)
    await db_session_fixture.commit()
    await db_session_fixture.refresh(other_user)
    
    other_group = ChatGroup(name="Other's Group", owner_id=other_user.id)
    db_session_fixture.add(other_group)
    await db_session_fixture.commit()
    await db_session_fixture.refresh(other_group)

    response = await authenticated_client.get(f"/groups/{other_group.id}") # Current client is test_user
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_message_history(authenticated_client: AsyncClient, db_session_fixture: AsyncSessionLocal, test_user):
    group = ChatGroup(name=f"Message History Group {uuid.uuid4()}", owner_id=test_user["id"])
    db_session_fixture.add(group)
    await db_session_fixture.commit()
    await db_session_fixture.refresh(group)

    # Add some messages
    messages_data = []
    for i in range(5):
        msg_time = datetime.now(timezone.utc) - timedelta(minutes=i*5)
        msg = Message(
            group_id=group.id,
            turn_id=uuid.uuid4(),
            sender_alias=f"Sender{i}",
            content=f"Message content {i}",
            timestamp=msg_time
        )
        messages_data.append(msg)
    db_session_fixture.add_all(messages_data)
    await db_session_fixture.commit()

    # Test basic retrieval
    response = await authenticated_client.get(f"/groups/{group.id}/messages?limit=3")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 3
    assert history[0]["content"] == "Message content 2" # Oldest of the 3 (4,3,2)
    assert history[2]["content"] == "Message content 0" # Newest of the 3

    # Test pagination with before_timestamp
    # Get timestamp of "Message content 2" (which was history[0] in previous call)
    # The messages are returned chronologically, so history[0] is the oldest of the batch.
    # messages_data was added with 0 being newest, 4 being oldest.
    # So, messages_data[2] is "Message content 2"
    # Its timestamp is messages_data[2].timestamp
    
    # To get messages older than "Message content 2"
    # We need the timestamp of messages_data[2]
    before_ts = messages_data[2].timestamp.isoformat()
    
    response = await authenticated_client.get(f"/groups/{group.id}/messages?limit=5&before_timestamp={before_ts}")
    assert response.status_code == 200
    older_history = response.json()
    assert len(older_history) == 2 # Should be "Message content 3" and "Message content 4"
    assert older_history[0]["content"] == "Message content 4"
    assert older_history[1]["content"] == "Message content 3"

    # Test on a group the user doesn't own or a non-existent group
    non_existent_uuid = uuid.uuid4()
    response = await authenticated_client.get(f"/groups/{non_existent_uuid}/messages")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message(authenticated_client: AsyncClient, db_session_fixture: AsyncSessionLocal, test_user, monkeypatch):
    # Mock arq_pool
    class MockArqPool:
        def __init__(self):
            self.enqueued_jobs = []
        async def enqueue_job(self, *args, **kwargs):
            self.enqueued_jobs.append({"args": args, "kwargs": kwargs})
            return "mock_job_id"

    mock_pool = MockArqPool()
    monkeypatch.setattr("backend.api_gateway.app.api.routers.groups.get_arq_pool", lambda: mock_pool)
    
    group = ChatGroup(name=f"Send Message Group {uuid.uuid4()}", owner_id=test_user["id"])
    db_session_fixture.add(group)
    await db_session_fixture.commit()
    await db_session_fixture.refresh(group)

    message_content = "Hello, agent!"
    response = await authenticated_client.post(f"/groups/{group.id}/messages", json={"content": message_content})
    assert response.status_code == 202 # Accepted
    sent_message_data = response.json()
    assert sent_message_data["content"] == message_content
    assert sent_message_data["sender_alias"] == "User"
    assert "id" in sent_message_data
    assert "turn_id" in sent_message_data

    # Verify message in DB
    msg_from_db = await db_session_fixture.get(Message, uuid.UUID(sent_message_data["id"]))
    assert msg_from_db is not None
    assert msg_from_db.content == message_content

    # Verify job enqueued
    assert len(mock_pool.enqueued_jobs) == 1
    enqueued_job = mock_pool.enqueued_jobs[0]
    assert enqueued_job["args"][0] == "start_turn"
    assert enqueued_job["kwargs"]["group_id"] == str(group.id)
    assert enqueued_job["kwargs"]["message_content"] == message_content
    assert enqueued_job["kwargs"]["message_id"] == sent_message_data["id"]


@pytest.mark.asyncio
async def test_list_available_tools(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/system/tools")
    assert response.status_code == 200
    tools_info = response.json()
    assert isinstance(tools_info, list)
    
    web_search_tool = next((t for t in tools_info if t["name"] == "web_search"), None)
    assert web_search_tool is not None
    assert "description" in web_search_tool
    assert "args_schema" in web_search_tool
    assert web_search_tool["args_schema"]["type"] == "object"
    assert "query" in web_search_tool["args_schema"]["properties"]


@pytest.mark.asyncio
async def test_list_llm_options(authenticated_client: AsyncClient):
    # Assuming OPENAI_API_KEY and GEMINI_API_KEY are set by conftest or env
    # And CLAUDE_API_KEY is not set, to test filtering
    
    # Temporarily unset Claude API key for this test if it was set by global env
    original_claude_key = os.environ.get("CLAUDE_API_KEY")
    if original_claude_key:
        del os.environ["CLAUDE_API_KEY"]

    try:
        response = await authenticated_client.get("/system/llm-options")
        assert response.status_code == 200
        llm_options = response.json()
        assert isinstance(llm_options, list)

        provider_names = {opt["provider_name"] for opt in llm_options}
        assert "openai" in provider_names
        assert "gemini" in provider_names
        assert "claude" not in provider_names # Because CLAUDE_API_KEY is not set

        openai_provider = next((p for p in llm_options if p["provider_name"] == "openai"), None)
        assert openai_provider is not None
        assert len(openai_provider["models"]) > 0
        assert any(m["id"] == "gpt-4o" for m in openai_provider["models"])

    finally:
        # Restore Claude API key if it was originally set
        if original_claude_key:
            os.environ["CLAUDE_API_KEY"] = original_claude_key
        # Ensure other keys are also present for other tests if they were manipulated
        os.environ.setdefault("OPENAI_API_KEY", "dummy_openai_key")
        os.environ.setdefault("GEMINI_API_KEY", "dummy_gemini_key")