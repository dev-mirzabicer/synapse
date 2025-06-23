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
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Configuration (`.env`)](#environment-configuration-env)
  - [Building and Running with Docker Compose](#building-and-running-with-docker-compose)
  - [Database Migrations (Alembic)](#database-migrations-alembic)
- [Development Workflow](#development-workflow)
  - [Code Changes & Hot Reloading](#code-changes--hot-reloading)
  - [Running Tests](#running-tests)
  - [Managing Database Schema (Alembic)](#managing-database-schema-alembic)
  - [API Documentation](#api-documentation)
  - [Viewing Logs](#viewing-logs)
- [Architectural Deep Dive](#architectural-deep-dive)
  - [The Request Lifecycle: A User's Message](#the-request-lifecycle-a-users-message)
  - [State Management with LangGraph](#state-management-with-langgraph)
  - [Real-time Communication via WebSockets](#real-time-communication-via-websockets)
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
    *   **Purpose:** The main public-facing entry point for all client interactions (e.g., frontend application). It handles HTTP requests and WebSocket connections.
    *   **Responsibilities:**
        *   User registration and login (JWT-based authentication).
        *   CRUD operations for chat groups and their members.
        *   Receiving user messages and initiating new conversation turns.
        *   Managing WebSocket connections for real-time event streaming to clients.
        *   Enqueuing tasks for the Orchestrator Service.
    *   **Key Technologies:** FastAPI, Uvicorn, SQLAlchemy (Async), Alembic, ARQ (client), Pydantic.
    *   **Entry Point:** `api_gateway/app/main.py` (FastAPI application)

2.  **Orchestrator Service (`orchestrator_service`)**
    *   **Purpose:** The "brain" of the multi-agent system. It manages the flow of conversation and coordinates agent actions using a stateful graph.
    *   **Responsibilities:**
        *   Consuming tasks from the `orchestrator_queue` (e.g., `start_turn`, `update_graph_with_message`).
        *   Using LangGraph to define and execute a stateful conversation graph.
        *   Routing messages between agents based on predefined logic and mentions.
        *   Persisting messages to PostgreSQL and graph state to Redis (for checkpoints).
        *   Dispatching tasks (agent LLM calls, tool executions) to Execution Workers.
        *   Publishing new messages to Redis Pub/Sub for real-time client updates.
    *   **Key Technologies:** ARQ (worker), LangGraph, SQLAlchemy (Async), Pydantic.
    *   **Entry Point:** `orchestrator_service/app/worker.py` (defines `WorkerSettings` for ARQ CLI)
    *   **Graph Definition:** `orchestrator_service/app/graph/`

3.  **Execution Workers (`execution_workers`)**
    *   **Purpose:** Perform the actual "work" delegated by the Orchestrator, such as running an LLM or a tool.
    *   **Responsibilities:**
        *   Consuming tasks from the `execution_queue` (e.g., `run_tool`, `run_agent_llm`).
        *   Interacting with various LLM providers (OpenAI, Gemini, Claude) via LangChain.
        *   Executing registered tools (e.g., web search via Tavily).
        *   Enqueuing results (agent responses, tool outputs) back to the Orchestrator Service.
    *   **Key Technologies:** ARQ (worker), LangChain, Pydantic.
    *   **Entry Point:** `execution_workers/app/worker.py` (defines `WorkerSettings` for ARQ CLI)

4.  **Shared Library (`shared`)**
    *   **Purpose:** Contains common code, models, schemas, and utilities used across multiple backend services to promote DRY principles and consistency.
    *   **Key Submodules:**
        *   `agents/`: Prompts, agent running logic, tool definitions.
        *   `core/`: Application configuration (`config.py`), logging setup (`logging.py`).
        *   `db.py`: Database engine and asynchronous session management.
        *   `models/`: SQLAlchemy ORM models (e.g., `User`, `ChatGroup`, `Message`).
        *   `schemas/`: Pydantic schemas for data validation and API contracts.
        *   `utils/`: Miscellaneous utility functions (e.g., message serialization/deserialization).

### Technology Stack

-   **Programming Language:** Python 3.11
-   **Web Framework (API Gateway):** FastAPI
-   **Asynchronous Task Queues:** ARQ (Async Redis Queue)
-   **Database:** PostgreSQL 16
-   **ORM & Migrations:** SQLAlchemy (async support), Alembic
-   **AI Orchestration & LLM Interaction:** LangChain, LangGraph
-   **Data Validation & Settings Management:** Pydantic, Pydantic-Settings
-   **Caching, Messaging & Checkpointing Broker:** Redis (via `redis/redis-stack-server`)
-   **Containerization:** Docker, Docker Compose
-   **Logging:** Structlog (for structured JSON logging)
-   **Authentication:** JWT (JSON Web Tokens) with Passlib for password hashing

## Getting Started

Follow these steps to get the entire backend stack running locally for development.

### Prerequisites

-   [Docker](https://docs.docker.com/get-docker/)
-   [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)

### Environment Configuration (`.env`)

All services are configured using environment variables, loaded from a `.env` file in the project root directory (the same directory as `docker-compose.yml`).

1.  **Create a `.env` file** in the project root.
2.  Populate it with the necessary configuration. Refer to `backend/shared/app/core/config.py` for all possible settings. A minimal example:

    ```dotenv
    # .env

    # --- PostgreSQL Settings ---
    # These must match the 'environment' section for the 'postgres' service in docker-compose.yml
    POSTGRES_DB=synapse
    POSTGRES_USER=synapse_user
    POSTGRES_PASSWORD=your_strong_postgres_password # CHANGE THIS!
    DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

    # --- Redis Settings ---
    # This should match the 'redis' service name in docker-compose.yml
    REDIS_URL=redis://redis:6379/0

    # --- Security Settings ---
    # Generate a strong key with: openssl rand -hex 32
    SECRET_KEY=your_very_strong_and_unique_secret_key_here # CHANGE THIS!
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=1440 # 24 hours

    # --- LLM Provider API Keys (provide only those you intend to use) ---
    OPENAI_API_KEY=sk-your_openai_api_key
    GEMINI_API_KEY=your_google_gemini_api_key
    CLAUDE_API_KEY=sk-ant-your_anthropic_claude_api_key
    TAVILY_API_KEY=tvly-your_tavily_api_key # For web_search tool

    # --- Logging ---
    # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL=INFO
    ```

    **Important:** Replace placeholder values (like passwords and API keys) with your actual credentials.

### Building and Running with Docker Compose

This is the recommended way to run all backend services along with PostgreSQL and Redis.

1.  **Navigate to the project root directory** (where `docker-compose.yml` is located).
2.  **Build and start the services:**
    ```bash
    docker-compose up --build
    ```
    To run in detached mode (in the background):
    ```bash
    docker-compose up --build -d
    ```
3.  **Services will be available at:**
    *   API Gateway: `http://localhost:8000`
    *   PostgreSQL: `localhost:5432` (accessible from host, or `postgres:5432` from other containers)
    *   Redis: `localhost:6379` (accessible from host, or `redis:6379` from other containers)

### Database Migrations (Alembic)

Database schema migrations are managed by Alembic. The migration scripts and configuration reside within the `api_gateway` service, as it's a primary interactor with the database schema, though models are defined in the `shared` library.

**Initial Setup:** The first time you start the stack, or if the database is new, you need to apply the schema.
1.  Ensure the services (especially `postgres`) are running: `docker-compose up`.
2.  In a separate terminal, execute the Alembic upgrade command inside the `api_gateway` container:
    ```bash
    docker-compose exec api_gateway alembic upgrade head
    ```
    This applies all pending migrations up to the latest version.

## Development Workflow

### Code Changes & Hot Reloading

The service directories (`api_gateway`, `orchestrator_service`, `execution_workers`, `shared`) are mounted as volumes in `docker-compose.yml`. This means code changes made on your host machine are reflected inside the containers.
-   The `api_gateway` (Uvicorn) is configured for hot reloading.
-   The ARQ workers (`orchestrator_service`, `execution_workers`) will also pick up changes on restart or if run with watch options (though the current Docker CMDs run them directly). For ARQ worker hot-reloading during active development, you might consider modifying the CMD in their Dockerfiles to use `watchfiles` or similar, or manually restart the specific service: `docker-compose restart orchestrator_service`.


### Running Tests

Tests are located in the project root's `tests/` directory and are designed to be run on your host machine against the services running in Docker (or against mocked/in-memory components where appropriate).

1.  **Install Test Dependencies:** From the project root directory:
    ```bash
    python -m pip install -r requirements.dev.txt
    python -m pip install -r backend/api_gateway/requirements.txt
    python -m pip install -r backend/orchestrator_service/requirements.txt
    python -m pip install -r backend/execution_workers/requirements.txt
    ```
2.  **Run Pytest:**
    ```bash
    pytest -q
    ```
    The `python-tests.yml` GitHub Actions workflow also follows this dependency installation pattern.


### Managing Database Schema (Alembic)

-   **Creating a New Migration:** After modifying SQLAlchemy models in `backend/shared/app/models/`:
    1.  Ensure your models are correctly imported in `backend/api_gateway/alembic/env.py` (specifically, ensure `target_metadata = Base.metadata` includes all your models).
    2.  Execute inside the `api_gateway` container:
        ```bash
        docker-compose exec api_gateway alembic revision --autogenerate -m "Your descriptive migration message"
        ```
    3.  Inspect the generated migration script in `backend/api_gateway/alembic/versions/` and adjust if necessary.
-   **Applying Migrations:**
    ```bash
    docker-compose exec api_gateway alembic upgrade head
    ```
-   **Downgrading Migrations:** To revert the last applied migration:
    ```bash
    docker-compose exec api_gateway alembic downgrade -1
    ```
    To revert to a specific revision: `alembic downgrade <revision_id>`

### API Documentation

Once the `api_gateway` service is running, interactive API documentation is available:
-   **Swagger UI:** `http://localhost:8000/docs`
-   **ReDoc:** `http://localhost:8000/redoc`

### Viewing Logs

To view logs from the running services:
-   For all services (aggregated and streaming):
    ```bash
    docker-compose logs -f
    ```
-   For a specific service (e.g., `api_gateway`):
    ```bash
    docker-compose logs -f api_gateway
    ```
    Structured JSON logging (via Structlog) is configured, which can be helpful for parsing and analysis.

## Architectural Deep Dive

### The Request Lifecycle: A User's Message

Understanding the flow of a single message from user to agent response:
1.  **Ingestion (API Gateway):**
    *   User sends a message (e.g., via HTTP POST to `/groups/{group_id}/messages`).
    *   The API Gateway authenticates the user and validates the request data.
    *   The initial user message is persisted to the PostgreSQL database (as a `Message` record).
    *   A `start_turn` task is enqueued to the `orchestrator_queue` on Redis. The payload includes `group_id`, `message_content`, `user_id`, `message_id`, and a new `turn_id`.
    *   The API Gateway returns a `202 Accepted` response.
2.  **Orchestration Begins (Orchestrator Service):**
    *   An ARQ worker from the `orchestrator_service` picks up the `start_turn` task.
    *   It fetches group member configurations from the database.
    *   The LangGraph application is compiled with an `AsyncRedisSaver` checkpointer.
    *   The graph is invoked with the initial state, including the user's message.
3.  **Graph Execution & Routing (Orchestrator Service):**
    *   The graph's `router_node` processes the current state (including new messages) and determines the next action (e.g., delegate to an agent, wait for tool, or end turn).
    *   Messages are persisted to PostgreSQL via `_persist_new_messages`, which also publishes them to a Redis Pub/Sub channel (e.g., `group:<group_id>`).
4.  **Dispatch to Execution (Orchestrator Service to Execution Workers):**
    *   If an agent needs to run or a tool needs to be executed, the `dispatcher_node` enqueues a task (e.g., `run_agent_llm` or `run_tool`) to the `execution_queue` on Redis. The payload includes necessary context like messages, agent config, and the `thread_id` (which is the `group_id` for checkpointing).
    *   The LangGraph then typically ends its current invocation, with its state automatically saved to Redis by the checkpointer.
5.  **Task Execution (Execution Workers):**
    *   An ARQ worker from the `execution_workers` pool picks up the task.
    *   It performs the LLM call (e.g., using LangChain with OpenAI, Gemini) or executes the specified tool.
6.  **Result Return (Execution Workers to Orchestrator Service):**
    *   The worker packages the result (e.g., an `AIMessage` from an LLM or a `ToolMessage` from a tool) into a serializable dictionary.
    *   It enqueues an `update_graph_with_message` task back to the `orchestrator_queue`, including the `thread_id` and the serialized message.
7.  **Graph Continuation (Orchestrator Service):**
    *   The `orchestrator_service` picks up the `update_graph_with_message` task.
    *   It deserializes the new message.
    *   The LangGraph application (re-compiled with the checkpointer) is invoked again. The checkpointer loads the previous state for the `thread_id` from Redis, appends the new message, and the graph continues execution from where it left off (typically starting at the `router_node` again).
    *   This loop (Orchestrator -> Persist/Publish -> Dispatcher -> Execution Worker -> Orchestrator) continues until the `router_node` determines the turn is complete (e.g., Orchestrator sends "TASK_COMPLETE") or requires further user input.
8.  **Real-time Update (API Gateway to Client):**
    *   Throughout the process, whenever `_persist_new_messages` in the Orchestrator publishes a message to the Redis Pub/Sub channel, the API Gateway's WebSocket handlers (listening to these channels) receive the message and broadcast it to all connected clients for that specific group.

### State Management with LangGraph

The `orchestrator_service` uses LangGraph to manage complex, stateful multi-agent conversations.
-   **`GraphState` (`orchestrator_service/app/graph/state.py`):** A TypedDict defining the complete state of a conversation turn. It includes the message history, group configuration, active agents, turn count, etc.
-   **Nodes (`orchestrator_service/app/graph/nodes.py`):** Asynchronous Python functions that operate on the `GraphState`. Key nodes include:
    *   `router_node`: Determines the next step, persists messages, and decides on next actors.
    *   `dispatcher_node`: Enqueues tasks for execution workers based on `router_node`'s decision.
    *   `sync_to_postgres_node`: Ensures final messages are persisted.
-   **Edges (`orchestrator_service/app/graph/graph.py`):** Define the control flow between nodes, including conditional logic (e.g., `should_dispatch_or_end`).
-   **Checkpointer (`AsyncRedisSaver`):** The LangGraph application (`workflow`) is compiled *at runtime* within the ARQ task functions (`start_turn`, `update_graph_with_message`) with an `AsyncRedisSaver` instance. This checkpointer automatically saves the full `GraphState` to Redis after each invocation, keyed by a `thread_id` (which is the `group_id`). When the graph is invoked again for the same `thread_id`, it loads the state from Redis, allowing the conversation to resume seamlessly across distributed task executions.

### Real-time Communication via WebSockets

To provide a live chat experience, the backend pushes updates to clients:
1.  A client establishes a WebSocket connection with the **API Gateway** at `/ws/{group_id}`, providing an auth token.
2.  The API Gateway authenticates the user and verifies their access to the group.
3.  If authorized, the Gateway subscribes to a Redis Pub/Sub channel specific to that group (e.g., `group:<uuid>`).
4.  As the **Orchestrator Service** processes a turn, its `_persist_new_messages` function (within the `router_node` or `sync_to_postgres_node`) saves messages to PostgreSQL and simultaneously `PUBLISH`es a JSON representation of the new message to the corresponding Redis Pub/Sub channel.
5.  The API Gateway's WebSocket listener for that channel receives the message from Redis and broadcasts it over the appropriate WebSocket connection to all connected clients for that group.

This Pub/Sub pattern effectively decouples the web-facing API Gateway from the internal message processing logic of the Orchestrator.

## Backend Directory Structure

```
backend/
├── api_gateway/            # Handles API requests, WebSockets, user auth
│   ├── alembic/            # Database migration scripts and configuration
│   │   ├── versions/       # Individual migration files
│   │   └── env.py          # Alembic environment setup
│   ├── app/                # FastAPI application code
│   │   ├── api/            # API endpoint definitions
│   │   │   ├── routers/    # Routers for different resources (auth, groups)
│   │   │   └── websockets.py # WebSocket connection management and logic
│   │   ├── core/           # Core utilities (ARQ client, security)
│   │   └── main.py         # FastAPI app instantiation and event handlers
│   ├── Dockerfile
│   └── requirements.txt
├── execution_workers/      # Executes agent LLM calls and tools
│   ├── app/                # ARQ worker code
│   │   └── worker.py       # ARQ task definitions (run_tool, run_agent_llm) & WorkerSettings
│   ├── Dockerfile
│   └── requirements.txt
├── orchestrator_service/   # Manages multi-agent conversation flow using LangGraph
│   ├── app/                # ARQ worker and LangGraph code
│   │   ├── graph/          # LangGraph definitions
│   │   │   ├── checkpoint.py # Checkpointer setup
│   │   │   ├── graph.py    # Graph structure (nodes, edges)
│   │   │   ├── nodes.py    # Node implementation logic
│   │   │   ├── router.py   # Routing logic for the graph
│   │   │   └── state.py    # GraphState TypedDict definition
│   │   ├── main.py         # Entry point for ARQ CLI to find WorkerSettings
│   │   └── worker.py       # ARQ task definitions (start_turn, update_graph_with_message) & WorkerSettings
│   ├── Dockerfile
│   └── requirements.txt
└── shared/                 # Common code, models, schemas used by multiple services
    └── app/
        ├── agents/         # Agent prompts, runner logic, and tool definitions
        │   ├── prompts.py
        │   ├── runner.py
        │   └── tools.py
        ├── core/           # Shared configuration and logging
        │   ├── config.py   # Pydantic settings management
        │   └── logging.py  # Structlog setup
        ├── models/         # SQLAlchemy ORM models
        │   ├── base.py
        │   └── chat.py
        ├── schemas/        # Pydantic schemas for data validation and API contracts
        │   ├── auth.py
        │   ├── chat.py
        │   └── groups.py
        ├── utils/          # Common utility functions
        │   └── message_serde.py # Message serialization/deserialization
        └── db.py           # Database engine and async session management
```

## Contributing

When contributing to the backend:
- Adhere to Python best practices (e.g., PEP 8, type hinting).
- Write clear, concise, and well-documented code.
- Update or add Pydantic schemas for any API or data structure changes.
- If database models are changed, generate and test Alembic migrations.
- Add unit or integration tests for new features or bug fixes (tests are in the project root's `tests/` directory).
- Ensure all services build and run correctly with Docker Compose.
- Keep this README updated if architectural changes are made.
