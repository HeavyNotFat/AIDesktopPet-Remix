from abc import ABC, abstractmethod


class BaseVectorStore(ABC):

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
        raise NotImplementedError

    @abstractmethod
    def query(self, query_text, embed_model, top_k):
        raise NotImplementedError
