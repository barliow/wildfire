"""
Probe whisperx progress capabilities.

Why this exists:
- The Wildfire GUI expects `whisperx` to support a `progress_callback` kwarg.
- In some `whisperx` versions, `progress_callback` is not supported and only
  stage-level 0/100 updates occur.

This script definitively checks whether the installed whisperx build supports
`progress_callback`, and (if it does) logs every callback invocation with
timestamps.
"""

from __future__ import annotations

import argparse
import inspect
import math
import sys
import time
import wave
from collections import Counter
from pathlib import Path
from typing import Callable

import numpy as np
import whisperx


def _write_sine_wav(path: Path, *, sr: int, seconds: float, freq_hz: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    n = int(sr * seconds)
    t = np.arange(n, dtype=np.float64) / sr
    audio = (0.2 * np.sin(2 * math.pi * freq_hz * t)).astype(np.float32)
    pcm16 = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def _summarize_callback_values(pcts: list[float]) -> None:
    if not pcts:
        print("No progress callback invocations.")
        return

    # Many implementations report 0..100, but some might report 0..1.
    min_p = min(pcts)
    max_p = max(pcts)

    rounded = [round(p, 1) for p in pcts]
    common = Counter(rounded).most_common(15)

    print(f"Callback calls: {len(pcts)}")
    print(f"Min/Max p: {min_p} / {max_p}")
    print(f"Most common rounded p values: {common}")


def probe_progress(
    *,
    input_path: str | None,
    model_id: str,
    device: str,
    compute_type: str,
    batch_size: int,
    chunk_size: int,
    print_progress: bool,
    combined_progress: bool,
    seconds_probe: float,
) -> int:
    wav_path: Path | None = None
    if input_path is None:
        wav_path = Path("out_probe") / f"sine_{seconds_probe:.1f}s_{model_id}.wav"
        if not wav_path.exists():
            _write_sine_wav(
                wav_path,
                sr=16000,
                seconds=seconds_probe,
                freq_hz=440.0,
            )
        input_path = str(wav_path)

    print(f"whisperx file input: {input_path}")

    # Load model.
    print("Loading whisperx model...")
    model = whisperx.load_model(model_id, device=device, compute_type=compute_type)

    # Inspect signature (this is the definitive check for support).
    sig = inspect.signature(model.transcribe)
    print("transcribe() signature:", sig)

    progress_supported = "progress_callback" in sig.parameters
    print("supports progress_callback?:", progress_supported)

    # Load audio.
    audio = whisperx.load_audio(str(input_path))

    calls: list[tuple[float, float]] = []
    start = time.time()

    def cb(p: float) -> None:
        # Some versions expect 0..100. Others might supply 0..1; we just record.
        t = time.time() - start
        calls.append((t, float(p)))

        # Print a small sample live so we can tell if progress is incremental.
        if len(calls) <= 15 or len(calls) in (20, 50, 100):
            print(f"callback #{len(calls)} t={t:.2f}s p={p}")

    # Call transcribe.
    print("Running transcribe()...")
    err: str | None = None
    try:
        kwargs = {
            "batch_size": batch_size,
            "chunk_size": chunk_size,
            "print_progress": print_progress,
            "combined_progress": combined_progress,
        }
        if progress_supported:
            kwargs["progress_callback"] = cb
        result = model.transcribe(audio, **kwargs)
    except TypeError as e:
        # This can happen even when signature looks compatible, but it typically
        # means the model implementation doesn't implement the kwarg.
        err = str(e)
        result = None

    print("\n--- Probe Summary ---")
    print("progress_callback TypeError?:", err is not None)
    if err:
        print("TypeError:", err)

    pcts = [p for _, p in calls]
    _summarize_callback_values(pcts)

    if result is not None:
        print("Transcribe done. Result keys:", list(result.keys()))

    return 0 if result is not None else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None, help="Path to an audio/video file. If omitted, a sine WAV is synthesized.")
    ap.add_argument("--model", default="tiny", help="whisperx model id (default: tiny)")
    ap.add_argument("--device", default="cpu", help="cpu|cuda (default: cpu)")
    ap.add_argument("--compute-type", default="float32", help="compute type (default: float32)")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--chunk-size", type=int, default=30)
    ap.add_argument("--print-progress", action="store_true", help="Let whisperx print its own progress to stdout.")
    ap.add_argument("--combined-progress", action="store_true", help="Let whisperx combine progress for internal steps.")
    ap.add_argument("--synth-seconds", type=float, default=6.0, help="Seconds for synthesized audio if --input is omitted.")
    args = ap.parse_args()

    return probe_progress(
        input_path=args.input,
        model_id=args.model,
        device=args.device,
        compute_type=args.compute_type,
        batch_size=args.batch_size,
        chunk_size=args.chunk_size,
        print_progress=args.print_progress,
        combined_progress=args.combined_progress,
        seconds_probe=args.synth_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())

