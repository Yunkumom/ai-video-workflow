import unittest
from system.pipeline.editor_project import SCHEMA, empty, clip, cue, validate, migrate_review


def fixture():
    doc = empty('test')
    doc['media']['source'] = dict(name='sample.mp4', kind='video', duration=6., width=640, height=360, audio=True)
    doc['clips'] = [clip('source', doc['media']['source'])]
    doc['cues'] = [cue('Hello 世界', 0., 2., original='', note='owner note', cue_id='cue1')]
    return doc


class ProjectTests(unittest.TestCase):
    def test_empty_and_captionless(self):
        validate(empty('x'))
        validate(empty('永大丟魚網'))
        with self.assertRaises(ValueError): validate(empty('../escaped'))
        doc = fixture(); doc['cues'] = []; validate(doc, render=True)

    def test_precise_cue_diagnostics(self):
        doc = fixture(); doc['cues'][0]['end'] = 8
        with self.assertRaisesRegex(ValueError, '001'): validate(doc)
        doc['sync'] = 'stale'; validate(doc)
        with self.assertRaises(ValueError): validate(doc, render=True)

    def test_style_runs_and_unknown_fields(self):
        doc = fixture(); doc['cues'][0]['appearances']['horizontal']['runs'][0]['text'] = 'lost'
        with self.assertRaises(ValueError): validate(doc)
        doc = fixture(); doc['secret'] = 'unexpected'
        with self.assertRaises(ValueError): validate(doc)

    def test_migration_keeps_owner_note(self):
        old = dict(cues=[dict(id=1, start=0, end=1, text='hello', note='辨識信心較低，請對照原聲。 人名要修正')])
        doc = migrate_review('test', old, 'source', fixture()['media']['source'])
        self.assertEqual(doc['cues'][0]['note'], '人名要修正')

    def test_nonfinite_rejected(self):
        doc = fixture(); doc['clips'][0]['end'] = float('nan')
        with self.assertRaises(ValueError): validate(doc)

    def test_v1_migration_preserves_both_orientation_appearance(self):
        doc = fixture(); item = doc['cues'][0]
        legacy = {**doc, 'schema': 'shine.video-editor-project.v1'}
        legacy['cues'] = [dict(id=item['id'], start=item['start'], end=item['end'], text=item['text'],
                               original=item['original'], note=item['note'], size=1.25,
                               runs=[dict(text=item['text'], scale=1.5, color='#ffe34a', animation='pop')])]
        migrated = validate(legacy)
        self.assertEqual(migrated['schema'], SCHEMA)
        self.assertEqual(migrated['cues'][0]['appearances']['horizontal'], migrated['cues'][0]['appearances']['vertical'])
        self.assertEqual(migrated['cues'][0]['appearances']['vertical']['size'], 1.25)
