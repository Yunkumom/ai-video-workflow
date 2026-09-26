import tempfile
import unittest
from pathlib import Path
from system.pipeline.editor_project import empty,clip,cue
from system.pipeline.editor_render import ffmpeg,render
from system.desktop_server import metadata


class MixedRenderTests(unittest.TestCase):
    def test_mixed_photo_video_captionless_audio_continuity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);v=p/'v.mp4';photo=p/'p.png'
            ffmpeg(['-f','lavfi','-i','color=red:s=320x180:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-t','1',str(v)])
            ffmpeg(['-f','lavfi','-i','color=blue:s=180x320','-frames:v','1',str(photo)])
            d=empty('synthetic');d['media']={'v':metadata(v),'p':metadata(photo)}
            d['clips']=[clip(k,m) for k,m in d['media'].items()];d['clips'][1]['end']=.5
            out=p/'out.mp4';render(d,{'v':v,'p':photo},'vertical',p/'work',out,size=(180,320))
            self.assertTrue(out.is_file())
            ffmpeg(['-i',str(out),'-f','null','-'])
            d['cues']=[cue('Hello 世界',0.,1.,cue_id='animated')]
            d['cues'][0]['appearances']['vertical']['runs'][0].update(scale=1.5,color='#ffe34a',animation='pop')
            animated=p/'animated.mp4';render(d,{'v':v,'p':photo},'vertical',p/'animated-work',animated,size=(180,320))
            first=ffmpeg(['-i',str(animated),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            middle=ffmpeg(['-ss','0.1','-i',str(animated),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            self.assertTrue(first != middle, 'Pop-in must change actual encoded frames, not only the browser.')
