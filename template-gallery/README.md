# SHINE Template Gallery / SHINE 模板展示庫

This independent folder generates synthetic videos that demonstrate SHINE's subtitle and editing vocabulary without using owner media, network assets, narration, or music.
此獨立資料夾會產生純合成影片，用來展示 SHINE 理解的字幕與剪輯語彙，不使用擁有者素材、網路資產、旁白或音樂。

## Generate / 產生

```bash
./template-gallery/generate-gallery --list
./template-gallery/generate-gallery --all
./template-gallery/generate-gallery --template split-reveal
```

The combined explainer is written to `template-gallery/generated/shine-template-gallery_vN.mp4`; individual clips are written to `template-gallery/generated/previews/template-<id>_vN.mp4`. Existing videos are never overwritten.
完整講解片會輸出至 `template-gallery/generated/shine-template-gallery_vN.mp4`；各別短片會輸出至 `template-gallery/generated/previews/template-<id>_vN.mp4`，既有影片永不覆寫。

## Included styles / 內含風格

- Subtitle / 字幕: `clean-impact`, `keyword-punch`, `split-reveal`
- Editing / 剪輯: `flash-cut`, `punch-zoom`, `freeze-hit`

All generated media and intermediate frames stay under `generated/` and are ignored by Git.
所有生成影片與中間畫格都保留在 `generated/`，並由 Git 忽略。
