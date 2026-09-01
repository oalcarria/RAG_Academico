import io
import wave
from pathlib import Path

from piper import PiperVoice

from . import config

_voice: PiperVoice | None = None


def get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        model_path = Path(config.PIPER_MODEL_PATH)
        if not model_path.exists():
            raise RuntimeError(
                f"No se encuentra el modelo de voz de Piper en {model_path}. "
                "Descárgalo siguiendo las instrucciones del README."
            )
        _voice = PiperVoice.load(str(model_path))
    return _voice


def synthesize(text: str) -> bytes:
    voice = get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buffer.getvalue()
