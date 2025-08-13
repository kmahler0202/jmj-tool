import requests
import time

import os
from dotenv import load_dotenv
load_dotenv()

API_URL = "https://api.atlassian.com"

JIRA_API_BASE = f"{API_URL}/ex/jira/{os.getenv('ATLASSIAN_CLOUD_ID')}/rest/agile/1.0/issue"

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
        """Fetches details for a specific issue."""
        # Using Jira Cloud Platform API v3 for issues
        url = f"{JIRA_API_BASE}/{issue_key}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 401:
            print("\n❌ Unauthorized. Your access token may have expired. Please re-authenticate.")
            raise Exception("Unauthorized")
        response.raise_for_status()  # Raise an exception for other bad status codes
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
                    print(f".", end="", flush=True) # Print a dot to show it's still running

            except requests.exceptions.RequestException as e:
                print(f"\n\u274c Error while watching {issue_key}: {e}")
                print("Stopping watcher.")
                break
            except KeyboardInterrupt:
                print("\n🛑 Watcher stopped by user.")
                break


    # def get_subtasks(self, parent_key: str):
        
