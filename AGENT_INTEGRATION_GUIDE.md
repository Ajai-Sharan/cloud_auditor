# Agent Integration Guide: CloudSecurityAuditor-v1

This document shows exactly how agents interact with the CloudSecurityAuditor-v1 environment server.

## Server Setup

Start the server locally:

```bash
uv sync --extra dev
uv run uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Endpoints available:
- `POST /reset` - Start or reset an episode
- `POST /step` - Execute an action
- `GET /state` - Get current state
- `GET /docs` - Interactive Swagger UI

## Request/Response Cycle

### 1. Reset: Initialize Episode

**Request:**
```json
POST /reset
Content-Type: application/json

{}
```

**Response:**
```json
{
  "observation": {
    "task_id": "task_easy_ssh",
    "task_description": "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22.",
    "command_output": "CloudSecurityAuditor-v1 initialized. Available commands: describe_instances, describe_security_groups, ...",
    "task_score": 0.0,
    "steps_remaining": 15,
    "status": "running",
    "metadata": {
      "step_count": 0,
      "supported_commands": ["describe_instances", "describe_security_groups", ...]
    }
  },
  "reward": 0.0,
  "done": false
}
```

### 2. Step: Execute CLI Command

**Request Format:**
```json
POST /step
Content-Type: application/json

{
  "action": {
    "command": "<command-name> [--option value ...]"
  }
}
```

**Response Format:**
```json
{
  "observation": {
    "task_id": "task_easy_ssh",
    "task_description": "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22.",
    "command_output": "<JSON output or error message>",
    "task_score": 0.0,
    "steps_remaining": 14,
    "status": "running",
    "metadata": {...}
  },
  "reward": 0.35,
  "done": false
}
```

## Available Commands

### EC2 & Security Group Commands

#### `describe_instances`

Lists all EC2 instances and their security groups.

**Request:**
```json
{
  "action": {
    "command": "describe_instances"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"instances\": [
        {
          \"instance_id\": \"i-web-01\",
          \"name\": \"prod-web-frontend\",
          \"role\": \"web\",
          \"public_ip\": \"54.31.22.10\",
          \"security_groups\": [\"sg-web\"]
        },
        {
          \"instance_id\": \"i-batch-01\",
          \"name\": \"nightly-batch\",
          \"role\": \"batch\",
          \"public_ip\": null,
          \"security_groups\": [\"sg-internal\"]
        }
      ]
    }",
    "task_score": 0.0,
    "steps_remaining": 14
  },
  "reward": 0.3,
  "done": false
}
```

#### `describe_security_groups [--group-id <id>]`

Lists security groups and their ingress rules.

**With filter:**
```json
{
  "action": {
    "command": "describe_security_groups --group-id sg-web"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"security_groups\": [
        {
          \"group_id\": \"sg-web\",
          \"name\": \"web-sg\",
          \"ingress\": [
            {
              \"port\": 22,
              \"protocol\": \"tcp\",
              \"cidr\": \"0.0.0.0/0\"
            },
            {
              \"port\": 80,
              \"protocol\": \"tcp\",
              \"cidr\": \"0.0.0.0/0\"
            }
          ]
        }
      ]
    }",
    "task_score": 0.0,
    "steps_remaining": 13
  },
  "reward": 0.15,
  "done": false
}
```

#### `revoke_security_group_ingress --group-id <id> --port <int> --cidr <cidr>`

Removes an ingress rule from a security group.

**Request:**
```json
{
  "action": {
    "command": "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"
  }
}
```

**Response (Success):**
```json
{
  "observation": {
    "command_output": "{
      \"group_id\": \"sg-web\",
      \"removed_rules\": 1,
      \"remaining_ingress\": [
        {
          \"port\": 80,
          \"protocol\": \"tcp\",
          \"cidr\": \"0.0.0.0/0\"
        }
      ]
    }",
    "task_score": 1.0,
    "status": "completed"
  },
  "reward": 0.55,
  "done": true
}
```

### S3 Commands

#### `describe_buckets`

Lists S3 buckets and their public access settings.

**Request:**
```json
{
  "action": {
    "command": "describe_buckets"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"buckets\": [
        {
          \"name\": \"customer-backup-prod\",
          \"purpose\": \"customer backups\",
          \"public_read\": true,
          \"encryption\": \"AES256\"
        },
        {
          \"name\": \"analytics-private\",
          \"purpose\": \"analytics\",
          \"public_read\": false,
          \"encryption\": \"AES256\"
        }
      ]
    }",
    "task_score": 0.0,
    "steps_remaining": 14
  },
  "reward": 0.3,
  "done": false
}
```

#### `put_public_access_block --bucket <name> --block-public-read <true|false>`

Blocks or allows public read access to a bucket.

**Request:**
```json
{
  "action": {
    "command": "put_public_access_block --bucket customer-backup-prod --block-public-read true"
  }
}
```

**Response (Success):**
```json
{
  "observation": {
    "command_output": "{
      \"bucket\": \"customer-backup-prod\",
      \"public_read\": false
    }",
    "task_score": 1.0,
    "status": "completed"
  },
  "reward": 0.65,
  "done": true
}
```

### IAM Commands

#### `describe_iam_users`

Lists all IAM users, policies, and access keys.

**Request:**
```json
{
  "action": {
    "command": "describe_iam_users"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"users\": [
        {
          \"user_name\": \"alice-admin\",
          \"last_login_days\": 140,
          \"policies\": [\"AdministratorAccess\"],
          \"access_keys\": [
            {
              \"id\": \"AKIAALICE001\",
              \"status\": \"Active\"
            },
            {
              \"id\": \"AKIAALICE002\",
              \"status\": \"Active\"
            }
          ]
        },
        {
          \"user_name\": \"bob-ops\",
          \"last_login_days\": 12,
          \"policies\": [\"ReadOnlyAccess\"],
          \"access_keys\": [
            {
              \"id\": \"AKIABOB001\",
              \"status\": \"Active\"
            }
          ]
        }
      ]
    }",
    "task_score": 0.0,
    "steps_remaining": 14
  },
  "reward": 0.1,
  "done": false
}
```

#### `list_attached_user_policies --user-name <name>`

Shows policies attached to a specific user.

**Request:**
```json
{
  "action": {
    "command": "list_attached_user_policies --user-name alice-admin"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"user_name\": \"alice-admin\",
      \"attached_policies\": [\"AdministratorAccess\"]
    }",
    "task_score": 0.0,
    "steps_remaining": 13
  },
  "reward": 0.15,
  "done": false
}
```

#### `list_access_keys --user-name <name>`

Lists all access keys for a user.

**Request:**
```json
{
  "action": {
    "command": "list_access_keys --user-name alice-admin"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "{
      \"user_name\": \"alice-admin\",
      \"access_keys\": [
        {
          \"id\": \"AKIAALICE001\",
          \"status\": \"Active\"
        },
        {
          \"id\": \"AKIAALICE002\",
          \"status\": \"Active\"
        }
      ]
    }",
    "task_score": 0.0,
    "steps_remaining": 12
  },
  "reward": 0.2,
  "done": false
}
```

#### `update_access_key --user-name <name> --access-key-id <id> --status <Active|Inactive>`

Activates or deactivates an access key.

**Request:**
```json
{
  "action": {
    "command": "update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive"
  }
}
```

**Response (Partial Completion):**
```json
{
  "observation": {
    "command_output": "{
      \"user_name\": \"alice-admin\",
      \"access_key_id\": \"AKIAALICE001\",
      \"status\": \"Inactive\"
    }",
    "task_score": 0.5,
    "steps_remaining": 11,
    "status": "running"
  },
  "reward": 0.4,
  "done": false
}
```

## Full Episode Walkthroughs

### Easy Task (task_easy_ssh) - Expected Agent Flow

```python
# Step 1: Reconnaissance
POST /reset
→ task_id: "task_easy_ssh"

# Step 2: Explore instances
POST /step {"action": {"command": "describe_instances"}}
→ reward: +0.3, identifies web server at i-web-01

# Step 3: Find target security group
POST /step {"action": {"command": "describe_security_groups --group-id sg-web"}}
→ reward: +0.15, identifies SSH rule

# Step 4: Remediate
POST /step {"action": {"command": "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"}}
→ reward: +0.55, task_score: 1.0, done: true, status: "completed"
```

**Total Episode:** 3 steps, ~1.0 cumulative reward, 100% task completion.

### Medium Task (task_medium_s3) - Expected Agent Flow

```python
# Reset to task 2
POST /reset
POST /reset
→ task_id: "task_medium_s3"

# Step 1: Discover buckets
POST /step {"action": {"command": "describe_buckets"}}
→ reward: +0.3, identifies "customer-backup-prod" bucket with public_read: true

# Step 2: Disable public read
POST /step {"action": {"command": "put_public_access_block --bucket customer-backup-prod --block-public-read true"}}
→ reward: +0.65, task_score: 1.0, done: true, status: "completed"
```

**Total Episode:** 2 steps, ~0.95 cumulative reward, 100% task completion.

### Hard Task (task_hard_iam) - Expected Agent Flow

```python
# Reset to task 3
POST /reset
POST /reset
POST /reset
→ task_id: "task_hard_iam"

# Step 1: List users
POST /step {"action": {"command": "describe_iam_users"}}
→ reward: +0.1, identifies alice-admin with last_login_days: 140

# Step 2: Check policies
POST /step {"action": {"command": "list_attached_user_policies --user-name alice-admin"}}
→ reward: +0.15, confirms AdministratorAccess

# Step 3: List keys
POST /step {"action": {"command": "list_access_keys --user-name alice-admin"}}
→ reward: +0.2, finds 2 active keys

# Step 4: Disable first key
POST /step {"action": {"command": "update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive"}}
→ reward: +0.4, task_score: 0.5, done: false

# Step 5: Disable second key
POST /step {"action": {"command": "update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive"}}
→ reward: +0.55, task_score: 1.0, done: true, status: "completed"
```

**Total Episode:** 5 steps, ~1.4 cumulative reward, 100% task completion.

## Error Cases

### Empty Command

**Request:**
```json
{
  "action": {
    "command": ""
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "Error: empty command",
    "task_score": 0.0,
    "status": "running"
  },
  "reward": -0.05,
  "done": false
}
```

### Unrecognized Command

**Request:**
```json
{
  "action": {
    "command": "invalid_command"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "Error: unrecognized command 'invalid_command'",
    "task_score": 0.0,
    "status": "running"
  },
  "reward": -0.07,
  "done": false
}
```

### Non-existent Resource

**Request:**
```json
{
  "action": {
    "command": "describe_security_groups --group-id sg-fake"
  }
}
```

**Response:**
```json
{
  "observation": {
    "command_output": "Error: security group 'sg-fake' not found",
    "task_score": 0.0,
    "status": "running"
  },
  "reward": -0.04,
  "done": false
}
```

## Episode Termination Conditions

An episode ends (done: true) when:

1. **Task Completion:** agent achieves task_score == 1.0
2. **Max Steps Reached:** 15 steps executed (status: "failed")

**Example - Max Steps:**
```json
{
  "observation": {
    "task_score": 0.0,
    "steps_remaining": 0,
    "status": "failed"
  },
  "done": true
}
```

## Task Rotation Pattern

Each new /reset cycles through tasks deterministically:

```
Reset #1 → task_easy_ssh
Reset #2 → task_medium_s3
Reset #3 → task_hard_iam
Reset #4 → task_easy_ssh (cycle repeats)
```

Each reset completely restores world state, so the environment is 100% reproducible and deterministic.

## Python Client Example

```python
from cloud_auditor import CloudAuditorAction, CloudAuditorEnv
import json

# Connect to running server
with CloudAuditorEnv(base_url="http://127.0.0.1:8000") as env:
    # Reset to start episode
    result = env.reset()
    print(f"Task: {result.observation.task_id}")
    print(f"Description: {result.observation.task_description}")
    
    # Execute commands
    for _ in range(5):
        result = env.step(CloudAuditorAction(
            command="describe_instances"
        ))
        
        print(f"Reward: {result.reward}")
        print(f"Score: {result.observation.task_score}")
        print(f"Steps remaining: {result.observation.steps_remaining}")
        
        if result.done:
            print(f"Episode done! Status: {result.observation.status}")
            break
```

## Tips for Agent Implementation

1. **Always call reset() first** - initializes the episode
2. **Parse JSON responses** - command_output is JSON (parse it to find resource IDs)
3. **Track task_score progression** - monitor grader score to understand task progress
4. **Respect steps_remaining** - plan actions within the 15-step budget
5. **Handle errors gracefully** - invalid commands continue episodes, agent can retry
6. **Use metadata.supported_commands** - reference the list of valid commands
7. **Deterministic and reproducible** - same action sequence always produces same outcome

## Testing Your Agent

See `tests/test_agent_integration.py` for 18 test cases covering:
- Happy path workflows for all 3 tasks
- Command request/response formats
- Error handling and recovery
- Response payload structures
- Deterministic behavior
- Episode termination conditions
