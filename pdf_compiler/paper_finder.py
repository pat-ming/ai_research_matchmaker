import requests
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
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

def europepmc(doi):
    if not doi:
        return "No abstract available."

    stripped_doi = doi[16:] if doi.startswith("https://doi.org/") else doi
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{stripped_doi}&resultType=core&format=json"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return "No abstract available."

        results = response.json().get('resultList', {}).get('result', [])
        if results and results[0].get('abstractText'):
            return results[0]['abstractText']
    except requests.RequestException:
        pass

    return "No abstract available."

def process_paper(paper):
    primary_topic = paper.get('primary_topic', {})
    open_access = paper.get('open_access', {})
    location = paper.get('primary_location', {})
    doi = paper.get('ids', []).get('doi')

    abstract = decode_abstract(paper.get('abstract_inverted_index'))

    return {
        'Title': paper.get('title'),
        'Citations': paper.get('cited_by_count'),
        'Date': paper.get('publication_date'),
        'Summary': abstract,
        'Subfield': primary_topic.get('subfield', {}).get('display_name', 'N/A'),
        'Topic': primary_topic.get('display_name', 'N/A'),
        'Doi': doi,
        "Open Acess": open_access.get('is_oa'),
        "OA Url": open_access.get('oa_url') if not None else None,
        'Journal': location.get('raw_source_name'),
        'WashU Proxy Server:': f'https://libproxy.wustl.edu/login?url={doi}'
    }

def get_paper_dataframe(orcid_id):
    # Fetch top 50 papers by citation count
    url = f'https://api.openalex.org/works?filter=authorships.author.orcid:https://orcid.org/{orcid_id}&sort=cited_by_count:desc&per_page=50'
    response = requests.get(url)

    if response.status_code != 200:
        print(f'Error: {response.status_code}')
        return None

    data = response.json().get('results', [])
    processed_list = []
    missing_abstracts = []

    for i, paper in enumerate(data):
        paper_dict = process_paper(paper)
        if paper_dict['Summary'] == "No abstract available." and paper_dict['Doi']:
            missing_abstracts.append((i, paper_dict['Doi']))
        processed_list.append(paper_dict)

    # Fetch 10 most recent papers and append any not already in the list
    recent_url = f'https://api.openalex.org/works?filter=authorships.author.orcid:https://orcid.org/{orcid_id}&sort=publication_date:desc&per_page=10'
    recent_response = requests.get(recent_url)

    if recent_response.status_code == 200:
        recent_data = recent_response.json().get('results', [])
        existing_dois = {p['Doi'] for p in processed_list if p['Doi']}
        for paper in recent_data:
            paper_dict = process_paper(paper)
            if paper_dict['Doi'] and paper_dict['Doi'] not in existing_dois:
                if paper_dict['Summary'] == "No abstract available." and paper_dict['Doi']:
                    missing_abstracts.append((len(processed_list), paper_dict['Doi']))
                processed_list.append(paper_dict)
                existing_dois.add(paper_dict['Doi'])

    # Batch fetch missing abstracts from Europe PMC in parallel
    if missing_abstracts:
        print(f"Fetching {len(missing_abstracts)} missing abstracts from Europe PMC...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(europepmc, doi): idx for idx, doi in missing_abstracts}
            for future in as_completed(futures):
                idx = futures[future]
                result = future.result()
                if result != "No abstract available.":
                    processed_list[idx]['Summary'] = result

    papers_df = pd.DataFrame(processed_list)
    papers_df['Date'] = pd.to_datetime(papers_df['Date'])

    return papers_df

def main(name, filename_prefix=None):
    faculty_df = get_paper_dataframe(get_faculty_orcid(name))
    name_lower = name.lower()
    formatted_name = filename_prefix if filename_prefix else name_lower.replace(" ", "_")
    faculty_df.to_csv(f'/Users/patrickming/Desktop/Coding Projects/AI Research Assistant/pdf_compiler/faculty_papers/{formatted_name}_papers.csv')

main('Richard Mabbs')
