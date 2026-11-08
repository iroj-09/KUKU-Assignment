# Step-by-step: run the Kuku Promo Discovery prototype

(The short version is in `README.md`. This is the same flow with every step spelled out.)

## 1. Put the screenplay files in the input folder
Copy the supplied `.txt` files (50 episodes) into `data/input/`. Do not commit this folder to a public GitHub repository.

## 2. Create and activate a virtual environment (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```
If PowerShell blocks activation, use Command Prompt and run `.venv\Scripts\activate.bat`.

## 3. Install packages
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Choose the model (optional, but needed for hook/cliffhanger judgement)
Copy `.env.example` to `.env` and fill in ONE provider. Gemini is the default:
```text
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
```
Other vendors (OpenAI-compatible APIs, Anthropic) are selected with `LLM_PROVIDER`; see `.env.example` and `src/llm.py`. Never commit `.env` or share the key.

## 5. Run the whole pipeline
```powershell
python run_all.py --input data/input
```
No API key? Add `--no-llm` for a free, heuristic-only ranking. Quick test: `--max-episodes 3`. Cheap test of the model: `--limit 10`.

Results are written to `outputs/runs/run_<time>/ranked_promos/`; start with `promos_submission.md`.
Each step can also be run alone from `src/` (see the docstring at the top of `run_all.py`).

## 6. Test the code
```powershell
pytest -q                      # Python
cd frontend; npm install; npm test; cd ..   # React utilities
```

## 7. Check the quality
```powershell
python scripts/quality_report.py --run outputs/runs/run_<time>
```
This writes `quality_report.md` (measured weak spots) and `human_check_sheet.csv`. Fill the `human_*` columns with Y/N for each clip: (a) does the opening have a hook within 3 s, (b) is the ending really unresolved, (c) can a new viewer follow it, (d) would you post it? Then:
```powershell
python scripts/score_human_check.py outputs/runs/run_<time>/human_check_sheet.csv
```

## 8. Review app (optional)
```powershell
cd frontend; npm run dev        # http://localhost:3000 (upload a drama's screenplay files on the Home page)
```

## 9. GitHub safety
Before pushing, run `git status` and confirm that `data/`, `outputs/`, `submission/raw_outputs/`, `.env` and `.venv/` are not staged. Keep the source screenplays and derived outputs private.
