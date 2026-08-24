import os

import lancedb

from ..embeddings import get_embedding
from ..utils import log
from .base import BaseVectorStore


class LanceVectorStore(BaseVectorStore):
    def __init__(self, store_path, collection_name):
        super().__init__(store_path, collection_name)
        self.db = None
        self.table = None

    def init(self):
        os.makedirs(self.store_path, exist_ok=True)
        self.db = lancedb.connect(self.store_path)

        if self.collection_name in self.db.table_names():
            self.table = self.db.open_table(self.collection_name)
        else:
            # 表在第一次写入 chunk 时才会被创建（需要至少一行数据来推断 schema）
            self.table = None

        log(f"LanceDB 初始化完成：{self.store_path}")

    def ensure_ready(self):
        if self.db is None:
            self.init()

    def count(self):
        self.ensure_ready()
        if self.table is None:
            return 0
        return self.table.count_rows()

    def clear(self):
        self.ensure_ready()
        if self.collection_name in self.db.table_names():
            self.db.drop_table(self.collection_name)
        self.table = None

    def add_chunks(self, chunks, embed_model):
        self.ensure_ready()

        rows = []
        for index, chunk in enumerate(chunks):
            try:
                vector = get_embedding(embed_model, chunk["text"])
                rows.append({
                    "id": chunk["id"],
                    "vector": vector,
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "chunk_index": chunk["chunk_index"],
                })
            except Exception as e:
                log(f"Embedding失败：Chunk {index} ({e})", "ERROR")
                return False

        if not rows:
            return True

        if self.table is None:
            self.table = self.db.create_table(self.collection_name, data=rows, mode="overwrite")
        else:
            self.table.add(rows)

        return True

    def query(self, query_text, embed_model, top_k):
        self.ensure_ready()
        results = []

        if self.table is not None and self.table.count_rows() > 0:
            query_vector = get_embedding(embed_model, query_text)
            hits = self.table.search(query_vector).limit(top_k).to_list()

            for hit in hits:
                # LanceDB 默认返回 L2 距离，这里沿用与 Chroma 一致的 1 - distance 换算方式，
                # 便于和 BM25 分数用同一套融合逻辑（如需严格可比，建议按需替换成余弦距离）。
                distance = hit.get("_distance", 0.0)
                results.append({
                    "score": 1 - distance,
                    "source": hit["source"],
                    "chunk_index": hit["chunk_index"],
                    "text": hit["text"],
                    "type": "vector",
                })

        return results
