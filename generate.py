"""Step 1: ask Gemini to write the story script as JSON."""
import json
import os
import re
import time

import requests

import config


def _prompt(topic, avoid_titles):
    avoid = "; ".join(avoid_titles[-30:]) or "none"
    return f"""You write scripts for a safe, gentle YouTube channel for children aged 2-6.
Topic: {topic}
Do NOT reuse these earlier titles: {avoid}

Return ONLY valid JSON with exactly this shape:
{{
  "title": "catchy kid-friendly title, max 70 characters, no emojis",
  "description": "2-3 friendly sentences for parents, in English",
  "tags": ["8 to 12 short tags"],
  "long_scenes": [
    {{"narration": "1-2 short simple sentences read aloud", "image_prompt": "what the picture shows"}}
  ],
  "short_title": "separate catchy title for a Short, max 60 characters",
  "short_scenes": [
    {{"narration": "1 short sentence", "image_prompt": "what the picture shows"}}
  ]
}}
Rules:
- exactly {config.LONG_SCENES} items in long_scenes and exactly {config.SHORT_SCENES} items in short_scenes
- simple words, positive and calm tone, nothing scary, no brands, no real people
- every image_prompt describes ONE clear scene with the same recurring friendly characters
- no text or letters inside the images unless the topic is letters or numbers"""


def _validate(data):
    for key in ("title", "description", "tags", "long_scenes", "short_title", "short_scenes"):
        if key not in data:
            raise ValueError(f"missing key: {key}")
    if len(data["long_scenes"]) < 3 or len(data["short_scenes"]) < 1:
        raise ValueError("not enough scenes")
    for sc in data["long_scenes"] + data["short_scenes"]:
        if not sc.get("narration") or not sc.get("image_prompt"):
            raise ValueError("scene missing narration or image_prompt")
    data["title"] = str(data["title"]).strip()[:95]
    data["short_title"] = str(data["short_title"]).strip()[:85]
    data["tags"] = [str(t).strip() for t in data["tags"]][:15]
    return data


BASE = "https://generativelanguage.googleapis.com/v1beta"
# models we never want (not text generators)
BAD_WORDS = ("image", "tts", "audio", "live", "embed", "exp", "thinking",
             "robotics", "computer", "learnlm", "gemma", "vision", "aqa")
ROUNDS = 4          # how many full passes over the model list
TIMEOUT = 45        # seconds per request


def _version_key(name):
    """gemini-2.5-flash -> (2, 5); used to prefer the newest model."""
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", name)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def list_candidates(key):
    """Ask Google which models this key can use. Order: stable newest first,
    previews next, 'lite' models last (cheaper and usually less busy = good fallback)."""
    forced = os.getenv("GEMINI_MODEL", "").strip()
    if forced:
        return [forced.removeprefix("models/")]
    names = []
    try:
        r = requests.get(f"{BASE}/models", params={"pageSize": 200},
                         headers={"x-goog-api-key": key}, timeout=30)
        r.raise_for_status()
        for m in r.json().get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if ("generateContent" in m.get("supportedGenerationMethods", [])
                    and "gemini" in name and "flash" in name
                    and not any(w in name for w in BAD_WORDS)):
                names.append(name)
    except Exception as e:
        print(f"[generate] could not list models: {e}")
    names.sort(key=lambda n: ("lite" in n, "preview" in n,
                              tuple(-x for x in _version_key(n)), n))
    return names or [config.GEMINI_MODEL]


def make_script(topic, avoid_titles):
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text": _prompt(topic, avoid_titles)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    allc = list_candidates(key)
    # keep the 4 best normal models + 2 'lite' fallbacks (lite is cheaper and usually less busy)
    candidates = [m for m in allc if "lite" not in m][:4] + [m for m in allc if "lite" in m][:2]
    print(f"[generate] models to try: {candidates}")
    dead = set()          # models that answered 404/403: skip them in later rounds
    last_err = None
    for rnd in range(1, ROUNDS + 1):
        alive = [m for m in candidates if m not in dead]
        if not alive:
            break
        for model in alive:
            url = f"{BASE}/models/{model}:generateContent"
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=TIMEOUT)
                if r.status_code in (404, 403):
                    dead.add(model)                        # gone or not allowed: never retry
                    last_err = f"{model}: HTTP {r.status_code}"
                    print(f"[generate] {last_err} (skipping this model)")
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    last_err = f"{model}: HTTP {r.status_code} (busy/quota)"
                    print(f"[generate] round {rnd}: {last_err}")
                    continue                               # try the next model
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip().removeprefix("```json").removesuffix("```").strip()
                data = _validate(json.loads(text))
                print(f"[generate] OK with model {model} (round {rnd})")
                return data
            except Exception as e:                         # timeout, bad JSON, network...
                last_err = f"{model}: {e}"
                print(f"[generate] round {rnd}: {last_err}")
        if rnd < ROUNDS:
            wait = 20 * rnd                                # 20s, 40s, 60s between rounds
            print(f"[generate] all busy, waiting {wait}s before round {rnd + 1}...")
            time.sleep(wait)
    raise RuntimeError(f"Gemini failed on all models. Last error: {last_err}")
