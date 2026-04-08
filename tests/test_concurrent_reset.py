from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.cloud_auditor_environment import CloudAuditorEnvironment


def _do_reset() -> str:
    env = CloudAuditorEnvironment()
    return env.reset().task_id


def test_50_concurrent_resets_cycle_correctly():
    cls = CloudAuditorEnvironment

    old_rotation = cls.USE_GLOBAL_TASK_ROTATION
    old_http_state = cls.USE_GLOBAL_HTTP_STATE

    try:
        cls.USE_GLOBAL_TASK_ROTATION = True
        cls.USE_GLOBAL_HTTP_STATE = False
        with cls._GLOBAL_LOCK:
            cls._GLOBAL_RESET_COUNT = 0

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _i: _do_reset(), range(50)))

        counts = Counter(results)
        assert sum(counts.values()) == 50
        assert set(counts.keys()) == {
            "task_easy_ssh",
            "task_medium_s3",
            "task_hard_iam",
        }

        # 50 resets split over 3 tasks should be 17, 17, 16 in some order.
        assert sorted(counts.values()) == [16, 17, 17]
    finally:
        cls.USE_GLOBAL_TASK_ROTATION = old_rotation
        cls.USE_GLOBAL_HTTP_STATE = old_http_state
