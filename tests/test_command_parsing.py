import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import CloudAuditorAction
from server.cloud_auditor_environment import CloudAuditorEnvironment


def _step(env: CloudAuditorEnvironment, command: str):
    return env.step(CloudAuditorAction(command=command))


def test_valid_command_with_args():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, "describe_security_groups --group-id sg-web")

    assert "Error" not in obs.command_output
    assert obs.done is False


def test_unclosed_quote_error():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, 'describe_security_groups --group-id "sg-web')

    assert obs.reward < 0.0
    assert "quotation" in obs.command_output.lower()


def test_extra_whitespace_handled():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, "describe_security_groups    --group-id    sg-web")

    assert "Error" not in obs.command_output


def test_empty_arg_error():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, 'revoke_security_group_ingress --group-id "" --port 22 --cidr 0.0.0.0/0')

    assert "cannot be empty" in obs.command_output
    assert obs.reward < 0.0


def test_sql_injection_attempt_fails():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, 'describe_security_groups --group-id "sg-web\'; DROP TABLE users;--"')

    assert "not found" in obs.command_output
    assert obs.reward < 0.0


def test_missing_required_arg_error():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, "revoke_security_group_ingress --group-id sg-web --port 22")

    assert "missing required option --cidr" in obs.command_output
    assert obs.reward < 0.0


def test_unknown_command_error():
    env = CloudAuditorEnvironment()
    env.reset()

    obs = _step(env, "totally_unknown")

    assert "unrecognized command" in obs.command_output
    assert obs.reward < 0.0
