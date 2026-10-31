# Clicky Classroom

A native window for recording a teacher, transcribing the class locally, and writing study notes with a local language model. Classroom is separate from Clicky's existing screen/Q&A Lesson Recording.

The full app also adds a native **Dashboard** with Home, Chat, Notes, Library, Tools and Settings. The Notes workspace follows the user-selected OpenWhispr layout: saved notes on the left, searchable transcripts, a large title, transcript/notes tabs and compact recording controls. It uses dark neutral colors, Clicky's blue accent, Segoe UI and consistent spacing. Existing assistant, cursor guidance, shortcuts, Sketch, Work/routines, connections, journal and recording controls remain available. Run `run-dashboard.cmd` after preparing full dependencies, or choose **Open Dashboard** from the fork's tray. The launcher can read the installed Clicky's legacy .env without copying keys into the repository. Existing protected settings keep precedence.

Use **Recording settings** for audio devices and local models. **More** contains import/open, generation, recovery and model preparation. **Your notes** is an editable text/Markdown notebook with Save notes; unsaved edits block switching and are saved before a normal close/quit. Editing is unavailable while processing. **New note** can also create a text-only note without opening audio. Search covers titles, transcripts and saved notes; Ctrl+K focuses it. Classroom's older internal route names remain compatible with the app.

## What it does

- Records a classroom microphone, Windows computer audio, or both as separate16kHz mono WAV tracks.
- Saves the audio continuously. Timestamped transcription jobs are checkpointed in a local SQLite database. If a model fails or Clicky closes unexpectedly, reopen the class and retry without rerecording it.
- Defaults to local Parakeet TDT0.6Bv3INT8 with sherpa-onnx, matching OpenWhispr's model family and file/decoder convention. Whisper remains selectable. The regular assistant/dictation path also supports Parakeet and automatically prefers a prepared Clicky-owned model unless you explicitly select another provider. There is no connection to OpenWhispr's running process or recording service.
- Adapts OpenWhispr's speech/silence gate and pause-aware segmentation, with attribution and its MIT license included.
- Produces timestamped `transcript.md` and local-model `notes.md`, with topic summaries, definitions, equations, worked examples, assignments, and review questions when the transcript supports them.
- Handles long classes in bounded sections instead of discarding the end of a long transcript or allocating a huge context window.
- Has no cloud fallback. Notes requests accept only loopback HTTP servers, ignore environment proxies, and refuse redirects.

## Prepare after your current recording

This source fork does not replace your installed Clicky or modify OpenWhispr. The development work does not start any audio device.

1. Open PowerShell in this checkout and run `./setup-classroom.ps1`. It uses uv to prepare a local Python3.11 environment and install `requirements-classroom.txt`. It does not launch the app, download speech weights, or begin recording.
2. Run `run-classroom.cmd`. The window opens idle. You can also run `.venv\Scripts\python.exe main.py --classroom`.
3. **Local Parakeet** is selected by default. Use **Prepare offline speech model** to download/cache Parakeet TDT0.6Bv3 once if needed (about680MB), or browse to an existing compatible model folder. Clicky's own cache is `%LOCALAPPDATA%\ClickyClassroom\models\parakeet-tdt-0.6b-v3`. `CLICKY_PARAKEET_MODEL` can point to another directory. Existing complete model files are read only, not moved or edited. Whisper remains an optional choice; its default model is `base`. Preparation never starts recording. Parakeet automatically detects its supported languages; the language field controls Whisper.
4. For notes, run your own local Ollama server with an already-downloaded text model, or a dedicated local llama.cpp/LM Studio server. Enter its loopback address and exact model name in the window. The default model name is a configurable example, not a bundled or automatically downloaded model. Do not point it at an OpenWhispr service that is busy recording.
5. Choose **Teacher in the room — microphone** or **Online class — computer audio**. Click **Find microphones** to list inputs if needed. Nothing records until you click **Start class recording**.
6. At the end, click **Stop and process**. Keep the window open while transcription and notes finish. You can read/copy the Transcript and Study notes tabs, or open the saved class folder.

Full Clicky integration: `./setup-classroom.ps1 -FullClicky` installs the full app's dependencies too. Run that checkout's `main.py` and open **Classroom — Record class & make local notes…** from its tray menu. The standalone Classroom entry point avoids starting the normal assistant microphone/hotkeys/screen services and is the simplest way to record a class independently.

## Parakeet model compatibility

The selected directory must contain `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, and `tokens.txt`. The adapter uses the offline `nemo_transducer` decoder. OpenWhispr's Parakeet TDT0.6Bv3 and Unified English transducer model layouts match this convention. Cohere, streaming-only models, and arbitrary ONNX speech models are not supported by this adapter. Model weights retain their own licenses and are not bundled.

## Files and recovery

Data is stored separately under `%LOCALAPPDATA%\ClickyClassroom\sessions\`, not inside OpenWhispr or the original Clicky profile. `CLICKY_CLASSROOM_DATA_DIR` can choose another destination.

Each class keeps `audio-microphone.wav`, `audio-system.wav`, or `audio-import.wav`; `session.json`; `session.sqlite3`; `transcript.md`; and, after successful generation, `notes.md` and cached note sections. Audio is roughly110MiB per hour per source. Both sources roughly double that. Each track's timestamps are relative to that track's recorded samples; this is not speaker diarization or precise inter-device clock synchronization.

If transcription fails, prepare/fix the model, choose **Open saved class**, and use **Retry transcription**. If notes fail, start/configure the local notes server and use **Generate study notes**. Already-completed transcription chunks are not duplicated. Retry also indexes audio left after an interrupted capture. Recording gaps and failures are shown in the transcript; it never claims a gap-free class after a device/queue/storage error.

If you do not need live text, leave **Transcribe while recording** off. Then the app saves audio first and loads the speech model after capture stops, reducing competition for CPU/RAM during class. Default CPU budget is2threads. The eight-hour live-recording limit keeps WAV sizes manageable; start a new class session for longer recordings.

## Existing audio files

Use **Import saved audio** to select WAV, FLAC, OGG, or AIFF. A source file is never altered. A local canonical copy is retained in the class folder. MP4/video extraction and automatic reading of another application's in-progress recordings are not implemented.

CLI example, without any live capture:

```powershell
.venv\Scripts\python.exe -m classroom.cli --no-notes import-audio "D:\Classes\physics.wav" --title "Physics — acceleration"
.venv\Scripts\python.exe -m classroom.cli --notes-model YOUR_DOWNLOADED_MODEL notes "PATH_TO_SAVED_CLASS_FOLDER"
```

## Build and validate

```powershell
uv pip install --python .venv\Scripts\python.exe pytest
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m pytest tests/test_classroom.py -q

# Optional portable Windows build after full classroom dependencies are prepared:
uv pip install --python .venv\Scripts\python.exe pyinstaller
.venv\Scripts\python.exe -m PyInstaller classroom.spec --clean --noconfirm
```

No live microphone, loopback stream, screen recorder or installed-app restart was used during development. Native UI tests run offscreen. Capture workers use synthetic PCM and fake devices. A loopback mock server validates notes requests. Real local models processed the same2,142-word prerecorded lecture: Parakeet measured0.84%word error rate in135seconds; Whisper measured1.82%in152seconds. See BENCHMARK.md. Clean synthetic-speech results do not establish accuracy in a noisy room. Live hardware, real local notes-model quality and a packaged executable check remain pending after the current meeting. No portable build or installer has been installed in this development pass.

Use recording only where your teacher/class rules allow it. AI transcription can mishear names, numbers and equations; keep the audio and verify important assignments and mathematical details. See THIRD_PARTY_NOTICES.md for source attribution.
