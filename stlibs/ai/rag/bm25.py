from rank_bm25 import BM25Okapi


def tokenize(text):
    return list(text)


class BM25Index:
    def __init__(self):
        self.bm25 = None
        self.chunks = []

    def build(self, chunks):
        self.chunks = chunks
        corpus = [tokenize(chunk["text"]) for chunk in chunks]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query, top_k):
        if self.bm25 is None:
            return []

        scores = self.bm25.get_scores(tokenize(query))
        indexes = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []

        for i in indexes:
            chunk = self.chunks[i]
            results.append({"score": scores[i], "source": chunk["source"], "chunk_index": chunk["chunk_index"],
                            "text": chunk["text"], "type": "bm25"})

        return results
