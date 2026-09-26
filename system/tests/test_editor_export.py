"""Synthetic fixtures only: editor formatting, versioning, HTTP, and real MP4."""
import copy
import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from system.pipeline.models import ProjectError


def fixture():
    style = dict(font='PingFang TC', size=6, weight=900, stroke=.07)
    return dict(schema='shine.project-subtitle-review.v2', revision=2,
                source='sample.mov', duration=2.0,
                styles=dict(horizontal=style, vertical={**style, 'size': 8}),
                cues=[dict(id=1, start=.2, end=1.8, text='字幕 Test',
                           original='字幕 Test', note='', size=1.2,
                           runs=[dict(text='字幕 ', scale=1), dict(text='Test', scale=1.5)])])


def framing_fixture():
    document = fixture()
    document.update(schema='shine.project-subtitle-review.v3', revision=3,
                    framing={'vertical': {'segments': [
                        {'start': 0.0, 'end': 2.0, 'mode': 'crop', 'positionX': 0.5}
                    ]}})
    return document


class EditorExportTests(unittest.TestCase):
    def api(self):
        from system import editor_export
        return editor_export

    def test_convert_both_orientation_and_word_sizes(self):
        api = self.api()
        doc = api.validate_editor(fixture())
        h, v = [api.native_document(doc, x) for x in ('horizontal', 'vertical')]
        self.assertEqual(h['style']['sizePct'], 6)
        self.assertEqual(v['style']['sizePct'], 8)
        self.assertAlmostEqual(h['cues'][0]['runs'][1]['style']['sizeScale'], 1.8)
        self.assertEqual(h['cues'][0]['text'], '字幕 Test')

    def test_legacy_document_migrates_without_changing_appearance(self):
        api = self.api()
        migrated = api.normalize_editor(fixture())
        self.assertEqual((migrated['schema'], migrated['revision']),
                         ('shine.project-subtitle-review.v3', 3))
        self.assertEqual(migrated['framing']['vertical']['segments'], [
            {'start': 0.0, 'end': 2.0, 'mode': 'extend', 'positionX': 0.5}
        ])

    def test_crop_geometry_tracks_left_center_and_right(self):
        api = self.api()
        left = api.crop_geometry(1920, 1080, 0)
        center = api.crop_geometry(1920, 1080, .5)
        right = api.crop_geometry(1920, 1080, 1)
        self.assertEqual(left, (0, 0, 606, 1080))
        self.assertEqual(center, (656, 0, 606, 1080))
        self.assertEqual(right, (1314, 0, 606, 1080))

    def test_probe_media_uses_display_rotation_for_orientation(self):
        from system.pipeline import media
        payload = {'streams': [
            {'codec_type': 'video', 'width': 1920, 'height': 1080,
             'side_data_list': [{'rotation': -90}]},
            {'codec_type': 'audio'}
        ], 'format': {'duration': '2'}}
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
        with patch('system.pipeline.media.require_tool', return_value='ffprobe'), \
             patch('system.pipeline.media.subprocess.run', return_value=completed):
            info = media.probe_media(Path('/tmp/rotated.mov'))
        self.assertEqual((info.width, info.height), (1080, 1920))
        self.assertTrue(info.has_audio)

    def test_invalid_framing_is_rejected(self):
        api = self.api()
        mutations = [
            lambda d: d['framing']['vertical'].update(extra=True),
            lambda d: d['framing']['vertical']['segments'][0].update(positionX=float('nan')),
            lambda d: d['framing']['vertical']['segments'][0].update(positionX=True),
            lambda d: d['framing']['vertical']['segments'][0].update(mode='follow'),
            lambda d: d['framing']['vertical']['segments'][0].update(end=1.5),
            lambda d: d['framing']['vertical']['segments'].append(
                {'start': 1.4, 'end': 2.0, 'mode': 'crop', 'positionX': .5}),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = framing_fixture(); mutate(document)
                with self.assertRaises(ProjectError):
                    api.validate_editor(document)

    def test_invalid_work_rejected(self):
        api = self.api()
        for mutate in [lambda d: d.update(extra=True),
                       lambda d: d.update(source='../sample.mov'),
                       lambda d: d.update(duration=float('nan')),
                       lambda d: d['cues'][0].update(end=3),
                       lambda d: d['cues'][0]['runs'][0].update(text='wrong'),
                       lambda d: d['cues'][0]['runs'][0].update(scale=True),
                       lambda d: d['styles']['horizontal'].update(font='x;bad'),
                       lambda d: d['cues'].append(copy.deepcopy(d['cues'][0]))]:
            with self.subTest(mutate=mutate):
                d = fixture(); mutate(d)
                with self.assertRaises(ProjectError): api.validate_editor(d)

    def setup_project(self, root):
        release = root / '3_output' / 'example' / 'tutorial_v1'
        source = root / '1_input' / 'example' / 'sample.mov'
        source.parent.mkdir(parents=True)
        release.mkdir(parents=True)
        source.touch()
        (release / 'editor.html').write_text('<!doctype html><html><head></head><body></body></html>')
        return self.api().ExportController(root, 'example', 'tutorial_v1')

    def test_version_reservation_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            c = self.setup_project(Path(temp))
            (c.release / 'example_horizontal_v4.mp4').write_bytes(b'keep')
            self.assertEqual(c.reserve_version(), 5)
            self.assertEqual(c.reserve_version(), 6)
            self.assertEqual((c.release / 'example_horizontal_v4.mp4').read_bytes(), b'keep')
            with ThreadPoolExecutor(4) as pool:
                versions = list(pool.map(lambda _: c.reserve_version(), range(4)))
            self.assertEqual(len(set(versions)), 4)

    def test_render_failure_exposes_no_partial_download(self):
        with tempfile.TemporaryDirectory() as temp:
            c = self.setup_project(Path(temp))
            c.jobs['test'] = dict(status='running', version=2, downloads=[])
            with patch('system.editor_export.render_movie', side_effect=ProjectError('render failed')):
                c.run('test', fixture())
            self.assertEqual(c.jobs['test']['status'], 'failed')
            self.assertEqual(c.downloads, {})
            self.assertFalse(list(c.release.glob('*_v2.mp4')))

    def test_success_saves_both_movies_and_matching_editable_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            c = self.setup_project(Path(temp))
            (c.release / 'editor.html').write_text('<html><script id="project-data" type="application/json">{}</script></html>')
            c.jobs['test'] = dict(status='running', version=2, downloads=[])
            def render(source, document, mode, work, output, progress): output.write_bytes(mode.encode())
            doc = fixture()
            with patch('system.editor_export.render_movie', side_effect=render): c.run('test', doc)
            self.assertEqual(c.jobs['test']['status'], 'complete')
            self.assertEqual(len(c.jobs['test']['downloads']), 4)
            saved = json.loads((c.release / 'example_v2.subtitle-workspace.json').read_text())
            self.assertEqual(saved, self.api().normalize_editor(doc))
            self.assertIn('"scale": 1.5', (c.release / 'example_v2.editor.html').read_text())

    def test_http_token_origin_download_and_range(self):
        with tempfile.TemporaryDirectory() as temp:
            c = self.setup_project(Path(temp))
            server = self.api().create_server(c)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            self.addCleanup(conn.close)
            conn.request('POST', '/api/export', body='{}', headers={'Content-Type': 'application/json'})
            r = conn.getresponse(); self.assertEqual(r.status, 403); r.read()
            conn.request('GET', '/editor.html', headers={'Origin': 'https://other.invalid'})
            r = conn.getresponse(); self.assertEqual(r.status, 403); r.read()
            conn.request('GET', '/editor.html')
            r = conn.getresponse(); self.assertEqual(r.status, 200)
            self.assertIn(b'export-config', r.read())
            headers = {'X-Workflow-Token': c.token}
            conn.request('GET', '/download/../../source.mov', headers=headers)
            r = conn.getresponse(); self.assertEqual(r.status, 404); r.read()
            path = c.release / 'example_horizontal_v2.mp4'; path.write_bytes(b'0123456789')
            c.downloads[path.name] = path
            conn.request('GET', '/download/' + path.name, headers={**headers, 'Range': 'bytes=2-5'})
            r = conn.getresponse(); self.assertEqual(r.status, 206)
            self.assertEqual(r.read(), b'2345')
            self.assertIn('attachment', r.getheader('Content-Disposition'))

    def test_real_render_has_both_geometry_and_full_audio(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'sample.mov'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=30:d=2',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True)
            for mode, size in [('horizontal', (640, 360)), ('vertical', (360, 640))]:
                target = root / (mode + '.mp4')
                api.render_movie(source, fixture(), mode, root / mode, target, lambda *_: None, size=size)
                info = api.probe_media(target)
                self.assertEqual((info.width, info.height), size)
                self.assertTrue(info.has_audio)
                self.assertLess(abs(info.duration - 2), .1)
                self.assertTrue((root / mode / 'caption-0001.png').is_file())
                api.verify_movie(target, 2, size, True)

    def test_vertical_crop_uses_segment_position(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'columns.mov'; target = root / 'vertical.mp4'
            subprocess.run([
                'ffmpeg', '-v', 'error', '-f', 'lavfi',
                '-i', 'color=c=black:s=320x240:r=30:d=2', '-f', 'lavfi',
                '-i', 'sine=frequency=440:duration=2', '-vf',
                'drawbox=x=0:y=0:w=107:h=240:color=red:t=fill,'
                'drawbox=x=107:y=0:w=106:h=240:color=green:t=fill,'
                'drawbox=x=213:y=0:w=107:h=240:color=blue:t=fill',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)
            ], check=True)
            document = framing_fixture()
            document['styles']['vertical'].update(font='Arial', size=6)
            document['cues'][0].update(text='T', original='T', size=1,
                                       runs=[{'text': 'T', 'scale': 1}])
            document['framing']['vertical']['segments'] = [
                {'start': 0.0, 'end': 1.0, 'mode': 'crop', 'positionX': 0.0},
                {'start': 1.0, 'end': 2.0, 'mode': 'crop', 'positionX': 1.0},
            ]
            api.render_movie(source, document, 'vertical', root / 'work', target,
                             lambda *_: None, size=(360, 640))

            def pixel(at):
                result = subprocess.run([
                    'ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(target),
                    '-frames:v', '1', '-vf', 'crop=1:1:180:320,format=rgb24',
                    '-f', 'rawvideo', '-'
                ], check=True, capture_output=True)
                return tuple(result.stdout[:3])

            left, right = pixel(.5), pixel(1.5)
            self.assertGreater(left[0], left[2] * 3)
            self.assertGreater(right[2], right[0] * 3)

    def test_outline_does_not_paint_over_white_lettering(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); white_counts = []
            for stroke in (.02, .12):
                doc = fixture(); doc['styles']['horizontal'].update(font='Arial', size=14, stroke=stroke)
                doc['cues'][0].update(text='TEST', size=1, runs=[dict(text='TEST', scale=1)])
                work = root / str(stroke); work.mkdir()
                path = work / 'native.json'; path.write_text(json.dumps(api.native_document(doc, 'horizontal')))
                subprocess.run(['swift', str(Path(api.__file__).parent/'pipeline/review_caption_images.swift'),
                                '--input', str(path), '--output-dir', str(work), '--width', '640', '--height', '360'],
                               check=True, capture_output=True,
                               env={**os.environ, 'CLANG_MODULE_CACHE_PATH': str(root/'swift-cache')})
                pixels = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(work/'caption-0001.png'),
                                         '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], check=True, capture_output=True).stdout
                white_counts.append(sum(1 for i in range(0, len(pixels), 4)
                                        if min(pixels[i:i+3]) > 245 and pixels[i+3] > 245))
            self.assertGreater(white_counts[0], 100)
            self.assertGreater(white_counts[1], white_counts[0]*.9,
                               'A thicker black outline must not cover the white glyph fill')


if __name__ == '__main__': unittest.main()
