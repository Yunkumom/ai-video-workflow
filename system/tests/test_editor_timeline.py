import unittest
from system.pipeline.editor_project import cue
from system.pipeline.editor_timeline import crop_rect, intervals, changed_media, trim_clip_with_cues, split_clip, delete_clip_with_cues
from system.tests.test_editor_project import fixture


class TimelineTests(unittest.TestCase):
    def test_crop_ratio_and_edges(self):
        for w,h in [(1920,1080),(1080,1920),(1000,1000),(1440,1080)]:
            for x in (0,.5,1):
                left,top,cw,ch=crop_rect(w,h,1080,1920,x)
                self.assertAlmostEqual(cw/ch,9/16)
                self.assertGreaterEqual(left,0); self.assertLessEqual(left+cw,w)

    def test_media_edit_invalidates_but_framing_does_not(self):
        import copy
        a=fixture(); b=copy.deepcopy(a); b['clips'][0]['framing']['vertical']['x']=.2
        self.assertFalse(changed_media(a,b))
        b['clips'][0]['start']=1
        self.assertTrue(changed_media(a,b))
        self.assertEqual(list(intervals(b))[0][2],5)

    def test_trim_remaps_and_clips_cues_atomically(self):
        doc=fixture(); doc['media']['source']['duration']=10; doc['clips'][0]['end']=10
        def item(name,start,end): return cue(name,start,end,original='',cue_id=name)
        doc['cues']=[item('before',.2,1),item('left',1.5,2.5),item('keep',3,4),item('right',7.5,8.5),item('after',9,9.5)]
        result=trim_clip_with_cues(doc,doc['clips'][0]['id'],2,8)
        self.assertEqual((result['clips'][0]['start'],result['clips'][0]['end']),(2,8))
        self.assertEqual([c['text'] for c in result['cues']],['left','keep','right'])
        self.assertEqual([(c['start'],c['end']) for c in result['cues']],[(0,.5),(1,2),(5.5,6)])
        self.assertIn('請核對文字與語音',result['cues'][0]['note'])
        self.assertIn('請核對文字與語音',result['cues'][2]['note'])
        self.assertEqual(result['sync'],'current')

    def test_trim_shifts_captions_in_later_clips(self):
        import copy
        doc=fixture(); doc['media']['source']['duration']=10; doc['clips'][0]['end']=5
        second=copy.deepcopy(doc['clips'][0]);second['id']='second';second['start']=5;second['end']=10;doc['clips'].append(second)
        text='later';doc['cues']=[cue(text,6,7,original=text,cue_id='later')]
        result=trim_clip_with_cues(doc,doc['clips'][0]['id'],1,5)
        self.assertEqual((result['cues'][0]['start'],result['cues'][0]['end']),(5,6))

    def test_split_preserves_timeline_and_independent_framing(self):
        doc=fixture(); clip_id=doc['clips'][0]['id']; result=split_clip(doc,clip_id,2.5)
        self.assertEqual(len(result['clips']),2); self.assertAlmostEqual(sum(x['end']-x['start'] for x in result['clips']),6)
        result['clips'][1]['framing']['vertical']['x']=.8
        self.assertEqual(result['clips'][0]['framing']['vertical']['x'],.5)
        self.assertEqual(result['cues'][0]['start'],doc['cues'][0]['start'])

    def test_delete_clip_removes_overlap_and_shifts_later_cues(self):
        import copy
        doc=fixture(); first=doc['clips'][0]; first['end']=3
        second=copy.deepcopy(first);second['id']='second';second['start']=3;second['end']=6;doc['clips'].append(second)
        doc['cues']=[cue('gone',.5,1.5,cue_id='gone'),cue('later',4,5,cue_id='later')]
        result=delete_clip_with_cues(doc,first['id'])
        self.assertEqual([x['text'] for x in result['cues']],['later'])
        self.assertEqual((result['cues'][0]['start'],result['cues'][0]['end']),(1,2))

    def test_word_aligned_trim_removes_cut_words_in_both_orientations(self):
        doc=fixture(); doc['cues']=[]
        words=[dict(text='one',start=.2,end=.8,startOffset=0,endOffset=3),
               dict(text='two',start=1.2,end=1.8,startOffset=4,endOffset=7),
               dict(text='three',start=2.2,end=2.8,startOffset=8,endOffset=13)]
        item=cue('one two three',.2,2.8,original='one two three',cue_id='words',words=words)
        for mode in ('horizontal','vertical'): item['appearances'][mode]['runs']=[dict(text='one two three',scale=1.2,color='#ffe34a',animation='none')]
        doc['cues']=[item]
        result=trim_clip_with_cues(doc,doc['clips'][0]['id'],1,6)
        kept=result['cues'][0]
        self.assertEqual(kept['text'],'two three')
        self.assertEqual(kept['appearances']['horizontal']['runs'][0]['text'],'two three')
        self.assertEqual(kept['appearances']['vertical']['runs'][0]['text'],'two three')
        self.assertEqual((kept['wordTimings'][0]['startOffset'],kept['wordTimings'][0]['endOffset']),(0,3))

    def test_word_aligned_delete_preserves_exact_boundary_words(self):
        import copy
        doc=fixture(); first=doc['clips'][0]; first['end']=2
        second=copy.deepcopy(first);second['id']='second';second['start']=2;second['end']=4;doc['clips'].append(second)
        words=[dict(text='keep',start=1.2,end=1.8,startOffset=0,endOffset=4),
               dict(text='drop',start=2.2,end=2.8,startOffset=5,endOffset=9)]
        item=cue('keep drop',1.2,2.8,original='keep drop',cue_id='words',words=words)
        doc['cues']=[item]
        result=delete_clip_with_cues(doc,second['id'])
        kept=result['cues'][0]
        self.assertEqual(kept['text'],'keep')
        self.assertEqual(kept['wordTimingState'],'valid')
        self.assertEqual(kept['appearances']['horizontal']['runs'][0]['text'],'keep')
        self.assertIn('逐字時間裁切',kept['note'])
