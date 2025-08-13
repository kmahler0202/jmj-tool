import requests
import json
import base64
from requests.auth import HTTPBasicAuth

from pathlib import Path
import os

from dotenv import load_dotenv
load_dotenv()

MONDAY_API_TOKEN = os.getenv('MONDAY_API_TOKEN')
MONDAY_MAINTENCE_BOARD_ID = os.getenv('MONDAY_MAINTENCE_BOARD_ID')
MONDAY_DX_RESOURCING_BOARD_ID = os.getenv('MONDAY_DX_RESOURCING_BOARD_ID')  




def get_board_issues(domain, headers, auth, board_id):
    """Get all issues from a specific board"""
    issues_url = f'https://{domain}/rest/agile/1.0/board/{board_id}/issue'
    
    print(f"\nGetting issues from board {board_id}...")
    response = requests.get(issues_url, headers=headers, auth=auth)
    
    if response.status_code == 200:
        issues_data = response.json()
        print(f"\nFound {len(issues_data.get('issues', []))} issues:")
        print("-" * 80)
        
        for issue in issues_data.get('issues', []):
            fields = issue.get('fields', {})
            print(f"Key: {issue['key']}")
            print(f"Summary: {fields.get('summary', 'N/A')}")
            print(f"Status: {fields.get('status', {}).get('name', 'N/A')}")
            print(f"Assignee: {fields.get('assignee', {}).get('displayName', 'Unassigned') if fields.get('assignee') else 'Unassigned'}")
            print(f"Priority: {fields.get('priority', {}).get('name', 'N/A') if fields.get('priority') else 'N/A'}")
            print("-" * 40)
            
    else:
        print(f"Error getting issues from board {board_id}:", response.status_code, response.text)


def change_board_status(item_id, board_id, status):
    """
    Change the status of a Monday.com item.
    
    Args:
        item_id (str): The ID of the item to update
        status (str): The new status value (e.g., 'UP TO DATE', 'UPDATE NEEDED')
    
    Returns:
        bool: True if successful, False otherwise
    """
    monday_url = 'https://api.monday.com/v2'
    headers = {
        'Authorization': f"{MONDAY_API_TOKEN}",
        'Content-Type': 'application/json'
    }
    
    # GraphQL mutation to change column value
    # The status column ID is 'color_mkrbrgx9' based on the data structur

    status_value = json.dumps({"label": status})  # Example: {"label": "UP TO DATE"}

    mutation = f'''
    mutation {{
        change_column_value(
            item_id: {item_id},
            board_id: {board_id},
            column_id: "color_mkrbrgx9",
            value: "{status_value.replace('"', '\\"')}"
        ) {{
            id
            name
            column_values {{
                id
                text
            }}
        }}
    }}
    '''

    
    data = {'query': mutation}


    response = requests.post(url=monday_url, json=data, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        
        if 'errors' in result:
            print("GraphQL Errors:")
            for error in result['errors']:
                print(f"  - {error['message']}")
            return False
            
        if 'data' in result and result['data']['change_column_value']:
            item_data = result['data']['change_column_value']
            print(f"✅ Successfully updated item '{item_data['name']}' (ID: {item_data['id']})")
            
            # Show the updated status
            for col_val in item_data.get('column_values', []):
                if col_val['id'] == 'color_mkrbrgx9':
                    print(f"   New status: {col_val['text']}")
                    break
            return True
        else:
            print("❌ No data returned from mutation")
            return False
            
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def get_item_id_by_name(item_name, board_ids=[MONDAY_MAINTENCE_BOARD_ID, MONDAY_DX_RESOURCING_BOARD_ID]):
    """
    Helper function to get an item ID by its name.
    
    Args:
        item_name (str): The name of the item to find
        board_ids (list): List of board IDs to search in
    
    Returns:
        str or None: The item ID if found, None otherwise
    """
    monday_url = 'https://api.monday.com/v2'
    headers = {
        'Authorization': f"{MONDAY_API_TOKEN}",
        'Content-Type': 'application/json'
    }
    
    board_ids_str = f'[{", ".join(str(bid) for bid in board_ids)}]'
    # query = f'{{boards(ids:{board_ids_str}) {{ items_page {{ items {{ id name }} }} }} }}'

    query = f"""
    {{
    boards(ids:[{MONDAY_MAINTENCE_BOARD_ID}, {MONDAY_DX_RESOURCING_BOARD_ID}]) {{
            items_page {{
                items {{
                    id
                    name
            }}
        }}
    }}
    }}
    """
    
    data = {'query': query}
    response = requests.post(url=monday_url, json=data, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        
        if 'errors' in result:
            print("GraphQL Errors:")
            for error in result['errors']:
                print(f"  - {error['message']}")
            return None
            
        boards = result.get('data', {}).get('boards', [])
        
        for board in boards:
            items = board.get('items_page', {}).get('items', [])
            for item in items:
                if item['name'].lower() == item_name.lower():
                    return item['id']
                    
        print(f"❌ Item '{item_name}' not found in the specified boards")
        return None
        
    else:
        print(f"❌ Error searching for item: {response.status_code}")
        return None


def test_monday_api():
    monday_url = 'https://api.monday.com/v2'
    headers = {
        'Authorization': f"{MONDAY_API_TOKEN}",
        'Content-Type': 'application/json'
    }

    # Simple working query based on the original structure
    # query = f"{boards(ids:[{MONDAY_MAINTENCE_BOARD_ID}, {MONDAY_DX_RESOURCING_BOARD_ID}]) { name id description items_page { items { name column_values{id type text } } } } }"

    query = f"""
    boards(ids:[{MONDAY_MAINTENCE_BOARD_ID}, {MONDAY_DX_RESOURCING_BOARD_ID}]) {{
        name
        id
        description
        items_page {{
            items {{
                name
                column_values {{
                    id
                    type
                    text
                }}
            }}
        }}
    }}
    """
    
    data = {'query': query}
    response = requests.post(url=monday_url, json=data, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        
        if 'errors' in result:
            print("GraphQL Errors:")
            for error in result['errors']:
                print(f"  - {error['message']}")
            return
            
        boards = result.get('data', {}).get('boards', [])
        
        if not boards:
            print("No boards found with the specified IDs.")
            return
            
        for board in boards:
            print(f"\n{'='*80}")
            print(f"BOARD: {board['name']} (ID: {board['id']})")
            print(f"Description: {board.get('description', 'No description')}")
            print(f"{'='*80}")
            
            # Display items (groups and columns aren't in this query response)
            print("\nITEMS:")
            items = board.get('items_page', {}).get('items', [])
            
            if not items:
                print("  No items found in this board.")
            else:
                print(f"  Found {len(items)} items:\n")
                
                # First, let's collect all unique column types to show what columns exist
                all_column_types = set()
                for item in items:
                    for col_val in item.get('column_values', []):
                        all_column_types.add((col_val['id'], col_val['type']))
                
                print("  COLUMN TYPES FOUND:")
                for col_id, col_type in sorted(all_column_types):
                    print(f"    - {col_id} ({col_type})")
                print()
                
                for item in items:
                    print(f"  📋 ITEM: {item['name']}")
                    
                    # Display column values
                    column_values = item.get('column_values', [])
                    if column_values:
                        print("     Column Values:")
                        for col_val in column_values:
                            # Show all column values, even empty ones, with their types
                            text_value = col_val.get('text')
                            display_value = text_value if text_value else 'Empty'
                            
                            print(f"       • {col_val['id']} ({col_val['type']}): {display_value}")
                    
                    print("     " + "-"*50)
                    
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

def update_monday_maintence_board(item_name, new_status, board_id=MONDAY_MAINTENCE_BOARD_ID):
    item_id = get_item_id_by_name(item_name)
    if item_id:
        print(f"Item ID for '{item_name}': {item_id}")
        change_board_status(item_id, board_id, new_status)
    else:
        print(f"Item '{item_name}' not found")

def get_all_jira_issue(board_id):
    """
    Fetch all Jira issues from the Maintenance board.
    Looks inthe 'link_mkncp8tr' column for the Jira Issue ID.
    """

    monday_url = 'https://api.monday.com/v2'
    headers = {
        'Authorization': f"{MONDAY_API_TOKEN}",
        'Content-Type': 'application/json'
    }
    query = f"""
    {{
            boards(ids:[{board_id}]) {{
            name
            id
            items_page {{
                items {{
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
    response = requests.post(url=monday_url, json=data, headers=headers)

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return []

    result = response.json()
    boards = result.get('data', {}).get('boards', [])
    jira_ids = []

    for board in boards:
        print(f"\n📋 Board: {board['name']} (ID: {board['id']})")
        for item in board.get('items_page', {}).get('items', []):
            link_value = item.get('column_values', [{}])[0].get('text', '')
            if link_value:
                # Many are in the format "WO-40 - https://..."
                issue_key = link_value.split()[0] if " " in link_value else link_value
                jira_ids.append(issue_key)
                print(f"  - {item['name']}: {issue_key}")
            else:
                print(f"  - {item['name']}: No Jira ID found")

    return jira_ids
    
    

if __name__ == "__main__":
    # item_name = "Test Project 4"
    # new_status = "UPDATE NEEDED"
    # update_monday_maintence_board(item_name, new_status)
    print("\nAll Jira IDs:", get_all_jira_issue(MONDAY_MAINTENCE_BOARD_ID))

