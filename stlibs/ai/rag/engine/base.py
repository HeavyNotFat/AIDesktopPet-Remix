from abc import ABC, abstractmethod


class BaseVectorStore(ABC):
    """
    所有向量引擎（Chroma、LanceDB ...）都需要实现的统一接口，
    RAG 主类只依赖这几个方法，不关心底层用的是哪个引擎。
    """

    def __init__(self, store_path, collection_name):
        self.store_path = store_path
        self.collection_name = collection_name

    @abstractmethod
    def init(self):
        """初始化底层客户端/表"""
        raise NotImplementedError

    def ensure_ready(self):
        raise NotImplementedError

    @abstractmethod
    def count(self):
        raise NotImplementedError

    @abstractmethod
    def clear(self):
        raise NotImplementedError

    @abstractmethod
    def add_chunks(self, chunks, embed_model):
        """
        chunks: [{"id": str, "source": str, "chunk_index": int, "text": str}, ...]
        返回 True/False 表示是否成功
        """
        raise NotImplementedError

    @abstractmethod
    def query(self, query_text, embed_model, top_k):
        """
        返回 [{"score": float, "source": str, "chunk_index": int, "text": str, "type": "vector"}, ...]
        """
        raise NotImplementedError
