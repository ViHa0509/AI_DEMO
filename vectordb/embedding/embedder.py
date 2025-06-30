from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer

# Setting up the embedding model details

model_name = "sentence-transformers/all-mpnet-base-v2"
model_kwargs = {'device': 'cpu'}  # or 'cuda' if you're using GPU
encode_kwargs = {'normalize_embeddings': True}  # Optional but often recommended


def get_embedder():
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs
    )
