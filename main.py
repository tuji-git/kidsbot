"""Runs one full cycle: script -> long video + Short -> upload -> save history."""
import argparse
import json
import os
import random
import shutil
from datetime import datetime, timedelta, timezone

import config
import generate
import media


def load_history():
    if os.path.exists(config.HISTORY_FILE):
        with open(config.HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def pick_topic(history):
    used = [h.get("topic") for h in history]
    fresh = [t for t in config.TOPICS if t not in used[-len(config.TOPICS) + 1:]]
    return random.choice(fresh or config.TOPICS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="make the videos but do NOT upload")
    ap.add_argument("--force", action="store_true", help="ignore the double-run protection")
    args = ap.parse_args()

    history = load_history()

    # protection: do not run twice within a few hours
    if history and not args.force and not args.dry_run:
        last = datetime.fromisoformat(history[-1]["time"])
        if datetime.now(timezone.utc) - last < timedelta(hours=config.MIN_HOURS_BETWEEN_RUNS):
            print("Last run was too recent. Skipping. (use --force to override)")
            return

    topic = pick_topic(history)
    print(f"Topic: {topic}")
    script = generate.make_script(topic, [h.get("title", "") for h in history])
    print(f"Title: {script['title']}")

    shutil.rmtree(config.OUT_DIR, ignore_errors=True)
    seed = random.randint(1, 10**6)

    long_path, first_img = media.build_video(
        script["long_scenes"], (1920, 1080), config.OUT_DIR, "long", (1280, 720), seed)
    short_path, _ = media.build_video(
        script["short_scenes"], (1080, 1920), config.OUT_DIR, "short", (720, 1280), seed + 100)
    thumb = os.path.join(config.OUT_DIR, "thumb.jpg")
    media.make_thumbnail(first_img, script["title"], thumb)

    if args.dry_run:
        print(f"Dry run finished. Files are in ./{config.OUT_DIR}/")
        return

    import upload  # imported here so --dry-run works without Google libraries
    entry = {"time": datetime.now(timezone.utc).isoformat(), "topic": topic,
             "title": script["title"], "privacy": config.PRIVACY}

    print("Uploading long video...")
    entry["long_id"] = upload.upload(
        long_path, script["title"], script["description"], script["tags"], "long", thumbnail=thumb)
    history.append(entry)
    save_history(history)  # save right away, in case the Short fails

    print("Uploading Short...")
    try:
        entry["short_id"] = upload.upload(
            short_path, script["short_title"], script["description"], script["tags"], "short")
    except Exception as e:
        print(f"Short upload failed: {e}")
    save_history(history)
    print("All done.")


if __name__ == "__main__":
    main()
