"""Real Chromium recordings and review frames for fictional demo data only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def recording_enabled():
    return os.environ.get('RECORD_DEMO') == '1'


def recording_options():
    if not recording_enabled():
        return {}
    return {'record_video_dir': 'recordings', 'record_video_size': {'width': 1440, 'height': 1000}}


def pause(page):
    if recording_enabled():
        page.wait_for_timeout(1800)


def finish_recording(page, name):
    if not recording_enabled():
        return
    video = page.video
    if video is None:
        raise RuntimeError('Recording was not enabled')
    page.context.close()  # Flush the browser recording before reading its path.
    source = Path(video.path())
    raw = source.with_name(name+'-source.webm')
    source.replace(raw)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('Install ffmpeg/ffprobe for recording review')
    output = raw.with_name(name+'-demo.webm')
    for crf in (36, 43):
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw), '-an',
                        '-vf', 'fps=12,scale=1280:-2', '-c:v', 'libvpx-vp9', '-b:v', '0',
                        '-crf', str(crf), '-deadline', 'good', '-cpu-used', '4', str(output)], check=True)
        if output.stat().st_size <= 750000:
            break
    if output.stat().st_size > 750000:
        raise RuntimeError('Demo exceeds the review size budget')
    details = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_entries',
                          'format=duration:stream=width,height,codec_type', '-of', 'json', str(output)], text=True))
    duration = float(details['format']['duration'])
    stream = next(s for s in details['streams'] if s['codec_type'] == 'video')
    if duration < 5 or any(s['codec_type'] == 'audio' for s in details['streams']):
        raise RuntimeError('Unexpected recording duration or audio stream')
    contact = raw.with_name(name+'-contact.png')
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(output),
                    '-vf', f'fps=6/{duration},scale=480:-1,tile=3x2', '-frames:v', '1', str(contact)], check=True)
    metadata = {'duration_seconds': round(duration, 2), 'width': stream['width'], 'height': stream['height'],
                'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'source': 'Chromium screen recording with fictional seeded data', 'audio': False}
    raw.with_name(name+'-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf8')
    print(json.dumps(metadata))
