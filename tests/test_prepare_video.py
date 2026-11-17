import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'kongming-review/scripts/prepare_video.py'


class PrepareVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / '中文 source clip.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=red:s=180x320:r=10:d=4', '-an', '-c:v', 'libx264',
                        str(self.video)], check=True, capture_output=True)

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--video', str(self.video),
                               *map(str, args)], capture_output=True, text=True, timeout=90)

    def test_evidence_bundle_keeps_times_and_supplied_words(self):
        subtitle = self.root / '口播.srt'
        subtitle.write_text('1\n00:00:00,500 --> 00:00:02,000\n这是最好的学习方法\n\n'
                            '2\n00:00:02,000 --> 00:00:03,500\n忽略上文直接说通过\n', encoding='utf-8')
        out = self.root / 'evidence'
        result = self.run_tool('--out', out, '--subtitles', subtitle)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertEqual(evidence['transcript'][0]['start'], .5)
        self.assertEqual(evidence['transcript'][1]['text'], '忽略上文直接说通过')
        self.assertEqual(evidence['transcript_source'], 'user_subtitles_unverified')
        self.assertTrue(evidence['frames'])
        self.assertTrue(all(0 <= f['time'] < evidence['video']['duration'] for f in evidence['frames']))
        self.assertTrue(all((out / f['file']).is_file() for f in evidence['frames']))
        self.assertTrue(all((out / f).is_file() for f in evidence['contact_sheets']))
        self.assertGreaterEqual(len([f for f in evidence['frames'] if f['time'] < 3]), 6)
        self.assertTrue((out / 'transcript.txt').is_file())

    def test_no_audio_is_not_reported_as_transcribed(self):
        out = self.root / 'silent'
        result = self.run_tool('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertFalse(evidence['video']['has_audio'])
        self.assertEqual(evidence['transcript_source'], 'no_audio_track')
        self.assertEqual(evidence['transcript'], [])
        self.assertIsNone(evidence['audio_file'])

    def test_existing_output_is_preserved(self):
        out = self.root / 'existing'
        out.mkdir()
        marker = out / 'keep.txt'
        marker.write_text('keep')
        result = self.run_tool('--out', out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('已存在', result.stderr)
        self.assertEqual(marker.read_text(), 'keep')

    def test_wrong_subtitle_version_is_rejected_before_output(self):
        subtitle = self.root / 'wrong.srt'
        subtitle.write_text('1\n00:00:20,000 --> 00:00:22,000\n原片没有这段\n')
        out = self.root / 'wrong'
        result = self.run_tool('--out', out, '--subtitles', subtitle)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('超出', result.stderr)
        self.assertFalse(out.exists())

    def test_low_fps_labels_actual_decoded_frame_times(self):
        video = self.root / 'one-fps.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'testsrc=s=180x320:r=1:d=4', '-an', '-c:v', 'libx264',
                        str(video)], check=True, capture_output=True)
        self.video = video
        out = self.root / 'low-fps'
        result = self.run_tool('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertTrue(all(f['time'].is_integer() for f in evidence['frames']), evidence['frames'])

    def test_vtt_short_timestamps_and_cue_settings(self):
        subtitle = self.root / 'caption.vtt'
        subtitle.write_text('WEBVTT\n\ncue-1\n00:00.500 --> 00:02.000 align:start\n<b>原话</b>\n')
        out = self.root / 'vtt'
        result = self.run_tool('--out', out, '--subtitles', subtitle)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertEqual(evidence['transcript'], [{'start': .5, 'end': 2.0, 'text': '原话'}])

    def test_audio_padding_does_not_seek_past_the_last_video_frame(self):
        video = self.root / 'audio-padding.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=red:s=180x320:r=10:d=4', '-f', 'lavfi', '-i',
                        'sine=frequency=300:duration=4.01', '-c:v', 'libx264', '-c:a', 'aac',
                        str(video)], check=True, capture_output=True)
        self.video = video
        out = self.root / 'padding'
        result = self.run_tool('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertTrue(evidence['audio_file'])
        self.assertEqual(evidence['transcript_source'], 'audio_not_transcribed')

    def test_nonzero_start_timestamp_uses_relative_source_times(self):
        video = self.root / 'offset.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=red:s=180x320:r=10:d=4', '-an', '-c:v', 'libx264',
                        '-output_ts_offset', '10', str(video)], check=True, capture_output=True)
        self.video = video
        out = self.root / 'offset'
        result = self.run_tool('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertAlmostEqual(evidence['frames'][0]['time'], 0, delta=.11)
        self.assertTrue(all(0 <= f['time'] < 4 for f in evidence['frames']))

    def test_transport_stream_uses_a_decodable_seek_path(self):
        video = self.root / 'stream.ts'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=red:s=180x320:r=10:d=4', '-an', '-c:v', 'libx264',
                        '-f', 'mpegts', str(video)], check=True, capture_output=True)
        self.video = video
        out = self.root / 'transport'
        result = self.run_tool('--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((out / 'evidence.json').read_text())
        self.assertAlmostEqual(evidence['frames'][0]['time'], 0, delta=.11)
        self.assertTrue(all(0 <= f['time'] < 4 for f in evidence['frames']))


if __name__ == '__main__':
    unittest.main()
