import pytest

from collector.http import RequestController, TransientError


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(round(s, 3))
        self.now += s


def make(t, **kw):
    return RequestController(sleep=t.sleep, clock=t.clock, jitter=lambda: 0.0, **kw)


def test_min_interval_enforced():
    t = FakeTime()
    ctl = make(t, min_interval=2.0)
    for _ in range(3):
        ctl.call(lambda: "ok")
        t.now += 0.5  # 응답 처리에 0.5초 걸린다고 가정
    assert t.sleeps == [1.5, 1.5]
    assert ctl.requests == 3


def test_interval_below_one_second_rejected():
    with pytest.raises(ValueError):
        RequestController(min_interval=0.5)


def test_retry_with_exponential_backoff_then_success():
    t = FakeTime()
    ctl = make(t, min_interval=1.0, max_retries=4, backoff_base=2.0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("429")
        return "ok"

    assert ctl.call(flaky) == "ok"
    assert t.sleeps == [2.0, 4.0]  # 2*2^0, 2*2^1 (대기 후 바로 다음 요청이라 간격 대기는 없음)


def test_retry_after_header_respected():
    t = FakeTime()
    ctl = make(t, min_interval=1.0)
    calls = {"n": 0}

    def once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientError("429", retry_after=7)
        return "ok"

    ctl.call(once)
    assert 7.0 in t.sleeps


def test_gives_up_after_max_retries():
    t = FakeTime()
    ctl = make(t, min_interval=1.0, max_retries=2, backoff_max=5.0)

    def always():
        raise TransientError("503")

    with pytest.raises(TransientError):
        ctl.call(always)
    assert ctl.requests == 3


def test_long_retry_after_is_not_shortened():
    t = FakeTime()
    assert make(t, backoff_max=60).backoff(0, retry_after=120) == 120
