"""Tkinter dialog: target dir, base name, model choice, copy vs move."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from wildfire.models_info import WHISPER_MODELS
from wildfire.workflow import run as run_workflow


def _run_in_background(
    source_path: str,
    target_dir: str,
    base_name: str,
    model_id: str,
    move: bool,
    engine: str,
    detect_speakers: bool,
    performance_profile: str,
    status_var: tk.StringVar,
    on_done: Callable[..., None],
) -> None:
    try:
        status_var.set(
            "Working… (transcribing; first run may download models and take a while)"
        )
        audio_path, txt_path = run_workflow(
            source_path,
            target_dir,
            base_name,
            model_id,
            move,
            engine=engine,
            detect_speakers=detect_speakers,
            performance_profile=performance_profile,
        )
        status_var.set("Done.")
        on_done(success=True, audio_path=audio_path, txt_path=txt_path)
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

    # Variables
    target_dir_var = tk.StringVar(value="")
    base_name_var = tk.StringVar(value=default_name)
    model_id_var = tk.StringVar(value=WHISPER_MODELS[0]["id"])
    move_var = tk.BooleanVar(value=False)
    engine_var = tk.StringVar(value="whisperx")
    detect_speakers_var = tk.BooleanVar(value=False)
    performance_profile_var = tk.StringVar(value="balanced")
    status_var = tk.StringVar(value="Ready.")

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
    model_combo = ttk.Combobox(
        model_frame,
        state="readonly",
        width=16,
        values=[m["label"] for m in WHISPER_MODELS],
    )
    model_combo.set(WHISPER_MODELS[0]["label"])
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
    update_model_info()
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
    ).pack(side=tk.LEFT)

    row += 1

    perf_frame = ttk.Frame(main)
    perf_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))

    ttk.Label(perf_frame, text="Performance:").pack(side=tk.LEFT, padx=(0, 6))
    perf_combo = ttk.Combobox(
        perf_frame,
        state="readonly",
        width=18,
        values=[
            "Balanced (recommended)",
            "Max speed",
            "Max quality",
        ],
    )
    perf_combo.set("Balanced (recommended)")
    perf_combo.pack(side=tk.LEFT)

    def update_performance_profile(*_: object) -> None:
        label = perf_combo.get()
        if label.startswith("Max speed"):
            performance_profile_var.set("fast")
        elif label.startswith("Max quality"):
            performance_profile_var.set("quality")
        else:
            performance_profile_var.set("balanced")

    perf_combo.bind("<<ComboboxSelected>>", update_performance_profile)
    update_performance_profile()
    row += 1

    ttk.Checkbutton(
        main,
        text="Move source file to target folder (instead of copy)",
        variable=move_var,
    ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
    row += 1

    status_label = ttk.Label(main, textvariable=status_var, foreground="gray")
    status_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
    row += 1

    def on_done(success: bool, error: str | None = None, audio_path=None, txt_path=None):
        if success:
            messagebox.showinfo(
                "Wildfire",
                f"Done.\n\nRecording: {audio_path}\nTranscript: {txt_path}",
            )
            root.quit()
            root.destroy()
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
            status_var.set("Transcribing in place… (no copy/move).")
        else:
            status_var.set("Preparing to transcribe…")

        for w in (btn_ok, btn_cancel, dir_entry, model_combo):
            try:
                w.config(state=tk.DISABLED)
            except Exception:
                pass

        def done(success, error=None, audio_path=None, txt_path=None):
            root.after(
                0,
                lambda s=success, e=error, a=audio_path, t=txt_path: on_done(
                    s, e, a, t
                ),
            )

        move_flag = bool(move_var.get()) and not target_was_empty

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
                status_var,
                done,
            ),
        )
        thread.daemon = True
        thread.start()

    btn_cancel = ttk.Button(main, text="Cancel", command=root.destroy)
    btn_cancel.grid(row=row, column=0, padx=(0, 6), pady=(8, 0))
    btn_ok = ttk.Button(main, text="OK", command=run)
    btn_ok.grid(row=row, column=1, sticky=tk.W, pady=(8, 0))
    row += 1

    root.mainloop()


if __name__ == "__main__":
    import sys
    show_wildfire_dialog(sys.argv[1] if len(sys.argv) > 1 else None)
