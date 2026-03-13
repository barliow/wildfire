# Wildfire

Quick audio transcription via **OpenAI Whisper**, triggered from the Windows right‑click **Send to → Wildfire**. Choose a target folder, name, and model; the app copies (or moves) the recording and saves a `.txt` transcript there.

## Features

- **Send to integration** — Right‑click an audio file → **Send to → Wildfire** (no admin rights).
- **Target folder** — Pick where to save the recording copy and the transcript.
- **Single base name** — One name is used for both the audio file and the transcript (e.g. `meeting` → `meeting.mp3` + `meeting.txt`).
- **Whisper model** — Choose from Tiny up to Large v3; UI shows speed/accuracy/disk info.
- **Copy or move** — Option to move the source file into the target folder instead of copying.

## Requirements

- **Windows**
- **Python 3.10+**
- **openai-whisper** (and its dependencies: e.g. PyTorch)

## Install

1. Clone or download this repo, then from the project root:

   ```bash
   cd wildfire
   pip install -e .
   ```

2. Add Wildfire to the **Send to** menu (per‑user, no admin):

   ```bash
   python scripts/install_sendto.py
   ```

   To remove it later:

   ```bash
   python scripts/install_sendto.py uninstall
   ```

## Usage

1. Right‑click an audio file (e.g. `.mp3`, `.wav`, `.m4a`).
2. Choose **Send to → Wildfire**.
3. In the dialog:
   - **Target folder** — Browse to the folder where the recording and transcript should go.
   - **Base name** — Name used for both files (e.g. `meeting` → `meeting.<ext>` and `meeting.txt`).
   - **Whisper model** — Tiny (fast, lower accuracy) up to Large v3 (slowest, best accuracy). The dropdown shows short performance hints.
   - **Move instead of copy** — Check to move the source file into the target folder; otherwise a copy is made.
4. Click **OK**. Whisper runs; when it finishes, the recording (copy or moved) and the transcript are in the target folder.

## Create the GitHub repo

1. On GitHub: [Create a new repository](https://github.com/new) named `wildfire` (no need to add a README or .gitignore here).
2. In this project folder, add the remote and push:

   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/wildfire.git
   git branch -M main
   git push -u origin main
   ```

   Replace `YOUR_USERNAME` with your GitHub username.

## Project layout

```
wildfire/
├── pyproject.toml
├── README.md
├── src/
│   └── wildfire/
│       ├── __init__.py
│       ├── __main__.py      # Entry (python -m wildfire [file])
│       ├── gui.py           # Tkinter dialog
│       ├── models_info.py   # Whisper model list + descriptions
│       └── workflow.py      # Copy/move + Whisper + save .txt
├── scripts/
│   ├── install_sendto.vbs   # Launcher (no console window)
│   └── install_sendto.py    # Copy launcher to Send To
└── tests/
```

## License

MIT
