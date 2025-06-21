"""Entry point for the orchestrator ARQ worker.

This file exposes ``WorkerSettings`` so that the ``arq`` CLI can run the
orchestrator service using:

```
arq orchestrator_service.app.main.WorkerSettings
```
"""

from .worker import WorkerSettings

__all__ = ["WorkerSettings"]

