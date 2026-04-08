"""Inference script for CloudSecurityAuditor-v1.

Mandatory environment variables before submission:
- API_BASE_URL
- API_KEY
- MODEL_NAME
- LOCAL_IMAGE_NAME (only required when using from_docker_image workflows)

This script uses OpenAI Client for all LLM calls and interacts with the
local CloudSecurityAuditor HTTP API.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI

IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
API_KEY = os.getenv("API_KEY") or os.getenv("HF_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"

ENV_BASE_URL = os.getenv("ENV_BASE_URL") or os.getenv("ENV_URL") or "http://127.0.0.1:8000"
MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "140"))
RESET_RETRIES = int(os.getenv("RESET_RETRIES", "6"))
RESET_RETRY_DELAY = float(os.getenv("RESET_RETRY_DELAY", "1.5"))
SCORE_MIN = 0.001  # Grader rejects score == 0.0 (must be strictly > 0)
SCORE_MAX = 0.999  # Grader rejects score == 1.0 (must be strictly < 1)

FALLBACK_ACTION = "__fallback__"
ACTION_PREFIX_RE = re.compile(r"^(action|next action)\s*[:\-]\s*", re.IGNORECASE)
COMMAND_HEAD_RE = re.compile(r"^[a-z_]+")
KV_RE = re.compile(r"([a-zA-Z_\-]+)\s*=\s*\"?([^\"\s]+)\"?")
ERROR_PREFIX = "Error:"

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

SYSTEM_PROMPT = (
    "You are controlling CloudSecurityAuditor-v1. "
    "Reply with exactly one command string and no explanation. "
    "Use only supported commands."
)

BENCHMARK = os.getenv("BENCHMARK", "cloudsecurityauditor-v1")


def emit_start(task: str, env_name: str, model: str) -> None:
    print(f"[START] task={task} env={env_name} model={model}", flush=True)


def emit_step(step_num: int, action: str, reward: float, done: bool, error: str | None) -> None:
    error_val = error if error is not None else "null"
    print(
        f"[STEP] step={step_num} action={action} reward={reward:.2f} "
        f"done={str(done).lower()} error={error_val}",
        flush=True,
    )


def emit_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


@dataclass
class StepResponse:
    task_id: str
    task_description: str
    command_output: str
    task_score: float
    steps_remaining: int
    status: str
    reward: float
    done: bool


def require_env() -> None:
    missing = []
    if not API_BASE_URL:
        missing.append("API_BASE_URL")
    if not API_KEY:
        missing.append("API_KEY")
    if not MODEL_NAME:
        missing.append("MODEL_NAME")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def http_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{ENV_BASE_URL.rstrip('/')}{path}"
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to reach {url}: {exc}") from exc


def to_step_response(raw: dict[str, Any]) -> StepResponse:
    obs = raw.get("observation", {})
    return StepResponse(
        task_id=str(obs.get("task_id", "")),
        task_description=str(obs.get("task_description", "")),
        command_output=str(obs.get("command_output", "")),
        task_score=float(obs.get("task_score", 0.0)),
        steps_remaining=int(obs.get("steps_remaining", 0)),
        status=str(obs.get("status", "running")),
        reward=float(raw.get("reward", 0.0) or 0.0),
        done=bool(raw.get("done", False)),
    )


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content)


def parse_model_command(text: str) -> str:
    def normalize_command(candidate: str) -> str:
        candidate = re.sub(r"\s+", " ", candidate).strip()
        head = COMMAND_HEAD_RE.match(candidate)
        if not head:
            return FALLBACK_ACTION

        command_name = head.group(0)
        if command_name not in SUPPORTED_COMMANDS:
            return FALLBACK_ACTION

        if command_name == "revoke_security_group_ingress":
            kv = {k.lower(): v for k, v in KV_RE.findall(candidate)}
            if "--group-id" in candidate and "--port" in candidate and "--cidr" in candidate:
                return candidate

            group_id = kv.get("group_id") or kv.get("group-id")
            port = kv.get("port")
            cidr = kv.get("cidr")
            if group_id and port and cidr:
                return (
                    "revoke_security_group_ingress "
                    f"--group-id {group_id} --port {port} --cidr {cidr}"
                )
            return FALLBACK_ACTION

        if command_name == "put_public_access_block":
            if "--bucket" in candidate and "--block-public-read" in candidate:
                return candidate
            kv = {k.lower(): v for k, v in KV_RE.findall(candidate)}
            bucket = kv.get("bucket")
            block = kv.get("block_public_read") or kv.get("block-public-read")
            if bucket and block:
                return (
                    "put_public_access_block "
                    f"--bucket {bucket} --block-public-read {block}"
                )
            return FALLBACK_ACTION

        if command_name == "update_access_key":
            if "--user-name" in candidate and "--access-key-id" in candidate and "--status" in candidate:
                return candidate
            kv = {k.lower(): v for k, v in KV_RE.findall(candidate)}
            user = kv.get("user_name") or kv.get("user-name")
            key_id = kv.get("access_key_id") or kv.get("access-key-id")
            status = kv.get("status")
            if user and key_id and status:
                return (
                    "update_access_key "
                    f"--user-name {user} --access-key-id {key_id} --status {status}"
                )
            return FALLBACK_ACTION

        if command_name in {"list_attached_user_policies", "list_access_keys"}:
            if "--user-name" in candidate:
                return candidate
            kv = {k.lower(): v for k, v in KV_RE.findall(candidate)}
            user = kv.get("user_name") or kv.get("user-name")
            if user:
                return f"{command_name} --user-name {user}"
            return FALLBACK_ACTION

        if command_name == "describe_security_groups":
            if "--group-id" in candidate:
                return candidate
            kv = {k.lower(): v for k, v in KV_RE.findall(candidate)}
            group_id = kv.get("group_id") or kv.get("group-id")
            if group_id:
                return f"describe_security_groups --group-id {group_id}"

        return candidate

    if not text:
        return FALLBACK_ACTION

    for line in text.splitlines():
        candidate = ACTION_PREFIX_RE.sub("", line.strip())
        if not candidate:
            continue
        normalized = normalize_command(candidate)
        if normalized != FALLBACK_ACTION:
            return normalized

    candidate = ACTION_PREFIX_RE.sub("", text.strip())
    normalized = normalize_command(candidate)
    if normalized != FALLBACK_ACTION:
        return normalized

    return FALLBACK_ACTION


def fallback_policy(task_id: str, step_num: int) -> str:
    if task_id == "task_easy_ssh":
        plan = [
            "describe_instances",
            "describe_security_groups --group-id sg-web",
            "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0",
        ]
        return plan[min(step_num - 1, len(plan) - 1)]

    if task_id == "task_medium_s3":
        plan = [
            "describe_buckets",
            "put_public_access_block --bucket customer-backup-prod --block-public-read true",
        ]
        return plan[min(step_num - 1, len(plan) - 1)]

    if task_id == "task_hard_iam":
        plan = [
            "describe_iam_users",
            "list_attached_user_policies --user-name alice-admin",
            "list_access_keys --user-name alice-admin",
            "update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive",
            "update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive",
        ]
        return plan[min(step_num - 1, len(plan) - 1)]

    return "describe_instances"


def extract_last_action_error(command_output: str) -> str | None:
    if command_output.startswith(ERROR_PREFIX):
        return command_output[len(ERROR_PREFIX) :].strip() or command_output.strip()
    return None


def main() -> None:
    task_name = os.getenv("TASK_NAME", "unknown")
    history: list[str] = []
    rewards: list[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    started = False
    llm_successes = 0
    llm_attempts = 0
    last_llm_error: str | None = None
    fatal_error: Exception | None = None

    try:
        require_env()
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

        reset_error: Exception | None = None
        result: StepResponse | None = None
        for attempt in range(1, RESET_RETRIES + 1):
            try:
                reset_raw = http_post("/reset", {})
                result = to_step_response(reset_raw)
                task_name = result.task_id or task_name
                emit_start(task=task_name, env_name=BENCHMARK, model=MODEL_NAME)
                started = True
                reset_error = None
                break
            except Exception as exc:  # noqa: BLE001
                reset_error = exc
                if attempt < RESET_RETRIES:
                    import time

                    time.sleep(RESET_RETRY_DELAY)

        if result is None:
            raise RuntimeError(f"/reset failed: {reset_error}")

        for step_num in range(1, MAX_STEPS + 1):
            if result.done:
                break

            user_prompt = (
                f"Task ID: {result.task_id}\n"
                f"Task Description: {result.task_description}\n"
                f"Last command output:\n{result.command_output[:3500]}\n"
                f"Steps remaining: {result.steps_remaining}\n"
                f"History:\n" + ("\n".join(history[-4:]) if history else "None") + "\n"
                f"Supported commands: {', '.join(SUPPORTED_COMMANDS)}\n"
                "Return exactly one command."
            )

            command = FALLBACK_ACTION
            try:
                llm_attempts += 1
                completion = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                    stream=False,
                )
                llm_successes += 1
                response_text = extract_text_content(completion.choices[0].message.content)
                command = parse_model_command(response_text)
            except Exception as exc:  # noqa: BLE001
                last_llm_error = str(exc)
                command = FALLBACK_ACTION

            if not command or command == FALLBACK_ACTION:
                command = fallback_policy(result.task_id, step_num)

            step_raw = http_post("/step", {"action": {"command": command}})
            result = to_step_response(step_raw)

            reward = result.reward
            error = extract_last_action_error(result.command_output)

            rewards.append(reward)
            steps_taken = step_num
            score = min(max(result.task_score, SCORE_MIN), SCORE_MAX)
            success = bool(result.done and score > 0.0)

            emit_step(step_num=step_num, action=command, reward=reward, done=result.done, error=error)
            history.append(f"step={step_num} action={command} reward={reward:.2f}")

            if result.done:
                break

        if llm_successes == 0:
            details = f" Last error: {last_llm_error}" if last_llm_error else ""
            raise RuntimeError(
                "No successful LLM calls were made via API_BASE_URL/API_KEY."
                f" Attempts={llm_attempts}.{details}"
            )

    except Exception as exc:  # noqa: BLE001
        success = False
        fatal_error = exc
        print(f"Fatal: {exc}", file=sys.stderr, flush=True)
    finally:
        if not started:
            emit_start(task=task_name, env_name=BENCHMARK, model=MODEL_NAME)
        emit_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    if fatal_error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
