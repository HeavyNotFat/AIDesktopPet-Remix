import os

import chromadb

from ..embeddings import get_embedding
from ..utils import log
from .base import BaseVectorStore


class ChromaVectorStore(BaseVectorStore):
    def __init__(self, store_path, collection_name):
        super().__init__(store_path, collection_name)
        self.client = None
        self.collection = None

    def init(self):
        os.makedirs(self.store_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.store_path)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        log(f"Chroma 初始化完成：{self.store_path}")

    def ensure_ready(self):
        if self.collection is None:
            self.init()

    def count(self):
        self.ensure_ready()
        return self.collection.count()

    def clear(self):
        self.ensure_ready()
        if self.collection.count() > 0:
            all_ids = self.collection.get()["ids"]
            if all_ids:
                self.collection.delete(ids=all_ids)

    def add_chunks(self, chunks, embed_model):
        self.ensure_ready()

        for index, chunk in enumerate(chunks):
            try:
                vector = get_embedding(embed_model, chunk["text"])

                self.collection.add(ids=[chunk["id"]], embeddings=[vector], documents=[chunk["text"]],
                                    metadatas=[{"source": chunk["source"], "chunk_index": chunk["chunk_index"]}])

            except Exception as e:
                log(f"Embedding失败：Chunk {index} ({e})", "ERROR")
                return False

        return True

    def query(self, query_text, embed_model, top_k):
        self.ensure_ready()
        results = []

        if self.collection.count() > 0:
            query_vector = get_embedding(embed_model, query_text)
            result = self.collection.query(query_embeddings=[query_vector], n_results=top_k)

            for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
                results.append(
                    {"score": 1 - distance, "source": meta["source"], "chunk_index": meta["chunk_index"],
                     "text": text, "type": "vector"})

        return results
