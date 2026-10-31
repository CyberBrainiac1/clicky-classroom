# Clicky dashboard and class notes — development summary

The original Clicky assistant is still here. Its cursor guidance, talk shortcut, typed chat, speech, drawing, document context, reviewed computer actions, Work/routines, connections, journal and existing screen lesson recorder were preserved. The dashboard and Classroom are additions.

The native dashboard collects those controls into Overview, Assistant, Classroom, Class library, Tools and Settings. It uses Clicky's existing dark gray colors, blue accent, Segoe UI, and consistent8pixel spacing. Advanced recording/model controls are collapsed so the transcript and notes stay visible. The user-requested design-dashboards skill informed the design; DASHBOARD-SPEC.md explains the decisions.

Classroom can record a teacher through the microphone or an online class through Windows computer audio. It saves audio first, with checkpoints, so a failed transcription model does not erase a class. Whisper runs locally on the CPU. A second adapter supports Parakeet through sherpa-onnx using OpenWhispr's model-file convention. OpenWhispr's silence and pause-splitting code was adapted with its MIT license and attribution.

Notes use a local Ollama or local llama.cpp/LM Studio server. They are based on timestamped transcript sections and request definitions, examples, equations, assignments and review questions only when supported by the recording. Important numbers and equations still need checking. A missing local notes server leaves the transcript/audio saved for retry.

A real transcription test processed2,142words of clean prerecorded speech,12minutes21seconds long. All25sections completed. Local Whisper base/int8 used one CPU thread and took152seconds, with1.82%word error rate compared with the script. This does not predict the same accuracy in a noisy classroom. No private meeting audio was used.

Automated tests cover the original Clicky features, the new UI/action routing, no-recording-on-open behavior, local-only notes requests, audio recovery and failure paths. Tests render offscreen and do not touch live audio devices. See BENCHMARK.md and CLASSROOM.md for validation details and remaining tests.

This work is in a separate fork/branch. The installed Clicky and OpenWhispr apps were not replaced or restarted during this development. No new live recording was started. The active OpenWhispr app and its speech server remained running. Live microphone/loopback hardware, Parakeet accuracy, real local notes-model quality and a packaged installer still need post-meeting validation. The checked-in code, launch/setup scripts and build specifications are ready for that next step.
