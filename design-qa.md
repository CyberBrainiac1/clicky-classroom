# Native dashboard visual and interaction check

Reference: user-supplied OpenWhispr Notes screenshot, October 31, 2026. This is a native PyQt desktop implementation, not a web prototype.

Compared the reference with rendered screenshots of the changed widgets at 1440×900 and 1000×700; also rendered 1920×1080. The three major regions, compact top bar, large note heading, muted metadata, restrained blue selection, transcript blocks and segmented tabs follow the reference. The design uses authored sample text and explicitly labels preview mode.

The navigation, title, metadata, recording controls and note content fit the small viewport without horizontal overflow. Long transcripts scroll inside their reading pane. Fixed widths keep navigation stable. Icons are shipped locally. A sample equation used an unsupported Unicode subscript character; replaced it with ordinary readable notation in the preview fixture.

The screenshot's team spaces, sharing, speaker labeling and promotion controls are outside Clicky's implemented feature set and are not presented as working features. Clicky tools and its normal assistant remain reachable. The notes editor uses editable plain text/Markdown; it is not a full rich-text editor. These are stated scope differences.

Automated checks cover all six navigation routes, no capture on page opening, title/transcript search, opening a filtered result, unsaved-edit protection, persisted notes on reopen/close, processing-state protection and escaping transcript text. Final full suite: 103 passed, including import completion. The packaged executable also rendered all six pages and transcribed the full 2,142-word prerecorded fixture. Model comparison is recorded separately in BENCHMARK.md.

Native visual/interaction result: passed for the implemented scope. Live microphone, computer-audio capture and real notes-model output were not tested during the user's recording.
