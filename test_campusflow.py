"""Regression checks. Uses only temporary SQLite databases."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from app import app, database, read
from scheduler import ALIASES, CLASSES, audit, pair_starts


class Practical(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old_db=app.config["DATABASE"]
        self.addCleanup(app.config.update,DATABASE=self.old_db)
        app.config.update(DATABASE=str(Path(self.directory.name)/"demo.db"))
        self.client=app.test_client()

    def state(self):
        db=database()
        try:
            return read(db)
        finally:
            db.close()

    def post(self,action,**values):
        return self.client.post("/action",data={"rev":self.state()[0],"action":action,**values})

    def test_demo(self):
        self.assertIn(b'<h1>Welcome to CampusFlow</h1>',self.client.get('/').data)
        self.assertIn(b'Time you could save',self.client.get('/?tab=schedule').data)
        self.assertIn(b'Build timetable',self.post("preview",selected=CLASSES).data)
        self.assertFalse(self.state()[2])
        self.assertIn(b'Saved 4 weekly timetables',self.post("generate",selected=CLASSES).data)
        _,c,old=self.state()
        report=audit(c,old)
        self.assertEqual((report['scheduled'],report['required'],report['issues']),(120,120,[]))
        for d in CLASSES[2:]:
            labs=[r for r in old[d] if r['subject']=='Machine Learning Lab']
            self.assertEqual([r['room'] for r in labs],['Computer Lab']*2)
            self.assertIn(labs[0]['slot'],pair_starts(c))
            self.assertEqual(labs[1]['slot'],labs[0]['slot']+1)
        self.post('generate',selected=CLASSES[:1])
        for d in CLASSES[1:]:
            self.assertEqual(old[d],self.state()[2][d])
        self.client=app.test_client()
        self.assertIn(b'Machine Learning Lab',self.client.get('/?tab=view&view=Third+Year+A').data)
        rows=list(csv.DictReader(io.StringIO(self.client.get('/download.csv').text)))
        self.assertEqual(len(rows),120)
        self.assertEqual({r['Class'] for r in rows},set(CLASSES))
        for field in ['Class','Teacher','Classroom']:
            self.assertEqual(len({(r[field],r['Day'],r['Time']) for r in rows}),120)
        before=self.state()
        self.assertEqual(self.post('timing',days='Monday',slots='09:00 - 10:00\n09:30 - 10:30').status_code,400)
        self.assertEqual(before,self.state())
        self.post('delete_room',name='Room 101')
        self.assertIn(b'Short by 30 room-periods',self.post('preview',selected=CLASSES).data)

    def test_planning_estimates_and_saved_room_use(self):
        def plan():
            return self.client.get('/', query_string={
                'tab': 'schedule', 'choose': '1', 'selected': CLASSES[:1]
            }).text

        self.assertIn('At least 1 of 4 available rooms', plan())
        self.post('generate', selected=CLASSES)
        self.assertIn('At least 4 of 4 available rooms', plan())
        self.assertIn('90 periods already saved', plan())
        saved = self.client.get('/?tab=view').text
        self.assertIn('4 rooms at the busiest time', saved)
        empty = self.client.get('/?tab=schedule&choose=1').text
        self.assertIn('Select at least one valid division', empty)
        self.assertNotIn('<meter', empty)

    def test_manual_comparison(self):
        page = self.client.get('/?tab=schedule').text
        self.assertNotIn('name="pace"', page)
        self.assertEqual(page, self.client.get('/?tab=schedule&pace=2').text)
        self.assertIn('2 hours 41 minutes', page)
        self.post('add_room', name='Lecture Hall')
        self.assertIn('2 hours 29 minutes', self.client.get('/?tab=schedule').text)
        self.assertIn('4 weekly timetables', page)
        self.assertIn('Saved 1 weekly timetable in', self.post('generate', selected=CLASSES[:1]).text)
        page = self.client.get('/?tab=schedule&choose=1&selected=Second+Year+B').text
        self.assertIn('1 weekly timetable', page)
        self.assertIn('31 minutes', page)
        self.assertIn('100% of periods use a teacher', page)

    def test_import(self):
        _,c,_=self.state()
        data=dict(rooms=c['rooms'],days=c['days'],slots=c['slots'],teachers=[{'name':c['teachers'][0]}],
                  subjects=[dict(name='My saved subject',className='SE-A',teacher=c['teachers'][0],periods=1)])
        row=dict(subject='My saved subject',teacher=c['teachers'][0],room='Room 101')
        backup=dict(data=data,timetables={'SE-A':{'SE-A|0-0':row}})
        self.assertEqual(self.post('import',replace='on',file=(io.BytesIO(json.dumps(backup).encode()),'old.json')).status_code,303)
        self.assertIn('My saved subject',self.client.get('/download.csv').text)
        self.assertEqual(set(self.state()[2]),{ALIASES['SE-A']})
        self.assertIn(b'Second Year A',self.client.get('/?tab=manage').data)

    def test_conflicts_and_independent_validation(self):
        self.post('generate',selected=CLASSES)
        rev,c,tables=self.state()
        self.assertEqual(self.post('add_room',name='Spare room',rev=rev-1).status_code,400)
        self.assertEqual(rev,self.state()[0])
        labs=[r for r in tables['Third Year A'] if r['subject']=='Machine Learning Lab']
        labs[1]['slot']=labs[0]['slot']
        report=audit(c,tables)
        self.assertTrue(report['clashes']['teacher'] and report['clashes']['room'])
        self.assertTrue(any('consecutive' in issue for issue in report['issues']))

    def test_odd_lab_periods_rejected(self):
        _,c,_=self.state()
        # Add a subject with odd lab periods
        c['subjects'].append(dict(
            division='Second Year A',
            name='Invalid Lab',
            teacher=c['teachers'][0],
            periods=3,  # Odd number - invalid for lab
            lab='Computer Lab'
        ))
        # check_catalog should catch this when editing subjects
        from scheduler import check_catalog
        with self.assertRaises(ValueError) as ctx:
            check_catalog(c)
        self.assertIn('even', str(ctx.exception).lower())
        # prepare() should also catch this before solve() wastes time
        c['subjects'][-1]['lab']=''  # Remove lab to pass check_catalog
        from scheduler import prepare
        c['subjects'][-1]['lab']='Computer Lab'  # Add it back
        with self.assertRaises(ValueError) as ctx:
            prepare(c, {}, ['Second Year A'])
        self.assertIn('even', str(ctx.exception).lower())


if __name__=='__main__':
    unittest.main()
