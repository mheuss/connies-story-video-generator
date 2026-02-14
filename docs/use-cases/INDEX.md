# Use-Case Domains

See [FORMAT.md](FORMAT.md) for how to document use-cases.

| Domain | Description | Code Location |
|--------|-------------|---------------|
| pipeline | Pipeline orchestration, phase management, state tracking | `src/story_video/pipeline/` |
| media | TTS generation, image generation, caption timing | `src/story_video/pipeline/` |
| ffmpeg | Video assembly, filters, transitions, subtitles | `src/story_video/ffmpeg/` |
| story | Story generation across all three input modes | `src/story_video/pipeline/story_writer.py` |
