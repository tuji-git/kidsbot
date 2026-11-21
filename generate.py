"""Step 1: ask Gemini to write the story script as JSON."""
import json
import os
import time

import requests

import config

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def make_script(topic, avoid_titles, retries=3):
    key = os.environ["GEMINI_API_KEY"]
    url = API.format(model=config.GEMINI_MODEL)
    body = {
        "contents": [{"parts": [{"text": _prompt(topic, avoid_titles)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=90)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip().removeprefix("```json").removesuffix("```").strip()
            return _validate(json.loads(text))
        except Exception as e:  # network, quota, bad JSON...
            last_err = e
            print(f"[generate] attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"Gemini failed after {retries} attempts: {last_err}")
