# Long-audio transcription validation

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

Local notes generation was tested through a loopback mock server and injected local responses, including long-transcript section coverage and retry caching. An actual local notes-model quality evaluation and live microphone/loopback hardware test remain pending. The Parakeet adapter's configuration/API was checked; this benchmark measures Whisper only.
