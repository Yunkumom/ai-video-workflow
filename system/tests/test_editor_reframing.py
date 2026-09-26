"""Synthetic-only reframing validation and real FFmpeg filter checks."""
import copy
import json
import shutil
import subprocess
import unittest
from system.tests.test_editor_project import fixture
from system.pipeline.editor_project import validate
from system.pipeline.editor_render import scene_filter
from system.pipeline.editor_timeline import split_clip


class ReframingTests(unittest.TestCase):
    def test_roundtrip_and_legacy(self):
        doc = fixture()
        original = copy.deepcopy(doc)
        self.assertEqual(validate(doc), original)
        f = doc['clips'][0]['framing']['vertical']
        f.update(zoom=1.75, y=.2, x=.8)
        self.assertEqual(validate(json.loads(json.dumps(doc))), doc)
        split = split_clip(doc, doc['clips'][0]['id'], 3)
        self.assertEqual(split['clips'][0]['framing'], split['clips'][1]['framing'])

    def test_reject_invalid_transforms(self):
        for key, value in [('zoom', float('nan')), ('zoom', 0), ('zoom', 9), ('y', -1), ('y', True), ('unknown', 1)]:
            with self.subTest(key=key, value=value):
                doc = fixture(); doc['clips'][0]['framing']['vertical'][key] = value
                with self.assertRaises(ValueError): validate(doc)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg unavailable')
    def test_actual_filters_for_both_orientations(self):
        for size in [(180, 320), (320, 180)]:
            for frame in [dict(mode='crop', x=.1, y=.8, zoom=1.5), dict(mode='crop', x=.5, y=.5, zoom=.32), dict(mode='extend', x=.8, y=.2, zoom=1.4)]:
                with self.subTest(size=size, frame=frame):
                    result = subprocess.run(['ffmpeg','-v','error','-filter_complex_threads','1','-f','lavfi','-i','testsrc2=size=640x360:rate=1','-filter_complex','[0:v]'+scene_filter(frame,*size),'-map','[v]','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],capture_output=True)
                    self.assertEqual(result.returncode,0,result.stderr.decode())
                    self.assertEqual(len(result.stdout),size[0]*size[1]*3)
