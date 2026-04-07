# CloudSecurityAuditor-v1 - Postman and cURL Commands

Use this file to test the environment quickly from Postman or terminal.

## Base URL

Default local server URL:

```text
http://127.0.0.1:8000
```

Endpoints:
- POST /reset
- POST /step
- GET /state
- GET /schema
- GET /docs

## Start Server

```bash
uv sync --extra dev
uv run uvicorn server.app:app --host 127.0.0.1 --port 8000
```

## Postman Setup

1. Create a new collection: CloudSecurityAuditor-v1.
2. Add collection variable: `base_url` = `http://127.0.0.1:8000`.
3. For POST requests, set header `Content-Type: application/json`.
4. For /step requests, use this body shape:

```json
{
  "action": {
    "command": "describe_instances"
  }
}
```

## Quick Endpoint Checks

### API docs

```bash
curl -X GET http://127.0.0.1:8000/docs
```

### Episode state metadata

```bash
curl -X GET http://127.0.0.1:8000/state
```

### Action and observation schema

```bash
curl -X GET http://127.0.0.1:8000/schema
```

## Reset

Reset starts a new episode and rotates tasks deterministically:
1. task_easy_ssh
2. task_medium_s3
3. task_hard_iam
4. repeats from task_easy_ssh

```bash
curl -X POST http://127.0.0.1:8000/reset \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Task Walkthroughs

Note: The server keeps global HTTP state for stateless requests. If you are in the middle of a task and want a clean flow, call /reset before running a walkthrough.

### EASY task (task_easy_ssh)

```bash
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"describe_instances"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"describe_security_groups --group-id sg-web"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"}}'
```

Expected final state: `task_score: 1.0`, `done: true`, `status: "completed"`.

### MEDIUM task (task_medium_s3)

Move to medium by resetting twice from a fresh process, or keep resetting until `task_id` is `task_medium_s3`.

```bash
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"describe_buckets"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"put_public_access_block --bucket customer-backup-prod --block-public-read true"}}'
```

Expected final state: `task_score: 1.0`, `done: true`, `status: "completed"`.

### HARD task (task_hard_iam)

Move to hard by resetting three times from a fresh process, or keep resetting until `task_id` is `task_hard_iam`.

```bash
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/reset -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"describe_iam_users"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"list_attached_user_policies --user-name alice-admin"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"list_access_keys --user-name alice-admin"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive"}}'
curl -X POST http://127.0.0.1:8000/step -H "Content-Type: application/json" -d '{"action":{"command":"update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive"}}'
```

Expected final state: `task_score: 1.0`, `done: true`, `status: "completed"`.

## Command Reference (/step)

All commands must be sent through:

```json
{
  "action": {
    "command": "<command>"
  }
}
```

Supported command names:
- describe_instances
- describe_security_groups [--group-id <id>]
- revoke_security_group_ingress --group-id <id> --port <int> --cidr <cidr>
- describe_buckets
- put_public_access_block --bucket <name> --block-public-read <true|false>
- describe_iam_users
- list_attached_user_policies --user-name <name>
- list_access_keys --user-name <name>
- update_access_key --user-name <name> --access-key-id <id> --status <Active|Inactive>

## Error Cases

### Empty command

```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action":{"command":""}}'
```

Expected: negative reward, `Error: empty command`.

### Unknown command

```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action":{"command":"invalid_command"}}'
```

Expected: negative reward, `Error: unrecognized command 'invalid_command'`.

### Missing required option

```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action":{"command":"update_access_key --user-name alice-admin --status Inactive"}}'
```

Expected: `Error: missing required option --access-key-id`.

### Invalid value format

```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action":{"command":"revoke_security_group_ingress --group-id sg-web --port abc --cidr 0.0.0.0/0"}}'
```

Expected: `Error: port must be an integer`.

## task_id During Testing

Yes, it is correct to see `task_easy_ssh`, `task_medium_s3`, or `task_hard_iam` while testing.

Important rules:
- Do not send `task_id` in your request body. It is generated by the server.
- `/reset` chooses the current task for the new episode.
- `/step` should keep the same `task_id` as the most recent `/reset` until you call `/reset` again.
- If you call `/step` without resetting first, the task may not be the one you expect.

Example valid `/step` body (no task_id field):

```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action":{"command":"describe_buckets"}}'
```

## Response Shape

Typical response for `/reset` and `/step`:

```json
{
  "observation": {
    "task_id": "task_easy_ssh",
    "task_description": "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22.",
    "command_output": "{...}",
    "task_score": 0.0,
    "steps_remaining": 15,
    "status": "running",
    "metadata": {
      "step_count": 0,
      "supported_commands": []
    }
  },
  "reward": 0.0,
  "done": false
}
```

Key fields to monitor:
- `task_score`: 0.0 to 1.0
- `reward`: positive for progress, negative for invalid actions
- `done`: true on completion or max-step termination
- `steps_remaining`: countdown from 15
- `command_output`: JSON-like payload or error string
