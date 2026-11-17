"""Run the toolchain with clearly labeled synthetic footage and example subtitles."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from prepare_video import prepare, run
from export_clip import export_clip


def demo(out):
    from PIL import Image, ImageDraw, ImageFont
    out = Path(out).expanduser().resolve()
    if out.exists():
        raise ValueError('演示输出目录已存在，请使用新目录')
    out.mkdir(parents=True)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=15)
    panels = [('INTRO', 'Team meeting notes'), ('KEY RESULT', '2 hours -> 40 minutes'),
              ('ONE RULE', 'Bring one solution')]
    for index, (title, text) in enumerate(panels):
        canvas = Image.new('RGB', (360, 640), '#101010')
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 360, 9), fill='#dc242c')
        draw.text((22, 50), 'SYNTHETIC DEMO', font=font, fill='#ff6068')
        draw.text((22, 84), 'NO SPEECH / TOOL TEST ONLY', font=small, fill='white')
        draw.text((22, 245), title, font=font, fill='white')
        draw.text((22, 294), text, font=font, fill='white')
        draw.text((22, 555), f'SOURCE {index * 3:02d}s - {(index + 1) * 3:02d}s',
                  font=small, fill='#a0a0a0')
        canvas.save(out / f'panel-{index}.png')
    source = out / 'source.mp4'
    args = []
    for index in range(3):
        args += ['-loop', '1', '-t', '3', '-i', out / f'panel-{index}.png']
    run([*args, '-filter_complex', '[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]',
         '-map', '[v]', '-r', '15', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-movflags', '+faststart', source])
    subtitles = out / 'example.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:03,000\n示例开场：今天聊开会\n\n'
                         '2\n00:00:03,000 --> 00:00:06,000\n示例结果：两小时缩到四十分钟\n\n'
                         '3\n00:00:06,000 --> 00:00:09,000\n示例做法：每人带一个解决方案\n', encoding='utf-8')
    prepare(SimpleNamespace(video=str(source), out=str(out / 'evidence'),
                            subtitles=str(subtitles), model=None, language='zh',
                            interval=2.0, max_frames=96))
    clip = export_clip(source, 3.0, 6.0, out / 'opening-candidate.mp4')
    result = {'synthetic': True, 'ai_review_performed': False,
              'description': '合成图卡，无原声；字幕是示例文字，非语音转写或真实客户案例。',
              'purpose': '验证安装、取材、字幕导入及明确区间的片段导出；不证明AI审片质量或传播效果。',
              'source': str(source), 'candidate': clip['preview']}
    (out / 'demo.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(demo(args.out), ensure_ascii=False))
    except (ImportError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('演示失败：' + str(exc), file=sys.stderr)
        sys.exit(1)
