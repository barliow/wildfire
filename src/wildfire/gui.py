"""Tkinter dialog: target dir, base name, model choice, copy vs move."""

from __future__ import annotations

import threading
import os
from pathlib import Path
from typing import Callable
import json
import shutil
import subprocess

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from wildfire.models_info import WHISPER_MODELS, DEFAULT_MODEL_ID
from wildfire.workflow import run as run_workflow

# Selectable input languages. Whisper uses a single "en" code for English (it has
# no separate British-English model), so British English maps to "en". "Auto"
# lets Whisper detect the language, which can drift on quiet/non-speech audio.
LANGUAGE_CHOICES: list[tuple[str, str | None]] = [
    ("English", "en"),
    ("Auto-detect", None),
    ("French", "fr"),
    ("German", "de"),
    ("Spanish", "es"),
    ("Italian", "it"),
    ("Dutch", "nl"),
    ("Portuguese", "pt"),
    ("Polish", "pl"),
    ("Russian", "ru"),
    ("Welsh", "cy"),
]
DEFAULT_LANGUAGE_CODE = "en"

# Bounds for a speaker voice-preview snippet (seconds).
_MIN_SNIPPET_SECONDS = 1.5
_MAX_SNIPPET_SECONDS = 8.0


def _speaker_snippets_from_words(segments: list[dict]) -> dict[str, tuple[float, float]]:
    """Pick a clean, representative audio span per speaker for voice preview.

    Whisper segments often straddle a speaker change, so the *segment* start can
    contain the tail of the previous speaker. WhisperX alignment + diarization
    label individual words with a speaker, so we instead find the longest
    *contiguous* run of words spoken by each speaker and start playback exactly
    where that speaker begins. Falls back to the speaker's longest segment when
    word-level data isn't available.
    """
    # Flatten words that have both timing and a speaker label, in transcript order.
    ordered: list[tuple[float, float, str]] = []
    for seg in segments:
        for w in seg.get("words") or []:
            spk = w.get("speaker") or seg.get("speaker")
            start = w.get("start")
            end = w.get("end")
            if spk is None or start is None or end is None:
                continue
            try:
                ordered.append((float(start), float(end), str(spk)))
            except (TypeError, ValueError):
                continue

    best: dict[str, tuple[float, float]] = {}

    if ordered:
        # Keep the longest contiguous same-speaker run, per speaker.
        def _consider(spk: str, start: float, end: float) -> None:
            prev = best.get(spk)
            if prev is None or (end - start) > (prev[1] - prev[0]):
                best[spk] = (start, end)

        run_start, run_end, run_spk = ordered[0]
        for start, end, spk in ordered[1:]:
            if spk == run_spk:
                run_end = end
            else:
                _consider(run_spk, run_start, run_end)
                run_start, run_end, run_spk = start, end, spk
        _consider(run_spk, run_start, run_end)

    # Fallback: speakers with no usable word run get their longest segment.
    seg_best: dict[str, tuple[float, float]] = {}
    for seg in segments:
        spk = seg.get("speaker")
        if not spk or spk in best:
            continue
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + _MIN_SNIPPET_SECONDS
        prev = seg_best.get(spk)
        if prev is None or (end - start) > (prev[1] - prev[0]):
            seg_best[spk] = (start, end)
    best.update(seg_best)

    # Clamp each snippet to a short, clearly-identifiable window.
    capped: dict[str, tuple[float, float]] = {}
    for spk, (start, end) in best.items():
        if end - start < _MIN_SNIPPET_SECONDS:
            end = start + _MIN_SNIPPET_SECONDS
        elif end - start > _MAX_SNIPPET_SECONDS:
            end = start + _MAX_SNIPPET_SECONDS
        capped[spk] = (start, end)
    return capped


def _run_in_background(
    source_path: str,
    target_dir: str,
    base_name: str,
    model_id: str,
    move: bool,
    engine: str,
    detect_speakers: bool,
    performance_profile: str,
    cpu_threads: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
    language: str | None,
    progress_callback: Callable[[str, float], None] | None,
    on_done: Callable[..., None],
) -> None:
    try:
        audio_path, txt_path, segments = run_workflow(
            source_path,
            target_dir,
            base_name,
            model_id,
            move,
            engine=engine,
            detect_speakers=detect_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            performance_profile=performance_profile,
            cpu_threads=cpu_threads,
            language=language,
            progress_callback=progress_callback,
        )
        on_done(success=True, audio_path=audio_path, txt_path=txt_path, segments=segments)
    except Exception as e:
        status_var.set("Error.")
        on_done(success=False, error=str(e))


def show_wildfire_dialog(source_file: str | None = None) -> None:
    """Show the main Wildfire dialog. If source_file is set, it's the audio to process."""
    root = tk.Tk()
    root.title("Wildfire — Transcribe with Whisper")
    root.minsize(420, 380)
    root.resizable(True, True)

    # Default base name from source file stem
    if source_file:
        try:
            default_name = Path(source_file).stem
        except Exception:
            default_name = "recording"
    else:
        default_name = "recording"

    # Settings persistence
    settings_path = Path.home() / ".wildfire_gui_settings.json"

    def _load_settings() -> dict:
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_settings(
        model_id: str,
        detect_speakers: bool,
        perf_profile: str,
        expected_speakers: int | None,
        language: str | None,
    ) -> None:
        data = {
            "model_id": model_id,
            "detect_speakers": bool(detect_speakers),
            "performance_profile": perf_profile,
            "expected_speakers": expected_speakers,
            "language": language,
        }
        try:
            settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # Settings persistence should never break the UI.
            return

    saved = _load_settings()

    # Variables
    target_dir_var = tk.StringVar(value="")
    base_name_var = tk.StringVar(value=default_name)
    default_model_id = DEFAULT_MODEL_ID
    saved_model_id = saved.get("model_id") or default_model_id
    model_id_var = tk.StringVar(value=saved_model_id)
    move_var = tk.BooleanVar(value=False)
    engine_var = tk.StringVar(value="whisperx")
    detect_speakers_var = tk.BooleanVar(value=bool(saved.get("detect_speakers", False)))
    performance_profile_var = tk.StringVar(
        value=str(saved.get("performance_profile") or "balanced")
    )
    expected_speakers_var = tk.StringVar(
        value=str(saved.get("expected_speakers") or "auto")
    )
    # Input language code; "" means Auto-detect. Default to English on first run,
    # but honor a previously saved choice (including an explicit Auto = None).
    if "language" in saved:
        initial_language_code = saved.get("language") or ""
    else:
        initial_language_code = DEFAULT_LANGUAGE_CODE
    language_var = tk.StringVar(value=initial_language_code)
    cpu_threads_var = tk.StringVar(value="auto")
    status_var = tk.StringVar(value="Ready.")
    progress_var = tk.DoubleVar(value=0.0)

    # Speaker/snippet state (populated after a successful diarized run).
    speaker_entries: dict[str, tk.StringVar] = {}
    speaker_snippets: dict[str, tuple[float, float]] = {}
    last_segments: list[dict] = []
    last_audio_path: Path | None = None
    last_txt_path: Path | None = None
    last_identified_path: Path | None = None

    # Layout
    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)

    row = 0

    if source_file:
        ttk.Label(main, text="Source file:", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=(0, 2)
        )
        row += 1
        ttk.Label(main, text=source_file, foreground="gray").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8)
        )
        row += 1

    ttk.Label(main, text="Target folder:", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1
    dir_frame = ttk.Frame(main)
    dir_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))
    main.columnconfigure(0, weight=1)
    dir_entry = ttk.Entry(dir_frame, textvariable=target_dir_var, width=50)
    dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

    def browse():
        d = filedialog.askdirectory(title="Choose target folder")
        if d:
            target_dir_var.set(d)

    ttk.Button(dir_frame, text="Browse…", command=browse).pack(side=tk.RIGHT)
    row += 1

    ttk.Label(main, text="Base name (for recording + transcript):", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1
    ttk.Entry(main, textvariable=base_name_var, width=40).grid(
        row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6)
    )
    row += 1

    ttk.Label(main, text="Engine:", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1

    engine_frame = ttk.Frame(main)
    engine_frame.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))

    ttk.Radiobutton(
        engine_frame,
        text="WhisperX (recommended)",
        value="whisperx",
        variable=engine_var,
    ).pack(side=tk.LEFT, padx=(0, 12))
    ttk.Radiobutton(
        engine_frame,
        text="Whisper",
        value="whisper",
        variable=engine_var,
    ).pack(side=tk.LEFT)
    row += 1

    ttk.Label(main, text="Whisper model:", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1

    model_frame = ttk.Frame(main)
    model_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
    model_labels = [m["label"] for m in WHISPER_MODELS]
    model_combo = ttk.Combobox(
        model_frame,
        state="readonly",
        width=16,
        values=model_labels,
    )
    model_combo.pack(side=tk.LEFT, padx=(0, 8))

    info_label = ttk.Label(model_frame, text="", foreground="gray", wraplength=320)
    info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def update_model_info(*args):
        sel = model_combo.get()
        for m in WHISPER_MODELS:
            if m["label"] == sel:
                model_id_var.set(m["id"])
                info_label.config(
                    text=f"{m['params']} • {m['speed']} • {m['accuracy']} • {m['disk']}"
                )
                break

    model_combo.bind("<<ComboboxSelected>>", update_model_info)

    # Restore last-used model selection if available.
    selected_label = None
    for m in WHISPER_MODELS:
        if m["id"] == saved_model_id:
            selected_label = m["label"]
            break
    if not selected_label:
        selected_label = WHISPER_MODELS[0]["label"]
        model_id_var.set(WHISPER_MODELS[0]["id"])
    model_combo.set(selected_label)
    update_model_info()
    row += 1

    ttk.Label(main, text="Input language:", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1

    language_frame = ttk.Frame(main)
    language_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))

    language_labels = [label for label, _code in LANGUAGE_CHOICES]
    language_combo = ttk.Combobox(
        language_frame,
        state="readonly",
        width=16,
        values=language_labels,
    )
    language_combo.pack(side=tk.LEFT, padx=(0, 8))

    ttk.Label(
        language_frame,
        text="Pinning the language stops mis-detection into another language.",
        foreground="gray",
        wraplength=320,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def update_language(*_: object) -> None:
        sel = language_combo.get()
        for label, code in LANGUAGE_CHOICES:
            if label == sel:
                language_var.set(code or "")
                break

    language_combo.bind("<<ComboboxSelected>>", update_language)

    # Restore last-used language selection (matching by code; "" == Auto-detect).
    current_code = language_var.get()
    selected_language_label = None
    for label, code in LANGUAGE_CHOICES:
        if (code or "") == current_code:
            selected_language_label = label
            break
    language_combo.set(selected_language_label or LANGUAGE_CHOICES[0][0])
    update_language()
    row += 1

    ttk.Separator(main, orient=tk.HORIZONTAL).grid(
        row=row, column=0, columnspan=2, sticky=tk.EW, pady=10
    )
    row += 1

    ttk.Label(main, text="Options:", font=("Segoe UI", 9, "bold")).grid(
        row=row, column=0, sticky=tk.W, pady=(0, 2)
    )
    row += 1

    options_frame = ttk.Frame(main)
    options_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))

    ttk.Checkbutton(
        options_frame,
        text="Detect speakers (WhisperX only)",
        variable=detect_speakers_var,
    ).pack(side=tk.LEFT, padx=(0, 10))

    ttk.Label(options_frame, text="Expected speakers:").pack(side=tk.LEFT, padx=(0, 6))
    expected_combo = ttk.Combobox(
        options_frame,
        state="readonly",
        width=6,
        values=["Auto", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
    )
    # Restore last-used expected speakers.
    if expected_speakers_var.get() in {"2", "3", "4", "5", "6", "7", "8", "9", "10"}:
        expected_combo.set(expected_speakers_var.get())
    else:
        expected_combo.set("Auto")
        expected_speakers_var.set("auto")
    expected_combo.pack(side=tk.LEFT)

    def update_expected_speakers(*_: object) -> None:
        v = expected_combo.get().strip()
        if v in {"2", "3", "4", "5", "6", "7", "8", "9", "10"}:
            expected_speakers_var.set(v)
        else:
            expected_speakers_var.set("auto")

    expected_combo.bind("<<ComboboxSelected>>", update_expected_speakers)

    row += 1

    perf_frame = ttk.Frame(main)
    perf_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))

    ttk.Label(perf_frame, text="Resource usage:").pack(side=tk.LEFT, padx=(0, 6))
    perf_combo = ttk.Combobox(
        perf_frame,
        state="readonly",
        width=18,
        values=[
            "Balanced (recommended)",
            "Aggressive (fast, more GPU memory)",
            "Conservative (lower GPU memory)",
        ],
    )
    # Restore last-used performance profile.
    if performance_profile_var.get() == "fast":
        perf_combo.set("Aggressive (fast, more GPU memory)")
    elif performance_profile_var.get() == "quality":
        perf_combo.set("Conservative (lower GPU memory)")
    else:
        perf_combo.set("Balanced (recommended)")
    perf_combo.pack(side=tk.LEFT)

    def update_performance_profile(*_: object) -> None:
        label = perf_combo.get()
        if label.startswith("Aggressive"):
            performance_profile_var.set("fast")
        elif label.startswith("Conservative"):
            performance_profile_var.set("quality")
        else:
            performance_profile_var.set("balanced")

    perf_combo.bind("<<ComboboxSelected>>", update_performance_profile)
    update_performance_profile()
    row += 1

    threads_frame = ttk.Frame(main)
    threads_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))

    ttk.Label(threads_frame, text="CPU threads:").pack(side=tk.LEFT, padx=(0, 6))
    threads_combo = ttk.Combobox(
        threads_frame,
        state="readonly",
        width=20,
        values=[
            "Auto (PyTorch default)",
            "Half of cores",
            "All cores",
        ],
    )
    threads_combo.set("Auto (PyTorch default)")
    threads_combo.pack(side=tk.LEFT)

    def update_cpu_threads(*_: object) -> None:
        label = threads_combo.get()
        if label.startswith("Half"):
            cpu_threads_var.set("half")
        elif label.startswith("All"):
            cpu_threads_var.set("all")
        else:
            cpu_threads_var.set("auto")

    threads_combo.bind("<<ComboboxSelected>>", update_cpu_threads)
    update_cpu_threads()
    row += 1

    ttk.Checkbutton(
        main,
        text="Move source file to target folder (instead of copy)",
        variable=move_var,
    ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
    row += 1

    status_label = ttk.Label(main, textvariable=status_var, foreground="gray")
    status_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
    row += 1

    progress_bar = ttk.Progressbar(
        main, variable=progress_var, maximum=100.0, mode="determinate"
    )
    progress_bar.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))
    row += 1

    identified_link_var = tk.StringVar(value="")
    identified_link_label = ttk.Label(
        main,
        textvariable=identified_link_var,
        foreground="#1f6feb",
        cursor="hand2",
    )
    identified_link_label.grid(
        row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 6)
    )
    identified_link_label.grid_remove()
    row += 1

    speakers_frame = ttk.LabelFrame(main, text="Speakers")
    speakers_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(4, 0))
    speakers_frame.grid_remove()
    row += 1

    def _clear_speakers_ui() -> None:
        for child in speakers_frame.winfo_children():
            child.destroy()
        speaker_entries.clear()
        speaker_snippets.clear()

    def _populate_speakers_ui(segments: list[dict], audio_path: Path) -> None:
        _clear_speakers_ui()

        speakers = _speaker_snippets_from_words(segments)

        if not speakers:
            speakers_frame.grid_remove()
            return

        for speaker, (start, end) in speakers.items():
            speaker_snippets[speaker] = (start, end)

        for row_idx, speaker in enumerate(sorted(speakers.keys())):
            snippet = speaker_snippets[speaker]
            frame = ttk.Frame(speakers_frame)
            frame.grid(row=row_idx, column=0, sticky=tk.EW, pady=2)

            ttk.Label(frame, text=speaker).pack(side=tk.LEFT, padx=(0, 6))

            def make_play_cmd(s_id: str) -> Callable[[], None]:
                def _cmd() -> None:
                    _play_speaker_snippet(s_id)

                return _cmd

            ttk.Button(frame, text="▶", width=3, command=make_play_cmd(speaker)).pack(
                side=tk.LEFT, padx=(0, 6)
            )

            name_var = tk.StringVar(value="")
            speaker_entries[speaker] = name_var
            ttk.Label(frame, text="Name:").pack(side=tk.LEFT, padx=(0, 2))
            ttk.Entry(frame, textvariable=name_var, width=24).pack(
                side=tk.LEFT, padx=(0, 4)
            )

            start_str = f"{snippet[0]:.1f}s"
            ttk.Label(frame, text=f"({start_str})", foreground="gray").pack(
                side=tk.LEFT
            )

        # Footer row: generate identified file.
        footer = ttk.Frame(speakers_frame)
        footer.grid(row=len(speakers) + 1, column=0, sticky=tk.EW, pady=(4, 0))

        spacer = ttk.Frame(footer)
        spacer.pack(side=tk.LEFT, expand=True, fill=tk.X)

        ttk.Button(
            footer,
            text="Generate file",
            command=_apply_speaker_names,
        ).pack(side=tk.RIGHT)

        speakers_frame.grid()

    def _play_speaker_snippet(speaker_id: str) -> None:
        if speaker_id not in speaker_snippets or last_audio_path is None:
            return

        start, end = speaker_snippets[speaker_id]
        duration = max(0.5, end - start)

        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showwarning(
                "Wildfire",
                "Audio preview requires FFmpeg's 'ffplay' to be installed and on PATH.",
            )
            return

        try:
            subprocess.Popen(
                [
                    ffplay,
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    "-ss",
                    f"{start:.2f}",
                    "-t",
                    f"{duration:.2f}",
                    str(last_audio_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            # Swallow preview errors so they never kill the main app.
            return

    def _open_identified_file() -> None:
        if last_identified_path is None:
            return
        try:
            if os.name == "nt":
                os.startfile(str(last_identified_path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(last_identified_path)])
        except Exception:
            messagebox.showerror(
                "Wildfire",
                f"Couldn't open file:\n\n{last_identified_path}",
            )

    identified_link_label.bind("<Button-1>", lambda _event: _open_identified_file())

    def _enable_controls() -> None:
        for w in (btn_ok, btn_cancel, dir_entry, model_combo):
            try:
                w.config(state=tk.NORMAL)
            except Exception:
                pass

    def _segments_to_plaintext_with_mapping(
        segments: list[dict], mapping: dict[str, str]
    ) -> str:
        from wildfire.workflow import _format_timestamp  # type: ignore[attr-defined]

        lines: list[str] = []
        for seg in segments:
            start = _format_timestamp(float(seg.get("start", 0.0)))
            end = _format_timestamp(float(seg.get("end", 0.0)))
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            speaker = seg.get("speaker")
            if speaker and speaker in mapping and mapping[speaker]:
                speaker_label = mapping[speaker]
            else:
                speaker_label = speaker
            prefix = f"[{start} - {end}]"
            if speaker_label:
                prefix += f" ({speaker_label})"
            lines.append(f"{prefix} {text}".rstrip())
        return "\n".join(lines)

    def _apply_speaker_names() -> None:
        nonlocal last_segments, last_txt_path, last_identified_path
        if not last_segments or last_txt_path is None:
            return

        mapping: dict[str, str] = {}
        for speaker_id, var in speaker_entries.items():
            name = var.get().strip()
            if name:
                mapping[speaker_id] = name

        if not mapping:
            messagebox.showinfo(
                "Wildfire", "Please enter at least one speaker name first."
            )
            return

        new_text = _segments_to_plaintext_with_mapping(last_segments, mapping)
        identified_stem = last_txt_path.stem
        if identified_stem.endswith("_anonymous"):
            identified_stem = identified_stem[: -len("_anonymous")]
        identified_path = last_txt_path.with_stem(identified_stem + "_identified")

        try:
            identified_path.write_text(new_text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(
                "Wildfire",
                f"Failed to generate identified transcript:\n\n{exc}",
            )
            return

        last_identified_path = identified_path
        identified_link_var.set(f"Open identified file: {identified_path.name}")
        identified_link_label.grid()
        status_var.set(f"Generated identified transcript: {identified_path.name}")

    def on_done(
        success: bool,
        error: str | None = None,
        audio_path=None,
        txt_path=None,
        segments: list[dict] | None = None,
    ):
        nonlocal last_segments, last_audio_path, last_txt_path, last_identified_path
        _enable_controls()
        if success:
            last_audio_path = Path(audio_path) if audio_path is not None else None
            last_txt_path = Path(txt_path) if txt_path is not None else None
            last_segments = segments or []
            last_identified_path = None
            identified_link_var.set("")
            identified_link_label.grid_remove()
            if last_segments:
                _populate_speakers_ui(last_segments, last_audio_path)  # type: ignore[arg-type]
            btn_ok.config(text="Run again")
            btn_cancel.config(text="Close")
        else:
            messagebox.showerror("Wildfire — Error", error or "Unknown error")
            status_var.set("")

    def run():
        target_dir = target_dir_var.get().strip()
        base_name = base_name_var.get().strip()
        target_was_empty = not target_dir

        if not base_name:
            messagebox.showwarning("Wildfire", "Please enter a base name.")
            return

        # Sanitize base name for filesystem
        base_name = "".join(c for c in base_name if c.isalnum() or c in " ._-").strip()
        if not base_name:
            base_name = "recording"
        base_name_var.set(base_name)

        model_label = model_combo.get()
        model_id = model_id_var.get()
        if not model_id:
            for m in WHISPER_MODELS:
                if m["label"] == model_label:
                    model_id = m["id"]
                    break
        model_id_var.set(model_id)

        source = source_file
        if not source:
            messagebox.showwarning(
                "Wildfire",
                "No source file was passed. Use 'Send to → Wildfire' from a file's context menu.",
            )
            return

        if target_was_empty:
            # Treat empty target as "use source folder, no move/copy".
            target_dir = str(Path(source).resolve().parent)
            target_dir_var.set(target_dir)
        status_var.set(
            "Working… (transcribing; first run may download models and take a while)"
        )
        progress_var.set(0.0)

        for w in (btn_ok, btn_cancel, dir_entry, model_combo):
            try:
                w.config(state=tk.DISABLED)
            except Exception:
                pass

        def report_progress(stage: str, pct: float) -> None:
            def _update() -> None:
                status_var.set(f"{stage}… {pct:.0f}%")
                progress_var.set(pct)

            root.after(0, _update)

        def done(success, error=None, audio_path=None, txt_path=None, segments=None):
            root.after(
                0,
                lambda s=success, e=error, a=audio_path, t=txt_path, seg=segments: on_done(
                    s, e, a, t, seg
                ),
            )

        move_flag = bool(move_var.get()) and not target_was_empty

        # Map CPU threads preference to an integer override (or None for auto).
        import multiprocessing

        try:
            cores = multiprocessing.cpu_count()
        except NotImplementedError:
            cores = 0

        cpu_threads_pref = cpu_threads_var.get()
        if cpu_threads_pref == "all" and cores > 0:
            cpu_threads = cores
        elif cpu_threads_pref == "half" and cores > 1:
            cpu_threads = max(1, cores // 2)
        else:
            cpu_threads = None

        exp = expected_speakers_var.get().strip().lower()
        if exp in {"2", "3", "4", "5", "6", "7", "8", "9", "10"}:
            min_speakers = int(exp)
            max_speakers = int(exp)
        else:
            min_speakers = None
            max_speakers = None

        language = language_var.get().strip() or None

        thread = threading.Thread(
            target=_run_in_background,
            args=(
                source,
                target_dir,
                base_name,
                model_id,
                move_flag,
                engine_var.get(),
                bool(detect_speakers_var.get()),
                performance_profile_var.get(),
                cpu_threads,
                min_speakers,
                max_speakers,
                language,
                report_progress,
                done,
            ),
        )
        thread.daemon = True
        thread.start()

        # Persist the most important user choices for next run.
        _save_settings(
            model_id=model_id_var.get(),
            detect_speakers=bool(detect_speakers_var.get()),
            perf_profile=performance_profile_var.get(),
            expected_speakers=(
                int(exp) if exp in {"2", "3", "4", "5", "6", "7", "8", "9", "10"} else None
            ),
            language=language,
        )

    btn_cancel = ttk.Button(main, text="Cancel", command=root.destroy)
    btn_cancel.grid(row=row, column=0, padx=(0, 6), pady=(8, 0))
    btn_ok = ttk.Button(main, text="OK", command=run)
    btn_ok.grid(row=row, column=1, sticky=tk.W, pady=(8, 0))
    row += 1

    root.mainloop()


if __name__ == "__main__":
    import sys
    show_wildfire_dialog(sys.argv[1] if len(sys.argv) > 1 else None)
