"""Run transcription and place audio + timestamped transcript in target folder."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

import torch
import whisper
import whisperx

# Avoid Windows privilege issues when Hugging Face Hub creates links.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_HARD_LINKS", "1")

# Work around torchcodec-related crashes in pyannote/torchaudio by forcing the
# fallback audio loader path instead of trying to use torchcodec.
os.environ.setdefault("PYANNOTE_AUDIO_DISABLE_TORCHCODEC", "1")


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


def _get_pyannote_token() -> str | None:
    """Return diarization auth token from env or local secrets file."""
    token = os.getenv("PYANNOTE_AUTH_TOKEN")
    if token:
        return token

    # Fallback: local secrets file next to project root (gitignored).
    secrets_path = Path(__file__).resolve().parents[2] / "wildfire_secrets.toml"
    if not secrets_path.is_file():
        return None

    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python <3.11
        return None

    try:
        data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    secrets = data.get("secrets") or {}
    token = secrets.get("pyannote_auth_token")
    if token:
        os.environ.setdefault("PYANNOTE_AUTH_TOKEN", str(token))
    return token


def _get_diarization_pipeline():
    """Return a WhisperX diarization pipeline class or raise a clear error."""
    # Newer WhisperX exposes DiarizationPipeline at top level.
    if hasattr(whisperx, "DiarizationPipeline"):
        return whisperx.DiarizationPipeline

    # Older versions may keep it under whisperx.diarize.
    try:
        from whisperx import diarize as _wx_diar  # type: ignore[import-not-found]
    except Exception:
        _wx_diar = None  # type: ignore[assignment]

    if _wx_diar is not None and hasattr(_wx_diar, "DiarizationPipeline"):
        return _wx_diar.DiarizationPipeline  # type: ignore[attr-defined]

    raise RuntimeError(
        "Speaker detection is not available in the installed whisperx version. "
        "Please upgrade whisperx (e.g. `pip install -U whisperx`) or turn off "
        "'Detect speakers' in the dialog."
    )


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
    cpu_threads: int | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
) -> tuple[Path, Path, list[dict]]:
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

    # Include model id in transcript filename so multiple runs with different
    # models keep separate outputs. Default transcript remains anonymous.
    safe_model_id = model_id.replace("/", "-")
    target_txt = target_dir / f"{base_name}_{safe_model_id}_anonymous.txt"

    if not same_folder_no_move:
        if move_instead_of_copy:
            shutil.move(str(source), str(target_audio))
        else:
            shutil.copy2(str(source), str(target_audio))

    engine_normalized = (engine or "whisperx").lower()

    # Optionally override CPU thread count for this run.
    if cpu_threads and cpu_threads > 0:
        try:
            torch.set_num_threads(cpu_threads)
            torch.set_num_interop_threads(cpu_threads)
        except Exception:
            # If the backend doesn't support changing threads at runtime, ignore.
            pass

    def report(stage: str, pct: float) -> None:
        if progress_callback is None:
            return
        try:
            pct_clamped = max(0.0, min(100.0, float(pct)))
        except Exception:
            pct_clamped = 0.0
        progress_callback(stage, pct_clamped)

    # If diarization is requested, validate/token + HF access up front so we fail
    # fast before doing heavy transcription work.
    diarize_model = None
    if detect_speakers:
        token = _get_pyannote_token()
        if not token:
            raise RuntimeError(
                "Speaker detection requires the PYANNOTE_AUTH_TOKEN environment "
                "variable to be set with a valid Hugging Face access token."
            )
        DiarizationPipeline = _get_diarization_pipeline()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # WhisperX 3.8+ takes `token=`; older versions used `use_auth_token=`.
        # It already defaults to the newer `pyannote/speaker-diarization-community-1`
        # pipeline, which is markedly more accurate on noisy meeting audio.
        try:
            diarize_model = DiarizationPipeline(token=token, device=device)
        except TypeError:
            diarize_model = DiarizationPipeline(
                use_auth_token=token,
                device=device,
            )

    if engine_normalized == "whisper":
        report("Transcribing (Whisper)", 0.0)
        model = whisper.load_model(model_id)
        result = model.transcribe(str(target_audio))
        segments = result.get("segments") or []
        if segments:
            text = _segments_to_plaintext(segments)
        else:
            text = result.get("text", "").strip()
        target_txt.write_text(text, encoding="utf-8")
        report("Transcribing (Whisper)", 100.0)
        segments = result.get("segments") or []
        return target_audio, target_txt, segments

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

    report("Transcribing", 0.0)
    tx_kwargs: dict = {"batch_size": batch_size}

    if progress_callback is not None:
        def _whisperx_progress(p: float) -> None:
            # WhisperX typically reports 0-100
            report("Transcribing", p)

        tx_kwargs["progress_callback"] = _whisperx_progress

    try:
        result = model.transcribe(audio, **tx_kwargs)
    except TypeError:
        # Installed whisperx version might not support progress_callback.
        tx_kwargs.pop("progress_callback", None)
        result = model.transcribe(audio, **tx_kwargs)

    report("Transcribing", 100.0)

    language = result.get("language")

    if use_word_timestamps and language:
        report("Aligning", 0.0)
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
        report("Aligning", 100.0)

    if detect_speakers and diarize_model is not None:
        report("Detecting speakers", 0.0)
        diarize_segments = diarize_model(
            audio,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        result = whisperx.assign_word_speakers(diarize_segments, result)
        report("Detecting speakers", 100.0)

    segments = result.get("segments") or []
    text = _segments_to_plaintext(segments)
    target_txt.write_text(text, encoding="utf-8")

    return target_audio, target_txt, segments
