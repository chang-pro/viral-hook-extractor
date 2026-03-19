# Research Notes

This file summarizes the external research used to shape the current version of the project.

## What Opus Clip does well

Official Opus pages and docs show a broader workflow than just "find clips from transcript":

1. AI clipping plus a full editor.
2. Dynamic or animated captions.
3. AI reframe for `9:16`, `16:9`, and `1:1`.
4. AI B-roll insertion.
5. Transcript-first editing after the AI draft.
6. Upload-your-own SRT support.

Relevant sources:

1. `https://www.opus.pro/`
2. `https://www.opus.pro/ai-b-roll`
3. `https://help.opus.pro/docs/article/upload-own-srt`
4. `https://help.opus.pro/docs/article/change-captions`
5. `https://help.opus.pro/docs/article/9442115-trim-the-clip-or-add-new-sections-from-original-video`
6. `https://help.opus.pro/docs/article/download-transcripts-subtitles`

## What that means for this repo

To be a credible Opus replacement, the local tool needs more than clip scoring:

1. Better caption workflow.
2. Better transcript correction path.
3. Better thumbnail workflow.
4. Better post-selection editing options.

That is why this pass added:

1. ASS caption generation.
2. External SRT input with clip-local slicing.
3. Thumbnail export from the selected `thumbnail_time`.
4. Multi-factor virality scoring in the Gemini prompt.

## Best open-source subtitle stack

The strongest open-source path for better subtitle timing is still:

1. `WhisperX` for alignment and diarization.
2. `faster-whisper` for fast transcription.
3. `pyannote-audio` for speaker labeling when needed.

Relevant sources:

1. `https://github.com/m-bain/whisperx`
2. `https://github.com/SYSTRAN/faster-whisper`
3. `https://github.com/pyannote/pyannote-audio`

Why they matter:

1. WhisperX explicitly targets word-level timestamps and diarization.
2. faster-whisper exposes `word_timestamps=True` and is efficient enough for local workflows.
3. pyannote gives speaker-aware splits if clips contain multiple speakers.

## Reddit signal

Reddit feedback is noisy, but a few themes repeat:

1. Users like the speed of all-in-one tools.
2. Users still clean up hook choices manually.
3. Captions, crop/framing, and export reliability are common complaints.
4. Accent-heavy or style-specific content breaks generic workflows faster.

Relevant discussions:

1. `https://www.reddit.com/r/VideoEditing/comments/1r8o7po/opusclip/`
2. `https://www.reddit.com/r/NewTubers/comments/1izmp9c/do_tools_like_opus_clips_work_anymore/`
3. `https://www.reddit.com/r/opusclip/comments/1r9evwp/what_services_are_having_issues_currently/`
4. `https://www.reddit.com/r/opusclip/comments/1ribs6n/issues_with_playback/`

## Practical takeaway

The strongest version of this project is not "copy Opus exactly."

It is:

1. Use Gemini video understanding to rank likely hooks.
2. Use better caption sources when the dialect matters.
3. Keep every decision inspectable through `hooks.json`.
4. Make the last mile editable instead of pretending AI gets it perfect.

## Next technical step

The next serious upgrade should be an optional local transcription pipeline:

1. Extract audio with FFmpeg.
2. Transcribe with `faster-whisper`.
3. Align with `WhisperX`.
4. Use that output for captions and optionally for transcript-aware clip cleanup.

That will improve caption quality far more than adding more prompt text alone.
