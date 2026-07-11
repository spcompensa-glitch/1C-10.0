import os
import logging
from pathlib import Path

logger = logging.getLogger("WhisperService")

class WhisperService:
    def __init__(self):
        self.model = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        try:
            logger.info("Initializing local Whisper model (tiny)...")
            # Lazy import to avoid loading heavy modules at startup
            from faster_whisper import WhisperModel
            # tiny is highly optimized, fast and small (around 75MB)
            self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
            self._initialized = True
            logger.info("Local Whisper model loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading Whisper model: {e}")

    def transcribe(self, file_path: str) -> str:
        self.initialize()
        if not self.model:
            return "[Erro: Modelo Whisper local não inicializado]"
        
        try:
            logger.info(f"Transcribing audio file: {file_path}")
            segments, info = self.model.transcribe(file_path, beam_size=5)
            text_segments = []
            for segment in segments:
                text_segments.append(segment.text)
            
            transcription = " ".join(text_segments).strip()
            logger.info(f"Transcription success. Language: {info.language} ({info.language_probability:.2f})")
            return transcription
        except Exception as e:
            logger.error(f"Failed to transcribe: {e}")
            return f"[Erro na Transcrição: {e}]"

whisper_service = WhisperService()
