"""Run Whisper transcription and place audio + transcript in target folder."""

from __future__ import annotations

import shutil
from pathlib import Path

import whisper


def run(
    source_path: str | Path,
    target_dir: str | Path,
    base_name: str,
    model_id: str,
    move_instead_of_copy: bool,
) -> tuple[Path, Path]:
    """Copy or move source to target dir, transcribe with Whisper, save transcript.

    Target files:
      - Audio: `{target_dir}/{base_name}.{source_suffix}` (copy or move)
      - Transcript: `{target_dir}/{base_name}.txt`

    Returns (path_to_audio_in_target, path_to_transcript).
    """
    source = Path(source_path).resolve()
    target_dir = Path(target_dir).resolve()

    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    target_dir.mkdir(parents=True, exist_ok=True)
    audio_ext = source.suffix
    target_audio = target_dir / f"{base_name}{audio_ext}"
    target_txt = target_dir / f"{base_name}.txt"

    if move_instead_of_copy:
        shutil.move(str(source), str(target_audio))
    else:
        shutil.copy2(str(source), str(target_audio))

    model = whisper.load_model(model_id)
    result = model.transcribe(str(target_audio))

    text = result.get("text", "").strip()
    target_txt.write_text(text, encoding="utf-8")

    return target_audio, target_txt
