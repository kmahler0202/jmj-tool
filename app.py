import os
import requests
import threading
from flask import Flask, redirect, request, session, jsonify
from dotenv import load_dotenv
import secrets
from flask_session import Session
from flask_cors import CORS, cross_origin
from jira_api import JiraWatcher
from main import change_board_status, MONDAY_MAINTENCE_BOARD_ID

import time

load_dotenv()

app = Flask(__name__)
# Use a consistent secret key for session persistence
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config.update(
    SESSION_TYPE='filesystem',
    SESSION_PERMANENT=False,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME='jira_session'  
)


Session(app)
CORS(app, supports_credentials=True)


CLIENT_ID = os.getenv("ATLASSIAN_CLIENT_ID")
CLIENT_SECRET = os.getenv("ATLASSIAN_CLIENT_SECRET")
REDIRECT_URI = os.getenv("ATLASSIAN_REDIRECT_URI")
AUTH_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"
API_URL = "https://api.atlassian.com"
SCOPES = "read:board-scope:jira-software read:project:jira read:issue:jira-software read:issue:jira read:project.component:jira read:issue-meta:jira"

# Monday.com configuration
MONDAY_API_TOKEN = os.getenv('MONDAY_API_TOKEN')
MONDAY_MAINTENCE_BOARD_ID = os.getenv('MONDAY_MAINTENCE_BOARD_ID')
MONDAY_DX_RESOURCING_BOARD_ID = os.getenv('MONDAY_DX_RESOURCING_BOARD_ID')

# TEMPORARY SAFETY GUARDS: limit sync strictly to test data only
# Jira tests (no subtasks): KT-1, KT-2, KT-3
ALLOWED_JIRA_KEYS = {"KT-1", "KT-2", "KT-3"}
# Monday tests in "Kyle Test Group": Test Project 1, 2, 3
ALLOWED_MONDAY_ITEM_NAMES = {"Test Project 1", "Test Project 2", "Test Project 3"}


@app.route('/')
def home(supports_credentials=True):
    return '<a href="/auth">Connect to Jira</a>'

@app.route('/auth')
def auth(supports_credentials=True):

    state = secrets.token_urlsafe(16)
    session['state'] = state

    return redirect(
        f"{AUTH_URL}?audience=api.atlassian.com&client_id={CLIENT_ID}&scope={SCOPES}&redirect_uri={REDIRECT_URI}&state={state}&response_type=code&prompt=consent"
    )

@app.route('/oauth/callback')
def callback(supports_credentials=True):
    returned_state = request.args.get('state')
    expected_state = session.get('state')

    if returned_state != expected_state:
        return "❌ Invalid state. Possible CSRF attack.", 400

    code = request.args.get('code')
    token_response = requests.post(TOKEN_URL, json={
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI
    })

    token_data = token_response.json()

    access_token = token_data.get('access_token')
    session['access_token'] = access_token

    headers = {'Authorization': f'Bearer {access_token}'}
    cloud_res = requests.get(f"{API_URL}/oauth/token/accessible-resources", headers=headers)
    cloud_data = cloud_res.json()

    if not cloud_data:
        return "❌ No accessible Jira resources found"

    print("☁️ Accessible resources:")
    for r in cloud_data:
        print(f"- name={r.get('name')} url={r.get('url')} id={r.get('id')}")
        print(f"  scopes={r.get('scopes')}")

    # choose the resource whose url matches your site (e.g., themxgroup.atlassian.net)
    my = next((r for r in cloud_data if "themxgroup.atlassian.net" in r.get('url','')), None)
    if not my:
        return "No matching Jira site found for your account", 400

    session['cloud_id'] = my['id']

    return redirect('/boards')



@app.route('/boards')
def get_boards(supports_credentials=True):
    access_token = session.get('access_token')
    cloud_id = session.get('cloud_id')
    
    if not access_token or not cloud_id:
        return redirect('/auth')

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }

    jira_url = f"{API_URL}/ex/jira/{cloud_id}/rest/agile/1.0/board"
    response = requests.get(jira_url, headers=headers)
    print("Agile GET status:", response.status_code)
    print("WWW-Authenticate:", response.headers.get('WWW-Authenticate'))
    try:
        print("Body:", response.json())
    except Exception:
        print("Body (text):", response.text)

    if response.ok:
        return jsonify(response.json())
    else:
        return f"\u274c Error: {response.status_code} - {response.text}"




@app.route('/watch/<string:issue_key>')
def watch_issue(issue_key):
    access_token = session.get('access_token')
    cloud_id = session.get('cloud_id')

    if not access_token or not cloud_id:
        return redirect('/auth')

    try:
        watcher = JiraWatcher(access_token, cloud_id)
        # Run the watcher in a background thread so it doesn't block the server
        watch_thread = threading.Thread(
            target=watcher.watch_issue_status,
            args=(issue_key,),
            daemon=True
        )
        watch_thread.start()
        return jsonify({'message': f'Started watching issue {issue_key} in the background.'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route("/resources")
def view_accessible_resources():
    """
    View all accessible resources for the current OAuth token.
    This is useful to confirm scopes and cloud IDs.
    """
    access_token = session.get("access_token")
    if not access_token:
        return redirect("/auth")

    url = "https://api.atlassian.com/oauth/token/accessible-resources"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return jsonify({"error": resp.text}), resp.status_code

    resources = resp.json()
    return jsonify(resources)



# Test one is COXDP-6
@app.route('/subtasks/<string:parent_key>')
def get_subtasks(parent_key):
    """
    Returns all subtasks for the given parent Jira issue key.
    Uses the Jira Cloud REST API v3 with the existing OAuth token and cloud_id from session.
    """
    access_token = session.get('access_token')
    cloud_id = session.get('cloud_id')

    if not access_token or not cloud_id:
        return redirect('/auth')

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }

    # JQL query: parent = "<parent_key>"
    jql = f'parent="{parent_key}" ORDER BY created ASC'
    url = f"{API_URL}/ex/jira/{cloud_id}/rest/agile/1.0/issue/{parent_key}"

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return jsonify({"error": f"{resp.status_code} - {resp.text}"}), resp.status_code

    issue_json = resp.json()

    # just the keys like "COXDP-7", "COXDP-8", ...
    subtask_keys = [s["key"] for s in issue_json.get("fields", {}).get("subtasks", [])]
    print(subtask_keys)

    return subtask_keys



def fetch_monday_items_with_jira(board_id: str):
    """Return a list of Monday items that have a Jira link column filled.

    Each element: { 'item_id': str, 'name': str, 'jira_key': str }
    """
    if not MONDAY_API_TOKEN:
        raise RuntimeError("MONDAY_API_TOKEN is not set in environment")

    monday_url = 'https://api.monday.com/v2'
    headers = {
        'Authorization': f"{MONDAY_API_TOKEN}",
        'Content-Type': 'application/json'
    }

    # Query item id, name, and the Jira link column text (assumed id: link_mkncp8tr)
    query = f"""
    {{
        boards(ids:[{board_id}]) {{
            id
            name
            items_page {{
                items {{
                    id
                    name
                    column_values(ids:["link_mkncp8tr"]) {{
                        id
                        text
                    }}
                }}
            }}
        }}
    }}
    """

    data = {'query': query}
    resp = requests.post(url=monday_url, json=data, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Monday API error {resp.status_code}: {resp.text}")

    out = []
    result = resp.json()
    boards = result.get('data', {}).get('boards', [])
    for b in boards:
        for item in b.get('items_page', {}).get('items', []):
            cv = (item.get('column_values') or [{}])[0]
            link_text = cv.get('text') or ''
            if not link_text:
                continue
            # Expected formats: "WO-40 - https://..." or just "WO-40"
            jira_key = link_text.split()[0] if ' ' in link_text else link_text

            # Safety filter: only include explicitly allowed test items
            if jira_key not in ALLOWED_JIRA_KEYS:
                continue
            if item['name'] not in ALLOWED_MONDAY_ITEM_NAMES:
                continue

            out.append({
                'item_id': item['id'],
                'name': item['name'],
                'jira_key': jira_key
            })
    return out


def is_done_status(issue_json: dict) -> bool:
    """Determine if an issue is in a 'done' category/state."""
    try:
        status = issue_json['fields']['status']
        # Prefer statusCategory if available
        cat = status.get('statusCategory', {}).get('key')
        if cat:
            return cat.lower() == 'done'
        # Fallback to name matching
        name = status.get('name', '').lower()
        return name in {'done', 'closed', 'resolved', 'complete'}
    except Exception:
        return False


def monitor_issue_completion(access_token: str, cloud_id: str, jira_key: str, monday_item_id: str, monday_item_name: str, poll_seconds: int = 60):
    """Background worker: poll Jira until the issue (or all its subtasks) are done, then update Monday status.

    Sets Monday status to 'UP TO DATE' on completion.
    """
    watcher = JiraWatcher(access_token, cloud_id)

    while True:
        try:
            parent = watcher.get_issue(jira_key)
            subtasks = parent.get('fields', {}).get('subtasks', []) or []

            if not subtasks:
                # No subtasks; consider parent status only
                all_done = is_done_status(parent)
            else:
                all_done = True
                for st in subtasks:
                    st_key = st.get('key')
                    if not st_key:
                        continue
                    st_issue = watcher.get_issue(st_key)
                    if not is_done_status(st_issue):
                        all_done = False
                        break

            if all_done:
                # Double-check safety before updating Monday
                if jira_key in ALLOWED_JIRA_KEYS and monday_item_name in ALLOWED_MONDAY_ITEM_NAMES:
                    try:
                        change_board_status(monday_item_id, MONDAY_MAINTENCE_BOARD_ID, 'UP TO DATE')
                        print(f"Updated Monday item {monday_item_id} ('{monday_item_name}') to 'UP TO DATE' for Jira {jira_key}")
                    except Exception as e:
                        print(f"Failed to update Monday for item {monday_item_id}: {e}")
                else:
                    print(f"Skipped update (outside allowlist): Jira {jira_key}, Monday '{monday_item_name}' ({monday_item_id})")
                break

            time.sleep(poll_seconds)
        except Exception as e:
            print(f"Error while monitoring {jira_key}: {e}")
            time.sleep(poll_seconds)


@app.route('/sync_monday_jira')
def sync_monday_jira():
    """Start background watchers for all Monday items that have Jira keys.

    Uses the current OAuth session's access_token and cloud_id.
    """
    access_token = session.get('access_token')
    cloud_id = session.get('cloud_id')
    if not access_token or not cloud_id:
        return redirect('/auth')

    board_id = MONDAY_MAINTENCE_BOARD_ID
    if not board_id:
        return jsonify({'error': 'MONDAY_MAINTENCE_BOARD_ID not configured'}), 500

    try:
        items = fetch_monday_items_with_jira(board_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    started = 0
    for item in items:
        jira_key = item['jira_key']
        item_id = item['item_id']
        item_name = item['name']

        # Extra guard on the route level
        if jira_key not in ALLOWED_JIRA_KEYS or item_name not in ALLOWED_MONDAY_ITEM_NAMES:
            continue

        t = threading.Thread(
            target=monitor_issue_completion,
            args=(access_token, cloud_id, jira_key, item_id, item_name),
            daemon=True
        )
        t.start()
        started += 1

    return jsonify({'message': f'Started watchers for {started} Monday items', 'items': items})


if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)
