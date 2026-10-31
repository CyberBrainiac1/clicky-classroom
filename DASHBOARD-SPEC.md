# Clicky dashboard design

Applies the user-requested dastoyan/design-dashboards skill (project .agents/skills/design-dashboards). This is a native desktop control dashboard, not a marketing page or an analytics scorecard.

## Objective and assumptions

One laptop owner needs to see what Clicky is doing, continue the regular assistant conversation, reach existing tools/settings, record a class, and review saved notes. Use is event-driven while studying or working; status updates once per second. The cursor companion, global shortcuts, floating panel, screen guidance, drawing, Drive reviews, Work/routines, connections, journal, recording and setup controls remain available.

## Structure

### User-selected notes layout (October 31)

The supplied OpenWhispr screenshot supersedes the earlier control-panel presentation. Use a slim dark application sidebar, a second private-notes rail, a top search/new-note bar, and an open transcript/editor workspace. Display labels are Home, Chat, Notes, Library, Tools and Settings; the internal routes remain compatible with the existing Clicky callbacks.

Notes is the main study workspace. Its title/date sit above compact recording controls and Transcript / Your notes / Activity tabs. Saved classes can be searched by title, transcript or notes, and opened from the rail. New note supports recording or a plain text note. Model/device controls live in a separate scrollable native dialog. Recovery, generation, import and folder actions stay in More. Real elapsed time appears only while recording. Source labels identify microphone/system/import; do not invent speaker identity or copy the screenshot's private content.

Edits are retained when switching notes is blocked, saved explicitly, and saved on dashboard close. Transcription refresh does not replace an edited note. Editing is unavailable during processing to avoid racing note generation. No nonfunctional sharing, speaker-label, team-space or subscription controls are included. Existing Clicky controls remain in Tools, Settings and the full tray menu.

Use #111314 for application navigation, #191b1c for the reading surface, #24272a for transcript blocks, restrained blue selection, Segoe UI and locally bundled Lucide outline icons. Use 8px-based spacing. At 1000px width both sidebars fit and transcript text wraps inside the reading pane; wider windows give the transcript more room.

The original overview below remains available under Home; it no longer defines the Notes page's layout.

- Stable left navigation: Overview, Assistant, Classroom, Class library, Tools, Settings.
- Overview: current assistant state, classroom state, model selection (labeled configuration, not verified service health), active errors, and direct next actions. No invented uptime, scores, token counts, trends or charts.
- Assistant: typed questions and actual streamed replies plus a button to show the existing floating companion.
- Classroom: the actual recording/settings/transcript/notes widget, not a promotional placeholder.
- Class library: saved sessions with title/date/status and available transcript/notes. Open a session into Classroom for recovery or generation; export remains in its actual folder.
- Tools: working routes to existing Sketch, Work/routines, connections, API keys, journal, lesson recording, workflow capture, setup, diagnostics, models, voice, shortcuts and full settings.
- Settings: existing native Settings window, preserving its actual controls and persistence; dashboard routes open the relevant existing surface rather than inventing a second settings database.

## Status and action model

Idle/ready is quiet neutral text. Recording/listening is explicit text with a blue accent. Processing shows its actual current phase. Errors use an amber text notice with a specific next action and time. No data shows an empty state and a useful action. Unknown model connection status remains unknown; selecting a model is not a health check. Live errors/activity persist in a capped list, with no automatic dismissal. A data-refresh failure shows a stale label/time instead of silently keeping fresh-looking values. The user owns the action; assignment/escalation/acknowledgement controls are not applicable to a single-person desktop app.

## Visual system

Reuse Clicky's dark neutral palette: window#121216, raised surfaces#1c1c22, border#3c3c4b, primary text#f0f0f5, secondary text#8c8ca0, blue#0078ff. Use Segoe UI. Spacing follows an8pixel grid:8,16,24,32. Page margins24; section gaps24; control height36; navigation rows40. Align labels, values and action columns. Neutral flat surfaces, minimal borders, no gradients or decorative illustrations. Blue indicates current focus/action, not a different meaning on every tile.

Overview should fit a normal laptop window; long transcripts, library rows and settings scroll within their own page. Keyboard focus and selection are visible. Text carries status meaning independently of color. No horizontal overflow at1100×760. Wider layouts distribute space, not extra decorative widgets.

## Preservation and validation

Dashboard controls dispatch existing callbacks. No recording or microphone test occurs on opening or navigating the dashboard. Existing shortcut bindings and app modes are not replaced. A preview mode uses explicit unconnected states and disables live-only controls; it never pretends mock values are live. Validate navigation/action routing, transcript streaming, empty and failed states, native offscreen rendering, existing regression tests, and recorded-audio transcription independently.
