SUPPORTED_ENGINES = ("chroma", "lancedb")


def get_vector_store(engine, store_path, collection_name):
    normalized = (engine or "chroma").strip().lower()

    if normalized in ("chroma", "chromadb"):
        from .chroma import ChromaVectorStore
        return ChromaVectorStore(store_path, collection_name)

    if normalized in ("lance", "lancedb"):
        from .lance import LanceVectorStore
        return LanceVectorStore(store_path, collection_name)

    raise ValueError(f"不支持的向量引擎：{engine}，可选值：{SUPPORTED_ENGINES}")
