import ctypes
import io
import sys
import wave
from pathlib import Path

from piper import PiperVoice
from piper.phonemize_espeak import ESPEAK_DATA_DIR

from . import config

_voice: PiperVoice | None = None


def _ascii_safe_dir(path: Path) -> str:
    """Return a path espeak-ng can actually open.

    espeak-ng is C code that mishandles non-ASCII characters in paths on
    Windows (e.g. a user folder like "C:\\Users\\Óscar"). It does not report an
    error: it silently falls back to a path compiled into the wheel and then
    aborts the whole process, taking the server down with it. The 8.3 short
    name is always ASCII, so prefer it whenever the real path is not.
    """
    if str(path).isascii():
        return str(path)

    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, 1024) and buffer.value.isascii():
            return buffer.value

    raise RuntimeError(
        f"La ruta de datos de espeak-ng contiene caracteres no ASCII ({path}) y no se "
        "ha podido obtener una ruta corta equivalente. Mueve el proyecto a una ruta sin "
        "acentos ni caracteres especiales para que la síntesis de voz funcione."
    )


def get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        model_path = Path(config.PIPER_MODEL_PATH)
        if not model_path.exists():
            raise RuntimeError(
                f"No se encuentra el modelo de voz de Piper en {model_path}. "
                "Descárgalo siguiendo las instrucciones del README."
            )
        _voice = PiperVoice.load(str(model_path), espeak_data_dir=_ascii_safe_dir(ESPEAK_DATA_DIR))
    return _voice


def synthesize(text: str) -> bytes:
    voice = get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buffer.getvalue()
