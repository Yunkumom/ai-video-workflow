# AI Video Workflow v1 — Implementation Plan

Date: 2026-08-29  
Approved design: `templates/DESIGN.md`

## Constraints

- Writable scope is this repository only.
- Do not read `.env`, credentials, sessions, voice samples, owner media, existing `1_input/`, `2_processing/`, `3_output/`, `template-gallery/generated/`, `_pending/`, or `_trash/` contents.
- Do not install packages, publish, push, add remotes, or enable network transcription during implementation or verification.
- Use only macOS `python3`, `ffmpeg`, `ffprobe`, `swift`, the existing Node runtime, and standard-library modules.
- Preserve the dirty working tree and move only the exact owner-approved retired paths to a new recoverable repository-level trash folder.

## File responsibilities

- `templates/editor.html`: the single standalone and enhanced owner interface, Mature/Testing tabs, video preview, cue editor, and three-stage progress.
- `templates/catalog.json`: validated names, versions, maturity states, and production-safe generic subtitle style parameters; no sample text, media, or private paths.
- `templates/tests/editor.test.cjs`: isolated offline-interface contracts and catalog-to-tab behavior.
- `system/pipeline/subtitle_templates.py`: catalog validation, orientation-aware caption segmentation, cue resegmentation, and renderer style selection.
- `system/app.py`: loopback-only static server and validated APIs for import, subtitle save/transcription gate, processing, status, and opening output.
- `AI Video Workflow v1.command`: executable local launcher for the enhanced interface.
- `system/pipeline/cli.py`, `planning.py`, and `render.py`: apply reviewed template IDs, resegment captions, and pass one authoritative style into production rendering.
- `system/pipeline/caption_images.swift`: draw text and its fitted per-line background from the same measured layout.
- `system/config/defaults.json`: approved 10/16-character and two-line defaults plus default template ID.
- `system/tests/test_subtitle_templates.py`: deterministic segmentation, catalog, timing, and style tests.
- `system/tests/test_app.py`: loopback, allowlist, path, import, processing-gate, and state-transition tests using temporary synthetic files only.
- `system/tests/test_structure.py`: the compact owner-facing structure and launcher contracts.
- Repository-root `AGENTS.md`, `.gitignore`, and `README.md`: consolidated governance, ignore protection, and the new single-workflow entry.
- `ai-video-workflow/README.md` and `.gitignore`: concise owner instructions and an independent workflow privacy boundary.

## Task 1 — Establish RED tests for the template catalog and segmentation

1. Add `system/tests/test_subtitle_templates.py` expecting S01–S05, unique IDs, numeric versions, `testing|mature` status, no private fields, portrait limit 10, landscape limit 16, maximum two lines, protected-token handling, text preservation, and monotonic proportional cue timing.
2. Extend `templates/tests/editor.test.cjs` to require Mature first, Testing second, empty-mature messaging, catalog-backed S01–S05 cards, local video preview, transcript/SRT inputs, editable cue timing, stage indicators, standalone restrictions, and fitted S01 markup.
3. Run `python3 -m unittest system.tests.test_subtitle_templates -v` and `node --test templates/tests/editor.test.cjs`; both must fail for missing contracts.

Evidence checkpoint: failures name the missing catalog/module/interface rather than environment or private data.

## Task 2 — Implement the catalog, segmentation, and standalone interface

1. Add `templates/catalog.json` and `system/pipeline/subtitle_templates.py` with strict schema and field validation.
2. Consolidate the existing offline editor into `templates/editor.html`, preserving the original S01/S02 settings and S03–S05 vocabulary while adding the two maturity tabs, local video preview, transcript/SRT loading, cue editing, and orientation-aware segmentation.
3. Keep the standalone content-security policy network-free and do not persist sample text or media paths in exported settings.
4. Run the Task 1 tests until GREEN, then refactor only with tests remaining green.

Evidence checkpoint: all catalog and offline-interface tests pass and the HTML contains no remote dependency or controller requirement for basic preview.

## Task 3 — Establish RED tests for production caption geometry and local control

1. Add fitted-background source tests that reject full-width S01 bands and require the same measured line rectangles for text and background.
2. Add `system/tests/test_app.py` for loopback binding, static allowlisting, project/template validation, traversal rejection, bounded upload metadata, per-operation transcription approval, asynchronous stage state, and output-open gating.
3. Update `system/tests/test_structure.py` to expect `AI Video Workflow v1.command` and no owner-facing `run-video`, `index.md`, `guide.html`, `CONTEXT.md`, `HANDOFF.md`, duplicate AGENTS files, or active `docs/` folder.
4. Run the new tests and record expected RED failures before implementation.

Evidence checkpoint: every failure maps to an approved interface or cleanup rule.

## Task 4 — Implement enhanced Input → Process → Output and fitted rendering

1. Add `system/app.py` and `AI Video Workflow v1.command`; bind to `127.0.0.1` on an ephemeral port, generate a per-launch token, serve only the consolidated application, and never log request bodies, captions, paths, or credentials.
2. Implement validated media import into a new `1_input/<project_id>/`, reviewed SRT save, controller status, pipeline invocation without shell interpolation, and opening only the matching `3_output/<project_id>/` after success.
3. Keep external transcription disabled unless the request contains explicit per-operation approval and the existing process environment satisfies the current Groq gate.
4. Update the pipeline to apply the selected template, orientation limits, and resegmented timing.
5. Rewrite the Swift S01 renderer so each line's background rectangle and text share one measurement and placement calculation.
6. Run Task 3 tests until GREEN and then run all focused template, app, planning, render, and structure tests.

Evidence checkpoint: synthetic API tests reach Input, Process, and Output states without inspecting real projects, and renderer tests prove fitted rather than full-width backgrounds.

## Task 5 — Consolidate folders and governance recoverably

1. Merge the repository-root `templates/` source, tests, version history, and retained template specifications into `ai-video-workflow/templates/` without reading generated media or drafts.
2. After their behavior is represented in the new interface and root governance, move these exact retired paths to a new repository-level `_trash/2026-08-29-ai-video-workflow-v1-cleanup/`: `ai-video-workflow/AGENTS (1).md`, `ai-video-workflow/AGENTS.md`, `ai-video-workflow/CONTEXT.md`, `ai-video-workflow/HANDOFF.md`, `ai-video-workflow/docs/`, `ai-video-workflow/guide.html`, `ai-video-workflow/index.md`, `ai-video-workflow/requirements.txt`, `ai-video-workflow/run-video`, and inactive `ai-video-workflow/system/legacy/`.
3. Do not move, read, or delete `ai-video-workflow/template-gallery/generated/`; retain `template-gallery/` as the untouched compatibility source while surfacing its named subtitle vocabulary in the new interface.
4. Consolidate necessary child privacy and behavior rules into root `AGENTS.md`, update both ignore layers, and simplify both README files.

Evidence checkpoint: every retired tracked path is recoverable under the exact trash folder, the active workflow has the approved compact entry points, and no private/generated path enters Git eligibility.

## Task 6 — Full verification

Run:

```bash
node --test ai-video-workflow/templates/tests/editor.test.cjs
cd ai-video-workflow && python3 -m unittest discover -s system/tests -v
cd ai-video-workflow && python3 -m compileall -q system
zsh -n 'ai-video-workflow/AI Video Workflow v1.command'
git status --short
git ls-files
git check-ignore -v ai-video-workflow/1_input/private/example.mp4 ai-video-workflow/2_processing/private/state.json ai-video-workflow/3_output/private/final.mp4 private.template-draft.json
```

Use the in-app browser against the local loopback controller to verify both tabs, a synthetic video preview if one can be generated without owner media, caption edits, S01 fitted backgrounds, stage changes, responsive layout, and visible error states. Do not authorize or perform external transcription.

Final evidence checkpoint: all tests pass, the browser surface matches the approved flow, ignored private paths remain ignored, no secret-like or media filename is tracked, no existing private/generated media was read or moved, and no completion claim is made without fresh verification.
