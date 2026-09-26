# AI Video Workflow v1 — Compact Template Program Design

Date: 2026-08-29  
Status: Approved by owner

## Outcome

AI Video Workflow v1 keeps the owner-facing path `1 Input → 2 Process → 3 Output` and presents reusable subtitle templates through one directly openable program instead of requiring the owner to understand the backend files.

## Owner-facing structure

```text
ai-video-workflow/
├── 1_input/
├── 2_processing/
├── 3_output/
├── templates/
├── system/
├── AI Video Workflow v1.command
└── README.md
```

Repository privacy controls remain in hidden files, and retired material remains recoverable under the repository-level `_trash/` rather than being permanently deleted.

## One program, two operating levels

- Opening `templates/editor.html` directly provides the basic offline level: choose a local video for browser-only preview, paste text or load SRT, segment captions, compare templates, and edit cues; it does not copy media, invoke local executables, or use the network.
- Double-clicking `AI Video Workflow v1.command` provides the enhanced local level through the same interface: import the selected video into `1_input/<project_id>/`, save the reviewed SRT, invoke the existing local pipeline in `2_processing/`, show progress, and open `3_output/<project_id>/`.
- Both levels use local assets only and make no background network requests.
- Automatic external transcription remains gated per operation: it runs only after an explicit UI approval for that video and only when `AI_VIDEO_ALLOW_NETWORK=1` and `GROQ_API_KEY` are already present in the launcher process; no credential is stored, displayed, logged, or read from `.env`.

## Template interface

The first tab is `Mature / 已成熟`; the second tab is `Testing / 測試中`. Status is a field in one `templates/catalog.json`, not a directory name. Only the owner can promote a template to `mature`; the program and AI may not infer maturity.

Initial catalog entries preserve the existing first versions:

| ID | Name | Initial status | Preserved behavior |
| --- | --- | --- | --- |
| S01 | 貼字黑底 | testing | White text with a fitted black background |
| S02 | 清晰描邊 | testing | White text with a dark outline and transparent background |
| S03 | 乾淨重擊 | testing | Existing `clean-impact` preview vocabulary |
| S04 | 關鍵字跳出 | testing | Existing `keyword-punch` preview vocabulary |
| S05 | 黃字裂開補白 | testing | Existing `split-reveal` preview vocabulary |

Every revision receives a new numeric version and retains its earlier version. A new version must pass the same caption fixtures as its baseline before it can be shown as a viable Testing revision.

## Subtitle contract

- Caption segmentation uses punctuation, meaning-preserving clause boundaries, whitespace, and speech timing; it must not split a name, number-unit pair, Latin word, or protected token when a safer boundary exists.
- Portrait video defaults to at most 10 Chinese characters per line; landscape video defaults to at most 16; captions use at most two lines, and overflow becomes the next cue instead of silently shrinking the type.
- Imported or transcribed cues are resegmented and their original time interval is divided proportionally without overlaps, reversals, or dropped text.
- The preview shows the selected video, current caption, cue timing, cue list, and Input–Process–Output progress; each cue's text, start, and end can be reviewed before rendering.
- The S01 black background is measured and drawn from the exact glyph layout in the same rendering pass, with a small padding behind each displayed line; it never becomes a full-width band and cannot use geometry measured by a different renderer.
- Transitions remain an AI editing decision and are outside this subtitle-focused first implementation.

## Safety and failure behavior

- The controller binds only to `127.0.0.1`, serves an allowlisted application surface, validates project IDs and template IDs, rejects path traversal, and writes owner media only under the ignored `1_input/` tree.
- Processing state and output remain ignored under `2_processing/` and `3_output/`.
- Upload, subtitle generation, and processing errors remain visible in the current stage; a failed Process action must not be presented as Output success.
- Existing owner media, processing state, rendered output, and generated gallery media are not inspected, staged, committed, or moved during repository cleanup.
- Existing `template-gallery/` generated media remains untouched; its subtitle vocabulary is surfaced in the consolidated program without reading or relocating generated files.

## Verification

Source contracts test both standalone and enhanced modes, Mature/Testing routing, caption segmentation, catalog validation, privacy gates, fitted-background geometry, and the three-stage progress model. Browser verification checks the actual local interface at desktop and narrow widths using synthetic text and synthetic or owner-independent media only.
