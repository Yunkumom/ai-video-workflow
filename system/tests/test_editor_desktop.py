import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import time
from unittest.mock import patch
from pathlib import Path
from system.desktop_server import Controller, create_server
from system.pipeline.editor_project import empty
from system.tests.test_editor_project import fixture


class DesktopTests(unittest.TestCase):
    def test_release_uses_media_snapshot_and_completion_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');d=fixture();source=c.input/'sample.mp4';source.write_bytes(b'original-media');c.sources['source']=source
            seen=[]
            def renderer(doc,sources,mode,work,target,progress):
                self.assertNotEqual(sources['source'],source)
                self.assertEqual(sources['source'].read_bytes(),b'original-media')
                self.assertEqual(c.history(),[])
                target.write_bytes(mode.encode());seen.append(mode);return []
            with patch('system.desktop_server.metadata',return_value=d['media']['source']),patch('system.desktop_server.render',side_effect=renderer):
                c.save(d);job=c.start_render(d)
                deadline=time.monotonic()+5
                while job['status']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(job['status'],'complete',job['message']);self.assertEqual(len(c.history()),1)
            self.assertEqual(seen,['horizontal','vertical']);self.assertEqual(source.read_bytes(),b'original-media')

    def test_single_orientation_release_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');d=fixture();source=c.input/'sample.mp4';source.write_bytes(b'media');c.sources['source']=source
            def renderer(doc,sources,mode,work,target,progress): target.write_bytes(mode.encode());return []
            with patch('system.desktop_server.metadata',return_value=d['media']['source']),patch('system.desktop_server.render',side_effect=renderer):
                c.save(d);job=c.start_render(d,['vertical'])
                deadline=time.monotonic()+5
                while job['status']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(job['status'],'complete',job['message'])
            self.assertEqual(job['movies'],['test_V1_直式.mp4'])
            self.assertEqual(c.history()[0]['modes'],['vertical'])
    def test_save_reopen_and_partial_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');d=empty('test');d['revision']=3;c.save(d)
            self.assertEqual(Controller(Path(tmp),'test').doc['revision'],3)
            (c.output/'保存區'/'V1').mkdir();(c.output/'test_V1_橫式.mp4').touch()
            self.assertEqual(c.history(),[])
    def test_damaged_latest_recovers_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');d=empty('test');d['revision']=3;c.save(d)
            d['revision']=4;c.save(d);c.document.write_text('{damaged')
            self.assertEqual(Controller(Path(tmp),'test').doc['revision'],3)
            self.assertEqual(len(list(c.saved.glob('damaged-project-*.json'))),1)
    def test_http_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');server=create_server(c);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            def request(path,headers={},body=None):
                data=json.dumps(body).encode() if body is not None else None
                return urllib.request.urlopen(urllib.request.Request(url+path,headers=headers,data=data))
            try:
                with request('/') as r:
                    self.assertIn('text/html',r.headers['Content-Type']);self.assertIn(b'Video Editor',r.read())
                with self.assertRaises(urllib.error.HTTPError):request('/api/project')
                headers={'X-Workflow-Token':c.token}
                with request('/api/project',headers) as r:self.assertEqual(json.load(r)['schema'],empty('test')['schema'])
                with self.assertRaises(urllib.error.HTTPError):request('/api/project',{**headers,'Origin':'https://invalid.example'})
                with self.assertRaises(urllib.error.HTTPError):request('/native/import',headers,{'paths':['/tmp/not-allowed.mp4']})
                with self.assertRaises(urllib.error.HTTPError):request('/media/../../etc/passwd',headers)
            finally:server.shutdown();server.server_close();thread.join()

    def test_import_files_standardized_naming(self):
        import copy, datetime
        with tempfile.TemporaryDirectory() as tmp:
            c = Controller(Path(tmp), 'campus_entrance')
            p1 = Path(tmp) / 'IMG_0001.mov'; p1.write_bytes(b'video1')
            p2 = Path(tmp) / 'IMG_0002.jpg'; p2.write_bytes(b'photo2')
            meta_v = dict(name='IMG_0001.mov', kind='video', duration=10.0, width=1920, height=1080, audio=True)
            meta_p = dict(name='IMG_0002.jpg', kind='photo', duration=5.0, width=1920, height=1080, audio=False)
            dt_v = datetime.datetime(2019, 12, 3, 10, 0, 0)
            dt_p = datetime.datetime(2019, 12, 3, 10, 5, 0)
            with patch('system.desktop_server.metadata', side_effect=lambda p: copy.deepcopy(meta_p if str(p).endswith('.jpg') else meta_v)), \
                 patch('system.pipeline.media_naming.extract_media_datetime', side_effect=lambda p: (dt_p if str(p).endswith('.jpg') else dt_v, 'mock')):
                imported = c.import_files([str(p1), str(p2)])
            self.assertEqual(len(imported), 2)
            self.assertEqual(imported[0]['media']['name'], '20191203_campus_entrance_001.mov')
            self.assertEqual(imported[0]['media']['originalName'], 'IMG_0001.mov')
            self.assertEqual(imported[1]['media']['name'], '20191203_campus_entrance_002.jpg')
            self.assertEqual(imported[1]['media']['originalName'], 'IMG_0002.jpg')
            self.assertTrue(c.sources[imported[0]['id']].exists())
            self.assertTrue(c.sources[imported[1]['id']].exists())

