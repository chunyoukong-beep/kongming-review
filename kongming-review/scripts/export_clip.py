"""Export an explicitly selected source interval to a playable MP4 preview."""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from prepare_video import inspect_video, run


def export_clip(video, start, end, out):
    video = Path(video).expanduser().resolve(strict=True)
    out = Path(out).expanduser().resolve()
    sidecar = out.with_suffix('.source.json')
    if out.exists() or sidecar.exists():
        raise ValueError('输出文件已存在，请使用新的文件名')
    if out.suffix.lower() != '.mp4':
        raise ValueError('预览输出请使用.mp4扩展名')
    if not all(math.isfinite(t) for t in (start, end)):
        raise ValueError('时间必须是有限的秒数')
    info = inspect_video(video)
    if not 0 <= start < end <= info['duration']:
        raise ValueError('时间范围倒置或超出原片，请核对来源起止位置')
    if end - start > 30:
        raise ValueError('预览片段最长30秒，请选择具体修改位置')
    out.parent.mkdir(parents=True, exist_ok=True)
    run(['-n', '-i', video, '-ss', start, '-t', end - start,
         '-map', '0:v:0', '-map', '0:a:0?', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
         '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-movflags', '+faststart', out])
    actual = inspect_video(out)
    run(['-v', 'error', '-i', out, '-map', '0:v:0', '-f', 'null', '-'])
    if abs(actual['duration'] - (end - start)) > max(.15, 1 / max(1, info['fps'])):
        raise ValueError('导出时长与选择区间不符，请核对源片时间信息')
    result = {'source_file': str(video), 'source_start': start, 'source_end': end,
              'actual_duration': actual['duration'], 'has_audio': actual['has_audio'],
              'preview': str(out), 'review_status': 'candidate_for_human_review'}
    sidecar.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--start', required=True, type=float)
    parser.add_argument('--end', required=True, type=float)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export_clip(args.video, args.start, args.end, args.out), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('导出失败：' + str(exc), file=sys.stderr)
        sys.exit(1)
