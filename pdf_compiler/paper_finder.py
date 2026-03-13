import requests
import json
from pathlib import Path
import pandas as pd

current_dir = Path(__file__).parent
api_keys_path = current_dir.parent / 'api_keys.json'

with open(api_keys_path, 'r') as file:
    data = json.load(file)

ORCID_client_id = data['orcid_client_id']
ORCID_client_secret = data['orcid_client_secret']

def get_faculty_orcid(faculty_name):
    # step 1, let ORCID know that I'm the one asking
    auth_url = 'https://orcid.org/oauth/token'
    
    # Ensure there are NO leading/trailing spaces in your keys
    client_id = ORCID_client_id.strip()
    client_secret = ORCID_client_secret.strip()

    auth_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': '/read-public',
        'grant_type': 'client_credentials'
    }
    
    # We use a standard header for OAuth
    headers = {'Accept': 'application/json'}

    print(f"Attempting to authenticate with ID starting: {client_id[:8]}...")

    auth_response = requests.post(auth_url, data=auth_data, headers=headers)
    
    if auth_response.status_code != 200:
        print(f"!!! AUTH FAILURE !!!")
        print(f"Status Code: {auth_response.status_code}")
        print(f"Server Response: {auth_response.text}")
        return None

    token = auth_response.json().get('access_token')
    print("Success! Token acquired.")
    
    # step 2, search and filter. 
    url = "https://pub.orcid.org/v3.0/expanded-search/"

    # Broaden the query: Just search for the name string
    # We will do the WashU check ourselves to be safe
    params = {
        'q': f'"{faculty_name}"', 
        'rows': 25 
    }
    response = requests.get(url, params=params, headers=headers).json()
    results = response.get('expanded-result', [])

    for person in results:
        # Get all their listed institutions
        institutions = person.get('institution-name', [])
        inst_text = " ".join(institutions).lower()
        
        # Check for ANY WashU variation
        washu_variants = ["washington university", "wustl", "washu", "bjc", "st. louis"]
        
        if any(variant in inst_text for variant in washu_variants):
            orcid_id = person.get('orcid-id')
            print(f"Match Found: {person.get('given-names')} {person.get('family-names')} -> {orcid_id}")
            return orcid_id

    print(f"No WashU match found for {faculty_name} in top 10 results.")
    return None

def decode_abstract(inverted_index):
    if not inverted_index:
        return "No abstract available."
    
    try:
        word_list = [
            (pos, word)
            for word, positions in inverted_index.items()
            for pos in positions
        ]
        return " ".join(word for _, word in sorted(word_list))
    except Exception:
        return "error reconstructing abstract"

def get_paper_dataframe(orcid_id):
    url = f'https://api.openalex.org/works?filter=authorships.author.orcid:https://orcid.org/{orcid_id}&sort=cited_by_count:desc&per_page=100'
    response = requests.get(url)

    if response.status_code != 200:
        print(f'Error: {response.status_code}')
        return None

    data = response.json().get('results', [])
    processed_list = []

    for paper in data:
        primary_topic = paper.get('primary_topic', {})

        paper_dict = {
            'Title': paper.get('title'),
            'Citations': paper.get('cited_by_count'),
            'Date': paper.get('publication_date'),
            'Summary': decode_abstract(paper.get('abstract_inverted_index')),
            'Subfield': primary_topic.get('subfield', {}).get('display_name', 'N/A'),
            'Topic': primary_topic.get('display_name', 'N/A')
        }
        processed_list.append(paper_dict)

    papers_df = pd.DataFrame(processed_list)
    papers_df['Date'] = pd.to_datetime(papers_df['Date'])

    return papers_df

#print(get_faculty_orcid('Nathan Jacobs'))
#get_papers(get_faculty_orcid('Nathan Jacobs'))

nathan_df = get_paper_dataframe(get_faculty_orcid('Nathan Jacobs'))
nathan_df.to_csv('Test.csv')
