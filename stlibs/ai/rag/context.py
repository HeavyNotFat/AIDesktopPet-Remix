import ollama

from .utils import log


def merge_results(bm25_results, vector_results, top_k):
    result_map = {}
    # BM25权重
    for r in bm25_results:
        key = r["text"]
        result_map[key] = {**r, "final_score": r["score"] * 2}

    # vector权重
    for r in vector_results:
        key = r["text"]
        if key in result_map:
            result_map[key]["final_score"] += (r["score"])
        else:
            result_map[key] = {**r, "final_score": r["score"]}

    results = list(result_map.values())
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results[:top_k]


def build_context(search_results):
    if not search_results:
        return "没有检索到相关知识。"

    parts = []
    for index, result in enumerate(search_results):
        parts.append(f"[知识片段 {index + 1}]\n来源：\n{result['source']}\n\n{result['text']}")
    return "\n".join(parts)


def compress_context(chat_model, prompts, query, search_results):
    if not search_results:
        return "没有检索到相关知识。"

    compressed = []
    for index, result in enumerate(search_results):
        try:
            content = prompts['rag_compressed'].replace("{query}", query).replace('text', result['text'])
            response = ollama.chat(model=chat_model, messages=[{"role": "user", "content": content}])
            text = (response["message"]["content"].strip())

            if text:
                compressed.append(f"[知识片段 {index + 1}]\n来源：\n{result['source']}\n\n{text}")
        except Exception as e:
            log(f"压缩失败 {index}: {e}", "ERROR")

    if not compressed:
        return "没有检索到相关知识。"

    return "\n".join(compressed)
