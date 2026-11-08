"""Central configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv(
    'GEMINI_API_KEY', ''
)

GEMINI_MODEL = os.getenv(
    'GEMINI_MODEL',
    'gemini-3.5-flash-lite'
)

INPUT_DIR = os.getenv(
    'INPUT_DIR',
    'data/input'
)

OUTPUT_DIR = os.getenv(
    'OUTPUT_DIR',
    'outputs/raw'
)

MIN_PROMO_SECONDS = int(
    os.getenv('MIN_PROMO_SECONDS', '20')
)

MAX_PROMO_SECONDS = int(
    os.getenv('MAX_PROMO_SECONDS', '60')
)

# Display name of the drama being analysed (shown on the React app's Home page).
SHOW_TITLE = os.getenv(
    'SHOW_TITLE', 'I Married a Broken Soldier. He was a Duke.'
)

# Weight of the local heuristic in the final hybrid score (the model gets 1 - this).
LOCAL_WEIGHT = float(
    os.getenv('LOCAL_WEIGHT', '0.30')
)

# Evidence windows used everywhere (scoring, Gemini evidence, compliance checks).
# The React app mirrors these values (frontend/src/utils/clientParser.js).
HOOK_WINDOW_SECONDS = float(
    os.getenv('HOOK_WINDOW_SECONDS', '3')
)

CLIFFHANGER_WINDOW_SECONDS = float(
    os.getenv('CLIFFHANGER_WINDOW_SECONDS', '5')
)
