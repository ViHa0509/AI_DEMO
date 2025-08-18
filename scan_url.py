import requests
from typing import Optional

class VirusTotalChecker:
    """A class to check URLs for safety using the VirusTotal API."""
    
    BASE_URL = "https://www.virustotal.com/api/v3/urls"
    
    def __init__(self, api_key: str):
        """Initialize with VirusTotal API key."""
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.headers = {"x-apikey": api_key}
        
    def _post_url(self, url: str) -> Optional[dict]:
        """Submit URL to VirusTotal for scanning."""
        try:
            response = requests.post(
                self.BASE_URL,
                headers=self.headers,
                data={"url": url}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error submitting URL: {e}")
            return None
            
    def _get_scan_results(self, detail_url: str) -> Optional[dict]:
        """Retrieve scan results from VirusTotal."""
        try:
            response = requests.get(detail_url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error retrieving scan results: {e}")
            return None
            
    def is_url_safe(self, url: str) -> bool:
        """Check if a URL is safe according to VirusTotal."""
        scan_response = self._post_url(url)
        if not scan_response or "data" not in scan_response:
            return False
            
        detail_url = scan_response["data"].get("links", {}).get("self")
        if not detail_url:
            return False
            
        result = self._get_scan_results(detail_url)
        if not result or "data" not in result:
            return False
            
        stats = result["data"].get("attributes", {}).get("stats", {})
        return stats.get("malicious", 1) == 0