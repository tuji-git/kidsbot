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
BAD_WORDS = ("lite", "image", "tts", "audio", "live", "embed", "exp", "thinking",
             "robotics", "computer", "learnlm", "gemma", "vision", "aqa")


def _version_key(name):
    """gemini-2.5-flash -> (2, 5); used to prefer the newest model."""
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", name)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def list_candidates(key):
    """Ask Google which models this key can use, newest stable 'flash' first."""
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
    # stable names first (no 'preview'), then newest version
    names.sort(key=lambda n: ("preview" in n, tuple(-x for x in _version_key(n)), n))
    return names or [config.GEMINI_MODEL]


def make_script(topic, avoid_titles, retries=2):
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text": _prompt(topic, avoid_titles)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    candidates = list_candidates(key)
    print(f"[generate] models to try: {candidates[:4]}")
    last_err = None
    for model in candidates[:5]:
        url = f"{BASE}/models/{model}:generateContent"
        for attempt in range(1, retries + 1):
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=90)
                if r.status_code in (404, 429, 403):   # model missing / no quota: try the next model
                    last_err = f"{model}: HTTP {r.status_code}"
                    print(f"[generate] {last_err} -> next model")
                    break
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip().removeprefix("```json").removesuffix("```").strip()
                data = _validate(json.loads(text))
                print(f"[generate] OK with model {model}")
                return data
            except Exception as e:  # bad JSON, network...
                last_err = f"{model}: {e}"
                print(f"[generate] attempt {attempt} failed: {last_err}")
                time.sleep(4 * attempt)
    raise RuntimeError(f"Gemini failed on all models. Last error: {last_err}")
