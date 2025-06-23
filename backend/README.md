# Synapse Multi-Agent System: Backend Services

Welcome to the backend of the Synapse Multi-Agent System! This directory houses the core services that power our intelligent, collaborative AI agent platform. The backend is designed as a set of microservices that communicate asynchronously via task queues, ensuring scalability, resilience, and maintainability.

The primary responsibilities of the backend include:
- Managing user authentication and sessions.
- Handling API requests for creating and managing chat groups and agents.
- Orchestrating complex multi-agent conversations using a stateful graph.
- Executing individual agent tasks, including LLM calls and tool usage.
- Persisting conversation history and application state.
- Streaming real-time updates to connected clients via WebSockets.

## Table of Contents

- [Architecture Overview](#architecture-overview)
  - [Core Components](#core-components)
  - [Technology Stack](#technology-stack)
- [API Endpoints Summary](#api-endpoints-summary)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Configuration (`.env`)](#environment-configuration-env)
  - [Building and Running with Docker Compose](#building-and-running-with-docker-compose)
  - [Database Migrations (Alembic)](#database-migrations-alembic)
- [Development Workflow](#development-workflow)
  - [Code Changes & Hot Reloading](#code-changes--hot-reloading)
  - [Running Tests](#running-tests)
  - [Managing Database Schema (Alembic)](#managing-database-schema-alembic)
  - [API Documentation (Swagger/ReDoc)](#api-documentation-swaggerredoc)
  - [Viewing Logs](#viewing-logs)
- [Architectural Deep Dive](#architectural-deep-dive)
  - [The Request Lifecycle: A User's Message](#the-request-lifecycle-a-users-message)
  - [State Management with LangGraph](#state-management-with-langgraph)
  - [Real-time Communication via WebSockets](#real-time-communication-via-websockets)
  - [Error Responses](#error-responses)
- [Backend Directory Structure](#backend-directory-structure)
- [Contributing](#contributing)

## Architecture Overview

The backend is built on a distributed, message-driven architecture. Services are decoupled and communicate asynchronously via a Redis-based message queue (ARQ). This design ensures scalability, resilience, and maintainability.

```mermaid
graph TD
    subgraph User
        Client[Client Browser/Application]
    end

    subgraph Infrastructure
        Postgres[(PostgreSQL Database)]
        Redis["Redis ARQ Task Queues LangGraph Checkpoints Pub/Sub Channels"]
    end

    subgraph Backend Services
        API["API Gateway (FastAPI, Uvicorn)"]
        Orchestrator["Orchestrator Service (ARQ Worker, LangGraph)"]
        Workers["Execution Workers (ARQ Worker, LangChain)"]
    end

    Client -- HTTP/REST & WebSocket --> API

    API -- Enqueues 'start_turn' job --> Redis
    API -- Reads/Writes User/Group data --> Postgres
    API -- Subscribes to Pub/Sub channel --> Redis
    API -- Broadcasts WebSocket messages --> Client

    Orchestrator -- Consumes jobs from 'orchestrator_queue' --> Redis
    Orchestrator -- Enqueues 'run_agent_llm'/'run_tool' jobs to 'execution_queue' --> Redis
    Orchestrator -- Writes/Reads graph state (checkpoints) --> Redis
    Orchestrator -- Publishes messages to Pub/Sub channel --> Redis
    Orchestrator -- Writes message data to DB --> Postgres

    Workers -- Consumes jobs from 'execution_queue' --> Redis
    Workers -- Enqueues 'update_graph_with_message' job to 'orchestrator_queue' --> Redis
```

### Core Components

The backend is composed of three main services and a shared library:

1.  **API Gateway (`api_gateway`)**
    *   **Purpose:** The main public-facing entry point for all client interactions.
    *   **Responsibilities:** User auth, CRUD for groups/agents, receiving messages, WebSocket management, task enqueuing.
    *   **Key Technologies:** FastAPI, Uvicorn, SQLAlchemy (Async), Alembic, ARQ (client), Pydantic.
2.  **Orchestrator Service (`orchestrator_service`)**
    *   **Purpose:** Manages conversation flow using LangGraph.
    *   **Responsibilities:** Consumes tasks, executes stateful graph, persists messages/state, dispatches tasks to Execution Workers, publishes to Redis Pub/Sub.
    *   **Key Technologies:** ARQ (worker), LangGraph, SQLAlchemy (Async), Pydantic.
3.  **Execution Workers (`execution_workers`)**
    *   **Purpose:** Perform LLM calls and tool executions.
    *   **Responsibilities:** Consumes tasks, interacts with LLMs/tools, enqueues results back to Orchestrator.
    *   **Key Technologies:** ARQ (worker), LangChain, Pydantic.
4.  **Shared Library (`shared`)**
    *   **Purpose:** Common code, models, schemas, utilities.

### Technology Stack

-   **Programming Language:** Python 3.11
-   **Web Framework (API Gateway):** FastAPI
-   **Asynchronous Task Queues:** ARQ (Async Redis Queue)
-   **Database:** PostgreSQL 16
-   **ORM & Migrations:** SQLAlchemy (async support), Alembic
-   **AI Orchestration & LLM Interaction:** LangChain, LangGraph
-   **Data Validation & Settings Management:** Pydantic, Pydantic-Settings
-   **Caching, Messaging & Checkpointing Broker:** Redis
-   **Containerization:** Docker, Docker Compose
-   **Logging:** Structlog
-   **Authentication:** JWT with Passlib

## API Endpoints Summary

This section provides a quick overview of the available API endpoints. For detailed request/response schemas and parameters, refer to the auto-generated API documentation (Swagger/ReDoc). All endpoints requiring authentication expect a JWT Bearer token in the `Authorization` header.

**Authentication (`/auth`)**
*   `POST /auth/register`: Register a new user.
*   `POST /auth/login`: Log in and receive an access token.
*   `GET /auth/me`: Get details of the currently authenticated user.

**Chat Groups (`/groups`)**
*   `POST /groups/`: Create a new chat group (including initial agents).
*   `GET /groups/`: List all chat groups owned by the current user.
*   `GET /groups/{group_id}`: Get detailed information about a specific chat group, including its members.
*   `PUT /groups/{group_id}`: Update the name of a specific chat group.
*   `DELETE /groups/{group_id}`: Delete a specific chat group and its associated data (members, messages).

**Group Members (Agents) (`/groups/{group_id}/members`)**
*   `POST /groups/{group_id}/members`: Add a new agent to a specific chat group.
*   `PUT /groups/{group_id}/members/{member_id}`: Update an existing agent within a group.
*   `DELETE /groups/{group_id}/members/{member_id}`: Remove an agent from a group.
    *Note: The "Orchestrator" agent, automatically added to each group, cannot be modified or deleted via these endpoints.*

**Messages (`/groups/{group_id}/messages`)**
*   `POST /groups/{group_id}/messages`: Send a new message to a chat group, initiating a new turn.
*   `GET /groups/{group_id}/messages`: Retrieve the message history for a chat group (supports pagination).

**System Information (`/system`)**
*   `GET /system/tools`: List all available tools that agents can use, including their descriptions and argument schemas.
*   `GET /system/llm-options`: List available LLM providers and their models that can be configured for agents.

**WebSockets (`/ws`)**
*   `GET /ws/{group_id}`: Establish a WebSocket connection for real-time message streaming for a specific group. Requires token authentication via query parameter or `Authorization` header.

**Health Check**
*   `GET /health`: Basic health check endpoint.

## Getting Started

Follow these steps to get the entire backend stack running locally for development.

### Prerequisites

-   [Docker](https://docs.docker.com/get-docker/)
-   [Docker Compose](https://docs.docker.com/compose/install/)

### Environment Configuration (`.env`)

All services are configured using environment variables, loaded from a `.env` file in the project root directory.

1.  **Create a `.env` file** in the project root.
2.  Populate it with the necessary configuration. Refer to `backend/shared/app/core/config.py` for all possible settings. A minimal example:

    ```dotenv
    # .env

    # --- PostgreSQL Settings ---
    POSTGRES_DB=synapse
    POSTGRES_USER=synapse_user
    POSTGRES_PASSWORD=your_strong_postgres_password # CHANGE THIS!
    DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

    # --- Redis Settings ---
    REDIS_URL=redis://redis:6379/0

    # --- Security Settings ---
    SECRET_KEY=your_very_strong_and_unique_secret_key_here # CHANGE THIS!
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=1440

    # --- LLM Provider API Keys ---
    OPENAI_API_KEY=sk-your_openai_api_key
    GEMINI_API_KEY=your_google_gemini_api_key
    CLAUDE_API_KEY=sk-ant-your_anthropic_claude_api_key
    TAVILY_API_KEY=tvly-your_tavily_api_key

    # --- Logging ---
    LOG_LEVEL=INFO
    ```

### Building and Running with Docker Compose

1.  Navigate to the project root directory.
2.  Build and start the services: `docker-compose up --build` (or `docker-compose up --build -d` for detached mode).
3.  Services: API Gateway (`http://localhost:8000`), PostgreSQL (`localhost:5432`), Redis (`localhost:6379`).

### Database Migrations (Alembic)

Migrations are managed by Alembic within the `api_gateway` service.
1.  Ensure services are running: `docker-compose up`.
2.  Apply migrations: `docker-compose exec api_gateway alembic upgrade head`.

## Development Workflow

### Code Changes & Hot Reloading

Service directories are mounted as volumes. `api_gateway` (Uvicorn) supports hot reloading. ARQ workers (`orchestrator_service`, `execution_workers`) may require a restart (`docker-compose restart <service_name>`) to pick up changes unless run with watch options.

### Running Tests

Tests are in `tests/`.
1.  Install test dependencies (from project root):
    ```bash
    python -m pip install -r requirements.dev.txt
    python -m pip install -r backend/api_gateway/requirements.txt
    # ... install requirements for orchestrator and execution_workers too
    ```
2.  Run Pytest: `pytest -q`

### Managing Database Schema (Alembic)

-   **Creating a New Migration:** After modifying SQLAlchemy models in `backend/shared/app/models/`:
    1.  Ensure models are imported in `backend/api_gateway/alembic/env.py`.
    2.  Execute: `docker-compose exec api_gateway alembic revision --autogenerate -m "Your migration message"`
    3.  Inspect and adjust the generated script in `backend/api_gateway/alembic/versions/`.
-   **Applying Migrations:** `docker-compose exec api_gateway alembic upgrade head`
-   **Downgrading:** `docker-compose exec api_gateway alembic downgrade -1`

### API Documentation (Swagger/ReDoc)

Interactive API documentation is available when `api_gateway` is running:
-   **Swagger UI:** `http://localhost:8000/docs`
-   **ReDoc:** `http://localhost:8000/redoc`

### Viewing Logs

-   All services: `docker-compose logs -f`
-   Specific service: `docker-compose logs -f api_gateway`

## Architectural Deep Dive

### The Request Lifecycle: A User's Message

Understanding the flow of a single message from user to agent response:
1.  **Ingestion (API Gateway):**
    *   User sends a message (e.g., `POST /groups/{group_id}/messages`).
    *   API Gateway authenticates, validates, persists the initial user message to PostgreSQL.
    *   A `start_turn` task is enqueued to `orchestrator_queue` on Redis. This task includes `group_id`, `message_content`, `user_id`, the persisted `message_id`, and a new unique `turn_id`.
    *   The `turn_id` is crucial: it links the initial user message and all subsequent agent/tool messages generated in response to that specific user input.
    *   API Gateway returns `202 Accepted`.
2.  **Orchestration Begins (Orchestrator Service):**
    *   `orchestrator_service` picks up `start_turn`. Fetches group members.
    *   LangGraph app is compiled with `AsyncRedisSaver` checkpointer.
    *   Graph invoked with initial state (user message, group info, `turn_id`).
3.  **Graph Execution & Routing (Orchestrator Service):**
    *   `router_node` processes state, determines next action.
    *   Messages (from user or agents) are persisted to PostgreSQL via `_persist_new_messages` (within `router_node` or `sync_to_postgres_node`). This function also publishes them to a Redis Pub/Sub channel (e.g., `group:<group_id>`).
4.  **Dispatch to Execution (Orchestrator Service to Execution Workers):**
    *   If an agent or tool needs to run, `dispatcher_node` enqueues a task (e.g., `run_agent_llm`, `run_tool`) to `execution_queue`. Payload includes context and `thread_id` (which is `group_id`).
    *   LangGraph invocation ends; state saved to Redis by checkpointer.
5.  **Task Execution (Execution Workers):**
    *   `execution_workers` pick up task, perform LLM call or tool execution.
6.  **Result Return (Execution Workers to Orchestrator Service):**
    *   Worker packages result (e.g., `AIMessage`, `ToolMessage`), enqueues `update_graph_with_message` to `orchestrator_queue` with `thread_id` and serialized message.
7.  **Graph Continuation (Orchestrator Service):**
    *   `orchestrator_service` picks up `update_graph_with_message`.
    *   LangGraph app re-invoked; checkpointer loads state, appends new message. Graph continues.
    *   This loop (Orchestrator -> Persist/Publish -> Dispatcher -> Worker -> Orchestrator) continues until the `router_node` determines the turn is complete for the current `turn_id` (e.g., Orchestrator sends "TASK_COMPLETE") or requires further user input.
8.  **Real-time Update (API Gateway to Client):**
    *   API Gateway's WebSocket handlers (listening to Redis Pub/Sub) receive new messages published by the Orchestrator and broadcast them to clients for that group.

### State Management with LangGraph

The `orchestrator_service` uses LangGraph for stateful multi-agent conversations.
-   **`GraphState`:** Defines the conversation turn's state (message history, group config, active agents, `turn_id`, etc.).
-   **Nodes:** Asynchronous functions operating on `GraphState` (e.g., `router_node`, `dispatcher_node`).
-   **Edges:** Define control flow.
-   **Checkpointer (`AsyncRedisSaver`):** Saves `GraphState` to Redis after each invocation, keyed by `thread_id` (`group_id`), enabling seamless resumption across distributed tasks.

### Real-time Communication via WebSockets

1.  Client connects to API Gateway (`/ws/{group_id}`) with auth token.
2.  API Gateway authenticates, verifies group access, subscribes to Redis Pub/Sub channel (e.g., `group:<uuid>`).
3.  Orchestrator's `_persist_new_messages` function (in `router_node` or `sync_to_postgres_node`) saves messages to DB and `PUBLISH`es a JSON representation to Redis Pub/Sub.
4.  API Gateway's WebSocket listener receives from Redis, broadcasts to connected clients.

**WebSocket Message Format:**
When a new message is processed by the orchestrator and persisted, it's broadcasted to connected WebSocket clients for the relevant group. The JSON payload for each message is:
```json
{
  "id": "message_uuid_string",        // Unique ID of the message
  "turn_id": "turn_uuid_string",        // ID of the current conversation turn
  "sender_alias": "string",             // Alias of the sender (e.g., "User", "Orchestrator", "AgentName", "ToolName")
  "content": "string",                  // The message content
  "timestamp": "iso_datetime_string",   // Timestamp of when the message was broadcast (UTC)
  "meta": { ... }                       // Full LangChain message dictionary (can include tool_calls, etc.)
  "parent_message_id": "uuid_string"    // Optional: ID of the parent message for threading
}
```

### Error Responses

The API uses standard HTTP status codes for errors.
-   **`422 Unprocessable Entity`**: For validation errors (e.g., invalid input data). The response body will be a JSON object detailing the validation errors, as provided by FastAPI:
    ```json
    {
      "detail": [
        {
          "loc": ["body", "field_name"],
          "msg": "Validation error message",
          "type": "validation_error_type"
        }
      ]
    }
    ```
-   **Other Client Errors (400, 401, 403, 404, 409)** and **Server Errors (500+)**: The response body will typically be a JSON object with a "detail" key:
    ```json
    {
      "detail": "A descriptive error message string"
    }
    ```
    Examples:
    *   `401 Unauthorized`: `{"detail": "Not authenticated"}` or `{"detail": "Could not validate credentials"}`
    *   `403 Forbidden`: `{"detail": "Not authorized to access this resource"}`
    *   `404 Not Found`: `{"detail": "Resource not found"}`
    *   `409 Conflict`: `{"detail": "Resource conflict, e.g., alias already exists"}`

## Backend Directory Structure
(This structure remains largely the same as initially provided, but the context of new files like `system.py` is now clearer)
```
backend/
├── api_gateway/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routers/    # auth.py, groups.py, system.py (new)
│   │   │   └── websockets.py
│   │   ├── core/
│   │   └── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── execution_workers/
│   ├── app/
│   │   └── worker.py
│   ├── Dockerfile
│   └── requirements.txt
├── orchestrator_service/
│   ├── app/
│   │   ├── graph/
│   │   └── worker.py (and main.py)
│   ├── Dockerfile
│   └── requirements.txt
└── shared/
    └── app/
        ├── agents/
        ├── core/
        ├── models/
        ├── schemas/        # auth.py, chat.py, groups.py, system.py (new)
        ├── utils/
        └── db.py
```

## Contributing

When contributing to the backend:
- Adhere to Python best practices.
- Write clear, concise, and well-documented code.
- Update/add Pydantic schemas for API/data changes.
- Generate and test Alembic migrations for DB model changes.
- Add tests for new features/bug fixes.
- Ensure services build and run correctly with Docker Compose.
- Keep this README updated.
