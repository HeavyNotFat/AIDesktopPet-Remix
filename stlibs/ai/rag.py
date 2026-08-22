from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Iterable
import hashlib
import os
import json
import threading

from .. import Config
import numpy as np


@dataclass
class DocumentChunk:
    """文档块数据结构"""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None


class _SharedRAGState:
    """所有 HybridRAG 实例共享的资源与缓存。"""
    lock = threading.RLock()
    clients: Dict[str, Any] = {}
    embed_cache: OrderedDict[str, np.ndarray] = OrderedDict()
    retrieve_cache: OrderedDict[str, List[DocumentChunk]] = OrderedDict()
    backends: Dict[str, Dict[str, Any]] = {}
    embed_cache_maxsize = 2048
    retrieve_cache_maxsize = 512


class HybridRAG:
    def __init__(
        self,
        chat_model: str = "qwen3.5:4b",
        embed_model: str = "qwen3-embedding:4b",
        top_k: int = 3,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        bm25_weight: float = 0.3,
        cache_maxsize: int = 128,
        host: Optional[str] = None,
    ):
        import ollama

        self.chat_model = chat_model
        self.embed_model = embed_model
        self.top_k = top_k
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.bm25_weight = bm25_weight
        self._cache_maxsize = cache_maxsize
        self.host = host or ""
        self.client = self._get_shared_client(ollama, host)

        self.engine = str(Config.rag["engine"]).lower()
        self.rag_path = os.path.join(".", "resources", "rag")

        self._db = None
        self._milvus_alias: Optional[str] = None
        self._collection_chunks: Dict[str, List[DocumentChunk]] = {}
        self._chunks: List[DocumentChunk] = []

        self._backend_key = self._make_backend_key()
        self._init_shared_backend()

    def _get_shared_client(self, ollama_module, host: Optional[str]):
        key = host or "__default__"
        with _SharedRAGState.lock:
            if key not in _SharedRAGState.clients:
                _SharedRAGState.clients[key] = ollama_module.Client(host=host) if host else ollama_module
            return _SharedRAGState.clients[key]

    def _make_backend_key(self) -> str:
        if self.engine == "milvus":
            location = f"{Config.rag.get('uri', 'http://localhost:19530')}|{Config.rag.get('alias', 'default')}"
        else:
            location = os.path.abspath(self.rag_path)

        return "|".join([
            self.engine,
            self.embed_model,
            str(self.chunk_size),
            str(self.chunk_overlap),
            location,
        ])

    def _init_shared_backend(self) -> None:
        with _SharedRAGState.lock:
            state = _SharedRAGState.backends.get(self._backend_key)

            if state is not None and state.get("initialized"):
                self._bind_backend_state(state)
                return

            if state is None:
                state = {
                    "initialized": False,
                    "documents_synced": False,
                    "db": None,
                    "milvus_alias": None,
                    "collection_chunks": {},
                    "chunks": [],
                }
                _SharedRAGState.backends[self._backend_key] = state

            if not state["initialized"]:
                self._init_engine_into_state(state)
                self._bind_backend_state(state)
                self._sync_documents_into_state(state)
                state["initialized"] = True

    def _bind_backend_state(self, state: Dict[str, Any]) -> None:
        self._backend_state = state
        self._db = state["db"]
        self._milvus_alias = state["milvus_alias"]
        self._collection_chunks = state["collection_chunks"]
        self._chunks = state["chunks"]

    def _init_engine(self) -> None:
        self._init_engine_into_state(self._backend_state)
        self._db = self._backend_state["db"]
        self._milvus_alias = self._backend_state["milvus_alias"]

    def _init_engine_into_state(self, state: Dict[str, Any]) -> None:
        if self.engine == "chroma":
            self._init_chroma_into_state(state)
        elif self.engine == "lance":
            self._init_lance_into_state(state)
        elif self.engine == "milvus":
            self._init_milvus_into_state(state)
        else:
            raise ValueError(f"不支持的 RAG engine: {self.engine}")

    def _init_chroma(self) -> None:
        self._init_chroma_into_state(self._backend_state)

    def _init_chroma_into_state(self, state: Dict[str, Any]) -> None:
        import chromadb

        db_path = os.path.join(self.rag_path, "chroma_db")
        os.makedirs(self.rag_path, exist_ok=True)
        state["db"] = chromadb.PersistentClient(path=db_path)
        state["milvus_alias"] = None

    def _init_lance(self) -> None:
        self._init_lance_into_state(self._backend_state)

    def _init_lance_into_state(self, state: Dict[str, Any]) -> None:
        import lancedb

        db_path = os.path.join(self.rag_path, "lance_db")
        os.makedirs(self.rag_path, exist_ok=True)
        state["db"] = lancedb.connect(db_path)
        state["milvus_alias"] = None

    def _init_milvus(self) -> None:
        self._init_milvus_into_state(self._backend_state)

    def _init_milvus_into_state(self, state: Dict[str, Any]) -> None:
        from pymilvus import connections

        uri = Config.rag.get("uri", "http://localhost:19530")
        alias = Config.rag.get("alias", "default")
        connections.connect(alias=alias, uri=uri)

        state["db"] = None
        state["milvus_alias"] = alias

    def _get_txt_files(self) -> List[str]:
        if not os.path.exists(self.rag_path):
            os.makedirs(self.rag_path, exist_ok=True)
            return []

        return sorted(
            os.path.join(self.rag_path, name)
            for name in os.listdir(self.rag_path)
            if name.lower().endswith(".txt")
        )

    @staticmethod
    def _get_collection_name(file_path: str) -> str:
        return os.path.splitext(os.path.basename(file_path))[0]

    def sync_documents(self, force: bool = False) -> None:
        state = self._backend_state

        with _SharedRAGState.lock:
            if state.get("documents_synced", False) and not force:
                return

            self._sync_documents_into_state(state)
            state["documents_synced"] = True

    def _sync_documents_into_state(self, state: Dict[str, Any]) -> None:
        for file_path in self._get_txt_files():
            collection_name = self._get_collection_name(file_path)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            metadata = {
                "source": os.path.basename(file_path),
                "collection": collection_name,
            }

            chunks = self._build_chunks(content, metadata)
            self._replace_collection(collection_name, chunks)

        self._load_all_chunks()
        self._clear_retrieve_cache()

    def _build_chunks(self, content: str, metadata: Dict[str, Any]) -> List[DocumentChunk]:
        chunks = self._chunk_text(content, metadata)
        self._embed_chunks(chunks)
        return chunks

    def _embed_chunks(self, chunks: List[DocumentChunk]) -> None:
        texts_to_embed = []
        uncached_indices = []

        for i, chunk in enumerate(chunks):
            cached = self._get_cached_embedding(chunk.content)
            if cached is not None:
                chunk.embedding = cached
            else:
                texts_to_embed.append(chunk.content)
                uncached_indices.append(i)

        if not texts_to_embed:
            return

        resp = self.client.embed(model=self.embed_model, input=texts_to_embed)
        embeddings = resp.get("embeddings") or []

        if len(embeddings) != len(uncached_indices):
            raise RuntimeError("Embedding 返回数量与输入文本数量不一致")

        for i, index in enumerate(uncached_indices):
            emb = np.asarray(embeddings[i], dtype=np.float32)
            chunks[index].embedding = emb
            self._set_cached_embedding(chunks[index].content, emb)

    def _make_embedding_cache_key(self, text: str) -> str:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.host}|{self.embed_model}|{text_hash}"

    def _get_cached_embedding(self, text: str) -> Optional[np.ndarray]:
        key = self._make_embedding_cache_key(text)

        with _SharedRAGState.lock:
            cached = _SharedRAGState.embed_cache.get(key)
            if cached is not None:
                _SharedRAGState.embed_cache.move_to_end(key)
                return cached

        return None

    def _set_cached_embedding(self, text: str, emb: np.ndarray) -> None:
        key = self._make_embedding_cache_key(text)

        with _SharedRAGState.lock:
            _SharedRAGState.embed_cache[key] = emb
            _SharedRAGState.embed_cache.move_to_end(key)

            while len(_SharedRAGState.embed_cache) > _SharedRAGState.embed_cache_maxsize:
                _SharedRAGState.embed_cache.popitem(last=False)

    def _replace_collection(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        if self.engine == "chroma":
            self._replace_chroma_collection(collection_name, chunks)
        elif self.engine == "lance":
            self._replace_lance_collection(collection_name, chunks)
        elif self.engine == "milvus":
            self._replace_milvus_collection(collection_name, chunks)

    def _chroma_collection_names(self) -> set:
        return {
            getattr(c, "name", str(c))
            for c in self._db.list_collections()
        }

    def _replace_chroma_collection(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        if collection_name in self._chroma_collection_names():
            self._db.delete_collection(name=collection_name)

        collection = self._db.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        if chunks:
            collection.upsert(
                ids=[self._make_id(c.content, c.metadata) for c in chunks],
                documents=[c.content for c in chunks],
                metadatas=[c.metadata for c in chunks],
                embeddings=[self._require_embedding(c).tolist() for c in chunks],
            )

    def _replace_lance_collection(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        import pandas as pd

        if collection_name in self._db.table_names():
            self._db.drop_table(collection_name)

        if chunks:
            self._db.create_table(
                collection_name,
                data=pd.DataFrame(self._chunks_to_rows(chunks)),
            )

    def _replace_milvus_collection(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        from pymilvus import Collection, utility

        if utility.has_collection(collection_name, using=self._milvus_alias):
            Collection(collection_name, using=self._milvus_alias).drop()

        if chunks:
            self._create_milvus_collection(collection_name, chunks)

    def _save_chunks(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        if not chunks:
            return

        if self.engine == "chroma":
            self._save_chroma(collection_name, chunks)
        elif self.engine == "lance":
            self._save_lance(collection_name, chunks)
        elif self.engine == "milvus":
            self._save_milvus(collection_name, chunks)

    def _save_chroma(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        collection = self._db.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        collection.upsert(
            ids=[self._make_id(c.content, c.metadata) for c in chunks],
            documents=[c.content for c in chunks],
            metadatas=[c.metadata for c in chunks],
            embeddings=[self._require_embedding(c).tolist() for c in chunks],
        )

    def _save_lance(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        import pandas as pd

        df = pd.DataFrame(self._chunks_to_rows(chunks))

        if collection_name in self._db.table_names():
            table = self._db.open_table(collection_name)
            table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(df)
        else:
            self._db.create_table(collection_name, data=df)

    def _save_milvus(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        from pymilvus import Collection, utility

        if not utility.has_collection(collection_name, using=self._milvus_alias):
            self._create_milvus_collection(collection_name, chunks)
            return

        collection = Collection(collection_name, using=self._milvus_alias)
        collection.insert(self._chunks_to_milvus_data(chunks))
        collection.flush()
        collection.load()

    def _create_milvus_collection(self, collection_name: str, chunks: List[DocumentChunk]) -> None:
        from pymilvus import Collection, DataType, FieldSchema, CollectionSchema

        dimension = len(self._require_embedding(chunks[0]))

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="metadata", dtype=DataType.JSON),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
        ]

        schema = CollectionSchema(
            fields=fields,
            description=f"RAG collection: {collection_name}",
        )

        collection = Collection(
            name=collection_name,
            schema=schema,
            using=self._milvus_alias,
        )

        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "AUTOINDEX",
                "metric_type": "COSINE",
                "params": {},
            },
        )

        collection.insert(self._chunks_to_milvus_data(chunks))
        collection.flush()
        collection.load()

    @staticmethod
    def _chunks_to_rows(chunks: Iterable[DocumentChunk]) -> List[Dict[str, Any]]:
        return [
            {
                "id": HybridRAG._make_id_static(c.content, c.metadata),
                "content": c.content,
                "metadata": c.metadata,
                "vector": HybridRAG._require_embedding_static(c).tolist(),
            }
            for c in chunks
        ]

    @staticmethod
    def _chunks_to_milvus_data(chunks: Iterable[DocumentChunk]) -> List[List[Any]]:
        chunks = list(chunks)

        return [
            [HybridRAG._make_id_static(c.content, c.metadata) for c in chunks],
            [c.content for c in chunks],
            [c.metadata for c in chunks],
            [HybridRAG._require_embedding_static(c).tolist() for c in chunks],
        ]

    def _load_all_chunks(self) -> None:
        self._collection_chunks.clear()

        if self.engine == "chroma":
            self._load_chroma_documents()
        elif self.engine == "lance":
            self._load_lance_documents()
        elif self.engine == "milvus":
            self._load_milvus_documents()

        self._rebuild_flat_chunks()

    def _rebuild_flat_chunks(self) -> None:
        chunks = [
            chunk
            for collection_chunks in self._collection_chunks.values()
            for chunk in collection_chunks
        ]

        self._chunks.clear()
        self._chunks.extend(chunks)

    def _load_chroma_documents(self) -> None:
        for collection_obj in self._db.list_collections():
            name = getattr(collection_obj, "name", str(collection_obj))
            collection = self._db.get_collection(name=name)

            if collection.count() == 0:
                self._collection_chunks[name] = []
                continue

            data = collection.get(
                include=["documents", "metadatas", "embeddings"],
            )

            self._collection_chunks[name] = self._rows_to_chunks(
                data.get("documents", []),
                data.get("metadatas", []),
                data.get("embeddings", []),
            )

    def _load_lance_documents(self) -> None:
        for collection_name in self._db.table_names():
            table = self._db.open_table(collection_name)
            rows = table.to_arrow().to_pylist()

            self._collection_chunks[collection_name] = [
                DocumentChunk(
                    content=row.get("content", ""),
                    metadata=row.get("metadata") or {},
                    embedding=np.asarray(row["vector"], dtype=np.float32) if row.get("vector") is not None else None,
                )
                for row in rows
            ]

    def _load_milvus_documents(self) -> None:
        from pymilvus import Collection, utility

        for collection_name in utility.list_collections(using=self._milvus_alias):
            collection = Collection(collection_name, using=self._milvus_alias)
            collection.load()

            rows = collection.query(
                expr="id != ''",
                output_fields=["id", "content", "metadata", "embedding"],
            )

            self._collection_chunks[collection_name] = [
                DocumentChunk(
                    content=row.get("content", ""),
                    metadata=row.get("metadata") or {},
                    embedding=np.asarray(row["embedding"], dtype=np.float32) if row.get("embedding") is not None else None,
                )
                for row in rows
            ]

    def _load_collection(self, collection: str) -> None:
        if self.engine == "chroma":
            self._load_one_chroma_collection(collection)
        elif self.engine == "lance":
            self._load_one_lance_collection(collection)
        elif self.engine == "milvus":
            self._load_one_milvus_collection(collection)
        else:
            raise ValueError(f"不支持的 engine: {self.engine}")

        self._rebuild_flat_chunks()

    def _load_one_chroma_collection(self, collection_name: str) -> None:
        if collection_name not in self._chroma_collection_names():
            self._collection_chunks[collection_name] = []
            return

        collection = self._db.get_collection(name=collection_name)
        data = collection.get(
            include=["documents", "metadatas", "embeddings"],
        )

        self._collection_chunks[collection_name] = self._rows_to_chunks(
            data.get("documents", []),
            data.get("metadatas", []),
            data.get("embeddings", []),
        )

    def _load_one_lance_collection(self, collection_name: str) -> None:
        if collection_name not in self._db.table_names():
            self._collection_chunks[collection_name] = []
            return

        rows = self._db.open_table(collection_name).to_arrow().to_pylist()

        self._collection_chunks[collection_name] = [
            DocumentChunk(
                content=row.get("content", ""),
                metadata=row.get("metadata") or {},
                embedding=np.asarray(row["vector"], dtype=np.float32) if row.get("vector") is not None else None,
            )
            for row in rows
        ]

    def _load_one_milvus_collection(self, collection_name: str) -> None:
        from pymilvus import Collection, utility

        if not utility.has_collection(collection_name, using=self._milvus_alias):
            self._collection_chunks[collection_name] = []
            return

        collection = Collection(collection_name, using=self._milvus_alias)
        collection.load()

        rows = collection.query(
            expr="id != ''",
            output_fields=["id", "content", "metadata", "embedding"],
        )

        self._collection_chunks[collection_name] = [
            DocumentChunk(
                content=row.get("content", ""),
                metadata=row.get("metadata") or {},
                embedding=np.asarray(row["embedding"], dtype=np.float32) if row.get("embedding") is not None else None,
            )
            for row in rows
        ]

    @staticmethod
    def _rows_to_chunks(
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: List[Any],
    ) -> List[DocumentChunk]:
        chunks = []

        for i, content in enumerate(documents):
            metadata = metadatas[i] if i < len(metadatas) else {}
            embedding = (
                np.asarray(embeddings[i], dtype=np.float32)
                if i < len(embeddings) and embeddings[i] is not None
                else None
            )

            chunks.append(
                DocumentChunk(
                    content=content,
                    metadata=metadata or {},
                    embedding=embedding,
                )
            )

        return chunks

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        collection: Optional[str] = None,
    ) -> None:
        if not documents:
            return

        collection = collection or self.memory_collection
        metadatas = metadatas or [{} for _ in documents]

        if len(documents) != len(metadatas):
            raise ValueError("documents 和 metadatas 长度必须一致")

        all_new_chunks = []

        for doc, meta in zip(documents, metadatas):
            chunk_metadata = {**meta, "collection": collection}
            chunks = self._chunk_text(doc, chunk_metadata)
            self._embed_chunks(chunks)
            all_new_chunks.extend(chunks)

        if not all_new_chunks:
            return

        with _SharedRAGState.lock:
            self._save_chunks(collection, all_new_chunks)
            self._load_collection(collection)
            self._clear_retrieve_cache()

        print(f"当前共 {len(self._chunks)} 个文档块")

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        import re
        return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]+", text.lower())

    def _chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[DocumentChunk]:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        chunks = []
        start = 0
        idx = 0
        step = self.chunk_size - self.chunk_overlap

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()

            if chunk_text:
                meta = {
                    **metadata,
                    "chunk_index": idx,
                    "char_start": start,
                }

                chunks.append(
                    DocumentChunk(
                        content=chunk_text,
                        metadata=meta,
                    )
                )

                idx += 1

            start += step

        return chunks

    @staticmethod
    def _make_id_static(content: str, metadata: Dict[str, Any]) -> str:
        raw = json.dumps(
            {"content": content, "metadata": metadata},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def _make_id(cls, content: str, metadata: Dict[str, Any]) -> str:
        return cls._make_id_static(content, metadata)

    @staticmethod
    def _require_embedding_static(chunk: DocumentChunk) -> np.ndarray:
        if chunk.embedding is None:
            raise ValueError("DocumentChunk 缺少 embedding，无法持久化")
        return chunk.embedding

    @classmethod
    def _require_embedding(cls, chunk: DocumentChunk) -> np.ndarray:
        return cls._require_embedding_static(chunk)

    def _bm25_scores(
        self,
        query: str,
        chunks: List[DocumentChunk],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> np.ndarray:
        query_tokens = self._tokenize(query)
        n_docs = len(chunks)

        if n_docs == 0:
            return np.array([], dtype=np.float32)

        doc_freq = {}
        doc_token_counts = []
        doc_lengths = []

        for chunk in chunks:
            tokens = self._tokenize(chunk.content)
            doc_lengths.append(len(tokens))

            tf_map = {}
            for token in tokens:
                tf_map[token] = tf_map.get(token, 0) + 1

            doc_token_counts.append(tf_map)

            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        avg_dl = float(np.mean(doc_lengths)) if doc_lengths else 1.0
        scores = np.zeros(n_docs, dtype=np.float32)

        for qt in query_tokens:
            df = doc_freq.get(qt, 0)

            if df == 0:
                continue

            idf = np.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)

            for i in range(n_docs):
                tf = doc_token_counts[i].get(qt, 0)
                dl = doc_lengths[i]
                denom = tf + k1 * (1 - b + b * dl / avg_dl)

                if denom != 0:
                    scores[i] += idf * (tf * (k1 + 1)) / denom

        return scores

    @staticmethod
    def _metadata_match(metadata: Dict[str, Any], metadata_filter: Dict[str, Any]) -> bool:
        return all(metadata.get(key) == value for key, value in metadata_filter.items())

    def _filter_chunks(
        self,
        chunks: List[DocumentChunk],
        metadata_filter: Optional[Dict[str, Any]],
    ) -> List[DocumentChunk]:
        if not metadata_filter:
            return chunks

        return [
            chunk
            for chunk in chunks
            if self._metadata_match(chunk.metadata, metadata_filter)
        ]

    def _get_query_embedding(self, query: str) -> np.ndarray:
        cached = self._get_cached_embedding(query)

        if cached is not None:
            return cached

        response = self.client.embed(
            model=self.embed_model,
            input=[query],
        )

        embeddings = response.get("embeddings") or []

        if not embeddings:
            raise RuntimeError("Query embedding 返回为空")

        embedding = np.asarray(embeddings[0], dtype=np.float32)
        self._set_cached_embedding(query, embedding)

        return embedding

    def _vector_scores(self, query: str, chunks: List[DocumentChunk]) -> np.ndarray:
        if not chunks:
            return np.array([], dtype=np.float32)

        q_emb = self._get_query_embedding(query)

        valid_chunks = [c for c in chunks if c.embedding is not None]

        if not valid_chunks:
            return np.zeros(len(chunks), dtype=np.float32)

        matrix = np.vstack([c.embedding for c in valid_chunks])
        valid_scores = self._cosine_similarity(matrix, q_emb)

        scores = np.zeros(len(chunks), dtype=np.float32)
        valid_index = 0

        for i, chunk in enumerate(chunks):
            if chunk.embedding is not None:
                scores[i] = valid_scores[valid_index]
                valid_index += 1

        return scores

    @staticmethod
    def _cosine_similarity(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)
        return (matrix @ vector) / np.where(norms == 0, 1e-10, norms)

    @staticmethod
    def _normalize(scores: np.ndarray) -> np.ndarray:
        if len(scores) == 0:
            return scores

        mn = scores.min()
        mx = scores.max()

        if mx - mn < 1e-10:
            return np.zeros_like(scores)

        return (scores - mn) / (mx - mn)

    def _make_retrieve_cache_key(
        self,
        query: str,
        collection: Optional[str],
        metadata_filter: Optional[Dict[str, Any]],
    ) -> str:
        filter_str = (
            json.dumps(
                metadata_filter,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            if metadata_filter
            else ""
        )

        return "|".join([
            self._backend_key,
            collection or "*",
            query,
            filter_str,
            str(self.top_k),
            str(self.bm25_weight),
        ])

    def _get_cached_retrieve(self, cache_key: str) -> Optional[List[DocumentChunk]]:
        with _SharedRAGState.lock:
            cached = _SharedRAGState.retrieve_cache.get(cache_key)

            if cached is not None:
                _SharedRAGState.retrieve_cache.move_to_end(cache_key)
                return cached

        return None

    def _set_cached_retrieve(self, cache_key: str, results: List[DocumentChunk]) -> None:
        with _SharedRAGState.lock:
            _SharedRAGState.retrieve_cache[cache_key] = results
            _SharedRAGState.retrieve_cache.move_to_end(cache_key)

            while len(_SharedRAGState.retrieve_cache) > _SharedRAGState.retrieve_cache_maxsize:
                _SharedRAGState.retrieve_cache.popitem(last=False)

    def _clear_retrieve_cache(self, collection: Optional[str] = None) -> None:
        with _SharedRAGState.lock:
            if collection is None:
                _SharedRAGState.retrieve_cache.clear()
                return

            prefix = f"{self._backend_key}|{collection}|"
            keys = [key for key in _SharedRAGState.retrieve_cache if key.startswith(prefix)]

            for key in keys:
                del _SharedRAGState.retrieve_cache[key]

    def retrieve(
        self,
        query: str,
        collection: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        cache_key = self._make_retrieve_cache_key(
            query,
            collection,
            metadata_filter,
        )

        cached = self._get_cached_retrieve(cache_key)

        if cached is not None:
            return cached

        chunks = self._chunks if collection is None else self._collection_chunks.get(collection, [])

        if not chunks:
            return []

        filtered_chunks = self._filter_chunks(chunks, metadata_filter)

        if not filtered_chunks:
            return []

        vec_scores = self._vector_scores(query, filtered_chunks)
        bm25_scores = self._bm25_scores(query, filtered_chunks)

        vec_norm = self._normalize(vec_scores)
        bm25_norm = self._normalize(bm25_scores)

        hybrid_scores = (
            (1 - self.bm25_weight) * vec_norm
            + self.bm25_weight * bm25_norm
        )

        top_local = np.argsort(hybrid_scores)[::-1][:self.top_k]
        results = [filtered_chunks[i] for i in top_local]

        self._set_cached_retrieve(cache_key, results)

        return results

    def ask(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        collection: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        context_docs = self.retrieve(
            question,
            collection=collection,
            metadata_filter=metadata_filter,
        )

        if context_docs:
            context = "\n".join(
                f"- [{d.metadata.get('source', d.metadata.get('collection', 'unknown'))}] {d.content}"
                for d in context_docs
            )

            user_content = (
                "用户提出的问题你可以参考以下资料\n\n"
                f"参考资料：\n{context}\n\n"
                f"问题：{question}"
            )
        else:
            user_content = question

        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        messages.append({
            "role": "user",
            "content": user_content,
        })

        response = self.client.chat(
            model=self.chat_model,
            messages=messages,
        )

        return response["message"]["content"]

    @classmethod
    def clear_shared_cache(cls) -> None:
        with _SharedRAGState.lock:
            _SharedRAGState.embed_cache.clear()
            _SharedRAGState.retrieve_cache.clear()

    @classmethod
    def clear_embedding_cache(cls) -> None:
        with _SharedRAGState.lock:
            _SharedRAGState.embed_cache.clear()

    @classmethod
    def clear_retrieve_cache(cls) -> None:
        with _SharedRAGState.lock:
            _SharedRAGState.retrieve_cache.clear()

    @classmethod
    def cache_stats(cls) -> Dict[str, Any]:
        with _SharedRAGState.lock:
            return {
                "embedding_cache_size": len(_SharedRAGState.embed_cache),
                "embedding_cache_maxsize": _SharedRAGState.embed_cache_maxsize,
                "retrieve_cache_size": len(_SharedRAGState.retrieve_cache),
                "retrieve_cache_maxsize": _SharedRAGState.retrieve_cache_maxsize,
                "backend_count": len(_SharedRAGState.backends),
                "client_count": len(_SharedRAGState.clients),
            }

    @classmethod
    def reset_shared_state(cls) -> None:
        with _SharedRAGState.lock:
            _SharedRAGState.embed_cache.clear()
            _SharedRAGState.retrieve_cache.clear()
            _SharedRAGState.backends.clear()
            _SharedRAGState.clients.clear()
