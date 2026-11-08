# Kuku Promo Discovery

Reads microdrama screenplays (timestamped `.txt`, `.srt` or `.fountain`) and finds the best **20–60 second promo clips**: where each one starts and ends, its hook, its cliffhanger, one line on why it works, and a ranking of which to post first.

Requirements: Python 3.10+ (pipeline) and, for the optional review app, Node.js 18+. No other tools.

## Run it (one command)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # then put your key in .env (see "Choose the model")

python run_all.py --input data/input          # any folder of screenplay files
```

Results land in `outputs/runs/run_<time>/ranked_promos/`:

| File | What it is |
|---|---|
| `promos_submission.md` | readable list of the top promos with hook, cliffhanger, why it works, why ranked here |
| `promos_submission.csv` / `.json` | every promo: episode, **segments** (start–end of each, in order), hook, cliffhanger, why, rank reason, scores |
| `final_ranking.csv` | full table behind the ranking |
| `top_10_*` | DaVinci / Premiere markers and a CMX 3600 EDL |

Useful flags: `--no-llm` (free, no API key: local heuristic ranking only), `--limit 10` (ask the model about only 10 clips), `--max-episodes 3` (quick test), `--output <folder>`.

## Connect any model (model name + API key)

Like a Hugging Face token: give a **model name** and an **API key**; the vendor is detected for you.

```env
# .env  (two lines are enough)
LLM_MODEL=gemini-3.5-flash-lite        # or gpt-4o-mini, claude-haiku-4-5, meta-llama/Llama-3.1-8B-Instruct, ...
LLM_API_KEY=your_key_here
```

or let a helper do it (asks for both, tests the connection, saves to `.env`):

```bash
python scripts/setup_model.py
python scripts/setup_model.py --model meta-llama/Llama-3.1-8B-Instruct     # then paste your hf_ token
```

| You enter | Detected as |
|---|---|
| key `AIza…` or model `gemini-*` | Google Gemini |
| key `sk-ant-…` or model `claude-*` | Anthropic |
| key `sk-…` or model `gpt-*`, `o1/o3/o4*` | OpenAI |
| key `hf_…` or model `org/name` | Hugging Face (router) |
| key `sk-or-…` / `gsk_…` | OpenRouter / Groq |
| `LLM_BASE_URL=…` (or `--provider ollama`) | any OpenAI-compatible server, e.g. local Ollama |

If the guess is wrong, set `LLM_PROVIDER` (`gemini, anthropic, openai, huggingface, openrouter, groq, together, ollama`). Your existing `GEMINI_API_KEY` + `GEMINI_MODEL` setup keeps working unchanged.

Switch for one run without touching `.env`: `python run_all.py --input data/input --model gpt-4o-mini` (key from the environment).

**In the review app:** the app uses the model from `.env` automatically, through a local proxy, so the key never reaches the browser. Click **AI Model** in the top bar to type a different model name and key instead (kept only in your browser). `src/llm.py` (Python) and `frontend/src/utils/llmClient.js` (React) share the same detection rules; `tests/test_llm.py` and `llmClient.test.js` run the same table.

## How it works

1. **Parse** screenplays into timestamped events (`src/parser.py`).
2. **Windows** (`src/candidate_generator.py`): every 20–60s stretch that starts and ends on event boundaries, so clips never cut a line in half.
3. **Cheap local score** (`src/scoring.py`): keyword/cadence heuristics rank the windows; the best 12 per episode go forward, then overlapping ones are dropped (`src/deduplicate.py`).
4. **Evidence** (`src/prepare_editorial_data.py`): the first 3 s and last 5 s of each clip are cut out, so the model must find the hook and cliffhanger *inside* those windows.
5. **Model judgement** (`src/editorial_evaluator.py`): hook, cliffhanger, emotional stakes, stand-alone clarity, progression, plus risks. Output is schema-validated; every returned timestamp is checked against the 3 s / 5 s windows (`PASS / PARTIAL / FAIL`).
6. **Rank** (`src/final_ranker.py`): `70% model + 30% local`. The local weight is `LOCAL_WEIGHT` in `.env`.
7. **Export** (`src/export_submission.py`, `src/nle_export.py`).

Shared parameters (clip length, hook/cliffhanger windows, local weight) are in `config.py` and can be overridden from `.env`.

## Is it any good? (and where it fails)

```bash
python scripts/quality_report.py          # measured failure modes -> outputs/quality_report.md
                                          # and outputs/human_check_sheet.csv
python scripts/score_human_check.py       # after a person fills the sheet: real accuracy numbers
```

`quality_report.md` shows where the model and heuristic disagree or look weak. It cannot say who is *right*; that needs the human-filled sheet. Known blind spots: screenplay text only (no acting, visuals or music), single continuous segment per promo (no joined moments or cross-episode promos), and a model that grades its own shortlist.

## Tests

```bash
pytest                       # Python (43 tests)
cd frontend && npm test      # React utilities (30 tests)
cd frontend && npm run lint  # ESLint (undefined variables, unused code, React hook mistakes)
python -m ruff check .        # Python lint (pip install -r requirements-dev.txt)
```

## Review app (optional)

```bash
cd frontend && npm install && npm run dev  # http://localhost:3000
```

The app contains no show data. On the Home page you upload a drama's screenplay files (.txt, .srt, .fountain); promo windows are found in your browser (no API cost) and your AI model can judge the best few. Then explore and compare clips, simulate the vertical-phone preview, sign off as a human reviewer (backup/import supported) and export NLE markers. Everything stays in your browser, including after a refresh.

**Same files, same answer.** Run `python scripts/build_known_results.py` once after a pipeline run. Uploading one of the pack's files again then shows the promos the pipeline found in it (the same ranking as `submission/raw_outputs/`, marked "saved pipeline results" in the upload report); any other file is processed in the browser. That data holds screenplay text, so it is git-ignored and exists only on this machine.

**Deploying (Vercel).** Import the GitHub repo, set the **Root Directory** to `frontend` (build `npm run build`, output `dist`). Build it from the repo, not from this machine, so the saved screenplay-derived results are not included. To let the deployed app use your model by default, add these **Environment Variables** in the Vercel project and redeploy:

| Variable | Example |
|---|---|
| `LLM_API_KEY` | your key (stays on the server; the browser never sees it) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` |
| `LLM_MAX_CALLS_PER_HOUR` | optional, default 60 per visitor |

The functions in `frontend/api/llm/` read them, so the header shows the model as connected, the model is fixed by the server, prompts are size-capped and each visitor is rate-limited. Anyone with the link can still spend that key's quota within the limit, so use a key with a small quota and rotate it afterwards. Without these variables the app still ranks promos by rules, and a visitor can enter their own model and key under **AI Model**. A plain environment variable on your computer is not enough for the dev server: put the key in `.env` (`python scripts/setup_model.py`).

## Confidentiality

Screenplays and everything generated from them (`data/`, `outputs/`) are git-ignored. Do not publish them. `.env` holds your API key and is also ignored; commit `.env.example` only.
