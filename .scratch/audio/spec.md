Status: ready-for-agent

# Audio server: transcribe and listen

## Problem Statement

The `audio` server is a shell: it declares two purposes (`listen`, `transcribe`) and exposes only `list_models`. An agent that is handed a recording (a meeting, a lecture, a voice memo, a podcast) cannot get anything out of it through mymcps. Two jobs are missing, and they are different:

- **Getting the words out.** The agent wants a transcript, optionally with timestamps, in a given language.
- **Understanding the sound.** The agent wants to ask a question that a transcript cannot answer well (who is speaking, what the tone is, what music or noise is there, what happens around a given moment).

Real recordings run into vendor limits that the agent should not have to know about: Gemini takes 20 MB inline and up to 9.5 hours per prompt through its Files API, OpenAI transcription takes 25 MB per file, and raw recordings are far larger than that. Naive solutions fail in known ways: fixed-length chunks cut words in half, overlapping chunks need fuzzy deduplication and have lost audio silently when one half was rejected, and splitting a recording for a question silently breaks answers that span the split.

## Solution

Two tools on the `audio` server, both fed by one shared preparation step (see ADR 0005 for the reasoning behind every choice here).

- **`transcribe_audio`** returns a transcript. Long recordings are split into chunks at silence, each chunk is transcribed, and segment times are shifted back onto the original recording.
- **`listen_audio`** answers a free-text question about a recording, sending the whole recording in one request. It never splits; when a recording is too long it fails with an error that tells the agent how to proceed on its own.

Both tools first convert the input to mono 16 kHz 32 kbps mp3, which fits most recordings in one request. Both accept a local path or an http(s) URL and an optional `start`/`end` to work on part of a recording. Neither writes files; results come back as text.

## User Stories

1. As an agent, I want `transcribe_audio` to return the transcript of a recording, so that I can read what was said.
2. As an agent, I want to pass a local path or an http(s) URL, so that I do not have to download audio myself.
3. As an agent, I want to pass `start` and `end`, so that I can transcribe or listen to only part of a recording.
4. As an agent, I want times in the output to be relative to the original file even when I passed `start`, so that I can refer back to the real position.
5. As an agent, I want a `timestamps` option that puts `[hh:mm:ss]` before each segment, so that I can point at a place in the recording.
6. As an agent, I want a clear error when I ask for timestamps and the model returns none, so that I do not mistake a plain transcript for a timed one.
7. As an agent, I want a `language` option on `transcribe_audio`, so that I can improve accuracy when I know the language.
8. As an agent, I want `listen_audio` to take a free-text `prompt`, so that I can ask the question I care about.
9. As an agent, I want `listen_audio` to accept the same `start`/`end` and a `timestamps` option, so that answers can cite moments in the recording.
10. As an agent, I want to pick a model per call through a `model` argument, so that I can override the configured model.
11. As an agent, I want a long recording to be transcribed without my doing anything special, so that I do not have to know the vendor's size limit.
12. As an agent, I want a recording to be split only when the compressed file is still over the vendor's size limit, so that ordinary recordings stay one request and keep their context.
13. As an agent, I want chunks cut at silence rather than at fixed offsets, so that words and sentences are not cut in half.
14. As an agent, I want segment times shifted onto the original recording after chunking, so that the transcript reads as one continuous timeline.
15. As an agent, I want a chunk the vendor rejects to be reported with its time range, never silently dropped, so that I know the transcript has a hole.
16. As an agent, I want `listen_audio` never to split the recording, so that answers that span the whole recording are not silently wrong.
17. As an agent, I want `listen_audio` to upload a recording over Gemini's inline limit through the Files API, so that long recordings up to the vendor's cap still work in one request.
18. As an agent, I want uploaded Gemini files to be deleted after the answer, so that nothing is left on the vendor's side.
19. As an agent, I want a recording longer than the listening limit to fail with an error naming two ways forward (work through it in order with `start`/`end`, carrying notes into each next `prompt`, or transcribe it first), so that I can choose the approach that fits my question.
20. As an agent, I want the recording validated (readable, has an audio stream, within limits) before any paid model call, so that a bad input never costs money.
21. As an agent, I want a bad path, a failed download, an unreadable file or a file with no audio stream to produce a readable error, so that I can fix the input.
22. As an agent, I want an error that names the missing setting when `transcribe_model` or `listen_model` is not configured, so that I know what to ask the user for.
23. As an agent, I want an error that names the configured model when it cannot do the job (a model that does not hear audio for `listen`, or does not transcribe for `transcribe`), so that I can pick another.
24. As a user, I want `transcribe_model` and `listen_model` to be separate settings in the `[audio]` section, so that I can use a cheap dedicated model for transcription and a multimodal model for listening.
25. As a user, I want a missing-ffmpeg error that names the `audio` extra to install, so that I know the fix.
26. As a user, I want temporary files (downloads, compressed audio, chunks) removed after every call, including failed ones, so that nothing piles up on disk.
27. As a user, I want nothing printed to stdout by the server, so that the stdio transport stays intact.
28. As a maintainer, I want the vendor limits (inline size, per-file size, maximum duration) kept in one place, so that a vendor change is a one-line edit.
29. As a maintainer, I want a vendor with a duration limit instead of a size limit left unsupported until manual testing confirms it, so that unverified numbers never ship.
30. As a maintainer, I want the cut-point planning to be a pure function with property-style tests, so that the data-loss edge cases are cheap to test and a later strategy change does not break the tests.
31. As a maintainer, I want an `audio` manual-testing checklist created together with the tools, so that the real-provider behaviour (compression accepted by the vendor, Files API upload and delete, real timestamps) is checked as `docs/agents/manual-testing.md` requires.

## Implementation Decisions

- **Tools**
  - `transcribe_audio(path, start=None, end=None, language=None, timestamps=False, model=None)` returns text.
  - `listen_audio(path, prompt, start=None, end=None, timestamps=False, model=None)` returns text.
  - `start`/`end` accept `hh:mm:ss`, `mm:ss` or seconds; `start` defaults to the beginning and `end` to the end.
  - Neither tool writes files; there is no `output_dir`.
  - Tool signatures use module-level types (annotations are resolved against the module's globals).
- **Purposes** stay as declared in the shell: `transcribe` (needs the transcribing ability) and `listen` (needs the audio-hearing ability); the configured model's abilities are derived from LiteLLM's table, never declared.
- **Shared preparation step** (the one deep module, used by both tools): resolve the input (path or URL, existing input resolver), probe it with ffmpeg and reject anything unreadable or without an audio stream, cut to `start`/`end`, and convert to mono 16 kHz 32 kbps mp3. All of this happens before any model call. The 32 kbps choice replaces an earlier idea of 16 kbps: Gemini's internal 16 Kbps representation is not the same thing as compressing the upload that low.
- **Transcription path**
  - If the compressed file fits the vendor's size limit, send it as one request.
  - Otherwise plan chunks: use ffmpeg `silencedetect` to find silence, then cut at the silence nearest each target length; if no silence is near, cut at the target length. No chunk exceeds the vendor limit, chunks tile the recording with no overlap and no gap, and no chunk has zero length.
  - Shift every segment's time by its chunk's start so the transcript is on the original timeline.
  - A chunk the vendor rejects is reported by time range in the result or error and never dropped silently.
  - OpenAI notes: only `whisper-1` returns timestamps (through the verbose response format), and `whisper-1` and the diarizing model are scheduled for deprecation on 2027-02-26; an error for `timestamps` on a model that returns none is required (story 6).
- **Listening path**
  - Send the whole compressed recording in one request.
  - If it exceeds Gemini's inline limit, upload it through the Files API, ask, then delete the uploaded file, also on failure.
  - If it exceeds the vendor's duration cap (9.5 h for Gemini), fail before calling the model with the error described in story 19.
  - Vendors other than Gemini that hear audio: the same limits table applies; an unknown vendor limit means the recording is sent inline and the vendor's own error is passed through readably.
- **Timestamps**: `timestamps` produces `[hh:mm:ss]` before each segment, relative to the original file. For `listen_audio` the model is instructed to cite times in that form; if none are produced the tool errors (story 6) rather than returning an unmarked answer.
- **LLM client**: `core/llm.py` gains a way to delete an uploaded file (there is only upload today) and keeps being the only module that imports `litellm`. LiteLLM errors are translated into the existing `ToolError` subclasses.
- **ffmpeg**: reuse the existing helpers (`probe`, `cut`, `split`, `compress`, `extract_audio`); add the `silencedetect` call beside them. ffmpeg stays a lazy property so servers that never use it need no `imageio-ffmpeg`; a missing install raises the existing missing-extra error naming `audio`.
- **Cut-point planning** is a pure function: inputs are the total duration, the silence intervals, the target chunk length and the hard maximum; output is the list of chunk start/end times. Detection (running ffmpeg and parsing its output) is separate and is not unit-tested on its own.
- **Limits table**: vendor, inline size limit, per-file size limit, duration cap, in one module. Initial values: Gemini 20 MB inline and 9.5 h through the Files API (about 32 tokens per second of audio); OpenAI transcription 25 MB per file.
- **Cleanup**: every temporary file created during a call is removed in a `finally`, as in the existing input resolver.
- **Docs**: `GLOSSARY.md` (Transcript, Segment, Chunk) and `docs/adr/0005-...` are already written. The README gains the audio tools and settings; `docs/manual-testing/audio.md` is created with the tools (this satisfies the "tool added" rule in the manual-testing convention).

## Testing Decisions

- Good tests check what the agent sees (the tool result or error) and what crossed the boundary to the vendor (which calls were made, with what format and size), not how the code is organised internally.
- **Seam 1: the audio server through the in-memory `mcp.Client`, with `FakeLiteLLM` and the real bundled ffmpeg.**
  - `FakeLiteLLM` is extended to record transcription calls (and their audio payload), file uploads and deletes, and to return configurable segments with times.
  - `make_ctx` is extended so it can build the audio server (configuring `transcribe_model` and `listen_model` unless `sections` is passed).
  - Audio inputs are generated with ffmpeg's lavfi sources (sine tones and silence), in tests marked `ffmpeg` like the existing core tests.
  - Behaviours covered: compressed upload is mono 16 kHz mp3; a short recording is one request; a long recording is split into chunks that end at silence; segment times are shifted correctly; a rejected chunk is reported with its range; validation fails before any model call (no fake calls recorded); `start`/`end` trim and offset times; `timestamps` formatting and the no-timestamps error; the Gemini Files API path uploads, asks and deletes (also when the ask fails); a too-long recording for listening gives the two-ways-forward error; unset purpose and wrong-ability model give readable errors; temporary files are gone afterwards; a missing ffmpeg gives the message naming `audio`.
- **Seam 2: the cut-point planner as a pure function.** It is tested directly with plain numbers, parametrised, and asserts properties rather than exact values: every chunk is within the maximum; chunks are contiguous and cover the whole recording; cut points strictly increase and no chunk has zero length; a cut falls inside a silence interval whenever one lies within the allowed window, otherwise at the target length. Boundary cases: no silence at all, silence at the very start or end, a silence longer than a chunk, total length equal to, just under and just over the limit, many dense silences. One or two concrete examples pin the "nearest silence" rule itself. These tests need no ffmpeg.
- Not tested automatically: real vendor acceptance of the compressed format, the real Files API, real timestamps (manual-testing checklist), and `silencedetect` output parsing on its own (covered by seam 1 with real audio).
- Two existing guarantees stay true: importing the servers does not load `litellm`, and a real `litellm` import writes nothing to stdout.
- Prior art: `tests/image/test_server.py` (in-memory client), `tests/core/test_ffmpeg.py` (real ffmpeg, `ffmpeg` marker, lavfi sources), `tests/conftest.py` (`FakeLiteLLM`, `make_ctx`).

## Out of Scope

- Splitting for `listen_audio`, in any form (map-reduce, accumulate, overlap); the agent does this itself with `start`/`end`.
- Writing audio or transcript files; speaker diarization; translation; text-to-speech; audio generation or editing.
- Vendors whose limit is a duration rather than a size, until manual testing confirms the numbers.
- Streaming or realtime audio.
- Video: extracting audio from video files is the `video` server's concern.
- Overlapping chunks and deduplication.

## Further Notes

- The design was settled in a grilling session; the decisions and the rejected options are recorded in ADR 0005 (fixed-length chunks, overlapping chunks, always-split-then-compress, map-reduce, accumulate, transcribe-then-answer).
- `gemini/gemini-3.5-transcribe` already exists in LiteLLM's table, so a dedicated Gemini transcription model is a valid `transcribe_model`.
- The existing docs check requires a record to list exactly its checklist's IDs, which breaks old records when an item is added later; this does not affect creating the audio checklist, but should be revisited before the checklist grows.
