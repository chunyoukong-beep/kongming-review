"""Prepare local, timecoded evidence. This script makes no network or model API calls."""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


def ffmpeg():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise ValueError('缺少 FFmpeg；请安装 requirements.txt 中的依赖') from exc


def run(args, timeout=600):
    result = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin',
                             '-protocol_whitelist', 'file,pipe', *map(str, args)],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('视频处理失败：' + result.stderr[-1200:])
    return result.stderr


def seconds(stamp):
    parts = stamp.replace(',', '.').split(':')
    value = sum(float(part) * 60 ** index for index, part in enumerate(reversed(parts)))
    if not math.isfinite(value) or value < 0:
        raise ValueError('时间格式不正确')
    return value


def inspect_video(video):
    result = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin',
                             '-protocol_whitelist', 'file,pipe', '-i', str(video)],
                            capture_output=True, text=True, timeout=30)
    match = re.search(r'Duration:\s*(\d+:\d+:\d+\.\d+)', result.stderr)
    if not match or 'Video:' not in result.stderr:
        raise ValueError('无法读取视频；请确认文件完整且包含视频轨道')
    duration = seconds(match[1])
    if duration <= 0:
        raise ValueError('视频时长必须大于零')
    rate = re.search(r'(\d+(?:\.\d+)?)\s+fps', result.stderr)
    return {'duration': duration, 'has_audio': 'Audio:' in result.stderr,
            'fps': float(rate[1]) if rate else 25.0}


def subtitles(path, duration):
    text = path.read_text(encoding='utf-8-sig').replace('\r', '')
    records = []
    stamp = r'(\d{1,3}:\d{2}(?::\d{2})?[,.]\d{1,3})'
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
            continue
        index = next((i for i, line in enumerate(lines) if '-->' in line), None)
        match = re.fullmatch(stamp + r'\s*-->\s*' + stamp + r'(?:\s+.*)?',
                             lines[index].strip()) if index is not None else None
        if not match:
            raise ValueError('字幕格式不正确；支持带时间点的 UTF-8 SRT / VTT')
        start, end = seconds(match[1]), seconds(match[2])
        words = re.sub(r'<[^>]*>', '', ' '.join(lines[index + 1:])).strip()
        if not 0 <= start < end <= duration + .05:
            raise ValueError('字幕时间倒置或超出视频时长；请检查是否同一版本')
        if words:
            records.append({'start': start, 'end': min(end, duration), 'text': words})
    if not records:
        raise ValueError('字幕中没有可读取的时间点和文字')
    return records


def sampling_times(duration, interval, scene_times, maximum, fps=25):
    # Container duration may include a small AAC tail beyond the last video frame.
    last = max(0, duration - max(.05, 1 / max(1, fps)) - .05)
    opening = {round(min(i * .5, last), 3) for i in range(6) if i * .5 < duration}
    tail = sorted(({round(min(i * interval, last), 3)
                    for i in range(math.ceil(duration / interval))}
                   | {round(t, 3) for t in scene_times if 0 <= t < duration}
                   | {round(last, 3)}) - opening)
    budget = maximum - len(opening)
    if len(tail) > budget:
        tail = [tail[round(i * (len(tail) - 1) / (budget - 1))] for i in range(budget)]
    return sorted(opening | set(tail))


def make_sheets(out, frames):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    sheets = []
    font = ImageFont.load_default(size=18)
    for offset in range(0, len(frames), 12):
        canvas = Image.new('RGB', (960, 1056), '#111111')
        draw = ImageDraw.Draw(canvas)
        for index, frame in enumerate(frames[offset:offset + 12]):
            x, y = (index % 4) * 240, (index // 4) * 352
            draw.text((x + 8, y + 5), f"{frame['time']:.3f}s", font=font, fill='white')
            with Image.open(out / frame['file']) as original:
                thumb = ImageOps.contain(original.convert('RGB'), (228, 314))
                canvas.paste(thumb, (x + (240 - thumb.width) // 2,
                                    y + 32 + (314 - thumb.height) // 2))
        name = f'contact-{offset // 12:03}.jpg'
        canvas.save(out / name, quality=90)
        sheets.append(name)
    return sheets


def transcribe(audio, model_file, language, duration):
    try:
        from pywhispercpp.model import Model
    except ImportError as exc:
        raise ValueError('本地转写需要 pywhispercpp；也可以通过 --subtitles 导入已有字幕') from exc
    # Only an existing local path reaches Model; never pass a model name that triggers a download.
    model = Model(str(model_file), n_threads=4, params_sampling_strategy=1,
                  beam_search={'beam_size': 5, 'patience': 1.0}, print_realtime=False,
                  print_progress=False, print_timestamps=False, language=language,
                  translate=False, redirect_whispercpp_logs_to=None)
    output = []
    for segment in model.transcribe(str(audio), token_timestamps=True, max_len=24):
        start, end = max(0, segment.t0 / 100), min(duration, segment.t1 / 100)
        text = segment.text.strip()
        if text and start < end:
            output.append({'start': start, 'end': end, 'text': text})
    return output


def prepare(args):
    video = Path(args.video).expanduser().resolve(strict=True)
    out = Path(args.out).expanduser().resolve()
    if not video.is_file():
        raise ValueError('输入必须是本地视频文件')
    if out.exists():
        raise ValueError('输出目录已存在；请换一个目录，原有内容将保留')
    if not math.isfinite(args.interval) or not 0 < args.interval <= 30:
        raise ValueError('抽帧间隔应大于零且不超过30秒')
    if not 12 <= args.max_frames <= 240:
        raise ValueError('抽帧上限应在12到240之间')
    info = inspect_video(video)
    if info['duration'] > 3600:
        raise ValueError('此工具面向短视频，单文件最长60分钟；请先选择需要审查的片段')
    records = subtitles(Path(args.subtitles).expanduser(), info['duration']) if args.subtitles else []
    model = Path(args.model).expanduser().resolve(strict=True) if args.model else None
    if model and not model.is_file():
        raise ValueError('模型必须是已下载的本地 Whisper GGML 文件')
    try:
        from PIL import Image  # dependency check before creating output
    except ImportError as exc:
        raise ValueError('缺少 Pillow；请安装 requirements.txt 中的依赖') from exc
    out.mkdir(parents=True)
    (out / 'frames').mkdir()
    # Decode the timeline for scene-change signals; this is not semantic review of every frame.
    scene_log = run(['-i', video, '-an', '-vf', r'select=gt(scene\,0.35),showinfo',
                     '-fps_mode', 'vfr', '-f', 'null', '-'])
    scenes = [float(t) for t in re.findall(r'pts_time:([\d.]+)', scene_log)]
    times = sampling_times(info['duration'], args.interval, scenes, args.max_frames, info['fps'])
    frames = []
    for index, time in enumerate(times):
        filename = f'frames/frame-{index:03}.jpg'
        log = run(['-copyts', '-start_at_zero', '-ss', time, '-i', video, '-frames:v', '1', '-an', '-vf',
                   'scale=640:640:force_original_aspect_ratio=decrease,showinfo',
                   '-fps_mode', 'vfr', '-pix_fmt', 'yuvj420p', '-q:v', '3', out / filename])
        if not (out / filename).is_file():
            # Some transport streams cannot seek to an interior frame. Decode from
            # the beginning and select by relative PTS, preserving a checkable time.
            log = run(['-copyts', '-start_at_zero', '-i', video, '-frames:v', '1', '-an',
                       '-vf', f'select=gte(t\\,{time:.9f}),scale=640:640:force_original_aspect_ratio=decrease,showinfo',
                       '-fps_mode', 'vfr', '-pix_fmt', 'yuvj420p', '-q:v', '3', out / filename])
        if not (out / filename).is_file():
            raise ValueError(f'{time:.3f}秒抽帧失败，不能视为已检查此处')
        decoded = re.search(r'pts_time:([\d.]+)', log)
        if not decoded:
            raise ValueError('未取得抽样画面的原片时间，不能标注猜测位置')
        actual = float(decoded[1])
        if any(abs(frame['time'] - actual) < .0001 for frame in frames):
            (out / filename).unlink()
            continue
        if not 0 <= actual < info['duration']:
            raise ValueError('画面时间超出原片范围')
        frames.append({'time': actual, 'file': filename})
    sheets = make_sheets(out, frames)
    audio = None
    if info['has_audio']:
        audio = 'audio.wav'
        run(['-i', video, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', out / audio])
    if args.subtitles:
        source = 'user_subtitles_unverified'
    elif audio and model:
        records = transcribe(out / audio, model, args.language, info['duration'])
        source = 'local_asr_unverified' if records else 'asr_no_speech_recognized'
    else:
        source = 'audio_not_transcribed' if audio else 'no_audio_track'
    evidence = {'schema_version': 1, 'video': info,
                'sampling': {'semantic_every_frame': False, 'scene_scan': True,
                             'interval_seconds': args.interval, 'max_frames': args.max_frames},
                'frames': frames, 'contact_sheets': sheets, 'audio_file': audio,
                'transcript': records, 'transcript_source': source,
                'limitations': ['画面为抽样，不能据此保证逐帧语义审核或检查全部画面文字。',
                                '转写或外部字幕须核对原声；音频文件已提取不代表AI已听取。']}
    (out / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'transcript.txt').write_text('\n'.join(
        f"[{r['start']:.2f}–{r['end']:.2f}s] {r['text']}" for r in records), encoding='utf-8')
    return {'evidence': str(out / 'evidence.json'), 'frames': len(frames),
            'sheets': len(sheets), 'transcript_segments': len(records), 'transcript_source': source}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--out', required=True, help='A new, non-existing local folder')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--subtitles', help='Local UTF-8 SRT or VTT for this exact video version')
    group.add_argument('--model', help='Existing local Whisper GGML model; no model downloads')
    parser.add_argument('--language', default='zh')
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--max-frames', type=int, default=96)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('准备失败：' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
