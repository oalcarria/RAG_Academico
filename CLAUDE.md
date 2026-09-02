# ProyectoRAG — Project Conventions

RAG agent for institute/school visits: students upload PDFs (all at once, shared
kiosk session) and ask questions by text or voice, getting both text and spoken
answers back.

## Stack decisions (already made, don't re-ask)

- **LLM provider: Groq API** (not xAI/Grok — easy to confuse, but this project
  uses Groq's OpenAI-compatible endpoint at `https://api.groq.com/openai/v1`).
  Config lives in `backend/config.py` (`GROQ_API_KEY`, `GROQ_MODEL`).
- **Embeddings**: local, via `sentence-transformers`
  (`intfloat/multilingual-e5-small`), so ingestion doesn't depend on a cloud
  embeddings API. e5 needs the `query: ` / `passage: ` prefixes it was trained
  with — they live in `EMBEDDING_QUERY_PREFIX` / `EMBEDDING_PASSAGE_PREFIX`.
  It replaced `paraphrase-multilingual-MiniLM-L12-v2`, whose 128-token window
  truncated roughly a quarter of every 120-word chunk.
- **PDF text extraction: pypdf.** Measured against PyMuPDF (equivalent output)
  and Firecrawl's `pdf-inspector` on this corpus: pdf-inspector extracted 11%
  less text overall (35% less on one deck) and its page indices were off by
  one, which would produce wrong page citations. Don't swap the extractor
  without re-running that comparison.
- **Chunking**: a sliding window over the whole document (`CHUNK_SIZE` words,
  `CHUNK_OVERLAP` overlap), not per page. Slide decks hold ~30 words a page,
  so page-sized chunks were too small to answer anything and title-only slides
  ranked highly while carrying no information.
- **Vector store**: hand-rolled flat index in `backend/rag.py` (numpy cosine
  similarity + a JSON metadata sidecar), persisted under `data/vector_store`.
  Not Chroma/FAISS — `chroma-hnswlib` and similar have no prebuilt Windows
  wheel for Python 3.13 and need a C++ compiler to build from source, which
  broke the install on this dev machine. Don't reintroduce a compiled ANN
  library here unless the chunk volume actually outgrows brute-force search.
- **Speech-to-text**: local `faster-whisper` (`backend/stt.py`), CPU, `small`
  model size by default.
- **Text-to-speech**: local Piper (`backend/tts.py`), Spanish voice model
  loaded from `PIPER_MODEL_PATH`. Piper's bundled espeak-ng is C code that
  cannot open paths containing non-ASCII characters on Windows: instead of
  raising, it falls back to a path baked into the wheel and aborts the whole
  process, killing the server. `backend/tts.py` passes the 8.3 short path for
  that reason — keep that workaround.
- **Deployment**: runs locally on a laptop/server during the visit (no cloud
  hosting needed); only the Groq LLM calls require internet, which is expected
  to be available on-site.
- **Usage mode**: single shared kiosk session — one browser tab, all students'
  PDFs go into the same knowledge base, with a "reset" action to clear it
  between groups.

## Code style

- **Code comments must be in English.** Follow the general house rule of
  writing as few comments as possible — only when the *why* is non-obvious —
  but any comment that does get written must be in English, including in
  config files like `.env.example`.
- **User-facing content stays in Spanish**: the frontend UI text, the LLM
  system prompt, and API error messages returned to the frontend are all in
  Spanish on purpose, since the end users are Spanish-speaking students. This
  is content, not code comments, so it's exempt from the English-comments rule.
