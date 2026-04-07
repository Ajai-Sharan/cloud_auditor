# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the Cloud Auditor Environment.

This module creates an HTTP server that exposes the CloudAuditorEnvironment
over HTTP and WebSocket endpoints, compatible with EnvClient.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    # Development (with auto-reload):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

    # Production:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 4

    # Or run directly:
    python -m server.app
"""

try:
    from openenv.core.env_server.http_server import create_fastapi_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import CloudAuditorAction, CloudAuditorObservation
    from .cloud_auditor_environment import CloudAuditorEnvironment
except (ModuleNotFoundError, ImportError):
    from models import CloudAuditorAction, CloudAuditorObservation
    from server.cloud_auditor_environment import CloudAuditorEnvironment


# Keep deterministic task rotation across repeated stateless HTTP /reset calls.
CloudAuditorEnvironment.USE_GLOBAL_TASK_ROTATION = True
# Keep task/world state between stateless HTTP requests (e.g., Postman).
CloudAuditorEnvironment.USE_GLOBAL_HTTP_STATE = True
# Recover empty commands produced by failing agents (e.g., LLM 403 cases).
CloudAuditorEnvironment.AUTO_RECOVER_EMPTY_COMMAND = True


# Create the FastAPI app with OpenEnv HTTP endpoints.
app = create_fastapi_app(
    CloudAuditorEnvironment,
    CloudAuditorAction,
    CloudAuditorObservation,
    max_concurrent_envs=1,  # increase this number to allow more concurrent WebSocket sessions
)

@app.get("/")
async def root():
    """Root endpoint to pass basic connectivity health checks."""
    return {"status": "ok", "message": "Cloud Auditor Server is running"}

@app.get("/health")
async def health_check():
    """Explicit health check endpoint."""
    return {"status": "healthy"}


def main():
    """
    Standard entry point for the validator and direct execution.
    """
    import uvicorn
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run the Cloud Auditor Environment Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to listen on")
    
    args = parser.parse_args()

    # The validator usually expects the app object to be passed as a string 
    # to uvicorn.run for multi-mode compatibility.
    uvicorn.run("server.app:app", host=args.host, port=args.port, reload=False)

    


if __name__ == "__main__":
    main()