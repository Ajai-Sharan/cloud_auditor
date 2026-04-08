import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import CloudAuditorAction
from server.cloud_auditor_environment import CloudAuditorEnvironment


def _cmd(env: CloudAuditorEnvironment, command: str):
    return env.step(CloudAuditorAction(command=command))


def test_reset_rotates_through_exact_three_tasks_deterministically():
    env = CloudAuditorEnvironment()

    obs1 = env.reset()
    obs2 = env.reset()
    obs3 = env.reset()
    obs4 = env.reset()

    assert obs1.task_id == "task_easy_ssh"
    assert obs2.task_id == "task_medium_s3"
    assert obs3.task_id == "task_hard_iam"
    assert obs4.task_id == "task_easy_ssh"


def test_easy_task_revoke_ssh_open_ingress():
    env = CloudAuditorEnvironment()
    reset_obs = env.reset()
    assert reset_obs.task_id == "task_easy_ssh"

    reconnaissance = _cmd(env, "describe_instances")
    assert reconnaissance.reward is not None
    assert reconnaissance.reward > 0.0

    remediation = _cmd(
        env,
        "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0",
    )
    assert remediation.done is True
    assert 0.0 < remediation.task_score < 1.0
    assert remediation.status == "completed"


def test_medium_task_disable_public_read():
    env = CloudAuditorEnvironment()
    env.reset()
    reset_obs = env.reset()
    assert reset_obs.task_id == "task_medium_s3"

    _cmd(env, "describe_buckets")
    remediation = _cmd(
        env,
        "put_public_access_block --bucket customer-backup-prod --block-public-read true",
    )

    assert remediation.done is True
    assert 0.0 < remediation.task_score < 1.0


def test_hard_task_disable_admin_stale_keys():
    env = CloudAuditorEnvironment()
    env.reset()
    env.reset()
    reset_obs = env.reset()
    assert reset_obs.task_id == "task_hard_iam"

    _cmd(env, "describe_iam_users")
    _cmd(env, "list_attached_user_policies --user-name alice-admin")
    _cmd(env, "list_access_keys --user-name alice-admin")

    partial = _cmd(
        env,
        "update_access_key --user-name alice-admin --access-key-id AKIAALICE001 --status Inactive",
    )
    assert partial.task_score == 0.8
    assert partial.done is False

    final = _cmd(
        env,
        "update_access_key --user-name alice-admin --access-key-id AKIAALICE002 --status Inactive",
    )
    assert 0.0 < final.task_score < 1.0
    assert final.done is True


def test_reset_restores_world_state_to_deterministic_defaults():
    env = CloudAuditorEnvironment()
    env.reset()

    _cmd(env, "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0")

    # Rotate back to easy task to verify initial state is restored exactly.
    env.reset()
    env.reset()
    env.reset()

    sg_obs = _cmd(env, "describe_security_groups --group-id sg-web")
    payload = json.loads(sg_obs.command_output)
    ingress = payload["security_groups"][0]["ingress"]

    assert {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"} in ingress


def test_unrecognized_command_is_penalized():
    env = CloudAuditorEnvironment()
    env.reset()

    bad = _cmd(env, "totally_unknown_command")

    assert bad.reward is not None
    assert bad.reward < 0.0
    assert "unrecognized command" in bad.command_output


def test_episode_ends_after_max_steps_even_if_incomplete():
    env = CloudAuditorEnvironment()
    env.reset()

    last = None
    for _ in range(env.MAX_STEPS):
        last = _cmd(env, "describe_security_groups")

    assert last is not None
    assert last.done is True
    assert last.status == "failed"


def test_easy_task_milestones_are_monotonic():
    env = CloudAuditorEnvironment()
    env.reset()

    step_a = _cmd(env, "describe_instances")
    step_b = _cmd(env, "describe_security_groups --group-id sg-web")
    step_c = _cmd(
        env,
        "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0",
    )

    assert step_b.task_score > step_a.task_score
    assert step_c.task_score > step_b.task_score


def test_score_does_not_decrease_after_completion():
    env = CloudAuditorEnvironment()
    env.reset()

    _cmd(
        env,
        "revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0",
    )
    after_fix = _cmd(env, "describe_instances")

    assert after_fix.task_score >= 0.95


def test_reset_observation_includes_expected_task_description():
    env = CloudAuditorEnvironment()
    obs = env.reset()

    expected = CloudAuditorEnvironment.TASK_SPECS[obs.task_id]["description"]
    assert obs.task_description == expected
    assert expected


def test_repeated_recon_does_not_farm_bonus():
    env = CloudAuditorEnvironment()
    env.reset()

    first = _cmd(env, "describe_instances")
    second = _cmd(env, "describe_instances")

    assert first.reward > 0.0
    assert second.reward <= 0.0
