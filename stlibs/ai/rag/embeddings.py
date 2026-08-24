import ollama


def get_embedding(embed_model, text):
    response = ollama.embeddings(model=embed_model, prompt=text)
    return response["embedding"]
