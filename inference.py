"""Inference script for CloudSecurityAuditor-v1 — Phase 2 Validation.

This script runs all three tasks in a single invocation and emits structured output:
  [START] task=<task_id> env=<benchmark> model=<model>
  [STEP] step=<n> action=<action> reward=<r> done=<true|false> error=<msg|null>
  [END] task=<task_id> success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...>

The validator injects:
  - API_KEY: used by OpenAI client for LLM calls through proxy
  - API_BASE_URL: proxy endpoint
  - MODEL_NAME: model to use
  - ENV_URL: environment HTTP endpoint (e.g., HF Space URL)
"""

from __future__ import annotations

import os
import json
import requests
from openai import OpenAI

# Read validator-injected environment variables
API_KEY = os.environ.get("API_KEY")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
ENV_URL = os.environ.get("ENV_URL", "https://ajaisharanv-cloud-auditor.hf.space")

# Configuration
BENCHMARK = "cloudsecurityauditor-v1"
MAX_STEPS = 15
TEMPERATURE = 0.2
MAX_TOKENS = 500

# Score bounds (grader rejects exactly 0.0 and 1.0)
SCORE_MIN = 0.001
SCORE_MAX = 0.999

# All three tasks to run
TASKS = [
    ("task_easy_ssh", "easy", "Find the web server and revoke its 0.0.0.0/0 ingress rule on port 22."),
    ("task_medium_s3", "medium", "Locate the customer backup S3 bucket and disable public read access."),
    ("task_hard_iam", "hard", "Find an IAM user with AdministratorAccess and disable all of that user's access keys."),
]

SYSTEM_PROMPT = (
    "You are controlling CloudSecurityAuditor-v1. "
    "Reply with exactly one command string and no explanation. "
    "Use only supported commands: "
    "describe_instances, describe_security_groups, revoke_security_group_ingress, "
    "describe_buckets, put_public_access_block, describe_iam_users, "
    "list_attached_user_policies, list_access_keys, update_access_key."
)


def emit_start(task: str, env: str, model: str) -> None:
    """Emit [START] marker for task."""
    print(f"[START] task={task} env={env} model={model}", flush=True)


def emit_step(step_num: int, action: str, reward: float, done: bool, error: str | None) -> None:
    """Emit [STEP] marker."""
    error_str = error if error else "null"
    print(
        f"[STEP] step={step_num} action={action[:500]} reward={reward:.2f} done={str(done).lower()} error={error_str}",
        flush=True,
    )


def emit_end(task: str, success: bool, steps: int, score: float, rewards: list[float]) -> None:
    """Emit [END] marker with task id, score and rewards."""
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] task={task} success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def main():
    """Run all tasks in sequence through HTTP environment."""
    # Create OpenAI client for all LLM calls (through proxy)
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    # Run each task in sequence
    for task_id, difficulty, description in TASKS:
        rewards = []
        steps = 0
        score = SCORE_MIN
        success = False

        emit_start(task_id, BENCHMARK, MODEL_NAME)

        try:
            # Reset environment for this task
            resp = requests.post(
                f"{ENV_URL}/reset",
                json={"task_id": task_id},
                timeout=30,
            )
            resp.raise_for_status()
            reset_data = resp.json()

            obs = reset_data.get("observation", {})
            done = reset_data.get("done", False)

            # Run episode loop
            for step in range(1, MAX_STEPS + 1):
                if done:
                    break

                # Get LLM action through validator's proxy
                try:
                    completion = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Task: {description}\n\nState: {json.dumps(obs, indent=2)}"},
                        ],
                        max_tokens=MAX_TOKENS,
                        temperature=TEMPERATURE,
                    )
                    action = completion.choices[0].message.content.strip()
                except Exception as e:
                    # Fallback action if LLM fails
                    action = "describe_instances"
                    emit_step(step, "ERROR", 0.0, False, str(e)[:100])
                    continue

                # Execute action in environment
                try:
                    resp = requests.post(
                        f"{ENV_URL}/step",
                        json={"action": {"command": action}},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    step_data = resp.json()

                    obs = step_data.get("observation", {})
                    reward = step_data.get("reward", 0.0) or 0.0
                    done = step_data.get("done", False)
                    error = obs.get("error") if isinstance(obs, dict) else None

                    rewards.append(reward)
                    steps = step

                    error_str = error if error else "null"
                    emit_step(step, action[:200], reward, done, error_str)

                except Exception as e:
                    emit_step(step, action[:200], 0.0, False, str(e)[:100])
                    break

                if done:
                    break

            # Extract final score from observation
            if isinstance(obs, dict):
                task_score = obs.get("task_score", 0.0) or 0.0
                success = obs.get("done", False)
            else:
                task_score = 0.0
                success = False

            # Clamp score to (SCORE_MIN, SCORE_MAX)
            score = max(SCORE_MIN, min(SCORE_MAX, task_score))
            if score <= 0.0:
                score = SCORE_MIN
            if score >= 1.0:
                score = SCORE_MAX

        except Exception as e:
            print(f"[DEBUG] {task_id} error: {e}", flush=True)
            score = SCORE_MIN

        finally:
            # Always emit [END], even if task failed
            emit_end(task_id, success, steps, score, rewards)


if __name__ == "__main__":
    main()
