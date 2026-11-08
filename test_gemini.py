"""Connection smoke test for the configured model (any provider, see src/llm.py).

    python test_gemini.py

Prints which provider/model is selected and whether a tiny request succeeds.
(Kept under its old name; it now works for every provider, not just Gemini.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import llm  # noqa: E402

print("Provider/model selected:", llm.describe())
print("Credentials configured:", llm.is_configured())

llm.require_configured()
reply = llm.complete_json('Reply with exactly this JSON and nothing else: {"status": "working"}', timeout=60)
print("\nModel reply:")
print(reply)
