"""Local audio helpers for macOS TTS and whisper.cpp STT."""

from __future__ import annotations

import io
import os
import re
import wave
import shutil
import logging
import subprocess
import tempfile
from collections import deque
from dataclasses import dataclass

import av
import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample


logger = logging.getLogger(__name__)

WHISPER_SAMPLE_RATE = 16000
LOCAL_TTS_SAMPLE_RATE = 24000


def list_macos_say_voices() -> list[str]:
    """Return the list of voices exposed by ``say -v ?``."""
    say_bin = shutil.which("say")
    if say_bin is None:
        return []

    result = subprocess.run(
        [say_bin, "-v", "?"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("Failed to list macOS voices: %s", result.stderr.strip() or result.stdout.strip())
        return []

    voices: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        voice_name = stripped.split(maxsplit=1)[0]
        if voice_name not in voices:
            voices.append(voice_name)
    return voices


def resolve_macos_say_voice(requested: str | None, available_voices: list[str], fallback: str) -> str:
    """Resolve a macOS voice name with graceful fallback."""
    if requested and requested in available_voices:
        return requested
    if fallback in available_voices:
        return fallback
    if available_voices:
        return available_voices[0]
    raise RuntimeError("No macOS TTS voices are available. Install a system voice or verify /usr/bin/say.")


def _ensure_mono(audio: NDArray[np.int16]) -> NDArray[np.int16]:
    """Convert stereo/multi-channel PCM to mono int16."""
    if audio.ndim == 1:
        return audio.astype(np.int16, copy=False)

    normalized = audio
    if normalized.shape[0] < normalized.shape[1]:
        normalized = normalized.T
    if normalized.shape[1] > 1:
        normalized = normalized[:, 0]
    else:
        normalized = normalized[:, 0]
    return normalized.astype(np.int16, copy=False)


def _resample_int16(audio: NDArray[np.int16], source_rate: int, target_rate: int) -> NDArray[np.int16]:
    """Resample mono PCM to a target sample rate."""
    if source_rate == target_rate:
        return audio.astype(np.int16, copy=False)

    num_samples = int(len(audio) * target_rate / source_rate)
    if num_samples <= 0:
        return np.zeros(0, dtype=np.int16)

    resampled = resample(audio.astype(np.float32), num_samples)
    return np.clip(np.round(resampled), -32768, 32767).astype(np.int16)


def pcm_to_wav_bytes(audio: NDArray[np.int16], sample_rate: int) -> bytes:
    """Encode mono PCM int16 samples to WAV bytes."""
    mono = _ensure_mono(audio)
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(mono.tobytes())
        return buffer.getvalue()


def split_audio_chunks(audio: NDArray[np.int16], chunk_size: int = 960) -> list[NDArray[np.int16]]:
    """Split PCM into playback-friendly chunks."""
    mono = _ensure_mono(audio)
    if mono.size == 0:
        return []
    return [mono[i : i + chunk_size] for i in range(0, len(mono), chunk_size)]


@dataclass
class WhisperCppTranscriber:
    """Thin whisper.cpp subprocess wrapper."""

    binary_path: str
    model_path: str

    def validate(self) -> None:
        """Validate the configured whisper.cpp binary and model."""
        if shutil.which(self.binary_path) is None and not os.path.isfile(self.binary_path):
            raise RuntimeError(
                f"whisper.cpp binary not found at '{self.binary_path}'. "
                "Set WHISPER_CPP_BIN or run scripts/setup-local-mac.sh.",
            )
        if not os.path.isfile(self.model_path):
            raise RuntimeError(
                f"whisper.cpp model not found at '{self.model_path}'. "
                "Set WHISPER_CPP_MODEL or run scripts/setup-local-mac.sh.",
            )

    def transcribe(self, audio: NDArray[np.int16], sample_rate: int) -> str:
        """Transcribe mono PCM using ``whisper-cli``."""
        self.validate()

        pcm = _resample_int16(_ensure_mono(audio), sample_rate, WHISPER_SAMPLE_RATE)
        if pcm.size == 0:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            wav_path = wav_file.name
            wav_file.write(pcm_to_wav_bytes(pcm, WHISPER_SAMPLE_RATE))

        try:
            command = [
                self.binary_path,
                "-m",
                self.model_path,
                "-f",
                wav_path,
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            if result.returncode != 0:
                raise RuntimeError(output.strip() or "whisper.cpp failed")
            return self._extract_transcript(output)
        finally:
            try:
                os.unlink(wav_path)
            except FileNotFoundError:
                pass

    @staticmethod
    def _extract_transcript(raw_output: str) -> str:
        """Extract transcript text from whisper.cpp CLI output."""
        text_lines: list[str] = []
        for line in raw_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("whisper_", "system_info:", "main:", "ggml_", "AVX", "WARNING")):
                continue
            stripped = re.sub(r"^\[[^\]]+\]\s*", "", stripped)
            if stripped:
                text_lines.append(stripped)
        return " ".join(text_lines).strip()


@dataclass
class MacOSTTSSynthesizer:
    """Simple ``say``-backed TTS for local speech output."""

    default_voice: str
    output_sample_rate: int = LOCAL_TTS_SAMPLE_RATE

    def synthesize(self, text: str, voice: str) -> tuple[int, NDArray[np.int16]]:
        """Synthesize text with macOS ``say`` and return mono PCM."""
        if not text.strip():
            return self.output_sample_rate, np.zeros(0, dtype=np.int16)

        say_bin = shutil.which("say")
        if say_bin is None:
            raise RuntimeError("macOS 'say' command not found")

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as output_file:
            output_path = output_file.name

        try:
            command = [
                say_bin,
                "-v",
                voice,
                "-o",
                output_path,
                text,
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "say failed")
            return self._decode_audio_file(output_path)
        finally:
            try:
                os.unlink(output_path)
            except FileNotFoundError:
                pass

    def _decode_audio_file(self, path: str) -> tuple[int, NDArray[np.int16]]:
        """Decode an AIFF/WAV file to mono PCM int16."""
        with av.open(path) as container:
            stream = container.streams.audio[0]
            sample_rate = stream.codec_context.sample_rate or self.output_sample_rate
            chunks: list[NDArray[np.int16]] = []
            for frame in container.decode(stream):
                chunk = frame.to_ndarray()
                mono = _ensure_mono(np.asarray(chunk))
                chunks.append(mono)

        if not chunks:
            return self.output_sample_rate, np.zeros(0, dtype=np.int16)

        combined = np.concatenate(chunks)
        normalized = _resample_int16(combined, sample_rate, self.output_sample_rate)
        return self.output_sample_rate, normalized


class EnergyTurnDetector:
    """Lightweight RMS-based speech turn detector."""

    def __init__(
        self,
        *,
        sample_rate: int = WHISPER_SAMPLE_RATE,
        speech_threshold: float = 650.0,
        min_speech_ms: int = 250,
        end_silence_ms: int = 800,
        preroll_ms: int = 150,
        max_turn_s: float = 20.0,
    ) -> None:
        """Initialize the detector."""
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self.max_turn_s = max_turn_s
        self._speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._chunks: list[NDArray[np.int16]] = []
        maxlen = max(1, int(preroll_ms / 20))
        self._preroll: deque[NDArray[np.int16]] = deque(maxlen=maxlen)

    def reset(self) -> None:
        """Reset detector state."""
        self._speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._chunks = []
        self._preroll.clear()

    def process_chunk(self, audio_chunk: NDArray[np.int16]) -> tuple[bool, NDArray[np.int16] | None]:
        """Process a PCM chunk.

        Returns:
            A tuple of ``(speech_started, completed_turn_audio)``.
        """
        chunk = _ensure_mono(audio_chunk)
        if chunk.size == 0:
            return False, None

        duration_ms = len(chunk) / self.sample_rate * 1000.0
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        is_speech = rms >= self.speech_threshold

        if not self._speaking:
            self._preroll.append(chunk)
            if is_speech:
                self._speaking = True
                self._speech_ms = duration_ms
                self._silence_ms = 0.0
                self._chunks = list(self._preroll)
                return True, None
            return False, None

        self._chunks.append(chunk)
        if is_speech:
            self._speech_ms += duration_ms
            self._silence_ms = 0.0
        else:
            self._silence_ms += duration_ms

        total_duration_ms = sum(len(part) for part in self._chunks) / self.sample_rate * 1000.0
        if total_duration_ms >= self.max_turn_s * 1000:
            return self._finish_turn()

        if self._speech_ms >= self.min_speech_ms and self._silence_ms >= self.end_silence_ms:
            return self._finish_turn()

        return False, None

    def _finish_turn(self) -> tuple[bool, NDArray[np.int16] | None]:
        """Finalize the current speech turn."""
        completed = np.concatenate(self._chunks) if self._chunks else None
        self.reset()
        return False, completed
