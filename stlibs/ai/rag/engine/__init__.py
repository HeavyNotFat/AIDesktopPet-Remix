SUPPORTED_ENGINES = ("chroma", "lancedb")


def get_vector_store(engine, store_path, collection_name):
    """
    根据 engine 名称创建对应的向量引擎实例。
    engine: "chroma" / "chromadb" 或 "lance" / "lancedb"（大小写不敏感）
    """
    normalized = (engine or "chroma").strip().lower()

    if normalized in ("chroma", "chromadb"):
        from .chroma import ChromaVectorStore
        return ChromaVectorStore(store_path, collection_name)

    if normalized in ("lance", "lancedb"):
        from .lance import LanceVectorStore
        return LanceVectorStore(store_path, collection_name)

    raise ValueError(f"不支持的向量引擎：{engine}，可选值：{SUPPORTED_ENGINES}")
