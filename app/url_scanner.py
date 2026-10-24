"""URL safety check backed by the VirusTotal v3 API."""
import base64
import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    safe: bool
    malicious: int = 0
    suspicious: int = 0
    reason: str = ""


class VirusTotalChecker:
    """Check URLs for safety using the VirusTotal API."""

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: str, timeout: int = 15, poll_attempts: int = 5, poll_interval: float = 3.0):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.headers = {"x-apikey": api_key}
        self.timeout = timeout
        self.poll_attempts = poll_attempts
        self.poll_interval = poll_interval

    @staticmethod
    def _url_id(url: str) -> str:
        return base64.urlsafe_b64encode(url.encode()).decode().strip("=")

    def _get(self, path: str) -> dict | None:
        response = requests.get(f"{self.BASE_URL}{path}", headers=self.headers, timeout=self.timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _cached_stats(self, url: str) -> dict | None:
        """Stats from the latest existing VirusTotal report, if the URL is already known."""
        report = self._get(f"/urls/{self._url_id(url)}")
        if not report:
            return None
        return report["data"]["attributes"].get("last_analysis_stats") or None

    def _fresh_stats(self, url: str) -> dict | None:
        """Submit the URL and poll until the analysis completes."""
        response = requests.post(f"{self.BASE_URL}/urls", headers=self.headers, data={"url": url}, timeout=self.timeout)
        response.raise_for_status()
        analysis_id = response.json()["data"]["id"]

        for _ in range(self.poll_attempts):
            analysis = self._get(f"/analyses/{analysis_id}")
            attributes = (analysis or {}).get("data", {}).get("attributes", {})
            if attributes.get("status") == "completed":
                return attributes.get("stats")
            time.sleep(self.poll_interval)
        return None

    def scan(self, url: str) -> ScanResult:
        try:
            stats = self._cached_stats(url) or self._fresh_stats(url)
        except (requests.RequestException, KeyError, ValueError) as e:
            logger.error("VirusTotal check failed for %s: %s", url, e)
            return ScanResult(safe=False, reason="Could not verify the URL with VirusTotal.")

        if stats is None:
            return ScanResult(safe=False, reason="VirusTotal analysis did not finish in time.")

        malicious, suspicious = stats.get("malicious", 0), stats.get("suspicious", 0)
        if malicious > 0:
            return ScanResult(False, malicious, suspicious, f"Flagged as malicious by {malicious} engine(s).")
        return ScanResult(True, malicious, suspicious)

    def is_url_safe(self, url: str) -> bool:
        return self.scan(url).safe
