from faster_whisper import WhisperModel

model = WhisperModel("base", device="cpu")


def transcribe_audio(file_path: str) -> str:
    segments, _ = model.transcribe(file_path)
    return " ".join([seg.text.strip() for seg in segments]).strip()