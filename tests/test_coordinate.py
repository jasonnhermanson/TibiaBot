import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from monitor.coordinate import (Bridge, BridgeError, CoordinateHunter, Recorder, atomic_json,
    library_defaults, load_library, save_library, validate_state)


def state():
    return {'version':1,'session':'session-a','seq':1,'online':True,'character_id':12,
            'position':{'x':32090,'y':32204,'z':7},'health':175,'max_health':175,
            'mana':65,'max_mana':65,'monsters':[], 'armed':True,'owner':'controller',
            'capabilities':{'walk':True,'monsters':True,'attack':True},'ack':{}}


class Controls:
    def __init__(self):
        self.focus=True
        self.keys=[]
    def ready(self):
        return self.focus
    def tap(self,key):
        self.keys.append(key)


class FakeBridge:
    controller='controller'
    def __init__(self):
        self.sent=[]
        self.heartbeats=0
    def send(self,s,action,**payload):
        self.sent.append((action,payload))
        return str(len(self.sent))
    def heartbeat(self,s):
        self.heartbeats+=1


class BridgeTests(unittest.TestCase):
    def test_file_transport_freshness_and_restart_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'origins_hunt_state.json'
            atomic_json(path,state())
            os.utime(path,(1000,1000))
            current=[0]
            bridge=Bridge(directory,clock=lambda:current[0],wall=lambda:1000)
            s=bridge.read()
            bridge.heartbeat(s)
            command=bridge.send(s,'walk',position={'x':32091,'y':32204,'z':7})
            saved=json.loads((Path(directory)/'origins_hunt_command.json').read_text())
            self.assertEqual(saved['id'],command)
            self.assertEqual(saved['observed_seq'],1)
            self.assertEqual(saved['session'],'session-a')
            current[0]=2
            with self.assertRaisesRegex(BridgeError,'stopped updating'):
                bridge.read()
            current[0]=0
            bridge.wall=lambda:1003
            with self.assertRaisesRegex(BridgeError,'stale'):
                bridge.read()

    def test_validation_rejects_bad_resources_and_normalizes_lua_empty_table(self):
        for key,value in [('max_health',0),('health',200),('mana',float('nan'))]:
            s=state()
            s[key]=value
            with self.assertRaises(BridgeError):
                validate_state(s)
        s=state()
        s['monsters']={}
        s['ack']=[]
        self.assertEqual(validate_state(s)['monsters'],[])
        self.assertEqual(s['ack'],{})

    def test_named_route_round_trip_and_actions(self):
        data=library_defaults()
        data['routes']={'Rats':[{'action':'walk','position':state()['position']},{'action':'wait','seconds':3}],
                        'Bears':[{'action':'walk','position':{'x':32100,'y':32204,'z':7}}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'routes.json'
            save_library(data,path)
            self.assertEqual(load_library(path),data)
            invalid=copy.deepcopy(data)
            invalid['routes']['Rats'][1]['seconds']=float('nan')
            with self.assertRaises(BridgeError):
                save_library(invalid,path)
            self.assertEqual(load_library(path),data)

    def test_auto_recorder_preserves_turns_spacing_and_floor(self):
        s=state()
        points=[]
        recorder=Recorder(s,points)
        for dx,dy in [(1,0),(2,0),(2,1),(2,2),(2,3)]:
            s['position']={'x':32090+dx,'y':32204+dy,'z':7}
            recorder.sample(s)
        self.assertIn({'action':'walk','position':{'x':32092,'y':32204,'z':7}},points)
        self.assertIn({'action':'walk','position':{'x':32092,'y':32207,'z':7}},points)
        s['position']['z']=8
        with self.assertRaisesRegex(BridgeError,'floor change'):
            recorder.sample(s)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.s=state()
        self.bridge=FakeBridge()
        self.controls=Controls()
        self.now=0
        self.options=library_defaults()['options']
        self.options['loop']=False
        self.points=[{'action':'walk','position':{'x':32093,'y':32204,'z':7}}]

    def hunter(self):
        return CoordinateHunter(self.bridge,self.controls,self.s,self.points,self.options,clock=lambda:self.now)

    def acknowledge(self,hunter,ok=True):
        self.s['ack']={'id':hunter.pending,'ok':ok,'error':'' if ok else 'No path'}

    def test_acknowledged_walk_and_confirmed_arrival(self):
        hunter=self.hunter()
        self.assertEqual(self.bridge.sent[0][0],'arm')
        hunter.step(self.s)
        self.assertEqual(len(self.bridge.sent),1)
        self.acknowledge(hunter)
        hunter.step(self.s)
        self.assertEqual(self.bridge.sent[-1][0],'walk')
        self.acknowledge(hunter)
        self.s['position']=dict(self.points[0]['position'])
        hunter.step(self.s)
        self.assertEqual(hunter.status,'Route complete')
        self.assertEqual(self.bridge.sent[-1][0],'stop')

    def test_target_is_retained_and_training_targets_are_excluded(self):
        self.options['walk_only']=False
        hunter=self.hunter()
        self.acknowledge(hunter)
        trainer={'id':1,'name':'Training Machine','hp':100,'monster':True,'position':dict(self.s['position'])}
        rat={'id':2,'name':'Rat','hp':80,'monster':True,'position':dict(self.s['position'])}
        self.s['monsters']=[trainer,rat]
        hunter.step(self.s)
        self.assertEqual(self.bridge.sent[-1],('attack',{'target_id':2}))
        self.acknowledge(hunter)
        self.s['target']=rat
        for tick in range(1,8):
            self.now=tick
            hunter.step(self.s)
        self.assertEqual(sum(action=='attack' for action,_ in self.bridge.sent),1)
        self.assertEqual(hunter.status,'Attacking Rat')

    def test_stuck_target_focus_loss_restart_and_rejected_command_stop(self):
        for failure in ('focus','session','rejected','timeout','disarmed'):
            with self.subTest(failure=failure):
                self.setUp()
                hunter=self.hunter()
                self.acknowledge(hunter,ok=failure!='rejected')
                if failure=='focus': self.controls.focus=False
                if failure=='session': self.s['session']='new-session'
                if failure=='disarmed': self.s['armed']=False
                if failure=='timeout':
                    self.s['ack']={}
                    self.now=3
                hunter.step(self.s)
                self.assertFalse(hunter.active)
                self.assertFalse(any(action=='walk' for action,_ in self.bridge.sent))

    def test_exact_resources_health_priority_cooldown_and_critical_stop(self):
        self.options.update(heal_enabled=True,mana_enabled=True)
        self.s['health']=70
        self.s['mana']=10
        hunter=self.hunter()
        self.acknowledge(hunter)
        hunter.step(self.s)
        self.assertEqual(self.controls.keys,['F1'])
        self.acknowledge(hunter)
        self.now=.5
        hunter.step(self.s)
        self.assertEqual(self.controls.keys,['F1','F2'])
        self.s['health']=1
        self.now=2.5
        hunter.step(self.s)
        self.assertFalse(hunter.active)
        self.assertIn('critical',hunter.status)

    def test_wait_action_and_loop(self):
        self.options['loop']=True
        self.points=[{'action':'walk','position':dict(self.s['position'])},{'action':'wait','seconds':3}]
        hunter=self.hunter()
        self.acknowledge(hunter)
        hunter.step(self.s)
        self.assertEqual(hunter.index,1)
        hunter.step(self.s)
        self.now=2
        hunter.step(self.s)
        self.assertEqual(hunter.index,1)
        self.now=3
        hunter.step(self.s)
        self.assertEqual(hunter.index,0)
        self.assertTrue(hunter.active)

    def test_healing_and_critical_stop_work_while_walk_ack_is_pending(self):
        self.options.update(heal_enabled=True)
        hunter=self.hunter()
        self.acknowledge(hunter)
        hunter.step(self.s)
        self.s['ack']={}
        self.s['health']=70
        self.now=.3
        hunter.step(self.s)
        self.assertEqual(self.controls.keys,['F1'])
        self.s['health']=1
        self.now=.4
        hunter.step(self.s)
        self.assertFalse(hunter.active)
        self.assertEqual(self.bridge.sent[-1][0],'stop')
