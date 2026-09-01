from openai import OpenAI

from . import config
from .rag import RetrievedChunk

# Intentionally written in Spanish: this is the LLM's instruction set, and the
# assistant must always answer students in Spanish.
SYSTEM_PROMPT = """Eres un asistente educativo que ayuda a estudiantes de instituto a entender
documentos PDF que ellos mismos han subido. Responde SIEMPRE en español, de forma clara,
cercana y adaptada a un público adolescente.

Reglas:
- Basa tu respuesta únicamente en los fragmentos de contexto proporcionados.
- Si la respuesta no está en el contexto, dilo honestamente en vez de inventarla.
- Cuando sea útil, indica de qué documento y página proviene la información.
- Sé conciso: el estudiante va a escuchar la respuesta en voz alta, así que evita
  listas muy largas o formato complejo; usa frases naturales para hablar.
"""

_client: OpenAI | None = None


def get_client() -> OpenAI:
    # Groq exposes an OpenAI-compatible API, so the official OpenAI SDK works
    # as-is, just pointed at Groq's base URL with a Groq API key.
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("Missing GROQ_API_KEY in the .env file")
        _client = OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL)
    return _client


def build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"[Documento: {c.source}, página {c.page}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def ask(question: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        context = "(No hay documentos cargados todavía)."
    else:
        context = build_context(chunks)

    user_message = f"Contexto de los documentos:\n{context}\n\nPregunta del estudiante: {question}"

    client = get_client()
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""
