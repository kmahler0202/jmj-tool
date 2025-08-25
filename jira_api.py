import requests
import time

import os
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.atlassian.com"

# Legacy placeholder; do not rely on module-level base constructed from env/session.
# We will construct URLs with the runtime cloud_id stored on the JiraWatcher instance.

class JiraWatcher:
    def __init__(self, access_token, cloud_id):
        if not access_token or not cloud_id:
            raise ValueError("Access token and cloud ID are required.")
        self.access_token = access_token
        self.cloud_id = cloud_id
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }

    def get_issue(self, issue_key):
        """Fetch details for a specific issue using the runtime cloud_id (REST API v3)."""
        url = f"{API_URL}/ex/jira/{self.cloud_id}/rest/api/3/issue/{issue_key}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 401:
            # Provide detailed diagnostics to help pinpoint the problem
            print("\n❌ Unauthorized. Your access token may have expired. Please re-authenticate.")
            print(f"Request URL: {url}")
            print(f"Auth header present: {'Authorization' in self.headers}")
            print(f"Auth scheme: {self.headers.get('Authorization', '')[:20]}... (truncated)")
            try:
                print(f"Response body: {response.text}")
            except Exception:
                pass
            raise Exception("Unauthorized")
        try:
            response.raise_for_status()  # Raise an exception for other bad status codes
        except requests.exceptions.HTTPError as e:
            # Log context for easier troubleshooting
            print("\nHTTP error while calling Jira issues API:")
            print(f"Status: {response.status_code}")
            print(f"URL: {url}")
            try:
                print(f"Response body: {response.text}")
            except Exception:
                pass
            raise e
        return response.json()

    def watch_issue_status(self, issue_key, interval=15):
        """Monitors a Jira issue for status changes and prints updates."""
        print(f"\n🔍 Watching issue {issue_key} for status changes (checking every {interval} seconds)...")
        last_status = None

        try:
            initial_issue = self.get_issue(issue_key)
            last_status = initial_issue['fields']['status']['name']
            print(f"Initial status for {issue_key}: '{last_status}'")
        except requests.exceptions.RequestException as e:
            print(f"\u274c Could not fetch initial status for {issue_key}: {e}")
            return

        while True:
            try:
                time.sleep(interval)
                issue = self.get_issue(issue_key)
                current_status = issue['fields']['status']['name']

                if current_status != last_status:
                    print(f"\n✨ Status changed for {issue_key}: '{last_status}' -> '{current_status}'")
                    last_status = current_status
                else:
                    print(f".", end="", flush=True)  # Print a dot to show it's still running

            except requests.exceptions.RequestException as e:
                print(f"\n\u274c Error while watching {issue_key}: {e}")
                print("Stopping watcher.")
                break
            except KeyboardInterrupt:
                print("\n🛑 Watcher stopped by user.")
                break
