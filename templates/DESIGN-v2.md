# Compact batch workspace — approved design

Date: 2026-08-30
Owner approval: after discussion, begin implementation with compact paginated views.

- Keep the program name AI Video Workflow v1; put it in a compact top bar with real Input / Process / Output tabs and a right-hand hamburger menu.
- Hide instructional prose in a modal GUI Guide; retain Mature first and Testing second inside the template chooser, with no large empty-state block.
- Input accepts a folder, discovers supported videos and matching relative-path SRT sidecars, naturally orders filenames, and permits manual reordering; paginate large lists rather than extending the document.
- Every video owns a stable ID, its own cues, annotations, selected template, analysis progress and versioned outputs; never concatenate a batch.
- Process shows one selected video with a previous/next selector and a paginated subtitle workspace; long videos are fully transcribed sequentially, not sampled.
- Reading paragraphs group cues without changing source time; custom range resegmentation can request sentence and paragraph counts, and must reject impossible limits without dropping text; estimated retiming is labeled for review.
- AI ordering and annotated text correction produce reviewable proposals, never silently mutate the originals; use the existing Groq provider only after explicit action-specific consent naming the destination and data, never inspect credentials during development.
- Output lists each video's result separately; render reviewed subtitles without automatically cutting or combining the source timeline.
- Keep all code in existing templates/ and system/ areas; generated media and work state remain ignored; no new maturity folders, no removal of existing files, no catalog/style revision in this UI release.
- Browser-only mode supports folder preview, SRT/transcript editing and local SRT/working-copy export; server mode adds imported-media analysis, AI proposals and rendering; work-copy export is distinct from a generic template draft and is explicitly private.
- Verify only synthetic media and mocked external APIs, no owner media, accounts, secrets, publication or package installation.
