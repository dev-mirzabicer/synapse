# Synapse Backend Services

This directory contains all backend microservices for the Synapse Multi-Agent Collaboration Platform. The system is designed as a set of modular, scalable, and resilient services that work together to orchestrate complex AI-driven tasks.

## Table of Contents

1.  [Architecture Overview](#1-architecture-overview)
2.  [Services](#2-services)
    *   [API Gateway (`api_gateway`)](#api-gateway-api_gateway)
    *   [Orchestrator Service (`orchestrator_service`)](#orchestrator-service-orchestrator_service)
    *   [Execution Workers (`execution_workers`)](#execution-workers-execution_workers)
    *   [Shared Logic (`shared`)](#shared-logic-shared)
3.  [Technology Stack](#3-technology-stack)
4.  [Local Development Setup](#4-local-development-setup)
    *   [Prerequisites](#prerequisites)
    *   [Configuration](#configuration)
    *   [Running the Stack](#running-the-stack)
    *   [Database Migrations](#database-migrations)
5.  [Core Concepts & Workflow](#5-core-concepts--workflow)
    *   [The Decoupled Execution Loop](#the-decoupled-execution-loop)
    *   [State Management with LangGraph](#state-management-with-langgraph)
6.  [API Endpoints](#6-api-endpoints)
7.  [Testing](#7-testing)

---

## 1. Architecture Overview

The backend follows a microservice architecture designed for scalability and separation of concerns. Communication between services is handled asynchronously via a Redis-based task queue (ARQ).

*   **`API Gateway`**: The single public-facing entry point. Handles user authentication, manages WebSocket connections for real-time updates, and validates incoming requests.
*   **`Orchestrator Service`**: The "brain" of the system. It runs a state machine (using LangGraph) to manage the flow of a conversation but does **not** perform any heavy computation itself. It dispatches tasks to the execution workers.
*   **`Execution Workers`**: The "hands" of the system. These are scalable workers that perform computationally expensive tasks like calling LLM APIs or executing tools (e.g., web search).

State persistence is handled through a dual-database approach:
*   **PostgreSQL**: The primary, long-term source of truth for all user data, group configurations, and finalized conversation histories.
*   **Redis**: Used as a high-speed cache, a message broker (ARQ), a Pub/Sub system for real-time events, and as a state backend for live LangGraph conversations (via `RedisSaver`).

 <!-- It's highly recommended to create and link a real diagram -->

## 2. Services

### API Gateway (`api_gateway`)

*   **Framework**: FastAPI
*   **Responsibilities**:
    *   User registration and JWT-based authentication (`/auth`).
    *   CRUD operations for chat groups (`/groups`).
    *   Accepting new user messages and initiating the orchestration workflow.
    *   Managing WebSocket connections (`/ws/{group_id}`) for pushing real-time updates to clients.
    *   Running database migrations via Alembic.

### Orchestrator Service (`orchestrator_service`)

*   **Framework**: ARQ (Async Task Queue) + LangGraph
*   **Responsibilities**:
    *   Listens for `start_turn` and `continue_turn` jobs from the task queue.
    *   Runs the core LangGraph state machine to determine the next logical step in a conversation.
    *   Dispatches specific, granular tasks (e.g., `run_tool`, `run_agent_llm`) to the `execution_workers`.
    *   Includes a final `sync_to_postgres` node in its graph to ensure data durability.

### Execution Workers (`execution_workers`)

*   **Framework**: ARQ (Async Task Queue)
*   **Responsibilities**:
    *   Listens for `run_tool` and `run_agent_llm` jobs.
    *   Executes the requested tool (e.g., `web_search`) with the provided arguments.
    *   Executes LLM calls for specific agents, binding the correct tools and system prompts.
    *   Updates the shared conversation state in Redis using the LangGraph checkpointer.
    *   Enqueues a `continue_turn` job for the orchestrator upon completion.

### Shared Logic (`shared`)

*   This is not a runnable service but a Python library shared across the backend services.
*   **Contents**:
    *   SQLAlchemy database models (`shared/app/models`).
    *   Pydantic API schemas (`shared/app/schemas`).
    *   Centralized application settings (`shared/app/core/config.py`).
    *   Shared business logic, such as agent runners and tool definitions (`shared/app/agents`).

## 3. Technology Stack

*   **Language**: Python 3.11+
*   **Web Framework**: FastAPI
*   **Task Queue**: ARQ
*   **AI Orchestration**: LangChain & LangGraph
*   **Primary Database**: PostgreSQL (with SQLAlchemy 2.0 and Alembic)
*   **Cache & Message Broker**: Redis
*   **Containerization**: Docker

## 4. Local Development Setup

### Prerequisites

*   Docker and Docker Compose
*   Python 3.11+ (for local tooling if needed)

### Configuration

1.  Navigate to the root of the `synapse` repository.
2.  Copy the example environment file: `cp backend/.env.example .env`.
3.  Open the `.env` file and fill in the required secrets:
    *   `SECRET_KEY`: A strong, random key for JWT signing. You can generate one with `openssl rand -hex 32`.
    *   `OPENAI_API_KEY`: Your API key for OpenAI.
    *   `TAVILY_API_KEY`: Your API key for the Tavily search service.
    *   Database and Redis settings are pre-populated for local development.

### Running the Stack

From the root of the `synapse` repository, run the following command:

```bash
docker-compose up --build
```

This will:
1.  Build the Docker images for all backend services.
2.  Start containers for PostgreSQL, Redis, and all application services.
3.  The API Gateway will be available at `http://localhost:8000`.
4.  The API documentation (Swagger UI) will be at `http://localhost:8000/docs`.

To run services in the background, use `docker-compose up -d`. To view logs, use `docker-compose logs -f <service_name>`.

### Database Migrations

All database schema changes are managed by Alembic from within the `api_gateway` service.

To create a new migration after changing a SQLAlchemy model in `shared/app/models/`:

```bash
# Ensure the postgres container is running
docker-compose up -d postgres

# Execute the alembic command inside the api_gateway container
docker-compose exec api_gateway alembic revision --autogenerate -m "Your descriptive migration message"
```

To apply migrations to the database:

```bash
docker-compose exec api_gateway alembic upgrade head
```

...or you can simply run `bash docker.sh` to run all.

## 5. Core Concepts & Workflow

### The Decoupled Execution Loop

The system is designed around a robust, asynchronous loop that ensures scalability and resilience.

1.  **Initiation**: The `api_gateway` receives a user message and enqueues a `start_turn` job for the `orchestrator_service`.
2.  **Orchestration & Dispatch**: The `orchestrator_service` runs its LangGraph state machine. It determines the next action (e.g., call the "Researcher" agent) and dispatches a `run_agent_llm` job to the `execution_workers`. The graph then pauses.
3.  **Execution**: An `execution_worker` picks up the job, calls the necessary LLM or tool, and gets a result.
4.  **State Update**: The worker updates the shared conversation state in Redis with the result of its action.
5.  **Continuation**: The worker's final step is to enqueue a `continue_turn` job for the `orchestrator_service`.
6.  **Loop**: The `orchestrator_service` picks up the `continue_turn` job, re-evaluates the updated state, and the loop continues until the task is complete.

### State Management with LangGraph

*   The state of each ongoing conversation is managed by LangGraph's `RedisSaver` checkpointer.
*   The `group_id` is used as the `thread_id` to uniquely identify each conversation's state in Redis.
*   This allows the graph to be stateless between invocations, picking up exactly where it left off.
*   For data durability, a final `sync_to_postgres` node in the graph ensures the complete conversation history is written to our primary database at the end of every turn.

## 6. API Endpoints

The primary API endpoints are exposed by the `api_gateway` service.

## 7. Testing

*TODO: This section will be updated with instructions on how to run the test suite. We will use `pytest` for unit and integration tests. Tests will be run automatically in our CI/CD pipeline.*