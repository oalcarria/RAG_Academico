import json
from dataclasses import dataclass

import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from . import config

EMBEDDINGS_FILE = config.VECTOR_STORE_DIR / "embeddings.npy"
METADATA_FILE = config.VECTOR_STORE_DIR / "metadata.json"


@dataclass
class RetrievedChunk:
    text: str
    source: str
    page: int


def extract_pages(pdf_path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i, text))
    return pages


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class VectorStore:
    """Minimal flat vector index (numpy cosine similarity + a JSON sidecar for
    metadata). Avoids native-compiled dependencies like chroma-hnswlib, which
    has no prebuilt Windows wheel for recent Python versions; a brute-force
    search is plenty fast for the chunk counts a school-visit demo produces.
    """

    def __init__(self):
        self._embedder = None
        self._embeddings: np.ndarray | None = None
        self._metadata: list[dict] = []
        self._load()

    @property
    def embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(config.EMBEDDING_MODEL)
        return self._embedder

    def _load(self):
        if EMBEDDINGS_FILE.exists() and METADATA_FILE.exists():
            self._embeddings = np.load(EMBEDDINGS_FILE)
            self._metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        else:
            self._embeddings = None
            self._metadata = []

    def _save(self):
        if self._embeddings is not None:
            np.save(EMBEDDINGS_FILE, self._embeddings)
        METADATA_FILE.write_text(json.dumps(self._metadata, ensure_ascii=False), encoding="utf-8")

    def reset(self):
        self._embeddings = None
        self._metadata = []
        EMBEDDINGS_FILE.unlink(missing_ok=True)
        METADATA_FILE.unlink(missing_ok=True)

    def count(self) -> int:
        return len(self._metadata)

    def add_pdf(self, pdf_path, filename: str) -> int:
        pages = extract_pages(pdf_path)
        docs, metadatas = [], []
        for page_num, page_text in pages:
            for chunk in chunk_text(page_text):
                docs.append(chunk)
                metadatas.append({"text": chunk, "source": filename, "page": page_num})

        if not docs:
            return 0

        new_embeddings = _normalize(np.asarray(self.embedder.encode(docs, show_progress_bar=False), dtype=np.float32))

        if self._embeddings is None:
            self._embeddings = new_embeddings
        else:
            self._embeddings = np.vstack([self._embeddings, new_embeddings])
        self._metadata.extend(metadatas)

        self._save()
        return len(docs)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        if not self._metadata or self._embeddings is None:
            return []
        top_k = top_k or config.TOP_K

        query_embedding = _normalize(np.asarray(self.embedder.encode([query]), dtype=np.float32))
        similarities = self._embeddings @ query_embedding[0]

        top_k = min(top_k, len(self._metadata))
        top_indices = np.argsort(-similarities)[:top_k]

        return [
            RetrievedChunk(text=self._metadata[i]["text"], source=self._metadata[i]["source"], page=self._metadata[i]["page"])
            for i in top_indices
        ]


vector_store = VectorStore()
