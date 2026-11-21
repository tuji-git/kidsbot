"""Step 3: upload to YouTube. Credentials come from environment variables (GitHub Secrets)."""
import argparse
import os
import time

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(path, title, description, tags, kind="long", privacy=None, thumbnail=None):
    privacy = privacy or config.PRIVACY
    if kind == "short" and "#shorts" not in (title + description).lower():
        title = f"{title[:90]} #Shorts"
        description = f"{description}\n\n#Shorts"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags,
            "categoryId": config.CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": config.MADE_FOR_KIDS,
        },
    }
    yt = get_service()
    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response, errors = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  uploaded {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and errors < 5:
                errors += 1
                time.sleep(2 ** errors)
                continue
            raise
    video_id = response["id"]
    print(f"  done: https://youtu.be/{video_id}  ({privacy})")

    if thumbnail and kind == "long":
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail)).execute()
        except Exception as e:  # needs a phone-verified channel; not critical
            print(f"  thumbnail skipped: {e}")
    return video_id


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Upload one video (for testing)")
    p.add_argument("video")
    p.add_argument("title")
    p.add_argument("description")
    p.add_argument("--kind", choices=["long", "short"], default="long")
    p.add_argument("--privacy", choices=["public", "unlisted", "private"], default="private")
    a = p.parse_args()
    upload(a.video, a.title, a.description, ["kids", "learning"], a.kind, a.privacy)
