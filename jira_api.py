import requests
import time

import os
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.atlassian.com"

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

    def _get_issue_platform_v3(self, issue_key):
        url = f"{API_URL}/ex/jira/{self.cloud_id}/rest/agile/1.0/issue/{issue_key}"
        resp = requests.get(url, headers=self.headers)
        return url, resp

    def get_issue(self, issue_key):
        """Fetch details for a specific issue using the Agile API (rest/agile/1.0)."""
        url, response = self._get_issue_platform_v3(issue_key)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print("\nHTTP error while calling Jira Agile issue API:")
            print(f"Status: {response.status_code}")
            print(f"URL: {url}")
            try:
                print(f"Body: {response.text}")
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
