"""
Integration test cases showing how an agent would interact with CloudSecurityAuditor-v1.

These tests demonstrate:
- Server reset and step HTTP/WebSocket protocols
- Expected request/response payloads for each task
- Full episode walkthroughs showing agent policy examples
- Error handling for malformed commands
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import CloudAuditorAction, CloudAuditorObservation
from server.cloud_auditor_environment import CloudAuditorEnvironment


class TestAgentServerInteraction:
    """Test cases for agent-server interaction patterns."""

    def test_reset_initial_state(self):
        """Test: Agent calls reset to start a new episode.

        Simulates:
          POST /reset with body: {}

        Expected response:
          {
            "observation": {
              "task_id": "task_easy_ssh",
              "task_description": "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22.",
              "command_output": "CloudSecurityAuditor-v1 initialized. Available commands: ...",
              "task_score": 0.0,
              "steps_remaining": 15,
              "status": "running"
            },
            "reward": 0.0,
            "done": false
          }
        """
        env = CloudAuditorEnvironment()
        obs = env.reset()

        assert obs.task_id == "task_easy_ssh"
        assert obs.status == "running"
        assert obs.done is False
        assert obs.reward == 0.0
        assert obs.steps_remaining == 15
        assert obs.task_score == 0.0

    def test_easy_task_agent_workflow_happy_path(self):
        """Test: Agent solves task_easy_ssh by:
        1. Calling describe_instances (reconnaissance)
        2. Calling describe_security_groups --group-id sg-web (finding target)
        3. Calling revoke_security_group_ingress (remediation)

        Expected responses:
        - describe_instances: +0.1 recon reward, +0.2 recon milestone
        - describe_security_groups: +0.15 target identification milestone
        - revoke_security_group_ingress: +0.35 remediation milestone + score delta
        """
        env = CloudAuditorEnvironment()
        env.reset()

        # Step 1: Reconnaissance
        recon = env.step(CloudAuditorAction(command="describe_instances"))
        assert recon.reward > 0.0  # +0.1 + 0.2 milestones
        assert recon.done is False
        assert json.loads(recon.command_output)  # valid JSON output

        # Step 2: Identify target security group
        identify = env.step(
            CloudAuditorAction(command="describe_security_groups --group-id sg-web")
        )
        assert identify.reward > 0.0  # +0.15 milestone
        assert identify.done is False

        # Step 3: Remediate (revoke the 0.0.0.0/0 SSH rule)
        remediate = env.step(
            CloudAuditorAction(
                command="revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"
            )
        )
        assert remediate.done is True
        assert remediate.task_score == 1.0
        assert remediate.status == "completed"
        assert remediate.reward > 0.0  # +0.35 + score delta

    def test_easy_task_agent_requests_format(self):
        """Test: Agent request format for easy task commands.

        Each command request follows this JSON format:
          {
            "action": {
              "command": "<command-name> [--option value ...]"
            }
          }

        Examples:
          - { "action": { "command": "describe_instances" } }
          - { "action": { "command": "describe_security_groups --group-id sg-web" } }
          - { "action": { "command": "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0" } }
        """
        env = CloudAuditorEnvironment()
        env.reset()

        # Valid command format
        action = CloudAuditorAction(command="describe_instances")
        assert action.command == "describe_instances"

        obs = env.step(action)
        assert obs.command_output  # Got a response
        assert "Error" not in obs.command_output

    def test_medium_task_agent_workflow_happy_path(self):
        """Test: Agent solves task_medium_s3 by:
        1. Calling describe_buckets (reconnaissance)
        2. Calling put_public_access_block (remediation)

        Expected full episode:
          - Reset -> task_id = "task_medium_s3"
          - describe_buckets -> +0.1 + 0.2 milestones
          - put_public_access_block -> +0.45 + score delta -> done=True, score=1.0
        """
        env = CloudAuditorEnvironment()
        env.reset()  # _reset_count=1 -> task 0 (easy)
        obs = env.reset()  # _reset_count=2 -> task 1 (medium)
        assert obs.task_id == "task_medium_s3"

        # Reconnaissance
        recon = env.step(CloudAuditorAction(command="describe_buckets"))
        assert recon.reward > 0.0
        payload = json.loads(recon.command_output)
        assert "buckets" in payload

        # Remediation
        remediate = env.step(
            CloudAuditorAction(
                command="put_public_access_block --bucket customer-backup-prod --block-public-read true"
            )
        )
        assert remediate.done is True
        assert remediate.task_score == 1.0

    def test_hard_task_agent_workflow_happy_path(self):
        """Test: Agent solves task_hard_iam (most complex task) by:
        1. describe_iam_users
        2. list_attached_user_policies --user-name alice-admin
        3. list_access_keys --user-name alice-admin
        4. update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive
        5. update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive

        Expected responses:
          - Steps 1-3: Progressive reconnaissance rewards
          - Step 4: Partial progress -> task_score=0.5, done=False
          - Step 5: Full completion -> task_score=1.0, done=True
        """
        env = CloudAuditorEnvironment()
        env.reset()  # _reset_count=1 -> task 0 (easy)
        env.reset()  # _reset_count=2 -> task 1 (medium)
        obs = env.reset()  # _reset_count=3 -> task 2 (hard)
        assert obs.task_id == "task_hard_iam"

        # Reconnaissance: list IAM users
        step1 = env.step(CloudAuditorAction(command="describe_iam_users"))
        assert step1.done is False
        payload = json.loads(step1.command_output)
        assert len(payload["users"]) >= 1
        assert any(u["user_name"] == "alice-admin" for u in payload["users"])

        # Identify alice-admin's policies
        step2 = env.step(
            CloudAuditorAction(command="list_attached_user_policies --user-name alice-admin")
        )
        assert step2.done is False
        policies = json.loads(step2.command_output)
        assert "AdministratorAccess" in policies["attached_policies"]

        # Get access keys
        step3 = env.step(CloudAuditorAction(command="list_access_keys --user-name alice-admin"))
        assert step3.done is False
        keys = json.loads(step3.command_output)
        assert len(keys["access_keys"]) == 2

        # Disable first key
        step4 = env.step(
            CloudAuditorAction(
                command="update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive"
            )
        )
        assert step4.done is False
        assert step4.task_score == 0.5  # Partial completion (1 of 2 keys)

        # Disable second key
        step5 = env.step(
            CloudAuditorAction(
                command="update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive"
            )
        )
        assert step5.done is True
        assert step5.task_score == 1.0  # Full completion

    def test_agent_empty_command_gets_penalty(self):
        """Test: Agent sends empty command (error case).

        Request:
          { "action": { "command": "" } }

        Expected response:
          - reward: negative
          - command_output: "Error: empty command"
          - done: False (unless it's the last step)
          - task_score: unchanged (0.0 for incomplete task)
        """
        env = CloudAuditorEnvironment()
        env.reset()

        obs = env.step(CloudAuditorAction(command=""))
        assert obs.reward < 0.0
        assert "Error" in obs.command_output
        assert obs.done is False

    def test_agent_unrecognized_command_gets_penalty(self):
        """Test: Agent sends unrecognized command.

        Request:
          { "action": { "command": "totally_invalid_command" } }

        Expected response:
          - reward: negative (-0.06)
          - command_output: "Error: unrecognized command 'totally_invalid_command'"
          - done: False
          - task_score: unchanged
        """
        env = CloudAuditorEnvironment()
        env.reset()

        obs = env.step(CloudAuditorAction(command="totally_invalid_command"))
        assert obs.reward < 0.0
        assert "unrecognized command" in obs.command_output
        assert obs.done is False

    def test_agent_missing_option_argument_error(self):
        """Test: Agent sends command with missing required option.

        Request:
          { "action": { "command": "describe_security_groups" } }
          (Missing --group-id)

        Expected response:
          - Incomplete command is still valid
          - Returns all security groups (no filter)
          - No error (since --group-id is optional for describe)
        """
        env = CloudAuditorEnvironment()
        env.reset()

        obs = env.step(CloudAuditorAction(command="describe_security_groups"))
        assert "group_id" not in obs.command_output or obs.reward > 0.0
        assert obs.done is False

    def test_agent_max_steps_termination(self):
        """Test: Agent hits maximum step limit (15 steps) without completing task.

        Expected behavior:
          - After 15 steps: done=True, status="failed" (if not completed)
          - steps_remaining decrements: 15 -> 14 -> ... -> 0
          - Episode automatically terminates
        """
        env = CloudAuditorEnvironment()
        env.reset()

        for step_num in range(15):
            obs = env.step(CloudAuditorAction(command="describe_instances"))
            expected_remaining = 15 - (step_num + 1)
            assert obs.steps_remaining == expected_remaining

            if step_num < 14:
                assert obs.done is False
            else:
                assert obs.done is True
                assert obs.status == "failed"

    def test_agent_task_rotation_across_resets(self):
        """Test: Agent runs multiple episodes; task rotates deterministically.

        Expected sequence:
          Reset 1 -> task_easy_ssh
          Reset 2 -> task_medium_s3
          Reset 3 -> task_hard_iam
          Reset 4 -> task_easy_ssh (cycle repeats)
        """
        env = CloudAuditorEnvironment()

        obs1 = env.reset()
        assert obs1.task_id == "task_easy_ssh"

        obs2 = env.reset()
        assert obs2.task_id == "task_medium_s3"

        obs3 = env.reset()
        assert obs3.task_id == "task_hard_iam"

        obs4 = env.reset()
        assert obs4.task_id == "task_easy_ssh"

    def test_agent_observation_fields_completeness(self):
        """Test: All observation fields are present and properly typed.

        Expected fields in CloudAuditorObservation:
          - task_id: str (task identifier)
          - task_description: str (human-readable objective)
          - command_output: str (JSON or error message)
          - task_score: float in [0.0, 1.0] (deterministic grader score)
          - steps_remaining: int >= 0 (countdown to episode limit)
          - status: str in {"running", "completed", "failed"}
          - reward: float (shaped reward for this step)
          - done: bool (episode terminal flag)
          - metadata: dict (optional step metadata)
        """
        env = CloudAuditorEnvironment()
        obs = env.reset()

        assert isinstance(obs.task_id, str)
        assert isinstance(obs.task_description, str)
        assert isinstance(obs.command_output, str)
        assert isinstance(obs.task_score, float)
        assert 0.0 <= obs.task_score <= 1.0
        assert isinstance(obs.steps_remaining, int)
        assert obs.steps_remaining >= 0
        assert obs.status in {"running", "completed", "failed"}
        assert isinstance(obs.reward, float)
        assert isinstance(obs.done, bool)
        assert isinstance(obs.metadata, dict)

    def test_agent_deterministic_world_state_restoration(self):
        """Test: World state is completely restored after reset.

        Scenario:
          1. Reset and partially modify world state
          2. Reset again (rotate task)
          3. Reset again (rotate task)
          4. Reset again (rotate back to task 1)
          5. Verify world state is identical to step 1
        """
        env = CloudAuditorEnvironment()

        # First episode: modify world state
        env.reset()
        env.step(
            CloudAuditorAction(
                command="revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"
            )
        )

        # Rotate through all tasks
        env.reset()  # task 2
        env.reset()  # task 3
        env.reset()  # back to task 1

        # Verify initial state is restored
        obs = env.step(CloudAuditorAction(command="describe_security_groups --group-id sg-web"))
        payload = json.loads(obs.command_output)
        sg = payload["security_groups"][0]
        ssh_rule = next(
            (r for r in sg["ingress"] if r["port"] == 22 and r["cidr"] == "0.0.0.0/0"),
            None,
        )
        assert ssh_rule is not None  # Rule is restored


class TestAgentResponsePayloads:
    """Test cases showing exact response payload structures for agent parsing."""

    def test_describe_instances_response_structure(self):
        """Test: describe_instances returns properly structured JSON.

        Response format:
          {
            "instances": [
              {
                "instance_id": "i-web-01",
                "name": "prod-web-frontend",
                "role": "web",
                "public_ip": "54.31.22.10",
                "security_groups": ["sg-web"]
              },
              ...
            ]
          }
        """
        env = CloudAuditorEnvironment()
        env.reset()
        obs = env.step(CloudAuditorAction(command="describe_instances"))

        payload = json.loads(obs.command_output)
        assert "instances" in payload
        instances = payload["instances"]
        assert len(instances) > 0

        instance = instances[0]
        assert "instance_id" in instance
        assert "name" in instance
        assert "role" in instance
        assert "public_ip" in instance
        assert "security_groups" in instance
        assert isinstance(instance["security_groups"], list)

    def test_describe_security_groups_response_structure(self):
        """Test: describe_security_groups returns ingress rules.

        Response format:
          {
            "security_groups": [
              {
                "group_id": "sg-web",
                "name": "web-sg",
                "ingress": [
                  {
                    "port": 22,
                    "protocol": "tcp",
                    "cidr": "0.0.0.0/0"
                  },
                  ...
                ]
              },
              ...
            ]
          }
        """
        env = CloudAuditorEnvironment()
        env.reset()
        obs = env.step(CloudAuditorAction(command="describe_security_groups"))

        payload = json.loads(obs.command_output)
        assert "security_groups" in payload
        groups = payload["security_groups"]
        assert len(groups) > 0

        group = groups[0]
        assert "group_id" in group
        assert "name" in group
        assert "ingress" in group
        assert isinstance(group["ingress"], list)

        rule = group["ingress"][0]
        assert "port" in rule
        assert "protocol" in rule
        assert "cidr" in rule

    def test_describe_buckets_response_structure(self):
        """Test: describe_buckets returns bucket metadata.

        Response format:
          {
            "buckets": [
              {
                "name": "customer-backup-prod",
                "purpose": "customer backups",
                "public_read": true,
                "encryption": "AES256"
              },
              ...
            ]
          }
        """
        env = CloudAuditorEnvironment()
        env.reset()  # _reset_count=1
        obs = env.step(CloudAuditorAction(command="describe_buckets"))

        payload = json.loads(obs.command_output)
        assert "buckets" in payload
        buckets = payload["buckets"]
        assert len(buckets) > 0

        bucket = buckets[0]
        assert "name" in bucket
        assert "purpose" in bucket
        assert "public_read" in bucket
        assert "encryption" in bucket

    def test_describe_iam_users_response_structure(self):
        """Test: describe_iam_users returns user metadata.

        Response format:
          {
            "users": [
              {
                "user_name": "alice-admin",
                "last_login_days": 140,
                "policies": ["AdministratorAccess"],
                "access_keys": [
                  {
                    "id": "AKIAALICE001",
                    "status": "Active"
                  },
                  ...
                ]
              },
              ...
            ]
          }
        """
        env = CloudAuditorEnvironment()
        env.reset()  # _reset_count=1
        env.reset()  # _reset_count=2
        obs = env.step(CloudAuditorAction(command="describe_iam_users"))

        payload = json.loads(obs.command_output)
        assert "users" in payload
        users = payload["users"]
        assert len(users) > 0

        user = users[0]
        assert "user_name" in user
        assert "last_login_days" in user
        assert "policies" in user
        assert "access_keys" in user

        key = user["access_keys"][0]
        assert "id" in key
        assert "status" in key


class TestAgentErrorRecovery:
    """Test cases for agent error handling and recovery."""

    def test_agent_malformed_option_recovery(self):
        """Test: Agent sends command with incorrect option format.

        Request:
          { "action": { "command": "describe_security_groups group-id sg-web" } }
          (Missing -- prefix)

        Expected response:
          - reward: negative
          - command_output: contains "Error"
          - Episode continues (agent can retry)
        """
        env = CloudAuditorEnvironment()
        env.reset()

        obs = env.step(CloudAuditorAction(command="describe_security_groups group-id sg-web"))
        assert obs.reward < 0.0
        assert obs.done is False  # Episode continues

    def test_agent_nonexistent_resource_graceful_failure(self):
        """Test: Agent queries for non-existent resource.

        Request:
          { "action": { "command": "describe_security_groups --group-id sg-nonexistent" } }

        Expected response:
          - command_output: "Error: security group 'sg-nonexistent' not found"
          - reward: negative
          - Episode continues
        """
        env = CloudAuditorEnvironment()
        env.reset()

        obs = env.step(
            CloudAuditorAction(command="describe_security_groups --group-id sg-nonexistent")
        )
        assert "not found" in obs.command_output or "Error" in obs.command_output
        assert obs.reward < 0.0
        assert obs.done is False
