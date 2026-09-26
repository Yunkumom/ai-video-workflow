from __future__ import annotations

import io
import json
import threading
import http.client
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from system.app import WorkflowController, _parse_cues, create_server
from system.pipeline.models import ProjectError, SubtitleCue
from system.pipeline.workspace import validate_assistant_request, validate_proposal, render_clip, assistant_proposal, network_readiness
from system.pipeline.transcription import audio_windows, transcribe_groq, groq_payload_to_cues
from system.pipeline.media import MediaInfo


class WorkspaceTests(unittest.TestCase):
    def test_missing_key_is_reported_before_job_without_exposing_credentials(self):
        result=network_readiness({})
        self.assertFalse(result['transcriptionReady']);self.assertIn('GROQ_API_KEY',result['message'])
        configured=network_readiness({'GROQ_API_KEY':'synthetic-private-value'})
        self.assertTrue(configured['transcriptionReady'])
        self.assertNotIn('synthetic-private-value',json.dumps(configured))
        with tempfile.TemporaryDirectory() as directory, patch('system.pipeline.workspace.os.environ',{}):
            controller=WorkflowController(Path(directory),token='synthetic')
            controller.import_media('clip','a.mp4',io.BytesIO(b'x'),1)
            with self.assertRaisesRegex(ProjectError,'GROQ_API_KEY'):
                controller.start_analyze({'projectId':'clip','approved':True})
            self.assertEqual(controller._jobs,{})

    def test_photo_render_loops_only_one_source_with_requested_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'a.jpg';source.touch()
            with patch('system.pipeline.workspace.probe_media',return_value=MediaInfo(7,641,361,False,True)), patch('system.pipeline.workspace.require_tool',return_value='ffmpeg'), patch('system.pipeline.workspace.run_command') as run, patch('system.pipeline.workspace.render_with_subtitles') as render:
                render_clip(source,root/'3_output'/'photo',root/'2_processing'/'photo','photo',[SubtitleCue(0,2,'照片字幕')],'S01',still_duration=7)
                command=run.call_args.args[0]
                self.assertEqual(command.count(str(source)),1);self.assertIn('-loop',command);self.assertIn('7.000000',command)
                self.assertEqual(render.call_args.kwargs['info'].duration,7)
                self.assertFalse(render.call_args.kwargs['info'].has_audio)
            with self.assertRaises(ProjectError):render_clip(source,root/'out',root/'processing','photo',[],'S01',still_duration=float('nan'))

    def test_new_http_actions_require_token_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=WorkflowController(Path(directory),token='synthetic-token')
            server=create_server(controller,port=0)
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            try:
                for route in ('analyze','render','assistant','review/render-assets','review/export'):
                    connection=http.client.HTTPConnection(*server.server_address,timeout=2)
                    connection.request('POST','/api/'+route,body='{}',headers={'Content-Type':'application/json'})
                    response=connection.getresponse(); response.read()
                    self.assertEqual(response.status,403); connection.close()
                self.assertEqual(controller._jobs,{})
            finally:
                server.shutdown(); server.server_close(); worker.join(2)

    def test_ai_service_uses_only_explicit_payload_and_rejects_incomplete_response(self):
        request={'action':'correct','approved':True,'items':[{'index':0,'text':'錯自','note':'應為錯字'}]}
        with patch('system.pipeline.workspace.os.environ',{'GROQ_API_KEY':'synthetic-test-value'}), patch('system.pipeline.workspace.urllib.request.build_opener') as opener:
            def response(finish):
                return json.dumps({'choices':[{'finish_reason':finish,'message':{'content':json.dumps({'changes':[{'index':0,'text':'錯字'}]})}}]}).encode()
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=response('stop')
            self.assertEqual(assistant_proposal(request),{'changes':[{'index':0,'text':'錯字'}]})
            sent=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(json.loads(sent['messages'][1]['content']),request['items'])
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=response('length')
            with self.assertRaises(ProjectError): assistant_proposal(request)

    def test_all_audio_chunks_offset_and_failure_does_not_write_partial_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); output=root/'recognized.srt'
            environment={'AI_VIDEO_ALLOW_NETWORK':'1','GROQ_API_KEY':'synthetic-test-value'}
            with patch('system.pipeline.transcription.require_tool',return_value='ffmpeg'), patch('system.pipeline.transcription.subprocess.run') as extract, patch('system.pipeline.transcription._request_transcription') as request:
                extract.return_value.returncode=0
                request.side_effect=[[SubtitleCue(1,2,'第一段')],[],[SubtitleCue(1,2,'最後段')]]
                transcribe_groq(root/'fake.mp4',output,root,duration=1250,environment=environment)
                self.assertEqual(extract.call_count,3)
                self.assertIn('00:20:01,000 --> 00:20:02,000',output.read_text())
                original=output.read_text()
                request.side_effect=[[SubtitleCue(1,2,'不完整')],ProjectError('synthetic failure')]
                with self.assertRaises(ProjectError):
                    transcribe_groq(root/'fake.mp4',output,root,duration=1250,environment=environment)
                self.assertEqual(output.read_text(),original)

    def test_invalid_transcription_timestamps_are_rejected(self):
        for start,end in ((0,float('inf')),(-1,2),(float('nan'),3)):
            with self.assertRaises(ProjectError):
                groq_payload_to_cues({'segments':[{'start':start,'end':end,'text':'字'}]})

    def test_extreme_times_and_nonstring_ai_action_rejected_cleanly(self):
        with self.assertRaises(ProjectError): _parse_cues([{'start':10**400,'end':10**401,'text':'字'}])
        with self.assertRaises(ProjectError): validate_assistant_request({'action':[],'approved':True,'items':[]})

    def test_full_audio_windows_cover_long_video_once(self):
        self.assertEqual(audio_windows(1250), [(0.0,600.0),(600.0,600.0),(1200.0,50.0)])
        for duration in (0, float('inf'), float('nan'), -1):
            with self.assertRaises(ProjectError): audio_windows(duration)

    def test_server_rejects_nonfinite_cue_times(self):
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ProjectError):
                _parse_cues([{'start':value,'end':value,'text':'test'}])

    def test_assistant_requires_exact_scope_and_validates_order_and_changes(self):
        payload = {'action':'order','approved':False,'items':[{'id':'a','name':'2.mp4'},{'id':'b','name':'1.mp4'}]}
        with self.assertRaises(ProjectError): validate_assistant_request(payload)
        payload['approved'] = True
        validate_assistant_request(payload)
        self.assertEqual(validate_proposal(payload, {'order':['b','a']}), {'order':['b','a']})
        for invalid in ({'order':['a','a']},{'order':['a']},{'order':['a','b'],'extra':1}):
            with self.assertRaises(ProjectError): validate_proposal(payload,invalid)
        correction={'action':'correct','approved':True,'items':[{'index':0,'text':'原字','note':'改成正字'}]}
        self.assertEqual(validate_proposal(correction,{'changes':[{'index':0,'text':'正字'}]})['changes'][0]['text'],'正字')
        with self.assertRaises(ProjectError):
            validate_proposal(correction,{'changes':[{'index':5,'text':'no'}]})

    def test_analyze_has_its_own_job_and_no_render_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); controller=WorkflowController(root,token='test')
            controller.import_media('clip-a','same.mp4',io.BytesIO(b'a'),1)
            controller.import_media('clip-b','same.mp4',io.BytesIO(b'b'),1)
            def analyze(source, processing_dir, *, approved, progress):
                self.assertFalse(approved)
                progress('synthetic complete')
                return {'cues':[{'start':0,'end':1,'text':source.parent.name}], 'duration':1,'width':640,'height':360}
            with patch('system.app.analyze_clip',side_effect=analyze):
                a=controller.start_analyze({'projectId':'clip-a','approved':False})
                b=controller.start_analyze({'projectId':'clip-b','approved':False})
                for job_id,name in ((a,'clip-a'),(b,'clip-b')):
                    job=controller.wait_for_job(job_id,2)
                    self.assertEqual(job['result']['cues'][0]['text'],name)
                    self.assertEqual(job['status'],'complete')
                    with self.assertRaises(ProjectError): controller.open_output(job_id)
            self.assertFalse((root/'3_output').exists())

    def test_render_does_not_cut_or_join_source_and_rejects_out_of_range_cues(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'one.mp4'; source.touch()
            info=MediaInfo(4,640,360,True)
            with patch('system.pipeline.workspace.probe_media',return_value=info), patch('system.pipeline.workspace.render_with_subtitles') as render:
                render_clip(source,root/'output',root/'processing','clip',[SubtitleCue(0,4,'字幕')],'S01')
                self.assertEqual(render.call_args.args[0],source)
                self.assertEqual(render.call_args.kwargs['info'].duration,4)
                with self.assertRaises(ProjectError):
                    render_clip(source,root/'output',root/'processing','clip',[SubtitleCue(0,9,'字幕')],'S01')


if __name__ == '__main__': unittest.main()
