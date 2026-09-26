# Compact batch workspace implementation plan

Approved specification: DESIGN-v2.md; owner authorized implementation on 2026-08-30.

## Responsibilities and boundaries

- templates/editor.html: self-contained offline/enhanced UI, embedded pure WorkflowCore functions, compact stage panels, folder pagination, per-video state, paragraph/cue editing, annotation proposals, guide/menu and private work-copy export/import.
- templates/tests/batch.test.cjs: execute pure embedded core in Node VM; natural ordering, duplicate basename isolation, pagination bounds, finite SRT times, exact split limits, no text loss, annotations and proposal validation.
- templates/tests/editor.test.cjs: preserve catalog and fitted-caption contracts; update retired single-video UI contracts only for approved replacements.
- system/pipeline/workspace.py: locally probe a selected clip, fully transcribe via existing Groq gate, render its reviewed cues without edits, and validate explicit text-only AI proposals.
- system/pipeline/transcription.py: bounded sequential audio chunks cover entire source, shifted timestamps, progress callbacks, no successful partial transcript.
- system/app.py: token-gated asynchronous analyze/render/assistant endpoints, request validation, resource allowlist, no private content logging and safe job failures; preserve existing legacy routes.
- system/tests/test_workspace.py: mocked external API and synthetic independent jobs, privacy gates, finite times, rejected malformed/duplicate proposals, and full transcription coverage.
- README.md and root AGENTS.md: active behavior and privacy boundaries; retain old design/plan/catalog baselines.

## Sequence and checkpoints

1. Write new core and server tests; run node --test templates/tests/batch.test.cjs and python3 -m unittest system.tests.test_workspace -v; confirm failures target missing behavior.
2. Implement testable model + controller services; repeat focused checks until green.
3. Replace the old long-page view with real stage tabs, folder and cue pagination, compact video preview and modal actions; ensure per-clip state survives tab and page switching.
4. Add external operations behind action-specific consent and review/apply/undo; mock networking in all automated tests; preserve original text on failed or rejected proposals.
5. Run python3 -m unittest discover -s system/tests -v, node --test templates/tests/*.test.cjs, python3 -m compileall -q system, zsh -n 'AI Video Workflow v1.command', and git diff --check.
6. Use the in-app browser at desktop and narrow widths; verify menu/guide, tabs, multi-file selection, individual SRT matching, pagination, range edits, annotations and separate synthetic outputs; never upload private media to an external service.
7. Inspect only eligible source filenames and ignore rules, keep existing private/generated/trash content untouched, and report live-network verification limits accurately.

## First owner trial corrections — authorized in conversation

Scope: repair the five reported issues without changing catalog versions, deleting original files, inspecting owner media, reading credential files, installing packages or calling external AI. Keep the existing compact panels and shallow layout.

1. `templates/editor.html` / `templates/tests/batch.test.cjs`: test then implement a real central folder button; mixed JPG/JPEG/PNG and video records; photo duration (existing 5-second baseline, editable 0.1–3600 seconds); manual cue insertion into a validated free time interval; removal and one-step restoration of a complete media record, including its captions and order. Work-copy v2 retains photo durations, supports existing v1 copies and can restore a subset after removals.
2. `system/pipeline/workspace.py`, `system/app.py`, `system/tests/test_workspace.py`: reproduce missing-key failure with a synthetic environment, expose only readiness booleans and safe Chinese instructions through a token-protected capabilities endpoint, stop before importing a whole batch when unavailable; mock successful analysis. Render a photo as a duration-controlled silent video before applying existing captions; allow caption-free photos, never concatenate items or pass photos to speech recognition.
3. UI integration: image preview with its own local timeline, photo duration validation, manual-add dialog, per-item failure details, restoration button, batch recognition skips photos, no-key guidance retains SRT/manual workflows. Tell users unsupported image formats are skipped rather than silently ignoring them. Do not claim burned-in captions are editable SRT.
4. Run `node --test templates/tests/*.test.cjs`, `python3 -m unittest discover -s system/tests -q`, syntax and whitespace checks. Use only generated fixtures in a temporary root for actual browser upload/add/remove/restore/photo-duration and independent photo/video render verification. Update README and root AGENTS, reporting missing real AI credentials as an unresolved external dependency, not a completed recognition fix.

### Trial correction verification

- Initial RED: four new frontend tests reproduced absent central action, rejected photos, missing manual insertion and missing reversible removal. Backend test failed on absent readiness API. Implemented then verified GREEN; added legacy-v1 work-copy compatibility coverage.
- Current regression: 23 Node tests and 80 Python tests pass. Existing subtitle catalog/renderer baselines remain unchanged. Inline JavaScript syntax, Python compilation, launcher syntax and whitespace checks pass.
- Browser: central plus opened a real folder chooser; imported two generated photos and one generated video. Missing-key preflight showed clear instructions without creating failed jobs. Added captions to a photo and video without transcription; rejected a deliberate overlap. Removed/restored a photo with its caption and note intact. Explicit Apply was added after testing exposed unclear duration commit behavior; verified 3-second setting in preview and output. Narrow 390×844 viewport had no document overflow, and browser warning/error logs were empty.
- Actual output: captioned JPG became a 3-second 640×360 MP4, uncaptained PNG became a 5-second 360×640 MP4, and the 4-second 640×360 source video retained its 4-second audio. Examined the photo output frame to verify fitted S01 black background. All fixtures/outputs lived outside the repository in a temporary test root; the test server deliberately excluded GROQ_API_KEY.
- Unresolved external dependency: real automatic transcription still requires the owner-provided launcher environment key and explicit destination consent. No real provider/account calls, credential-file inspection or private-owner-media processing occurred. HEIC and other unimplemented image formats are disclosed as unsupported, not silently treated as successfully imported.

## Previous verification record — before first owner trial

- RED: the initial core/controller tests failed for absent batch behavior. Additional regression tests reproduced work-copy stale renders, hidden metadata entries, nonfinite/extreme timestamps and missing long-caption preview segmentation before correction.
- GREEN: 18 Node tests and 78 Python tests passed; compileall, launcher syntax and git diff whitespace checks passed. HTTP tests rejected all three new endpoints without a token; mocked AI tests verified exact scoped payload and incomplete-response rejection. Full-length audio tests cover three windows, silent windows, time offsets and all-or-nothing failure.
- Browser: imported eight synthetic clips from a directory, including duplicate basenames in separate subfolders and matching SRT; verified natural ordering, manual move/undo, input/output pagination, per-video subtitle isolation, cue pages, range resegmentation/undo, menu guide, maturity tabs and an unchecked AI-consent rejection. Desktop 1280×720 and narrow 390×844 had no outer document overflow; browser error/warning logs were empty.
- Render: two synthetic 6-second clips (640×360 and 360×640) produced independent MP4/SRT results with matching 6-second video/audio durations. Inspected extracted frames to confirm S01 fitted-line black backgrounds. Repeated with latest UI, an edited overlong cue and a portrait clip not previously opened; both rendered successfully with separate output states.
- Privacy: test media and generated results stayed in a temporary root outside this repository. No owner project/media, secret files or real external AI service were inspected/called. Private work-copy and generic draft ignore checks passed at all applicable layers; outer repository still ignores this nested repository. No files were staged or committed.
- Limits: real Groq recognition/correction quality and provider account setup remain unverified. Filename sorting does not analyze video contents. Direct-file offline behavior has source/unit coverage; browser interaction testing used the loopback enhanced controller.
