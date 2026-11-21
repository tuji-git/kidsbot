"""All settings in one place. Most can be overridden with environment variables."""
import os

# --- Content ---
TOPICS = [
    "learning colors", "counting from 1 to 10", "farm animals and their sounds",
    "shapes around us", "the alphabet letters A to E", "good manners and saying thank you",
    "brushing teeth every day", "the days of the week", "sharing with friends",
    "ocean animals", "fruits and vegetables", "the four seasons",
    "kind words and helping others", "baby animals and their mommies",
    "the weather: sun, rain and snow", "bedtime and sleeping well",
    "zoo animals", "transport: cars, trains and planes", "the five senses",
    "being brave and trying new things",
]
LONG_SCENES = 8     # scenes in the long video
SHORT_SCENES = 3    # scenes in the Short

# --- AI (free Gemini API key from https://aistudio.google.com/apikey) ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
IMAGE_STYLE = ("cute colorful 2D cartoon illustration for toddlers, soft pastel colors, "
               "thick outlines, friendly smiling characters, simple clean background")

# --- Voice (free, no key) ---
VOICE = os.getenv("TTS_VOICE", "en-US-AnaNeural")
VOICE_RATE = os.getenv("TTS_RATE", "-5%")   # slightly slower for kids

# --- YouTube ---
PRIVACY = os.getenv("PRIVACY", "private")   # private | unlisted | public
CATEGORY_ID = "27"                           # Education
MADE_FOR_KIDS = True
MIN_HOURS_BETWEEN_RUNS = 6                   # protection against accidental double runs

# --- Paths ---
OUT_DIR = "out"
HISTORY_FILE = "history.json"
