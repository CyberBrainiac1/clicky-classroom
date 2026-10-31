# Long-audio transcription validation

## Parakeet comparison and new default

The fork now defaults to **Parakeet TDT0.6Bv3INT8** for Classroom. The regular assistant/dictation path supports Parakeet too and prefers an available Clicky-owned cache unless another provider is explicitly selected.

Both models processed the identical2,142-word/741.36-second prerecorded lecture, through the same file-import/checkpoint pipeline with one CPU inference thread:

| Model | Processing time | Word error rate | Chunks completed |
|---|---:|---:|---:|
| Parakeet TDT0.6Bv3INT8 / sherpa-onnx CPU | 135seconds | **0.84%** | 25/25 |
| Whisper base / faster-whisper CPU int8 | 152seconds | 1.82% | 25/25 |

Parakeet produced2,137words. Its measured word error rate was18word edit errors against the2,142-word reference. Timing includes model initialization and transcription, not the audio-file import. These are individual runs on a live laptop, not a controlled repeated speed study.

The four Parakeet files were copied into Clicky's separate model cache and SHA256-compared with OpenWhispr's selected model files. OpenWhispr's model files were not edited, moved or replaced, and its running speech service was never contacted. The benchmark process set itself to Windows BelowNormal priority and used CPU only. No microphone, playback, screen capture or live/private meeting audio was used.

October31,2026: processed a synthetic physics/precalculus review through the actual Classroom import, checkpointing and transcription path. No microphone, live meeting recording, active OpenWhispr model/server, or GPU was used.

| Measurement | Result |
|---|---:|
| Reference script | 2,142 words |
| Prerecorded speech duration | 12minutes21.36seconds |
| ASR | faster-whisper base, CPU int8 |
| CPU threads | 1 |
| Processing time | 152seconds |
| Audio chunks | 25, all processed |
| Transcribed word count | 2,139 |
| Word error rate | 1.82% |

Word error rate counts substitutions, deletions and insertions relative to the script, after lowercasing and removing punctuation. It is not a guarantee of accuracy in a noisy classroom. Input was clear synthetic English spoken with Edge's Emma voice. Different speakers, accents, distant microphones, simultaneous speech and equations require additional evaluation.

The full raw audio, timestamped transcript and detailed measurements were retained locally by the developer. No private meeting audio was used or published. The repository includes `tools/benchmark_classroom.py` to repeat the same pipeline on any explicitly supplied audio/reference pair. Install `jiwer` in the development environment first. It never opens a live capture device.

Local notes generation was tested through a loopback mock server and injected local responses, including long-transcript section coverage and retry caching. Actual local notes-model quality and live microphone/loopback hardware tests remain pending. Both Parakeet and Whisper have now been tested on the prerecorded lecture; the older detailed table above records the original Whisper run.
