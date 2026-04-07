# Quick Reference: CloudSecurityAuditor-v1 Agent Testing

## Start Server

```bash
uv sync --extra dev
uv run uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Server is ready when you see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

## Browser Testing

Open in browser:
- **Interactive Docs:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **OpenAPI Schema:** http://127.0.0.1:8000/openapi.json

In Swagger UI:
1. Click "POST /reset"
2. Click "Try it out"
3. Click "Execute"
4. Copy the response and paste into POST /step with different commands

## cURL Examples

### Reset Episode
```bash
curl -X POST http://127.0.0.1:8000/reset \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Step: Describe Instances
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "describe_instances"}}'
```

### Step: Describe Security Groups
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "describe_security_groups"}}'
```

### Step: Describe with Filter
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "describe_security_groups --group-id sg-web"}}'
```

### Step: Revoke SSH Rule (Easy Task Solution)
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"}}'
```

### Step: Describe Buckets
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "describe_buckets"}}'
```

### Step: Block Public Access (Medium Task Solution)
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "put_public_access_block --bucket customer-backup-prod --block-public-read true"}}'
```

### Step: Describe IAM Users
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "describe_iam_users"}}'
```

### Step: Disable Admin Access Keys (Hard Task Solution - Part 1)
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive"}}'
```

### Step: Disable Admin Access Keys (Hard Task Solution - Part 2)
```bash
curl -X POST http://127.0.0.1:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"command": "update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive"}}'
```

## PowerShell Examples

### Reset
```powershell
$body = @{} | ConvertTo-Json
Invoke-WebRequest -Uri "http://127.0.0.1:8000/reset" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body $body | ConvertTo-Json
```

### Step
```powershell
$body = @{action = @{command = "describe_instances"}} | ConvertTo-Json
Invoke-WebRequest -Uri "http://127.0.0.1:8000/step" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body $body | ConvertTo-Json
```

## Python Examples

### Simple Client
```python
import json
import urllib.request

# Reset
req = urllib.request.Request(
    'http://127.0.0.1:8000/reset',
    data=b'{}',
    headers={'Content-Type': 'application/json'},
    method='POST'
)
response = json.loads(urllib.request.urlopen(req).read())
print(response['observation']['task_id'])

# Step
action = {'action': {'command': 'describe_instances'}}
req = urllib.request.Request(
    'http://127.0.0.1:8000/step',
    data=json.dumps(action).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
response = json.loads(urllib.request.urlopen(req).read())
print(response['reward'])
print(response['observation']['task_score'])
```

### Using CloudAuditorEnv Client
```python
from cloud_auditor import CloudAuditorAction, CloudAuditorEnv

with CloudAuditorEnv(base_url="http://127.0.0.1:8000") as env:
    obs = env.reset()
    print(f"Task: {obs.observation.task_id}")
    
    result = env.step(CloudAuditorAction(command="describe_instances"))
    print(f"Reward: {result.reward}")
    print(f"Done: {result.done}")
```

## Run Local Tests

### All Tests
```bash
uv run python -m pytest -v
```

### Integration Tests Only
```bash
uv run python -m pytest tests/test_agent_integration.py -v
```

### Unit Tests Only
```bash
uv run python -m pytest tests/test_cloud_auditor_environment.py -v
```

### Watch Tests (requires pytest-watch)
```bash
uv run pytest-watch -- -v
```

## Expected Task Solutions

### Task 1: Easy SSH
Commands to execute:
1. `describe_instances`
2. `describe_security_groups --group-id sg-web`
3. `revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0`

Expected result: task_score = 1.0, done = true

### Task 2: Medium S3
Commands to execute:
1. `describe_buckets`
2. `put_public_access_block --bucket customer-backup-prod --block-public-read true`

Expected result: task_score = 1.0, done = true

### Task 3: Hard IAM
Commands to execute:
1. `describe_iam_users`
2. `list_attached_user_policies --user-name alice-admin`
3. `list_access_keys --user-name alice-admin`
4. `update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive`
5. `update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive`

Expected result: task_score = 1.0, done = true

## Response Parsing Tips

All `command_output` fields are JSON strings. Parse them to extract data:

```python
import json

# After executing a command
output_json = json.loads(response['observation']['command_output'])

# For instances:
instances = output_json['instances']
web_server = next(i for i in instances if 'web' in i['name'].lower())

# For security groups:
groups = output_json['security_groups']
risky_rules = [r for r in groups[0]['ingress'] if r['cidr'] == '0.0.0.0/0']

# For buckets:
buckets = output_json['buckets']
public_bucket = next(b for b in buckets if b['public_read'])

# For IAM users:
users = output_json['users']
admin_user = next(u for u in users if 'AdministratorAccess' in u['policies'])
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Calling step before reset | Always call reset() first |
| Missing `--` in option names | Use `--group-id` not `-group-id` or `group-id` |
| Not parsing JSON output | `command_output` is a JSON string, must `json.loads()` it |
| Invalid CIDR format | Use full notation like `0.0.0.0/0` |
| Port as string not int | Port must be int: `--port 22` not `--port "22"` |
| Status is string not bool | Use `"Active"` and `"Inactive"` (capitalized) |
| Ignoring steps_remaining | Monitor it to stay under MAX_STEPS=15 |

## Debugging

### Enable Verbose Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Server Logs
Watch the terminal where uvicorn is running for full request/response logs.

### Manual State Inspection
```bash
curl -X GET http://127.0.0.1:8000/state \
  -H "Content-Type: application/json"
```

### Validate Action Schema
```bash
curl -X GET http://127.0.0.1:8000/schema \
  -H "Content-Type: application/json"
```

## Benchmarking Your Agent

Track these metrics per task:

```python
import time

metrics = {"success_rate": 0, "avg_reward": 0, "avg_steps": 0, "times": []}

for episode in range(100):
    with CloudAuditorEnv(base_url="http://127.0.0.1:8000") as env:
        start = time.time()
        obs = env.reset()
        
        cumulative_reward = 0
        steps = 0
        
        while not obs.done and steps < 15:
            result = env.step(CloudAuditorAction(command=get_agent_action()))
            obs = result.observation
            cumulative_reward += result.reward
            steps += 1
        
        elapsed = time.time() - start
        metrics["times"].append(elapsed)
        metrics["avg_steps"] += steps
        
        if obs.task_score == 1.0:
            metrics["success_rate"] += 1
        
        metrics["avg_reward"] += cumulative_reward

print(f"Success rate: {metrics['success_rate']/100*100}%")
print(f"Avg steps: {metrics['avg_steps']/100}")
print(f"Avg time: {sum(metrics['times'])/len(metrics['times']):.2f}s")
```

## Next Steps

1. **Integration Tests:** Run `uv run python -m pytest tests/test_agent_integration.py -v` to understand the expected behavior
2. **Manual Testing:** Try the cURL examples above to familiarize yourself with commands
3. **Agent Implementation:** Implement your agent using the CloudAuditorEnv client
4. **Benchmarking:** Run episodes and track success rate, steps, and rewards
5. **Submission:** Docker build and push to Hugging Face Spaces
