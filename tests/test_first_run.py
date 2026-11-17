import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import imageio_ffmpeg

SCRIPTS = Path(__file__).resolve().parents[1] / 'kongming-review/scripts'


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              capture_output=True, text=True, timeout=120)

    def make_video(self):
        path = self.root / 'original.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=red:s=180x320:r=10:d=6', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=6', '-c:v', 'libx264', '-c:a', 'aac',
                        str(path)], check=True, capture_output=True)
        return path

    def test_doctor_distinguishes_basic_readiness_from_unconfigured_asr(self):
        result = self.invoke('doctor.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertTrue(status['ready'])
        self.assertFalse(status['transcription_ready'])
        self.assertEqual(status['ai_review'], 'requires_host_capabilities')

    def test_doctor_rejects_a_requested_missing_model(self):
        result = self.invoke('doctor.py', '--model', self.root / 'missing.bin')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, '自查必须返回可读的检查结果')
        status = json.loads(result.stdout)
        self.assertFalse(status['ready'])
        self.assertFalse(status['transcription_ready'])

    def test_export_keeps_the_requested_duration_and_audio(self):
        video = self.make_video()
        out = self.root / 'candidate.mp4'
        result = self.invoke('export_clip.py', '--video', video, '--start', '1.2',
                             '--end', '4.2', '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(out.is_file())
        self.assertAlmostEqual(report['actual_duration'], 3.0, delta=.15)
        self.assertTrue(report['has_audio'])
        self.assertEqual(report['source_start'], 1.2)
        self.assertEqual(report['source_end'], 4.2)
        self.assertTrue(out.with_suffix('.source.json').is_file())

    def test_export_rejects_out_of_range_and_preserves_existing_output(self):
        video = self.make_video()
        out = self.root / 'candidate.mp4'
        result = self.invoke('export_clip.py', '--video', video, '--start', '4',
                             '--end', '12', '--out', out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('时间', result.stderr)
        self.assertFalse(out.exists())
        out.write_bytes(b'keep')
        result = self.invoke('export_clip.py', '--video', video, '--start', '1',
                             '--end', '4', '--out', out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('已存在', result.stderr)
        self.assertEqual(out.read_bytes(), b'keep')

    def test_export_contains_the_selected_scene(self):
        video = self.root / 'red-then-blue.mp4'
        binary = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([binary, '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=red:s=180x320:r=10:d=3', '-f', 'lavfi', '-i',
                        'color=c=blue:s=180x320:r=10:d=3', '-filter_complex',
                        '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]',
                        '-c:v', 'libx264', str(video)], check=True, capture_output=True)
        out = self.root / 'blue.mp4'
        result = self.invoke('export_clip.py', '--video', video, '--start', '3',
                             '--end', '6', '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = subprocess.run([binary, '-v', 'error', '-ss', '0.5', '-i', str(out),
                                  '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                                  'pipe:1'], check=True, capture_output=True).stdout
        red, green, blue = decoded[:3]
        self.assertGreater(blue, 220)
        self.assertLess(red, 20)

    def test_export_handles_transport_stream_with_nonzero_start(self):
        video = self.root / 'stream.ts'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=blue:s=180x320:r=10:d=4', '-an', '-c:v', 'libx264',
                        '-f', 'mpegts', str(video)], check=True, capture_output=True)
        result = self.invoke('export_clip.py', '--video', video, '--start', '.5',
                             '--end', '3.5', '--out', self.root / 'stream-preview.mp4')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertAlmostEqual(json.loads(result.stdout)['actual_duration'], 3, delta=.15)

    def test_demo_runs_the_toolchain_and_identifies_synthetic_content(self):
        out = self.root / 'demo'
        result = self.invoke('demo.py', '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        demo = json.loads((out / 'demo.json').read_text())
        self.assertTrue(demo['synthetic'])
        self.assertFalse(demo['ai_review_performed'])
        self.assertTrue((out / 'source.mp4').is_file())
        self.assertTrue((out / 'opening-candidate.mp4').is_file())
        evidence = json.loads((out / 'evidence/evidence.json').read_text())
        self.assertTrue(evidence['frames'])
        self.assertEqual(evidence['transcript_source'], 'user_subtitles_unverified')
        clip = json.loads((out / 'opening-candidate.source.json').read_text())
        self.assertEqual((clip['source_start'], clip['source_end']), (3.0, 6.0))
        self.assertAlmostEqual(clip['actual_duration'], 3.0, delta=.15)


if __name__ == '__main__':
    unittest.main()
