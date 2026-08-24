import os

from ... import Config

from .bm25 import BM25Index
from .context import build_context, compress_context, merge_results
from .document import create_chunks
from .prompts import prompts
from .utils import log
from .engine import get_vector_store


class RAG:
    RAG_ROOT = "./resources/rag"

    def __init__(
        self,
        chat_model=None,
        embed_model=None,
        top_k=None,
        chunk_size=None,
        overlap=None,
        vector_engine=None
    ):
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.collection_name = Config.rag["collection"]
        self.knowledge_path = os.path.join(self.RAG_ROOT, self.collection_name)

        # 引擎优先级：显式传参 > Config.rag["engine"] > 默认 chroma
        self.vector_engine = (vector_engine or Config.rag['engine']).lower()
        # 不同引擎的数据互不兼容，分别存放在各自的目录下
        self.store_path = os.path.join(self.RAG_ROOT, f"{self.vector_engine}_db")

        self.top_k = top_k
        self.chunk_size = chunk_size
        self.overlap = overlap

        self.vector_store = get_vector_store(self.vector_engine, self.store_path, self.collection_name)
        self.bm25_index = BM25Index()

    @staticmethod
    def log(message, level="INFO"):
        log(message, level)

    def init_vector_store(self):
        self.vector_store.init()

    # 向后兼容旧调用方
    init_chroma = init_vector_store

    def build(self):
        self.vector_store.ensure_ready()

        chunks = create_chunks(self.knowledge_path, self.chunk_size, self.overlap)
        self.bm25_index.build(chunks)

        if not chunks:
            self.log("知识库中没有可用内容", "WARN")
            return False

        self.vector_store.clear()

        ok = self.vector_store.add_chunks(chunks, self.embed_model)
        if not ok:
            return False

        self.log(f"索引建立完成，共 {len(chunks)} 个chunk")

        return True

    def load(self):
        count = self.vector_store.count()
        if count <= 0:
            self.log(f"索引为空（引擎：{self.vector_engine}）", "WARN")
            return False

        return True

    def load_or_build(self):
        if self.load():
            return True

        self.log("没有现有索引，开始建立", "WARN")

        return self.build()

    def bm25_search(self, query, top_k=None):
        top_k = top_k or self.top_k
        return self.bm25_index.search(query, top_k)

    def search(self, query, top_k=None):
        top_k = top_k or self.top_k

        bm25_results = self.bm25_search(query, top_k)
        vector_results = self.vector_store.query(query, self.embed_model, top_k)

        return merge_results(bm25_results, vector_results, top_k)

    def compress_context(self, query, search_results):
        return compress_context(self.chat_model, prompts, query, search_results)

    @staticmethod
    def build_context(search_results):
        return build_context(search_results)

    def clear(self):
        self.vector_store.clear()
