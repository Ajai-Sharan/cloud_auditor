# Baseline Results

This file records reproducible baseline runs for all runtime tasks.

## Run Configuration

- Script: `inference.py`
- Model: `llama-3.3-70b-versatile` (Groq)
- Environment URL default: `http://localhost:8000`
- Max steps per task: `15`
- Tasks: `task_easy_ssh`, `task_medium_s3`, `task_hard_iam`

## How To Run

1. Start environment server:

```bash
python -m server.app --host 0.0.0.0 --port 8000
```

2. Set model and proxy variables (example):

```bash
set API_KEY=YOUR_KEY
set API_BASE_URL=https://router.huggingface.co/v1
set MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
set ENV_URL=http://localhost:8000
```

3. Run baseline and save output:

```bash
python inference.py > baseline_cloud_auditor.txt
```

## Model Comparison Summary

| Model | Easy SSH | Medium S3 | Hard IAM | Mean Score | Best Task | Notes |
|---|---:|---:|---:|---:|---|---|
| llama-3.3-70b-versatile (Groq) | 0.700 | 0.400 | 0.250 | 0.450 | Easy (15 steps) | Baseline reference |
| Cerebras llama3.1-8b | 0.950 | 0.400 | 0.250 | 0.533 | Easy (5 steps) | Fast convergence on easy task |
| meta/Llama-3.3-70B-Instruct | 0.700 | 0.400 | 0.250 | 0.450 | Easy (15 steps) | Positional command issues |
| meta/Llama-4-Maverick-17B-128E-Instruct-FP8 | 0.950 | 0.400 | 0.250 | 0.533 | Easy (3 steps) | **Fastest easy task completion** |
| microsoft/Phi-4 | 0.400 | 0.400 | 0.250 | 0.350 | Medium/Hard (tied) | Backtick parsing issues |
| mistral-ai/Codestral-2501 | 0.700 | 0.400 | 0.250 | 0.450 | Easy (15 steps) | Underscore parameter names |

## Latest Local Baseline (To Be Updated Per Evaluation Run)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.700 | 15 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.450 | - | - |

## Cerebras Baseline Run (`llama3.1-8b`)


| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.950 | 5 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.533 | - | - |

Notes:
- task_easy_ssh reached `done=true` at step 5, but did not meet the exact success threshold.
- task_medium_s3 and task_hard_iam both exhausted the 15-step limit without success.

## Baseline Run (`meta/Llama-3.3-70B-Instruct`)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.700 | 15 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.450 | - | - |

Notes:
- task_easy_ssh repeatedly used positional revoke arguments (for example `revoke_security_group_ingress sg-web tcp 22 0.0.0.0/0`) instead of the expected option-based form.
- task_medium_s3 attempted `put_public_access_block` with unsupported argument patterns such as `--bucket-name` and function-style syntax.
- task_hard_iam issued concatenated multi-command strings and malformed `update_access_key` arguments, leading to no successful remediation.

## Baseline Run (`meta/Llama-4-Maverick-17B-128E-Instruct-FP8`)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.950 | 3 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.533 | - | - |

Notes:
- task_easy_ssh converged quickly in 3 steps but still ended below the strict success threshold.
- task_medium_s3 used `put_public_access_block` with `--bucket-name` and `key=value` style flags rather than the expected command schema.
- task_hard_iam repeatedly attempted semicolon-chained multi-actions and underscore option names (for example `--user_name`, `--access_key_id`), which were not accepted.

## Baseline Run (`microsoft/Phi-4`)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.400 | 15 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.350 | - | - |

Notes:
- task_easy_ssh wrapped actions in backticks (for example `` `describe_security_groups --group-ids sg-web` ``), causing parsing failures.
- task_medium_s3 used simplified flag names like `--public-read-block` instead of the full `--block-public-acls`, etc.
- task_hard_iam included placeholder arguments like `--user-name <user_name>` and `--user-name <user-name>`, indicating no dynamic value extraction.

## Baseline Run (`mistral-ai/Codestral-2501`)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.700 | 15 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.450 | - | - |

Notes:
- task_easy_ssh used underscore-based parameter names (for example `--group_id` instead of `--group-id`) and mixed positional arguments.
- task_medium_s3 used underscore separators in flags (for example `--bucket_name`, `--block_public_acls`) and Python-style boolean capitalization (e.g., `True` instead of `true`).
- task_hard_iam failed to build complete update commands, using bare key IDs without the required `--user-name` identifier.

## Repeat-Run Comparison (Groq)

Two consecutive runs with the same model produced identical outputs:

- task_easy_ssh: `0.700` vs `0.700`
- task_medium_s3: `0.400` vs `0.400`
- task_hard_iam: `0.250` vs `0.250`
- mean: `0.450` vs `0.450`

Conclusion: results are stable/reproducible for this model and setup.
