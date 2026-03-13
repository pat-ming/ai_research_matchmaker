from pinecone import Pinecone
import json 

with open('api_keys.json', 'r') as file:
    keys = json.load(file)

pinecone_api_key = keys["pinecone_api_key"]



