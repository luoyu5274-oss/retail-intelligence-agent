"""
Vector store using sklearn TfidfVectorizer for fast indexing.
Instant on CPU — no model download, no GPU needed.
Persists to data/vector_store.npz + data/vector_meta.json.
"""
import json
import joblib
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import DATA_DIR, TOP_K_RESULTS

_STORE_NPZ = DATA_DIR / "vector_store.npz"
_STORE_META = DATA_DIR / "vector_meta.json"
_VECTORIZER_PKL = DATA_DIR / "vectorizer.pkl"

_vectorizer: TfidfVectorizer | None = None
_embeddings: np.ndarray | None = None
_docs: list[str] = []
_metas: list[dict] = []


def _build_vectorizer(texts: list[str], progress_cb=None) -> TfidfVectorizer:
    """Build a TF-IDF vectorizer on the corpus, with reasonable limits."""
    if progress_cb:
        progress_cb("构建 TF-IDF 向量化器…")
    return TfidfVectorizer(
        max_features=8000,
        ngram_range=(1, 2),
        stop_words="english",
        max_df=0.85,
        min_df=1,
        sublinear_tf=True,
    ).fit(texts)


def _load_store():
    global _embeddings, _docs, _metas, _vectorizer
    if _embeddings is None and _STORE_NPZ.exists() and _STORE_META.exists():
        data = np.load(str(_STORE_NPZ), allow_pickle=True)
        _embeddings = data["embeddings"]
        with open(_STORE_META, "r", encoding="utf-8") as f:
            store = json.load(f)
        _docs = store["docs"]
        _metas = store["metas"]
        if _VECTORIZER_PKL.exists():
            _vectorizer = joblib.load(str(_VECTORIZER_PKL))


def _save_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(_STORE_NPZ), embeddings=_embeddings)
    with open(_STORE_META, "w", encoding="utf-8") as f:
        json.dump({"docs": _docs, "metas": _metas}, f, ensure_ascii=False)
    if _vectorizer is not None:
        joblib.dump(_vectorizer, str(_VECTORIZER_PKL))


def is_indexed() -> bool:
    _load_store()
    return _embeddings is not None and len(_embeddings) > 0


def index_chunks(chunks: list[dict], progress_cb=None) -> int:
    global _embeddings, _docs, _metas, _vectorizer

    texts = [c["text"] for c in chunks]
    metas = [c["metadata"] for c in chunks]

    if progress_cb:
        progress_cb(f"构建索引（{len(texts)} 个文本块）…")

    _vectorizer = _build_vectorizer(texts, progress_cb)
    _embeddings = _vectorizer.transform(texts).toarray().astype(np.float32)
    _docs = texts
    _metas = metas
    _save_store()

    if progress_cb:
        progress_cb(f"索引完成，{len(_docs)} 个文本块")

    return len(_docs)


def query(question: str, brand_filter: str | None = None, k: int = TOP_K_RESULTS) -> list[dict]:
    _load_store()
    if _embeddings is None or len(_embeddings) == 0:
        return []

    global _vectorizer
    if _vectorizer is None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        # Rebuild from scratch if not in memory (shouldn't happen if index_chunks was called)
        return []

    q_vec = _vectorizer.transform([question])
    scores = cosine_similarity(q_vec, _embeddings)[0]

    if brand_filter:
        mask = np.array([m.get("brand") == brand_filter for m in _metas])
        scores = np.where(mask, scores, -1.0)

    top_idx = np.argsort(scores)[::-1][:k]
    results = []
    for idx in top_idx:
        if scores[idx] < 0:
            continue
        results.append({
            "text": _docs[idx],
            "metadata": _metas[idx],
            "relevance": float(round(scores[idx], 3)),
        })
    return results


def reset():
    global _embeddings, _docs, _metas, _vectorizer
    _embeddings = None
    _docs = []
    _metas = []
    _vectorizer = None
    if _STORE_NPZ.exists():
        _STORE_NPZ.unlink()
    if _STORE_META.exists():
        _STORE_META.unlink()
    if _VECTORIZER_PKL.exists():
        _VECTORIZER_PKL.unlink()
