+# Copyright (c) Meta Platforms, Inc. and affiliates.
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

from fastapi import Request
from fastapi.responses import HTMLResponse


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

UI_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Cloud Auditor</title>
    <style>
        :root {
            --bg: #d7f5ff;
            --dot: #53b8da;
            --ink: #0c0f14;
            --panel: #f6dc54;
            --panel-soft: #ffd79a;
            --cream: #ffeac8;
            --line: #121212;
            --ok: #10883f;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            color: var(--ink);
            font-family: "Trebuchet MS", "Segoe UI", sans-serif;
            background-color: var(--bg);
            background-image: radial-gradient(var(--dot) 1px, transparent 1px);
            background-size: 20px 20px;
            line-height: 1.45;
        }

        .wrap {
            width: min(1180px, calc(100% - 24px));
            margin: 24px auto 36px;
        }

        .card {
            border: 3px solid var(--line);
            border-radius: 14px;
            box-shadow: 5px 5px 0 var(--line);
            overflow: hidden;
            background: #fff;
        }

        .hero {
            background: linear-gradient(180deg, #f8e45f 0%, #f0d948 100%);
            padding: 26px 20px 24px;
            text-align: center;
        }

        .hero h1 {
            margin: 0;
            font-size: clamp(2rem, 4vw, 3rem);
            letter-spacing: 0.5px;
        }

        .hero p {
            margin: 6px 0 0;
            font-size: clamp(0.95rem, 1.6vw, 1.15rem);
            font-weight: 700;
        }

        .tabs {
            display: grid;
            grid-template-columns: repeat(4, minmax(120px, 1fr));
            gap: 10px;
            margin: 18px 0;
        }

        .tab {
            display: block;
            text-align: center;
            text-decoration: none;
            color: var(--ink);
            font-weight: 800;
            border: 3px solid var(--line);
            border-radius: 12px;
            background: var(--cream);
            padding: 12px 10px;
            box-shadow: 3px 3px 0 var(--line);
            transition: transform 120ms ease;
        }

        .tab.active { background: #f8b146; }
        .tab:hover { transform: translateY(-2px); }

        .section {
            background: #f2f2f2;
            padding: 22px;
            border-top: 3px solid var(--line);
        }

        .pane {
            border: 3px solid var(--line);
            border-radius: 12px;
            background: linear-gradient(180deg, #f7bc5d 0%, #f1b14c 100%);
            box-shadow: 3px 3px 0 var(--line);
            padding: 20px;
        }

        h2 {
            margin: 0 0 8px;
            font-size: clamp(1.2rem, 2.2vw, 2rem);
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 14px;
        }

        .chip {
            border: 2px solid var(--line);
            background: #ffecbf;
            border-radius: 10px;
            padding: 10px 12px;
            font-weight: 700;
        }

        .status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #ddffd9;
            border: 2px solid #2a8f44;
            color: #125226;
            border-radius: 999px;
            padding: 6px 12px;
            font-weight: 800;
            margin-top: 10px;
        }

        .dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: var(--ok);
            box-shadow: 0 0 0 4px rgba(16, 136, 63, 0.2);
        }

        .footer {
            margin-top: 14px;
            font-size: 0.95rem;
            font-weight: 700;
        }

        @media (max-width: 900px) {
            .tabs { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main class="wrap">
        <header class="card hero">
            <h1>Cloud Auditor</h1>
            <p>AWS-style Security Incident Response Training for LLM Agents</p>
        </header>

        <nav class="tabs" aria-label="Primary">
            <a class="tab active" href="#overview">Overview</a>
            <a class="tab" href="/schema">Schema</a>
            <a class="tab" href="/state">State</a>
            <a class="tab" href="/health">Health</a>
        </nav>

        <section id="overview" class="card section">
            <article class="pane">
                <h2>Cloud Auditor: Deterministic Security Tasks for Agent Evaluation</h2>
                <p>
                    This environment simulates realistic cloud misconfiguration incidents across EC2, S3, and IAM.
                    Agents receive a task, investigate the environment through constrained commands, and resolve
                    the issue in a maximum of 15 steps.
                </p>
                <div class="grid">
                    <div class="chip">Task 1: Revoke world-open SSH ingress</div>
                    <div class="chip">Task 2: Disable public S3 read access</div>
                    <div class="chip">Task 3: Disable stale IAM admin keys</div>
                </div>
                <p class="footer">
                    API endpoints: <strong>/reset</strong>, <strong>/step</strong>, <strong>/state</strong>, <strong>/schema</strong>, <strong>/ws</strong>
                </p>
                <div class="status"><span class="dot" aria-hidden="true"></span>Environment online</div>
            </article>
        </section>
    </main>
</body>
</html>
"""


@app.get("/")
async def root(request: Request):
        """Serve browser UI while preserving JSON for non-browser health checks."""
        accept = request.headers.get("accept", "")
        if "text/html" in accept.lower():
                return HTMLResponse(content=UI_HTML)
        return {"status": "ok", "message": "Cloud Auditor Server is running"}

@app.get("/health")
async def health_check():
    """Explicit health check endpoint."""
    return {"status": "healthy"}


@app.get("/tasks")
async def list_tasks():
    """Return task ids and descriptions for evaluator checks."""
    return [
        {
            "task_id": task_id,
            "description": spec["description"],
        }
        for task_id, spec in CloudAuditorEnvironment.TASK_SPECS.items()
    ]


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
