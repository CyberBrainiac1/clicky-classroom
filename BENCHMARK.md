# Long-audio transcription validation

## Packaged executable verification

The full Windows `Clicky.exe` also processed the entire 2,142-word / 741.36-second fixture through the same 25-chunk pipeline: 2,137 output words, 0.84% word error rate, all chunks completed, one CPU inference thread at BelowNormal priority. The packaged check rendered all six dashboard pages and loaded the bundled SVG icons, Sketch and speech dependencies. It used isolated test data and the explicit prerecorded fixture; no live devices or normal assistant services started. This validates the packaged speech runtime as well as source execution. It does not validate live audio hardware or real study-note model quality.

## Same-size alternatives checked October 31

Tested two additional compatible INT8 transducers on the same 2,142-word / 741.36-second synthetic English lecture, same 25-chunk file pipeline, CPU only, one inference thread, BelowNormal priority. No live devices or private recordings were used.

| Model | Required model files | Word error rate | Processing time | Completed |
|---|---:|---:|---:|---:|
| Parakeet TDT 0.6B V3 | 670,478,772 bytes | **0.84%** | 135 s, prior baseline run | 25/25 |
| Parakeet Unified EN 0.6B | 663,043,117 bytes | 1.07% | 111 s | 25/25 |
| Orukeet v0.1.0 INT8 | 671,476,984 bytes | 1.96% | 100 s | 25/25 |

Keep Parakeet V3 as the default: neither alternative improved accuracy on this fixture. These are single runs on a working laptop. Times are not a controlled speed ranking, and the baseline was measured earlier. This clean synthetic lecture cannot establish a winner for distant microphones, noisy rooms or overlapping speakers.

Published results helped select candidates, rather than deciding the winner for this laptop. [NVIDIA's Unified card](https://huggingface.co/nvidia/parakeet-unified-en-0.6b) reports 5.91% offline English WER in its evaluation, compared with 6.04% for TDT V2 in the same table; it is not a direct V3 comparison. [Orukeet's card](https://huggingface.co/oruk/orukeet) reports broad improvements over V3, including English FLEURS. Its LibriSpeech test-other results are not held out: that split was used for final adaptation/checkpoint selection. Its published native-model scores also do not guarantee the same results from quantized ONNX on this particular audio.

Unified was downloaded from the [official sherpa-onnx transducer distribution](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html). Orukeet's pinned archive and every packaged file matched its official SHA256 manifest at revision `55a984d46f68323301837194ce647c702f55facc`. Models were downloaded only into Clicky's own research cache, never into OpenWhispr. Weights are not included in this source repository or the portable app.

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
