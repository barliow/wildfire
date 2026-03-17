"""Run transcription and place audio + timestamped transcript in target folder."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import torch
import whisper
import whisperx

# Avoid Windows privilege issues when Hugging Face Hub creates links.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_HARD_LINKS", "1")


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    total_seconds, ms = divmod(millis, 1000)
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}.{ms:03d}"


def _segments_to_plaintext(segments: list[dict]) -> str:
    """Convert segments with timestamps (and optional speakers) to plaintext."""
    lines: list[str] = []
    for seg in segments:
        start = _format_timestamp(float(seg.get("start", 0.0)))
        end = _format_timestamp(float(seg.get("end", 0.0)))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        speaker = seg.get("speaker")
        prefix = f"[{start} - {end}]"
        if speaker:
            prefix += f" ({speaker})"
        lines.append(f"{prefix} {text}".rstrip())
    return "\n".join(lines)


def run(
    source_path: str | Path,
    target_dir: str | Path,
    base_name: str,
    model_id: str,
    move_instead_of_copy: bool,
    *,
    engine: str = "whisperx",
    use_word_timestamps: bool = True,
    detect_speakers: bool = False,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    performance_profile: str = "balanced",
) -> tuple[Path, Path]:
    """Copy or move source, transcribe, and save timestamped plaintext transcript.

    Target files:
      - Audio: `{target_dir}/{base_name}.{source_suffix}` (copy or move)
      - Transcript: `{target_dir}/{base_name}.txt`
      - Returns (path_to_audio_in_target, path_to_transcript).
    """
    source = Path(source_path).resolve()
    target_dir = Path(target_dir).resolve()

    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    target_dir.mkdir(parents=True, exist_ok=True)
    audio_ext = source.suffix

    same_folder_no_move = (
        not move_instead_of_copy and target_dir == source.parent.resolve()
    )

    if same_folder_no_move:
        target_audio = source
    else:
        target_audio = target_dir / f"{base_name}{audio_ext}"
    target_txt = target_dir / f"{base_name}.txt"

    if not same_folder_no_move:
        if move_instead_of_copy:
            shutil.move(str(source), str(target_audio))
        else:
            shutil.copy2(str(source), str(target_audio))

    engine_normalized = (engine or "whisperx").lower()

    if engine_normalized == "whisper":
        model = whisper.load_model(model_id)
        result = model.transcribe(str(target_audio))
        segments = result.get("segments") or []
        if segments:
            text = _segments_to_plaintext(segments)
        else:
            text = result.get("text", "").strip()
        target_txt.write_text(text, encoding="utf-8")
        return target_audio, target_txt

    # WhisperX (default)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "float32"

    if performance_profile == "fast":
        batch_size = 32
    elif performance_profile == "quality":
        batch_size = 8
    else:
        batch_size = 16

    audio = whisperx.load_audio(str(target_audio))
    model = whisperx.load_model(model_id, device, compute_type=compute_type)
    result = model.transcribe(audio, batch_size=batch_size)

    language = result.get("language")

    if use_word_timestamps and language:
        align_model, metadata = whisperx.load_align_model(
            language_code=language,
            device=device,
        )
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )

    if detect_speakers:
        token = os.getenv("PYANNOTE_AUTH_TOKEN")
        if not token:
            raise RuntimeError(
                "Speaker detection requires the PYANNOTE_AUTH_TOKEN environment "
                "variable to be set with a valid Hugging Face access token."
            )
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=token,
            device=device,
        )
        diarize_segments = diarize_model(
            audio,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        result = whisperx.assign_word_speakers(diarize_segments, result)

    segments = result.get("segments") or []
    text = _segments_to_plaintext(segments)
    target_txt.write_text(text, encoding="utf-8")

    return target_audio, target_txt
