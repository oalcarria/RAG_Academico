import json
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from . import config

EMBEDDINGS_FILE = config.VECTOR_STORE_DIR / "embeddings.npy"
METADATA_FILE = config.VECTOR_STORE_DIR / "metadata.json"
INDEX_CONFIG_FILE = config.VECTOR_STORE_DIR / "index_config.json"


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


def strip_repeated_lines(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop headers/footers that repeat across the document.

    Slide decks carry the same author and course line on every page. Left in,
    that boilerplate lands in every embedding and pulls unrelated chunks
    towards each other, so remove any line present on most pages.
    """
    if len(pages) < 4:
        return pages

    counts = Counter()
    for _, text in pages:
        for line in {line.strip() for line in text.splitlines() if line.strip()}:
            counts[line] += 1

    threshold = len(pages) * 0.5
    boilerplate = {line for line, n in counts.items() if n > threshold}

    cleaned = []
    for page_num, text in pages:
        lines = [line for line in text.splitlines() if line.strip() and line.strip() not in boilerplate]
        body = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if body:
            cleaned.append((page_num, body))
    return cleaned


def build_chunks(pages: list[tuple[int, str]], filename: str) -> list[dict]:
    """Slide a fixed-size window over the whole document.

    Chunking page by page is a poor fit for slides: each one holds a couple of
    dozen words, so a chunk ends up too small to answer anything on its own and
    title-only slides score high while carrying no information. A window that
    crosses page boundaries keeps each chunk self-contained.
    """
    words: list[str] = []
    page_of_word: list[int] = []
    for page_num, text in pages:
        for word in text.split():
            words.append(word)
            page_of_word.append(page_num)

    if not words:
        return []

    size = config.CHUNK_SIZE
    step = max(size - config.CHUNK_OVERLAP, 1)
    min_words = min(25, size)

    chunks = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if len(window) < min_words and chunks:
            break
        chunks.append(
            {
                "text": " ".join(window),
                "source": filename,
                "page": page_of_word[start],
            }
        )
        if start + size >= len(words):
            break
    return chunks


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _current_index_config() -> dict:
    return {
        "embedding_model": config.EMBEDDING_MODEL,
        "passage_prefix": config.EMBEDDING_PASSAGE_PREFIX,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
    }


class VectorStore:
    """Minimal flat vector index (numpy cosine similarity + a JSON sidecar for
    metadata). Avoids native-compiled dependencies like chroma-hnswlib, which
    has no prebuilt Windows wheel for recent Python versions; a brute-force
    search is plenty fast for the chunk counts this app produces.
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
        self._embeddings = None
        self._metadata = []

        if not (EMBEDDINGS_FILE.exists() and METADATA_FILE.exists()):
            return

        # Vectors built by a different model or chunking are not comparable to
        # new ones, so discard them instead of silently degrading every search.
        stored = {}
        if INDEX_CONFIG_FILE.exists():
            stored = json.loads(INDEX_CONFIG_FILE.read_text(encoding="utf-8"))
        if stored != _current_index_config():
            self.reset()
            return

        self._embeddings = np.load(EMBEDDINGS_FILE)
        self._metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))

    def _save(self):
        if self._embeddings is not None:
            np.save(EMBEDDINGS_FILE, self._embeddings)
        METADATA_FILE.write_text(json.dumps(self._metadata, ensure_ascii=False), encoding="utf-8")
        INDEX_CONFIG_FILE.write_text(json.dumps(_current_index_config(), ensure_ascii=False), encoding="utf-8")

    def reset(self):
        self._embeddings = None
        self._metadata = []
        EMBEDDINGS_FILE.unlink(missing_ok=True)
        METADATA_FILE.unlink(missing_ok=True)
        INDEX_CONFIG_FILE.unlink(missing_ok=True)

    def count(self) -> int:
        return len(self._metadata)

    def add_pdf(self, pdf_path, filename: str) -> int:
        pages = strip_repeated_lines(extract_pages(pdf_path))
        chunks = build_chunks(pages, filename)
        if not chunks:
            return 0

        texts = [config.EMBEDDING_PASSAGE_PREFIX + c["text"] for c in chunks]
        new_embeddings = _normalize(np.asarray(self.embedder.encode(texts, show_progress_bar=False), dtype=np.float32))

        if self._embeddings is None:
            self._embeddings = new_embeddings
        else:
            self._embeddings = np.vstack([self._embeddings, new_embeddings])
        self._metadata.extend(chunks)

        self._save()
        return len(chunks)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        if not self._metadata or self._embeddings is None:
            return []
        top_k = min(top_k or config.TOP_K, len(self._metadata))

        query_embedding = _normalize(
            np.asarray(self.embedder.encode([config.EMBEDDING_QUERY_PREFIX + query]), dtype=np.float32)
        )
        similarities = self._embeddings @ query_embedding[0]
        top_indices = np.argsort(-similarities)[:top_k]

        return [
            RetrievedChunk(
                text=self._metadata[i]["text"],
                source=self._metadata[i]["source"],
                page=self._metadata[i]["page"],
            )
            for i in top_indices
        ]


vector_store = VectorStore()
