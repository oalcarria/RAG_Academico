# Asistente RAG

Aplicación para subir documentos PDF y hacer preguntas sobre ellos, por texto
o por voz, recibiendo la respuesta tanto en texto como hablada.

## ¿Qué es un RAG?

Un modelo de lenguaje (LLM) solo sabe lo que aprendió en su entrenamiento; no
ha leído tus PDFs. **RAG** (*Retrieval-Augmented Generation*) resuelve esto en
dos pasos:

1. **Retrieval**: buscar en tus documentos los fragmentos de texto más
   relacionados con la pregunta.
2. **Generation**: pasarle esos fragmentos al LLM junto con la pregunta para
   que redacte la respuesta basándose en ellos.

Así el modelo puede responder sobre documentos que nunca ha visto, citando de
dónde saca la información, sin necesidad de volver a entrenarlo.

## Cómo funciona

**Al subir un PDF:**

```
PDF → extraer texto → trocear en fragmentos → convertir cada
fragmento en un embedding (vector) → guardarlo en el almacén local
```

**Al preguntar:**

```
Pregunta (texto o voz) → embedding de la pregunta → comparar con
los fragmentos guardados y quedarnos con los más parecidos →
enviar esos fragmentos + la pregunta al LLM (Groq) → responder en
texto y locutarlo en voz
```

Un **embedding** es una representación numérica del significado de un texto:
fragmentos con significado parecido tienen embeddings parecidos, lo que
permite buscar por significado y no solo por palabras exactas.

## Arquitectura

- **LLM**: [Groq](https://console.groq.com) (API compatible con OpenAI, muy
  rápida). Es la única parte que necesita internet.
- **Embeddings**: locales, con `sentence-transformers`
  (`intfloat/multilingual-e5-small`, multilingüe, ventana de 512 tokens).
- **Extracción de PDF**: `pypdf`. Se comparó con PyMuPDF (resultados
  equivalentes) y con `pdf-inspector` de Firecrawl, que extrajo un 11% menos
  de texto y numeraba mal las páginas.
- **Troceado**: ventana deslizante sobre el documento completo, no página a
  página, para que cada fragmento sea autosuficiente.
- **Base vectorial**: almacén propio simple (numpy + JSON) en
  `data/vector_store`. Se evitó Chroma porque su dependencia
  `chroma-hnswlib` no tiene wheel para Windows + Python 3.13 y exige
  compilador de C++.
- **Voz → texto**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), local.
- **Texto → voz**: [Piper](https://github.com/rhasspy/piper), local, voces en español.
- **Backend**: FastAPI (Python).
- **Frontend**: HTML/CSS/JS sencillo, sin frameworks, servido por el backend.

## Estructura del proyecto

```
backend/
  config.py   → carga la configuración desde .env
  rag.py      → extracción/troceado de PDFs, embeddings y base vectorial
  llm.py      → construye el prompt y llama a Groq
  stt.py      → transcribe audio a texto con faster-whisper
  tts.py      → convierte texto en audio con Piper
  main.py     → API FastAPI que conecta todo con el frontend

frontend/
  index.html, style.css, app.js  → interfaz de subida de PDFs y chat

data/
  uploads/, vector_store/  → PDFs y embeddings generados en tiempo de ejecución

models/       → aquí van los ficheros de voz de Piper (no se suben a git)
```

## Instalación

### 1. Entorno de Python

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. API key de Groq

Copia `.env.example` a `.env` y añade tu clave de Groq
(https://console.groq.com/keys):

```bash
copy .env.example .env
```

Revisa también `GROQ_MODEL`: Groq depreca o renombra modelos con cierta
frecuencia, así que si sale un error `model_not_found`, consulta
[console.groq.com/docs/models](https://console.groq.com/docs/models) y pon
ahí un modelo vigente.

### 3. Voz de Piper (texto → voz)

1. Crea la carpeta `models/` si no existe.
2. Descarga `es_ES-davefx-medium.onnx` y `es_ES-davefx-medium.onnx.json`
   desde [rhasspy/piper-voices en Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium).
3. Colócalos en `models/`.

Para usar otra voz, cambia `PIPER_MODEL_PATH` en `.env`.

### 4. Whisper (voz → texto)

No requiere descarga manual: `faster-whisper` descarga el modelo la primera
vez que se usa y lo deja cacheado para funcionar sin conexión después.

## Arrancar la aplicación

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000` (Chrome recomendado, para que el micrófono
funcione bien).

## Uso

1. Sube uno o varios PDFs desde "Tus documentos".
2. Pregunta escribiendo o pulsando el micrófono 🎤.
3. La respuesta aparece en texto (con las páginas de origen citadas) y se
   reproduce en voz automáticamente.
4. "Empezar de cero" borra los documentos y el historial.

## Personalización

Todo esto se ajusta en `.env` (ver `.env.example`):

- `TOP_K`: fragmentos de contexto recuperados por pregunta (por defecto 8).
- `CHUNK_SIZE` / `CHUNK_OVERLAP`: tamaño y solapamiento de los fragmentos, en
  palabras (por defecto 120 / 40). Al cambiarlos, el índice existente se
  invalida y se reconstruye solo: hay que volver a subir los PDFs.
- `WHISPER_MODEL_SIZE`: tamaño del modelo de voz→texto (`tiny`/`base`/`small`/`medium`).
- `EMBEDDING_MODEL` / `GROQ_MODEL` / `PIPER_MODEL_PATH`: cambiar los modelos usados.

La estrategia de troceado está en [backend/rag.py](backend/rag.py), función
`build_chunks`.