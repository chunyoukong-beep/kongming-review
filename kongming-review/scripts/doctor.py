"""Check first-run requirements without installing packages or downloading models."""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from prepare_video import ffmpeg


def check(model_file=None):
    checks = [{'id': 'python', 'ok': sys.version_info >= (3, 10), 'required': True,
               'detail': sys.version.split()[0]}]
    pillow = importlib.util.find_spec('PIL') is not None
    checks.append({'id': 'pillow', 'ok': pillow, 'required': True,
                   'detail': '已安装' if pillow else '请安装 requirements.txt 中的依赖'})
    try:
        binary = ffmpeg()
        result = subprocess.run([binary, '-version'], capture_output=True, text=True, timeout=10)
        ffmpeg_ok = result.returncode == 0
        detail = result.stdout.splitlines()[0] if result.stdout else 'FFmpeg无法启动'
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        ffmpeg_ok, detail = False, str(exc)
    checks.append({'id': 'ffmpeg', 'ok': ffmpeg_ok, 'required': True, 'detail': detail})
    asr = importlib.util.find_spec('pywhispercpp') is not None
    model = bool(model_file and Path(model_file).expanduser().is_file())
    checks.extend([
        {'id': 'local_asr_package', 'ok': asr, 'required': bool(model_file),
         'detail': '已安装' if asr else '可选：安装pywhispercpp，或导入已有字幕'},
        {'id': 'local_asr_model', 'ok': model, 'required': bool(model_file),
         'detail': '已提供本地模型文件；兼容性仍须实际转写验证' if model else '未提供可用模型，可使用已有字幕'}])
    return {'ready': all(c['ok'] for c in checks if c['required']),
            'transcription_ready': asr and model, 'checks': checks,
            'ai_review': 'requires_host_capabilities',
            'notice': '此检查验证基础工具及转写依赖；不验证模型内容、AI图像理解、音频理解或云端额度。'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Optional existing local Whisper GGML model')
    args = parser.parse_args()
    status = check(args.model)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    sys.exit(0 if status['ready'] else 1)
