import io

from faster_whisper import WhisperModel

from . import config

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(config.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_bytes: bytes) -> str:
    model = get_model()
    segments, _info = model.transcribe(io.BytesIO(audio_bytes), language="es", beam_size=1)
    return " ".join(segment.text.strip() for segment in segments).strip()
