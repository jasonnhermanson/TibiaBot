"""Execute the actual companion script in Lua 5.1 against a mocked OTClient."""
import json
from pathlib import Path
import unittest
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime=None

SOURCE=Path(__file__).resolve().parents[1]/'client_bridge'/'origins_bridge.lua'
MOCK='''
clock=1000; events={}; actions={}; files={}; online=true; walkAccepted=true
p={x=32090,y=32204,z=7,id=12,health=175,mana=65}
function p:getPosition() return {x=self.x,y=self.y,z=self.z} end
function p:getId() return self.id end
function p:getHealth() return self.health end
function p:getMaxHealth() return 175 end
function p:getMana() return self.mana end
function p:getMaxMana() return 65 end
function p:autoWalk(pos) table.insert(actions,'walk:'..pos.x..','..pos.y..','..pos.z); return walkAccepted end
function p:stopAutoWalk() table.insert(actions,'stopWalk') end
function makeCreature(id,name,hp)
  return {getId=function() return id end, getName=function() return name end,
    getHealthPercent=function() return hp end, isMonster=function() return true end,
    getPosition=function() return {x=32091,y=32204,z=7} end}
end
rat=makeCreature(10,'Rat',100); trainer=makeCreature(11,'Training Machine',100)
spectators={rat,trainer}
g_game={getLocalPlayer=function() if online then return p end end,
 getAttackingCreature=function() return currentTarget end,
 stop=function() table.insert(actions,'stop') end,
 cancelAttackAndFollow=function() currentTarget=nil; table.insert(actions,'cancelAttack') end,
 attack=function(c) currentTarget=c; table.insert(actions,'attack:'..c:getId()) end}
g_map={getSpectators=function() return spectators end}
g_resources={getWriteDir=function() return '/test/folder/' end,
 readFileContents=function(path) if not files[path] then error('Missing file') end; return files[path] end,
 writeFileContents=function(path,text) files[path]=text; return true end}
json={encode=function(value) return py_encode(value) end,decode=function(text) return py_decode(text) end}
os.time=function() return clock end
scheduleEvent=function(callback,delay) nextTick=callback; return 1 end
g_keyboard={bindKeyDown=function(key,callback) stopKey=callback end,unbindKeyDown=function() stopKey=nil end}
'''


@unittest.skipIf(LuaRuntime is None,'Install requirements-dev.txt to run Lua 5.1 bridge tests')
class LuaBridgeTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.g=self.lua.globals()
        self.g.py_encode=lambda value:json.dumps(self.to_python(value))
        self.g.py_decode=lambda text:self.to_lua(json.loads(text))
        self.lua.execute(MOCK)
        self.lua.execute(SOURCE.read_text())
        self.counter=0

    def to_python(self,value):
        if hasattr(value,'items'):
            items=dict(value.items())
            if items and set(items)==set(range(1,len(items)+1)):
                return [self.to_python(items[k]) for k in range(1,len(items)+1)]
            return {k:self.to_python(v) for k,v in items.items()}
        return value

    def to_lua(self,value):
        if isinstance(value,dict):
            return self.lua.table_from({k:self.to_lua(v) for k,v in value.items()})
        if isinstance(value,list):
            return self.lua.table_from([self.to_lua(v) for v in value])
        return value

    def state(self):
        return json.loads(self.g.files['/origins_hunt_state.json'])

    def message(self,action,**payload):
        self.counter+=1
        s=self.state()
        message={'session':s['session'],'observed_seq':s['seq'],'controller':'test',
                 'id':str(self.counter),'action':action,**payload}
        self.g.files['/origins_hunt_command.json']=json.dumps(message)
        self.g.files['/origins_hunt_heartbeat.json']=json.dumps({**message})
        return message

    def tick(self,seconds=0):
        self.g.clock+=seconds
        self.g.nextTick()

    def arm(self):
        self.message('arm')
        self.tick()
        self.assertTrue(self.state()['armed'])

    def test_startup_is_observe_only_and_exact_state_excludes_training(self):
        s=self.state()
        self.assertEqual((s['health'],s['mana']),(175,65))
        self.assertEqual(len(self.g.actions),0)
        self.assertFalse(s['armed'])
        self.assertEqual([c['name'] for c in s['monsters']],['Rat'])

    def test_destination_api_and_command_deduplication(self):
        self.arm()
        self.message('walk',position={'x':32093,'y':32204,'z':7})
        self.tick()
        self.assertTrue(self.state()['ack']['ok'])
        count=len(self.g.actions)
        self.assertEqual(self.g.actions[count],'walk:32093,32204,7')
        self.tick()
        self.assertEqual(len(self.g.actions),count)

    def test_training_target_is_rejected_and_normal_target_works(self):
        self.arm()
        self.message('attack',target_id=11)
        self.tick()
        self.assertFalse(self.state()['armed'])
        self.assertFalse(self.state()['ack']['ok'])
        self.arm()
        self.message('attack',target_id=10)
        self.tick()
        self.assertEqual(self.g.currentTarget.getName(),'Rat')

    def test_expired_lease_and_f10_cancel_hunt(self):
        self.arm()
        self.tick(2)
        self.assertFalse(self.state()['armed'])
        self.assertIn('heartbeat',self.state()['error'])
        self.arm()
        self.g.stopKey()
        self.tick()
        self.assertFalse(self.state()['armed'])
        self.assertIn('F10',self.state()['error'])

    def test_old_session_and_expired_commands_do_not_move(self):
        self.arm()
        message=self.message('walk',position={'x':32093,'y':32204,'z':7})
        message['session']='previous-client'
        self.g.files['/origins_hunt_command.json']=json.dumps(message)
        count=len(self.g.actions)
        self.tick()
        self.assertEqual(len(self.g.actions),count)
        message['session']=self.state()['session']
        message['observed_seq']=-100
        self.g.files['/origins_hunt_command.json']=json.dumps(message)
        self.tick()
        self.assertEqual(len(self.g.actions),count)

    def test_floor_change_bad_destination_and_rejected_walk_stop(self):
        for kind in ('floor','far','rejected'):
            with self.subTest(kind=kind):
                self.setUp()
                self.arm()
                pos={'x':32093,'y':32204,'z':7}
                if kind=='floor': pos['z']=8
                if kind=='far': pos['x']=40000
                if kind=='rejected': self.g.walkAccepted=False
                self.message('walk',position=pos)
                self.tick()
                self.assertFalse(self.state()['armed'])
                self.assertFalse(self.state()['ack']['ok'])

    def test_disconnect_and_bridge_reload_disarm(self):
        self.arm()
        self.g.online=False
        self.tick()
        self.assertFalse(self.state()['armed'])
        self.assertFalse(self.state()['online'])
        old=self.state()['session']
        self.g.online=True
        self.lua.execute(SOURCE.read_text())
        self.assertNotEqual(self.state()['session'],old)
        self.assertFalse(self.state()['armed'])

    def test_real_python_transport_and_lua_destination_controller(self):
        from tempfile import TemporaryDirectory
        from monitor.coordinate import Bridge, CoordinateHunter, atomic_json, library_defaults
        from test_coordinate import Controls
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            def export():
                atomic_json(folder/'origins_hunt_state.json',self.state())
            def exchange():
                for kind in ('command','heartbeat'):
                    path=folder/f'origins_hunt_{kind}.json'
                    if path.exists():
                        self.g.files[f'/origins_hunt_{kind}.json']=path.read_text()
                self.tick()
                export()
            export()
            bridge=Bridge(folder)
            options=library_defaults()['options']
            options['loop']=False
            hunter=CoordinateHunter(bridge,Controls(),bridge.read(),
                [{'action':'walk','position':{'x':32093,'y':32204,'z':7}}],options)
            exchange()
            hunter.step(bridge.read())
            exchange()
            self.assertTrue(self.state()['ack']['ok'])
            self.g.p.x=32093
            hunter.step(bridge.read())
            # Publish the new position before asking the controller to confirm arrival.
            exchange()
            hunter.step(bridge.read())
            exchange()
            self.assertEqual(hunter.status,'Route complete')
            self.assertFalse(self.state()['armed'])

    def test_character_change_and_suspended_client_disarm(self):
        for kind in ('character','suspend'):
            with self.subTest(kind=kind):
                self.setUp()
                self.arm()
                if kind=='character': self.g.p.id=99
                self.tick(4 if kind=='suspend' else 0)
                self.assertFalse(self.state()['armed'])
