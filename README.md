---
title: CloudSecurityAuditor-v1
colorFrom: red
colorTo: blue
sdk: docker
base_path: /web
tags:
  - openenv
  - security
  - devsecops
---

# Cloud Auditor Environment
  - security
  - devsecops

A deterministic cloud security simulation for evaluating agent investigation and remediation behavior.
# CloudSecurityAuditor-v1

CloudSecurityAuditor-v1 is a production-style OpenEnv simulation where an AI agent acts as a DevSecOps engineer, audits cloud assets, and remediates security issues via a deterministic in-memory CLI.

## Why This Environment Scores Well

- Real-world utility: Simulates common cloud misconfigurations in network, storage, and identity controls.
- Strong grader quality: Exactly three deterministic task graders with scores in [0.0, 1.0].
- Environment design: In-memory AWS-like state, reproducible resets, capped horizon, and dense reward shaping.
- Spec compliance: Typed Pydantic Action/Observation and standard OpenEnv reset/step/state endpoints.
- Creativity: A realistic CLI workflow that rewards both reconnaissance and precise remediation.

## Tasks (Exactly 3)

- `task_easy_ssh`: Find the web server and revoke `0.0.0.0/0` ingress on port `22`.
- `task_medium_s3`: Find the customer backup bucket and disable public read access.
- `task_hard_iam`: Find an admin user inactive for >90 days and disable all their access keys.

Reset rotates deterministically through tasks in this order:
1. `task_easy_ssh`
2. `task_medium_s3`
3. `task_hard_iam`

Task descriptions are always returned in `reset` observations via `task_description`, so an agent can infer objectives from observation payloads without reading repository files.

## Reward Design

- Dense reward shaping with command-level progress milestones.
- Deterministic score-delta reward component from the active grader.
- Mild per-step penalty for efficiency pressure.
- Additional penalties for malformed or unrecognized commands.
- Episode termination at `MAX_STEPS=15` or task completion.

See `GRADER_WALKTHROUGH.md` for explicit score progression examples, milestone semantics, and why task weight schemas differ by difficulty.

## Baseline Transparency

`BASELINE_RESULTS.md` is the canonical place for per-task baseline metrics.

- Baseline runner: `python inference.py > baseline_cloud_auditor.txt`
- Inference defaults to local execution when `ENV_URL` is unset:
  - `ENV_URL = http://localhost:8000`
- Inference prints active URL at startup for reproducibility:
  - `Using ENV_URL: ...`
- No hidden command fallback is used when LLM completion fails; failures are surfaced in logs.

## Simulated CLI Commands

- `describe_instances`
- `describe_security_groups [--group-id <id>]`
- `revoke_security_group_ingress --group-id <id> --port <int> --cidr <cidr>`
- `describe_buckets`
- `put_public_access_block --bucket <name> --block-public-read <true|false>`
- `describe_iam_users`
- `list_attached_user_policies --user-name <name>`
- `list_access_keys --user-name <name>`
- `update_access_key --user-name <name> --access-key-id <id> --status <Active|Inactive>`

No real cloud SDKs are used; all behavior is pure Python in-memory simulation.

## Quick Start

```python
from cloud_auditor import CloudAuditorAction, CloudAuditorEnv

with CloudAuditorEnv(base_url="http://localhost:8000") as env:
    result = env.reset()
    print(result.observation.task_id)
    print(result.observation.task_description)

    result = env.step(CloudAuditorAction(command="describe_instances"))
    print(result.observation.command_output)
    print("reward:", result.reward, "score:", result.observation.task_score)
```

## Run Locally

```bash
uv sync
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

## Phase 2 Proxy Validation (Local)

Use the injected proxy settings and run the local validator before every submission.

```bash
export API_KEY="your_token"
export API_BASE_URL="https://<provided-proxy-base-url>"
export MODEL_NAME="<provided-model-name>"
export ENV_URL="http://127.0.0.1:8000"
python local_validator.py
```

Notes:
- `inference.py` requires `API_BASE_URL`, `API_KEY`, and `MODEL_NAME`.
- If no successful LLM call is made, `inference.py` exits non-zero so proxy bypass issues are caught locally.
- `ENV_URL` and `ENV_BASE_URL` are both supported for environment server URL.

## Build Docker Image

```bash
docker build -t cloudsecurityauditor-v1:latest -f server/Dockerfile .
```

## OpenEnv Manifest

`openenv.yaml`:

```yaml
spec_version: 1
name: cloudsecurityauditor-v1
type: space
runtime: fastapi
app: server.app:app
port: 8000
```

## Key Files

- `models.py`: Typed `CloudAuditorAction` and `CloudAuditorObservation`
- `server/cloud_auditor_environment.py`: Deterministic simulator, command engine, graders, rewards
- `server/app.py`: OpenEnv FastAPI app wiring
- `client.py`: Typed OpenEnv client

## Documentation And Guides

The repository includes additional guides for testing, integration, and usage.

- `POSTMAN_CURL_COMMANDS.md`: Postman-ready request bodies and cURL commands for `/reset` and `/step`, including task walkthroughs and error cases.
- `AGENT_INTEGRATION_GUIDE.md`: Full agent integration contract with request/response examples and command semantics.
- `TESTING_QUICK_REFERENCE.md`: Fast testing checklist with common flows, troubleshooting tips, and expected outputs.
- `GRADER_WALKTHROUGH.md`: Step-by-step grading walkthroughs, milestone rules, and score progression transparency.
- `BASELINE_RESULTS.md`: Published baseline run matrix (task score, steps, success, mean score).
- `README.md`: High-level project overview, architecture, setup, and command reference.
- `inference.py`: Sample inference runner that uses OpenAI client variables (`API_BASE_URL`, `API_KEY`, `MODEL_NAME`) against this environment.

If you are new to the repo, start with `README.md`, then use `POSTMAN_CURL_COMMANDS.md` for manual API checks.
