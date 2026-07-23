# Web front-end

`python -m shia_aalim.web` serves a small local web app around the same
pipeline the CLI uses. It exists so the assistant can be used in a browser —
type a question, get cited answers; type a topic, get a lecture outline —
instead of at the terminal.

It is a **thin presentation layer**. Every answer is produced by the exact same
`AnswerGenerator` / `LectureGenerator` as `scripts/demo.py`, so the charter
guarantees are unchanged: no claim without a citation, confidence shown on every
passage, weak/disputed evidence flagged, and anything the grounding firewall
can't verify is withheld. The browser only renders that structured output.

## Install & run

```bash
pip install -e ".[web]"          # fastapi + uvicorn (optional extra)
python -m shia_aalim.web         # serve on http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>. The corpus is loaded at startup and the default
(dependency-free TF-IDF) index is built then, so it runs anywhere the CLI does —
no GPU, no API key, no network.

Without the extra installed, importing the module or starting the server prints
a clear install hint rather than a stack trace; the CLI keeps working with no
extras at all.

## Switching the retrieval index

Pass more than one embedder as a comma-separated list to offer a **retrieval
index** dropdown in the UI (the first is the default and is built at startup):

```bash
python -m shia_aalim.web --embedder "tfidf,st:BAAI/bge-m3"
```

Each embedder has its own index (the vectors differ), so switching means
querying a different retriever. Non-default indexes are built **lazily on first
use** and cached — startup stays fast, and if a semantic model isn't reachable
(the hosted sandbox blocks the HuggingFace Hub) the query returns a clear
"index unavailable" message and the toggle marks it *unavailable* instead of
crashing the server. `/api/status` reports each embedder's state
(`ready` / `lazy` / `failed`). Requests may also name the index explicitly with
an `"embedder"` field.

## Exporting a result

Every answer and lecture result has **⧉ Copy Markdown** and **⭳ Download .md**
buttons. Both use the same Markdown the CLI prints (`format_markdown` /
`Lecture.to_markdown`) — the `markdown` field returned by `/api/answer` and
`/api/lecture` — so what you copy into your notes or a lecture file is identical
to the terminal output, citations and all.

## Options

```bash
python -m shia_aalim.web \
  --host 127.0.0.1 --port 8000 \
  --knowledge-dir data/knowledge \      # folder of .jsonl knowledge files
  --embedder tfidf \                    # tfidf | hashing | st:BAAI/bge-m3
  --synthesize none \                   # none | mock | claude:<model>
  --judge lexical \                     # lexical | mock | claude:<model>
  --decompose none \                    # none | rule | claude:<model>
  --k 6                                 # default evidence count per answer
```

* **`--knowledge-dir`** — point it anywhere; the app answers only from the
  documents it finds there. Build the full corpus first with
  `python scripts/ingest.py`, or aim it at the committed sample
  (`data/knowledge/sample`) to try it immediately.
* **`--embedder st:BAAI/bge-m3`** — semantic retrieval, where a HuggingFace
  model is reachable (blocked in the hosted sandbox).
* **`--synthesize claude:<model>`** — LLM-composed prose (needs the `llm` extra
  + `ANTHROPIC_API_KEY`); it is still re-verified against the evidence before
  being shown, and withheld if it doesn't ground.

## API

The page is backed by three JSON endpoints (usable directly, e.g. from scripts):

| Method & path      | Body                                              | Returns |
|--------------------|---------------------------------------------------|---------|
| `GET  /api/status` | —                                                 | corpus size, each embedder's state, providers |
| `POST /api/answer` | `{"question": "...", "k": 6, "embedder": "..."}`  | `{answer, markdown, embedder}` — `answer` is `Answer.to_dict()` |
| `POST /api/lecture`| `{"topic": "...", "depth": 4, "embedder": "..."}` | topic + the 11-section framework, evidence per section, `markdown` |

`embedder` is optional (defaults to the startup default). Naming one that isn't
enabled, or a semantic model that can't be built here, returns HTTP 503 with an
explanatory `error`.

`GET /` serves the single, self-contained HTML page (no external assets, works
offline). FastAPI also exposes interactive API docs at `/docs`.

Example:

```bash
curl -s -X POST http://127.0.0.1:8000/api/answer \
  -H 'Content-Type: application/json' \
  -d '{"question": "the guardian (wali) is Allah, His Messenger and the believers", "k": 3}'
```

## What it is not

Not a hosted, multi-user, or authenticated service — it binds to localhost for a
single user. Treat generated answers as research aids that must be checked
against the primary sources, not as a substitute for a qualified scholar
(marjaʿ). Standing up a shared, hardened deployment (Qdrant behind the vector
store, a reverse proxy, rate limiting) is future work tracked in the
[roadmap](roadmap.md).
