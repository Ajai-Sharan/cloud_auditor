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

## Latest Local Baseline (To Be Updated Per Evaluation Run)

| Task | Score | Steps | Success |
|---|---:|---:|---|
| task_easy_ssh | 0.700 | 15 | false |
| task_medium_s3 | 0.400 | 15 | false |
| task_hard_iam | 0.250 | 15 | false |
| Mean score | 0.450 | - | - |

## Repeat-Run Comparison (Groq)

Two consecutive runs with the same model produced identical outputs:

- task_easy_ssh: `0.700` vs `0.700`
- task_medium_s3: `0.400` vs `0.400`
- task_hard_iam: `0.250` vs `0.250`
- mean: `0.450` vs `0.450`

Conclusion: results are stable/reproducible for this model and setup.
