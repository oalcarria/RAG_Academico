import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, stt, tts
from .rag import vector_store

app = FastAPI(title="Asistente RAG - Visitas de institutos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


class TTSRequest(BaseModel):
    text: str


@app.post("/api/upload")
async def upload_pdfs(files: list[UploadFile] = File(...)):
    total_chunks = 0
    processed = []
    for upload in files:
        if not upload.filename.lower().endswith(".pdf"):
            continue
        dest = config.UPLOAD_DIR / f"{uuid.uuid4().hex}_{upload.filename}"
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)

        added = vector_store.add_pdf(dest, upload.filename)
        total_chunks += added
        processed.append({"filename": upload.filename, "chunks": added})

    if not processed:
        raise HTTPException(status_code=400, detail="No se ha subido ningún PDF válido")

    return {"processed": processed, "total_chunks_added": total_chunks, "total_chunks": vector_store.count()}


@app.post("/api/reset")
async def reset_knowledge_base():
    vector_store.reset()
    for item in config.UPLOAD_DIR.iterdir():
        # Leave .gitkeep alone: it is what keeps the empty directory in git.
        if item.is_file() and not item.name.startswith("."):
            item.unlink()
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    return {"total_chunks": vector_store.count()}


@app.post("/api/ask")
async def ask_question(payload: AskRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="La pregunta está vacía")

    chunks = vector_store.search(question)
    try:
        answer = llm.ask(question, chunks)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sources = [{"source": c.source, "page": c.page} for c in chunks]
    return {"answer": answer, "sources": sources}


@app.post("/api/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    try:
        text = stt.transcribe(audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al transcribir el audio: {exc}") from exc
    return {"text": text}


@app.post("/api/tts")
async def text_to_speech(payload: TTSRequest):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto está vacío")
    try:
        wav_bytes = tts.synthesize(text)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=wav_bytes, media_type="audio/wav")


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
