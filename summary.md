# Clicky dashboard and class notes — development summary

New import update: Clicky can copy existing local OpenWhispr notes into its Notes library. It keeps personal notes, saved summaries, transcripts, folders, dates and original source fields. The source database is opened read-only; deleted/unavailable notes, audio, credentials and sharing tokens are excluded. Importing again keeps existing Clicky edits and does not duplicate notes. This is an import, not automatic two-way synchronization.

Normal startup opens Notes, while `--tray-only` keeps background startup available. The suite now passes **118 tests**, including importing a live WAL database, preserving every same-time segment, protecting user edits, streaming errors and memory release before note generation. A real small local-model test completed in about 27 seconds and unloaded afterward. It is a draft generator: the test showed that timestamps and extra numerical facts still need checking. Imported saved summaries are copied exactly rather than regenerated.

October 31 update: the Notes screen now follows the OpenWhispr screenshot you chose. A slim navigation bar and saved-note list sit beside a large transcript and notebook. Search finds words in titles, transcripts and saved notes. Device/model options are in Recording settings; import, recovery and generation are in More. You can write a text-only note without recording. Unsaved edits are protected when changing notes and saved before a normal close or quit. The full automated suite passed **103 tests**; previews used made-up physics lesson text, not your meeting.

Two other speech models were tested on the same 2,142-word recording. Parakeet V3 made 0.84% word errors, Unified English 1.07%, and Orukeet 1.96%. All finished all 25 sections. They have almost the same file size, but neither improved this test, so Parakeet V3 stays the default. A clean synthetic lecture cannot tell us which model wins in every real classroom. BENCHMARK.md has sources and details.

For the separate Claude question: making a Console agent does not automatically upgrade Clicky's computer control. The code still needs to connect to it. Anthropic currently documents its built-in computer-use tool as Messages API only, unavailable in Managed Agents. The current direct integration should be checked and improved separately; this UI work does not change that API or send notes to a cloud agent.

Latest update: **Parakeet TDT0.6Bv3INT8 is now the Classroom default**, with a regular Clicky talk/dictation adapter too. It uses Clicky's own model cache, separate from the running OpenWhispr service. The same2,142-word/12m21s prerecorded lecture was fully transcribed in135seconds on one CPU thread, with0.84%word error rate. All25chunks completed. The updated automated suite passed98tests. Whisper remains available and its original benchmark is retained below. No installed app or current recording was restarted or changed.

The original Clicky assistant is still here. Its cursor guidance, talk shortcut, typed chat, speech, drawing, document context, reviewed computer actions, Work/routines, connections, journal and existing screen lesson recorder were preserved. The dashboard and Classroom are additions.

The native dashboard collects those controls into Home, Chat, Notes, Library, Tools and Settings. The Notes page follows the user's OpenWhispr screenshot: private notes on the left, a large reading area, search and compact recording controls. It uses dark neutrals, Clicky's blue accent, Segoe UI, and consistent spacing. Recording/model controls are in a separate dialog. The user-requested design-dashboards skill informed the design; DASHBOARD-SPEC.md explains the decisions.

Classroom can record a teacher through the microphone or an online class through Windows computer audio. It saves audio first, with checkpoints, so a failed transcription model does not erase a class. Whisper runs locally on the CPU. A second adapter supports Parakeet through sherpa-onnx using OpenWhispr's model-file convention. OpenWhispr's silence and pause-splitting code was adapted with its MIT license and attribution.

Notes use a local Ollama or local llama.cpp/LM Studio server. They are based on timestamped transcript sections and request definitions, examples, equations, assignments and review questions only when supported by the recording. Important numbers and equations still need checking. A missing local notes server leaves the transcript/audio saved for retry.

A real transcription test processed2,142words of clean prerecorded speech,12minutes21seconds long. All25sections completed. Local Whisper base/int8 used one CPU thread and took152seconds, with1.82%word error rate compared with the script. This does not predict the same accuracy in a noisy classroom. No private meeting audio was used.

Automated tests cover the original Clicky features, the new UI/action routing, no-recording-on-open behavior, local-only notes requests, audio recovery and failure paths. Tests render offscreen and do not touch live audio devices. See BENCHMARK.md and CLASSROOM.md for validation details and remaining tests.

This work is in a separate fork/branch. The installed Clicky and OpenWhispr apps were not replaced or restarted during this development. No new live recording was started. The full portable executable passed its packaged check: all six dashboard pages, local icons, Sketch and speech dependencies. The actual executable also transcribed the entire 2,142-word audio, completing 25/25 sections with 0.84% word errors on one CPU thread. It did not open live capture or start normal assistant services during the test. Live microphone/loopback hardware and real local notes-model quality still need post-meeting validation. The portable app can run without replacing the installed app; an installer is not required.


## Real mouse controls — October 31

The blue guide and the real Windows mouse are separate. Added a move-only Drive action, accepted move/hover requests, fixed same-request locator fallback and matched Claude tools to selected models. Visible CAD parts can be targets. Requests typed into the dashboard reveal the saved target app first. Approval, Escape stop and existing privacy/freshness checks remain. 148 tests and the packaged application check passed using fake inputs. Claude generated valid move and click plans on an authored test image, without executing them. Installed update and preserved configuration/notes; user still needs to test real interaction in their app. Voice delay was explained, not optimized. These updates are preserved on the classroom-local-notes branch.


## GitHub retention and local removal

The user requested uninstalling Clicky from their laptop and keeping the project on GitHub. Preserve the latest source on the classroom-local-notes branch before removing the local checkout, installed application and packaged copies. Keep personal saved notes and recordings out of GitHub.
