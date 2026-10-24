"""Access control for public deployments: a shared password and a per-client rate limit."""
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque


class AuthManager:
    """Password login that issues signed, expiring bearer tokens (stateless, no cookies).

    Tokens are signed with `secret`; with a random secret they stop working after a restart,
    which only means users log in again.
    """

    def __init__(self, password: str | None, secret: str | None = None, ttl_seconds: int = 7 * 24 * 3600):
        self.password = password or None
        self.secret = (secret or secrets.token_hex(32)).encode()
        self.ttl_seconds = ttl_seconds

    @property
    def enabled(self) -> bool:
        return self.password is not None

    def check_password(self, candidate: str) -> bool:
        return self.enabled and hmac.compare_digest(candidate.encode(), self.password.encode())

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()

    def issue_token(self) -> str:
        expires = str(int(time.time()) + self.ttl_seconds)
        return f"{expires}.{self._sign(expires)}"

    def verify_token(self, token: str | None) -> bool:
        if not self.enabled:
            return True
        if not token or "." not in token:
            return False
        expires, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, self._sign(expires)):
            return False
        return expires.isdigit() and int(expires) > time.time()


class RateLimiter:
    """Sliding-window limit of `limit` requests per `window` seconds per key (0 disables it)."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
