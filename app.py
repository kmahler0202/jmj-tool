import os
import requests
import threading
from flask import Flask, redirect, request, session, jsonify
from dotenv import load_dotenv
import secrets
from flask_session import Session
from flask_cors import CORS, cross_origin
from jira_api import JiraWatcher

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



if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)

