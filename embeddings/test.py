from FlagEmbedding import BGEM3FlagModel
import numpy as np

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


