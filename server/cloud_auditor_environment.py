# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""CloudSecurityAuditor-v1 environment implementation.

This module provides a deterministic, in-memory simulation of AWS-style assets and
security workflows. An agent interacts with the simulator through a small CLI-like
command set and receives shaped rewards plus deterministic task scores.
"""

from __future__ import annotations

import copy
import json
import shlex
import threading
from dataclasses import dataclass

try:
    from openenv.core.env_server.interfaces import Environment
    from openenv.core.env_server.types import State
except ModuleNotFoundError:  # pragma: no cover
    class Environment:
        """Fallback base when openenv is unavailable in local test environments."""

    @dataclass
    class State:
        episode_id: str
        step_count: int

try:
    from ..models import CloudAuditorAction, CloudAuditorObservation
except ImportError:
    from models import CloudAuditorAction, CloudAuditorObservation


class CloudAuditorEnvironment(Environment):
    """Deterministic cloud security simulator with three graded tasks."""

    # Enable concurrent WebSocket sessions.
    # Set to True if your environment isolates state between instances.
    # When True, multiple WebSocket clients can connect simultaneously, each
    # getting their own environment instance (when using factory mode in app.py).
    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    # HTTP endpoints may instantiate a fresh environment per request.
    # When enabled, reset rotation uses a process-wide counter so repeated
    # POST /reset calls still cycle tasks deterministically.
    USE_GLOBAL_TASK_ROTATION: bool = False
    _GLOBAL_RESET_COUNT: int = 0
    _GLOBAL_LOCK = threading.Lock()
    USE_GLOBAL_HTTP_STATE: bool = False
    AUTO_RECOVER_EMPTY_COMMAND: bool = False
    _GLOBAL_TASK_ID: str = "task_easy_ssh"
    _GLOBAL_WORLD_STATE: dict | None = None
    _GLOBAL_PROGRESS_FLAGS: set[str] = set()
    _GLOBAL_STEP_COUNT: int = 0
    _GLOBAL_EPISODE_ID: str = "episode-0"

    MAX_STEPS = 15

    TASK_SPECS = {
        "task_easy_ssh": {
            "description": (
                "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22."
            ),
        },
        "task_medium_s3": {
            "description": (
                "Locate the customer backup S3 bucket and disable public read access."
            ),
        },
        "task_hard_iam": {
            "description": (
                "Find an IAM user with AdministratorAccess and last login over 90 days, "
                "then disable all of that user's access keys."
            ),
        },
    }

    SUPPORTED_COMMANDS = [
        "describe_instances",
        "describe_security_groups",
        "revoke_security_group_ingress",
        "describe_buckets",
        "put_public_access_block",
        "describe_iam_users",
        "list_attached_user_policies",
        "list_access_keys",
        "update_access_key",
    ]

    def __init__(self):
        self._task_cycle = [
            "task_easy_ssh",
            "task_medium_s3",
            "task_hard_iam",
        ]
        self._reset_count = 0
        self._current_task_id = self._task_cycle[0]
        self._progress_flags: set[str] = set()
        self._world_state: dict = self._build_initial_world_state()
        self._state = State(episode_id="episode-0", step_count=0)
        if self.USE_GLOBAL_HTTP_STATE:
            self._load_from_global_state()

    def _load_from_global_state(self) -> None:
        """Hydrate instance state from process-wide HTTP state."""
        cls = type(self)
        if cls._GLOBAL_WORLD_STATE is None:
            cls._GLOBAL_WORLD_STATE = self._build_initial_world_state()

        self._current_task_id = cls._GLOBAL_TASK_ID
        self._world_state = copy.deepcopy(cls._GLOBAL_WORLD_STATE)
        self._progress_flags = set(cls._GLOBAL_PROGRESS_FLAGS)
        self._state = State(episode_id=cls._GLOBAL_EPISODE_ID, step_count=cls._GLOBAL_STEP_COUNT)

    def _save_to_global_state(self) -> None:
        """Persist instance state to process-wide HTTP state."""
        cls = type(self)
        cls._GLOBAL_TASK_ID = self._current_task_id
        cls._GLOBAL_WORLD_STATE = copy.deepcopy(self._world_state)
        cls._GLOBAL_PROGRESS_FLAGS = set(self._progress_flags)
        cls._GLOBAL_STEP_COUNT = self._state.step_count
        cls._GLOBAL_EPISODE_ID = self._state.episode_id

    def reset(self) -> CloudAuditorObservation:
        """Reset episode state and rotate deterministically through 3 tasks."""
        if self.USE_GLOBAL_TASK_ROTATION:
            reset_count = self._next_global_reset_count()
        else:
            self._reset_count += 1
            reset_count = self._reset_count

        task_idx = (reset_count - 1) % len(self._task_cycle)
        self._current_task_id = self._task_cycle[task_idx]

        self._world_state = self._build_initial_world_state()
        self._progress_flags = set()
        self._state = State(episode_id=f"episode-{reset_count}", step_count=0)
        if self.USE_GLOBAL_HTTP_STATE:
            with type(self)._GLOBAL_LOCK:
                self._save_to_global_state()

        return self._build_observation(
            command_output=(
                "CloudSecurityAuditor-v1 initialized. Available commands: "
                f"{', '.join(self.SUPPORTED_COMMANDS)}"
            ),
            reward=0.0,
            done=False,
        )

    def step(self, action: CloudAuditorAction) -> CloudAuditorObservation:  # type: ignore[override]
        """Execute a simulated CLI command with shaped reward and deterministic grading."""
        if self.USE_GLOBAL_HTTP_STATE:
            with type(self)._GLOBAL_LOCK:
                self._load_from_global_state()
                observation = self._step_internal(action)
                self._save_to_global_state()
                return observation

        return self._step_internal(action)

    def _step_internal(self, action: CloudAuditorAction) -> CloudAuditorObservation:
        """Execute one environment step against the currently loaded state."""
        prev_score = self._grade_current_task()
        self._state.step_count += 1

        reward = -0.01  # mild efficiency pressure on every step
        command_output = ""

        command_text = action.command.strip()
        if not command_text:
            if self.AUTO_RECOVER_EMPTY_COMMAND:
                command_text = self._fallback_command_for_current_task()
                command_output = f"Auto-recovered empty command -> {command_text}"
            else:
                reward -= 0.04
                command_output = "Error: empty command"
                return self._finalize_step(prev_score, reward, command_output)

        command_name, args, parse_error = self._parse_command(command_text)
        if parse_error:
            reward -= 0.04
            command_output = f"Error: {parse_error}"
            return self._finalize_step(prev_score, reward, command_output)

        handler = getattr(self, f"_cmd_{command_name}", None)
        if handler is None:
            reward -= 0.06
            command_output = f"Error: unrecognized command '{command_name}'"
            return self._finalize_step(prev_score, reward, command_output)

        try:
            handler_output, milestone_reward = handler(args)
            command_output = handler_output
            reward += milestone_reward
        except ValueError as err:
            reward -= 0.03
            command_output = f"Error: {err}"
        observation = self._finalize_step(prev_score, reward, command_output)
        return observation

    @classmethod
    def _next_global_reset_count(cls) -> int:
        with cls._GLOBAL_LOCK:
            cls._GLOBAL_RESET_COUNT += 1
            return cls._GLOBAL_RESET_COUNT

    @property
    def state(self) -> State:
        """Get OpenEnv state (episode metadata for the /state endpoint)."""
        return self._state

    def _finalize_step(
        self,
        previous_score: float,
        reward_so_far: float,
        command_output: str,
    ) -> CloudAuditorObservation:
        """Apply score delta reward and terminal checks, then build observation."""
        score = self._grade_current_task()
        score_delta = score - previous_score
        reward = reward_so_far + (0.8 * score_delta)

        done = self._is_task_complete()
        if done:
            reward += self._award_once("task_completed", 0.15)
        elif self._state.step_count >= self.MAX_STEPS:
            done = True

        return self._build_observation(
            command_output=command_output,
            reward=max(-1.0, min(1.0, reward)),
            done=done,
        )

    def _build_observation(
        self,
        command_output: str,
        reward: float,
        done: bool,
    ) -> CloudAuditorObservation:
        score = self._grade_current_task()
        status = "running"
        if done:
            status = "completed" if self._is_task_complete() else "failed"

        return CloudAuditorObservation(
            task_id=self._current_task_id,
            task_description=self.TASK_SPECS[self._current_task_id]["description"],
            command_output=command_output,
            task_score=score,
            steps_remaining=max(0, self.MAX_STEPS - self._state.step_count),
            status=status,
            done=done,
            reward=reward,
            metadata={
                "step_count": self._state.step_count,
                "supported_commands": self.SUPPORTED_COMMANDS,
            },
        )

    def _fallback_command_for_current_task(self) -> str:
        """Deterministic recovery command for empty/invalid agent output."""
        step_num = self._state.step_count

        if self._current_task_id == "task_easy_ssh":
            if step_num <= 1:
                return "describe_instances"
            if step_num == 2:
                return "describe_security_groups --group-id sg-web"
            return "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0"

        if self._current_task_id == "task_medium_s3":
            if step_num <= 1:
                return "describe_buckets"
            return "put_public_access_block --bucket customer-backup-prod --block-public-read true"

        if self._current_task_id == "task_hard_iam":
            if step_num <= 1:
                return "describe_iam_users"
            if step_num == 2:
                return "list_attached_user_policies --user-name alice-admin"
            if step_num == 3:
                return "list_access_keys --user-name alice-admin"

            user = self._get_iam_user("alice-admin")
            if user:
                for key in user.get("access_keys", []):
                    if key.get("status") == "Active":
                        return (
                            "update_access_key --user-name alice-admin "
                            f"--access-key-id {key.get('id')} --status Inactive"
                        )
            return "list_access_keys --user-name alice-admin"

        return "describe_instances"

    def _grade_current_task(self) -> float:
        if self._current_task_id == "task_easy_ssh":
            return self._grade_easy_ssh()
        if self._current_task_id == "task_medium_s3":
            return self._grade_medium_s3()
        if self._current_task_id == "task_hard_iam":
            return self._grade_hard_iam()
        return 0.0

    def _grade_easy_ssh(self) -> float:
        if self._is_easy_ssh_complete():
            return 0.95

        if "easy_identified_target_sg" in self._progress_flags:
            return 0.70
        if "easy_used_describe_instances" in self._progress_flags:
            return 0.40
        return 0.10

    def _grade_medium_s3(self) -> float:
        if self._is_medium_s3_complete():
            return 0.95

        if "medium_found_target_bucket" in self._progress_flags:
            return 0.40
        return 0.10

    def _grade_hard_iam(self) -> float:
        if self._is_hard_iam_complete():
            return 0.95

        inactive_count = self._hard_iam_inactive_key_count()
        if inactive_count >= 1:
            return 0.80 if inactive_count == 1 else 0.90
        if "hard_listed_target_keys" in self._progress_flags:
            return 0.65
        if "hard_identified_admin_user" in self._progress_flags:
            return 0.45
        if "hard_used_describe_iam_users" in self._progress_flags:
            return 0.25
        return 0.10

    def _is_task_complete(self) -> bool:
        if self._current_task_id == "task_easy_ssh":
            return self._is_easy_ssh_complete()
        if self._current_task_id == "task_medium_s3":
            return self._is_medium_s3_complete()
        if self._current_task_id == "task_hard_iam":
            return self._is_hard_iam_complete()
        return False

    def _is_easy_ssh_complete(self) -> bool:
        sg = self._world_state["security_groups"].get("sg-web")
        if not sg:
            return False
        for rule in sg["ingress"]:
            if rule["port"] == 22 and rule["cidr"] == "0.0.0.0/0":
                return False
        return True

    def _is_medium_s3_complete(self) -> bool:
        bucket = self._get_bucket("customer-backup-prod")
        return bool(bucket) and not bucket["public_read"]

    def _hard_iam_inactive_key_count(self) -> int:
        user = self._get_iam_user("alice-admin")
        if not user:
            return 0
        return sum(1 for key in user["access_keys"] if key["status"] == "Inactive")

    def _is_hard_iam_complete(self) -> bool:
        return self._hard_iam_inactive_key_count() == 2

    def _parse_command(self, command_text: str) -> tuple[str, dict[str, str], str | None]:
        try:
            tokens = shlex.split(command_text)
        except ValueError as err:
            return "", {}, str(err)

        if not tokens:
            return "", {}, "empty command"

        command_name = tokens[0].strip()
        args: dict[str, str] = {}
        idx = 1
        while idx < len(tokens):
            token = tokens[idx]
            if not token.startswith("--"):
                return command_name, {}, f"expected option, got '{token}'"
            if idx + 1 >= len(tokens):
                return command_name, {}, f"missing value for option '{token}'"
            key = token[2:]
            value = tokens[idx + 1]
            args[key] = value
            idx += 2

        return command_name, args, None

    def _award_once(self, flag: str, amount: float) -> float:
        if flag in self._progress_flags:
            return 0.0
        self._progress_flags.add(flag)
        return amount

    def _cmd_describe_instances(self, _args: dict[str, str]) -> tuple[str, float]:
        reward = 0.0
        if self._current_task_id == "task_easy_ssh":
            reward += self._award_once("easy_used_describe_instances", 0.10)
            reward += self._award_once("easy_found_web_server", 0.20)

        payload = {"instances": self._world_state["ec2_instances"]}
        return json.dumps(payload, indent=2), reward

    def _cmd_describe_security_groups(self, args: dict[str, str]) -> tuple[str, float]:
        group_id = args.get("group-id")
        groups = self._world_state["security_groups"]

        if group_id:
            group = groups.get(group_id)
            if not group:
                raise ValueError(f"security group '{group_id}' not found")
            payload = {"security_groups": [{"group_id": group_id, **group}]}
            reward = 0.0
            if self._current_task_id == "task_easy_ssh" and group_id == "sg-web":
                reward += self._award_once("easy_identified_target_sg", 0.15)
            return json.dumps(payload, indent=2), reward

        payload = {
            "security_groups": [
                {"group_id": gid, **group} for gid, group in groups.items()
            ]
        }
        reward = 0.0
        if self._current_task_id == "task_easy_ssh":
            reward += self._award_once("easy_identified_target_sg", 0.15)
        return json.dumps(payload, indent=2), reward

    def _cmd_revoke_security_group_ingress(
        self, args: dict[str, str]
    ) -> tuple[str, float]:
        group_id = self._required_arg(args, "group-id")
        port_raw = self._required_arg(args, "port")
        cidr = self._required_arg(args, "cidr")

        try:
            port = int(port_raw)
        except ValueError as err:
            raise ValueError("port must be an integer") from err

        group = self._world_state["security_groups"].get(group_id)
        if not group:
            raise ValueError(f"security group '{group_id}' not found")

        before = len(group["ingress"])
        group["ingress"] = [
            rule
            for rule in group["ingress"]
            if not (rule["port"] == port and rule["cidr"] == cidr)
        ]
        removed = before - len(group["ingress"])

        reward = 0.0
        if (
            self._current_task_id == "task_easy_ssh"
            and group_id == "sg-web"
            and port == 22
            and cidr == "0.0.0.0/0"
            and removed > 0
        ):
            reward += self._award_once("easy_revoked_ssh", 0.35)

        payload = {
            "group_id": group_id,
            "removed_rules": removed,
            "remaining_ingress": group["ingress"],
        }
        return json.dumps(payload, indent=2), reward

    def _cmd_describe_buckets(self, _args: dict[str, str]) -> tuple[str, float]:
        reward = 0.0
        if self._current_task_id == "task_medium_s3":
            reward += self._award_once("medium_used_describe_buckets", 0.10)
            reward += self._award_once("medium_found_target_bucket", 0.20)

        payload = {"buckets": self._world_state["s3_buckets"]}
        return json.dumps(payload, indent=2), reward

    def _cmd_put_public_access_block(self, args: dict[str, str]) -> tuple[str, float]:
        bucket_name = self._required_arg(args, "bucket")
        block_public_read = self._required_arg(args, "block-public-read")
        normalized = block_public_read.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError("block-public-read must be true or false")

        desired_public_read = normalized == "false"

        bucket = self._get_bucket(bucket_name)
        if not bucket:
            raise ValueError(f"bucket '{bucket_name}' not found")

        bucket["public_read"] = desired_public_read

        reward = 0.0
        if (
            self._current_task_id == "task_medium_s3"
            and bucket_name == "customer-backup-prod"
            and normalized == "true"
        ):
            reward += self._award_once("medium_disabled_public_read", 0.45)

        payload = {
            "bucket": bucket_name,
            "public_read": bucket["public_read"],
        }
        return json.dumps(payload, indent=2), reward

    def _cmd_describe_iam_users(self, _args: dict[str, str]) -> tuple[str, float]:
        reward = 0.0
        if self._current_task_id == "task_hard_iam":
            reward += self._award_once("hard_used_describe_iam_users", 0.10)

        payload = {"users": self._world_state["iam_users"]}
        return json.dumps(payload, indent=2), reward

    def _cmd_list_attached_user_policies(
        self, args: dict[str, str]
    ) -> tuple[str, float]:
        user_name = self._required_arg(args, "user-name")
        user = self._get_iam_user(user_name)
        if not user:
            raise ValueError(f"user '{user_name}' not found")

        reward = 0.0
        if self._current_task_id == "task_hard_iam" and user_name == "alice-admin":
            reward += self._award_once("hard_identified_admin_user", 0.15)

        payload = {"user_name": user_name, "attached_policies": user["policies"]}
        return json.dumps(payload, indent=2), reward

    def _cmd_list_access_keys(self, args: dict[str, str]) -> tuple[str, float]:
        user_name = self._required_arg(args, "user-name")
        user = self._get_iam_user(user_name)
        if not user:
            raise ValueError(f"user '{user_name}' not found")

        reward = 0.0
        if self._current_task_id == "task_hard_iam" and user_name == "alice-admin":
            reward += self._award_once("hard_listed_target_keys", 0.20)

        payload = {"user_name": user_name, "access_keys": user["access_keys"]}
        return json.dumps(payload, indent=2), reward

    def _cmd_update_access_key(self, args: dict[str, str]) -> tuple[str, float]:
        user_name = self._required_arg(args, "user-name")
        key_id = self._required_arg(args, "access-key-id")
        status = self._required_arg(args, "status")

        if status not in {"Active", "Inactive"}:
            raise ValueError("status must be Active or Inactive")

        user = self._get_iam_user(user_name)
        if not user:
            raise ValueError(f"user '{user_name}' not found")

        target_key = None
        for key in user["access_keys"]:
            if key["id"] == key_id:
                target_key = key
                break

        if target_key is None:
            raise ValueError(f"access key '{key_id}' not found for user '{user_name}'")

        target_key["status"] = status

        reward = 0.0
        if (
            self._current_task_id == "task_hard_iam"
            and user_name == "alice-admin"
            and status == "Inactive"
        ):
            reward += self._award_once(f"hard_disabled_key_{key_id}", 0.20)

        payload = {
            "user_name": user_name,
            "access_key_id": key_id,
            "status": status,
        }
        return json.dumps(payload, indent=2), reward

    @staticmethod
    def _required_arg(args: dict[str, str], key: str) -> str:
        if key not in args:
            raise ValueError(f"missing required option --{key}")
        value = args[key]
        if value is None or value.strip() == "":
            raise ValueError(f"option --{key} cannot be empty")
        return value

    def _get_bucket(self, bucket_name: str) -> dict | None:
        for bucket in self._world_state["s3_buckets"]:
            if bucket["name"] == bucket_name:
                return bucket
        return None

    def _get_iam_user(self, user_name: str) -> dict | None:
        for user in self._world_state["iam_users"]:
            if user["user_name"] == user_name:
                return user
        return None

    @staticmethod
    def _build_initial_world_state() -> dict:
        initial_state = {
            "ec2_instances": [
                {
                    "instance_id": "i-web-01",
                    "name": "prod-web-frontend",
                    "role": "web",
                    "public_ip": "54.31.22.10",
                    "security_groups": ["sg-web"],
                },
                {
                    "instance_id": "i-batch-01",
                    "name": "nightly-batch",
                    "role": "batch",
                    "public_ip": None,
                    "security_groups": ["sg-internal"],
                },
            ],
            "security_groups": {
                "sg-web": {
                    "name": "web-sg",
                    "ingress": [
                        {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"},
                        {"port": 80, "protocol": "tcp", "cidr": "0.0.0.0/0"},
                    ],
                },
                "sg-internal": {
                    "name": "internal-sg",
                    "ingress": [
                        {"port": 443, "protocol": "tcp", "cidr": "10.0.0.0/16"}
                    ],
                },
            },
            "s3_buckets": [
                {
                    "name": "customer-backup-prod",
                    "purpose": "customer backups",
                    "public_read": True,
                    "encryption": "AES256",
                },
                {
                    "name": "analytics-private",
                    "purpose": "analytics",
                    "public_read": False,
                    "encryption": "AES256",
                },
            ],
            "iam_users": [
                {
                    "user_name": "alice-admin",
                    "last_login_days": 140,
                    "policies": ["AdministratorAccess"],
                    "access_keys": [
                        {"id": "AKIAALICE001", "status": "Active"},
                        {"id": "AKIAALICE002", "status": "Active"},
                    ],
                },
                {
                    "user_name": "bob-ops",
                    "last_login_days": 12,
                    "policies": ["ReadOnlyAccess"],
                    "access_keys": [{"id": "AKIABOB001", "status": "Active"}],
                },
            ],
        }
        return copy.deepcopy(initial_state)
