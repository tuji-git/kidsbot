"""Step 2: make images (free), voice (free) and assemble the video with FFmpeg."""
import asyncio
import io
import os
import random
import subprocess
import time
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

import config

FPS = 25


# ---------- images ----------
def _fallback_card(text, size, path):
    """If the image service is down, make a colorful card with text so the run still works."""
    w, h = size
    color = random.choice([(255, 205, 210), (187, 222, 251), (200, 230, 201), (255, 236, 179)])
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", w // 14)
    except OSError:
        font = ImageFont.load_default()
    words, lines, line = text.split(), [], ""
    for wd in words:
        if len(line + " " + wd) > 22:
            lines.append(line.strip())
            line = wd
        else:
            line += " " + wd
    lines.append(line.strip())
    y = h // 2 - len(lines) * (w // 14)
    for ln in lines[:6]:
        d.text((w // 2, y), ln, fill=(60, 60, 60), font=font, anchor="mm")
        y += w // 10
    img.save(path, "JPEG", quality=90)


def make_image(prompt, size, path, seed, retries=3):
    w, h = size
    full = f"{prompt}, {config.IMAGE_STYLE}"
    url = (f"https://image.pollinations.ai/prompt/{quote(full)}"
           f"?width={w}&height={h}&seed={seed}&nologo=true")
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            img = img.resize(size)
            img.save(path, "JPEG", quality=90)
            return
        except Exception as e:
            print(f"[image] attempt {attempt} failed: {e}")
            time.sleep(4 * attempt)
    print("[image] using fallback card")
    _fallback_card(prompt, size, path)


# ---------- voice ----------
async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE).save(path)


def make_voice(text, path, retries=3):
    for attempt in range(1, retries + 1):
        try:
            asyncio.run(_tts(text, path))
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:
            print(f"[voice] attempt {attempt} failed: {e}")
            time.sleep(3 * attempt)
    raise RuntimeError("Text-to-speech failed")


# ---------- ffmpeg ----------
def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stderr[-1500:])


def audio_duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    return float(p.stdout.strip())


def _scene_clip(img, audio, out, size, pad=0.6):
    w, h = size
    dur = audio_duration(audio) + pad
    frames = int(dur * FPS)
    # gentle zoom-in so the picture is not static
    vf = (f"scale={w*2}:{h*2},zoompan=z='min(zoom+0.0007,1.12)':d={frames}"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS},format=yuv420p")
    _run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", audio,
          "-vf", vf, "-af", f"apad=pad_dur={pad}", "-t", f"{dur:.2f}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", out])


def build_video(scenes, size, workdir, name, gen_size, seed_base):
    """scenes: list of {narration, image_prompt}. Returns path to the final mp4 and first image."""
    os.makedirs(workdir, exist_ok=True)
    clips, first_img = [], None
    for i, sc in enumerate(scenes):
        img = os.path.join(workdir, f"{name}_{i}.jpg")
        aud = os.path.join(workdir, f"{name}_{i}.mp3")
        clip = os.path.join(workdir, f"{name}_{i}.mp4")
        print(f"[{name}] scene {i+1}/{len(scenes)}")
        make_image(sc["image_prompt"], gen_size, img, seed_base + i)
        make_voice(sc["narration"], aud)
        _scene_clip(img, aud, clip, size)
        clips.append(clip)
        first_img = first_img or img
    listfile = os.path.join(workdir, f"{name}_list.txt")
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    final = os.path.join(workdir, f"{name}.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", final])
    return final, first_img


def make_thumbnail(src_img, title, path):
    """1280x720 JPEG under 2 MB with the title on a bar."""
    img = Image.open(src_img).convert("RGB").resize((1280, 720))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
    except OSError:
        font = ImageFont.load_default()
    d.rectangle([0, 540, 1280, 720], fill=(0, 0, 0))
    d.text((640, 630), title[:38], fill=(255, 255, 255), font=font, anchor="mm")
    img.save(path, "JPEG", quality=85)
