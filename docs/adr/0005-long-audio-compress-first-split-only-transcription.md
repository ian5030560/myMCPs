# Long audio: compress first, split only for transcription, never for listening

Vendors cap a request by size (Gemini 20 MB inline and 9.5 hours per prompt through its Files API, OpenAI transcription 25 MB per file). Both audio tools first convert the input to mono 16 kHz 32 kbps mp3, which fits most recordings in one request (about 1.4 hours inline for Gemini, 1.7 hours for OpenAI). Transcription splits into chunks only when the compressed file is still over the vendor's size limit, cutting at the silence nearest each target length and shifting segment times back onto the original recording. Listening never splits: it sends the whole compressed file, uploads it through Gemini's Files API when it is over the inline limit, and otherwise fails with an error that tells the agent how to split the work itself, because only the agent knows whether its question survives being split.

## Considered Options

- **Fixed-length chunks**: simplest, but cut words and sentences in half, which vendors warn lowers accuracy.
- **Overlapping chunks with deduplication**: the most accurate merge, but needs fuzzy matching of the overlap and has lost audio silently in other projects when one half was rejected.
- **Always split at silence, then compress each chunk**: handles duration limits, but turns every ordinary recording into several requests and breaks the model's context, while the limits found in the vendors' documentation are about size.
- **Map-reduce for listening** (ask each chunk, then merge the answers): works for summaries but answers questions that span chunks wrongly without any sign of it, and costs at least twice as much.
- **Accumulate for listening** (each chunk sees the notes from the previous ones): better than map-reduce across chunks, but runs strictly in sequence, loses early detail as the notes are compressed, and still cannot compare distant parts; the server cannot know what the notes should keep.
- **Transcribe, then answer from the text**: cheaper per question, but loses tone, speakers, music and other sounds; the agent can already do it with `transcribe_audio`.

## Consequences

- An agent with audio longer than the listening limit gets an error that names two ways forward: work through the recording in order with `start`/`end`, carrying its notes into each next `prompt`, or transcribe it first.
- A duration limit is added to a vendor only after manual testing confirms it. Manual testing found one: Gemini's transcription model takes 1 hour per request, and 30 minutes when word times are asked for, which is shorter than the 20 MB size limit allows (83 minutes), so a chunk may not be longer than the tighter of the size and duration limits (`.scratch/audio-manual-findings/issues/01-gemini-transcribe-token-limit.md`). A rejected chunk is always reported, never dropped.
