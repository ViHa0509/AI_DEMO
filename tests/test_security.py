import time

from app.security import AuthManager, RateLimiter


def test_auth_disabled_without_password():
    auth = AuthManager(None)
    assert not auth.enabled
    assert auth.verify_token(None)


def test_token_roundtrip_and_tampering():
    auth = AuthManager("pw", secret="s")
    assert auth.check_password("pw") and not auth.check_password("nope")
    token = auth.issue_token()
    assert auth.verify_token(token)
    assert not auth.verify_token(token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert not auth.verify_token(None)
    assert not AuthManager("pw", secret="other").verify_token(token)


def test_token_expires():
    auth = AuthManager("pw", secret="s", ttl_seconds=-1)
    assert not auth.verify_token(auth.issue_token())


def test_rate_limiter_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    limiter = RateLimiter(limit=2, window=60)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # limits are per client
    now[0] += 61
    assert limiter.allow("a")


def test_rate_limiter_disabled():
    limiter = RateLimiter(limit=0)
    assert all(limiter.allow("a") for _ in range(100))
