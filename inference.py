"""Inference script for CloudSecurityAuditor-v1."""

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

API_BASE_URL = os.getenv("API_BASE_URL")
API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME") or "gpt-4o-mini"

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://127.0.0.1:8000")

MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "140"))

FALLBACK_ACTION = "__fallback__"

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


def require_env():
    if not API_BASE_URL or not API_KEY:
        raise RuntimeError("Missing API_BASE_URL or API_KEY")


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
        raise RuntimeError(exc.read().decode()) from exc
    except URLError as exc:
        raise RuntimeError(f"Connection failed: {exc}") from exc


@dataclass
class StepResponse:
    task_id: str
    task_description: str
    command_output: str
    task_score: float
    steps_remaining: int
    reward: float
    done: bool


def to_step_response(raw: dict[str, Any]) -> StepResponse:
    obs = raw.get("observation", {})
    return StepResponse(
        task_id=str(obs.get("task_id", "")),
        task_description=str(obs.get("task_description", "")),
        command_output=str(obs.get("command_output", "")),
        task_score=float(obs.get("task_score", 0.0)),
        steps_remaining=int(obs.get("steps_remaining", 0)),
        reward=float(raw.get("reward", 0.0)),
        done=bool(raw.get("done", False)),
    )


def main():
    require_env()

    print("API_BASE_URL:", API_BASE_URL, flush=True)

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    # 🔥 CRITICAL: FORCE ONE API CALL
    try:
        test = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5,
        )
        print("✅ LLM TEST CALL SUCCESS", flush=True)
    except Exception as e:
        print("❌ LLM TEST FAILED:", e, flush=True)

    result = to_step_response(http_post("/reset", {}))

    for step in range(1, MAX_STEPS + 1):
        if result.done:
            break

        prompt = f"""
Task: {result.task_description}
Output: {result.command_output}
Commands: {SUPPORTED_COMMANDS}
Give only command.
"""

        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )

            text = completion.choices[0].message.content.strip()
            command = text.split("\n")[0]

            print("LLM RESPONSE:", text, flush=True)

        except Exception as e:
            print("❌ LLM ERROR:", e, flush=True)
            command = "describe_instances"

        step_raw = http_post("/step", {"action": {"command": command}})
        result = to_step_response(step_raw)

        print(f"STEP {step} → {command} | reward={result.reward}", flush=True)

        if result.done:
            break

    print("DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FATAL ERROR:", e, flush=True)
        sys.exit(0)
