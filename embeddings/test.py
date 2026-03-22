from FlagEmbedding import BGEM3FlagModel
import numpy as np
import spacy

nlp = spacy.load("en_core_web_md")

model = BGEM3FlagModel(
    'BAAI/bge-m3',
    use_fp16=True,
    device='mps'
)

def text_vec(text: str | list[str]) -> np.ndarray:
    print("Encoding text...")
    if isinstance(text, str):
        return model.encode([text])['dense_vecs'][0]
    return model.encode(text)['dense_vecs']

def extract_core(text):
    doc = nlp(text)
    
    # 1. Get Noun Chunks (usually captures "RNA sequencing" as one unit)
    # We filter out pronouns like "I", "me", "my"
    keywords = [chunk.text for chunk in doc.noun_chunks 
                if not any(pron == chunk.root.lemma_.lower() for pron in ['i', 'me', 'my'])]
    
    # 2. Get Entities (captures specific names/tech)
    entities = [ent.text for ent in doc.ents]
    
    # 3. Use a list to keep order and prevent the 'set' from scrambling strings
    # We use a simple loop to avoid duplicates
    combined = keywords + entities
    unique_concepts = []
    for item in combined:
        if item not in unique_concepts:
            unique_concepts.append(item)
            
    return {
        "original": text,
        "core_concepts": unique_concepts,
        "clean_string": " ".join(unique_concepts)
    }

def scaled_vector(text):
    extracted = extract_core(text)
    vector = text_vec([
        extracted.get("clean_string"), 
        extracted.get("original")
        ]
    )
    return 0.75 * vector[0] + 0.25 * vector[1]

ex = extract_core("I'm interested in applying machine learning to RNA sequencing and drug discovery.")
print(ex.get('clean_string'))
vector_ex = text_vec([ex.get("clean_string"), ex.get("original")])
scaled_ex = 0.75 * vector_ex[0] + 0.25 * vector_ex[1]

professor_interest = text_vec("Computational Systems Biology")

print(scaled_ex @ professor_interest)