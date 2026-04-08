# Grader Walkthrough

This document makes task grading behavior explicit and testable.

## How Scoring Works

Each step returns:
- `task_score`: deterministic milestone score in `[0.0, 1.0]`
- `reward`: shaped reward for that step (step penalty + milestone rewards + score-delta component)

The per-step reward includes:
1. Base efficiency penalty: `-0.01` every step.
2. Command/milestone reward: command-specific bonus (awarded once per milestone flag).
3. Score-delta shaping: `0.8 * (current_task_score - previous_task_score)`.
4. Completion bonus: `+0.15` once when the task completes.

Milestones are cumulative and sticky:
- once a progress flag is earned, it is not removed,
- repeated investigation does not re-award the same one-time bonus,
- score progression is monotonic for correct progress.

## Evaluator-Sample Walkthrough: cascading_failure (Illustrative)

The external evaluation request included this sample scenario. It is shown here as an illustrative pattern of how one-time flags and belief alignment bonuses accumulate.

Task: `cascading_failure`

Step 1: `check_logs`
- Reward impact: `+0.15` evidence bonus
- Note: marks `investigations.logs`

Step 2: `update_belief` with `{auth: 0.3, db: 0.5, network: 0.2}`
- Reward impact: `+0.10` belief alignment bonus

Step 3: `wait`
- Reward impact: `-0.01` efficiency penalty

Step 4: `update_belief` with `{auth: 0.1, db: 0.8, network: 0.1}`
- Reward impact: `+0.15` improved belief alignment

Step 5: `check_logs` again
- Reward impact: no extra evidence bonus (already earned for `investigations.logs`)

Step 6: `commit_fix("restart_db")`
- Reward impact: `+0.37` (correct fix + coordination + evidence shaping)
- Final score example: `0.76` (assuming other factors)

Important: `cascading_failure` is not one of the three runtime tasks in this repository; it is included here to clarify scoring semantics requested by evaluators.

## Cloud Auditor Task Walkthroughs (Runtime)

### Task: task_easy_ssh

Goal: revoke world-open SSH rule on the web security group.

Example episode:
1. `describe_instances`
- score goes from `0.10` to `0.40`
- milestone flags: `easy_used_describe_instances`, `easy_found_web_server`

2. `describe_security_groups --group-id sg-web`
- score goes from `0.40` to `0.70`
- milestone flag: `easy_identified_target_sg`

3. `revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0`
- score goes from `0.70` to `0.95`
- milestone flag: `easy_revoked_ssh`
- task completes and receives completion bonus once

Repeated `describe_security_groups` calls do not re-award `easy_identified_target_sg`.

### Task: task_medium_s3

Goal: disable public read on `customer-backup-prod`.

Example episode:
1. `describe_buckets`
- score goes from `0.10` to `0.40`

2. `put_public_access_block --bucket customer-backup-prod --block-public-read true`
- score goes from `0.40` to `0.95`
- completion bonus applies once

### Task: task_hard_iam

Goal: disable all access keys for stale admin user `alice-admin`.

Example episode:
1. `describe_iam_users`
- score from `0.10` to `0.25`

2. `list_attached_user_policies --user-name alice-admin`
- score from `0.25` to `0.45`

3. `list_access_keys --user-name alice-admin`
- score from `0.45` to `0.65`

4. `update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive`
- score from `0.65` to `0.80`

5. `update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive`
- score from `0.80` to `0.95`
- completion bonus applies once

## Why Task Weights Differ

Task schemas intentionally differ because complexity differs:
- `task_easy_ssh`: short path with one critical remediation action.
- `task_medium_s3`: two-step flow with a single high-confidence fix.
- `task_hard_iam`: multi-step identity investigation and multiple key remediations.

The harder task includes more intermediate milestones so agents can receive partial credit for meaningful progress before full completion.
