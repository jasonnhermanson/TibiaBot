"""File bridge, coordinate route storage and observation-driven hunting controller."""
import json
import math
from pathlib import Path
import time
import uuid
from .settings import settings_path


class BridgeError(ValueError):
    pass


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def position(value):
    if not isinstance(value, dict) or any(type(value.get(k)) is not int for k in ('x','y','z')):
        raise BridgeError('Invalid coordinate data')
    if not (0<=value['x']<=65535 and 0<=value['y']<=65535 and 0<=value['z']<=15):
        raise BridgeError('Coordinate outside supported map range')
    return dict(value)


def distance(a, b):
    return max(abs(a['x']-b['x']), abs(a['y']-b['y'])) if a['z']==b['z'] else float('inf')


def allowed_monster(value):
    return (isinstance(value, dict) and value.get('monster') is True and value.get('hp',0)>0
            and not any(name in str(value.get('name','')).lower() for name in ('training machine','training dummy')))


def validate_state(data):
    if data.get('version') != 1 or not isinstance(data.get('session'),str) or not data['session']:
        raise BridgeError('Unsupported bridge data')
    if type(data.get('seq')) is not int or data['seq']<1 or type(data.get('online')) is not bool:
        raise BridgeError('Invalid bridge heartbeat')
    if data.get('ack') in (None, []):
        data['ack']={}
    if not isinstance(data.get('ack'),dict):
        raise BridgeError('Invalid command acknowledgement')
    if data['online']:
        position(data['position'])
        if type(data.get('character_id')) is not int:
            raise BridgeError('Missing character identity')
        for key in ('health','max_health','mana','max_mana'):
            if type(data.get(key)) not in (int,float) or not math.isfinite(data[key]) or data[key]<0:
                raise BridgeError('Invalid resource data')
        if data['max_health']<=0 or data['health']>data['max_health'] or data['mana']>data['max_mana']:
            raise BridgeError('Invalid resource totals')
        monsters=data.get('monsters',[])
        # Some client JSON encoders represent an empty Lua table as {}.
        if monsters == {}:
            data['monsters'] = monsters = []
        if not isinstance(monsters,list) or len(monsters)>1000:
            raise BridgeError('Invalid creature list')
        for creature in monsters + ([data['target']] if data.get('target') else []):
            position(creature['position'])
            if type(creature.get('id')) is not int or type(creature.get('hp')) not in (int,float) or not 0<=creature['hp']<=100:
                raise BridgeError('Invalid creature data')
    return data


class Bridge:
    def __init__(self, folder, clock=time.monotonic, wall=time.time):
        self.folder=Path(folder)
        self.clock, self.wall = clock, wall
        self.controller=uuid.uuid4().hex
        self.sequence=None
        self.seen_at=None

    def read(self):
        path=self.folder/'origins_hunt_state.json'
        if path.stat().st_size>1_000_000:
            raise BridgeError('Bridge file is too large')
        if abs(self.wall()-path.stat().st_mtime)>2:
            raise BridgeError('Bridge data is stale. Load the Lua bridge in the client.')
        for attempt in range(3):
            try:
                data=validate_state(json.loads(path.read_text(encoding='utf-8')))
                break
            except (json.JSONDecodeError, PermissionError):
                if attempt==2:
                    raise
                time.sleep(.005)
        sequence=(data['session'],data['seq'])
        if self.sequence and sequence[0]==self.sequence[0] and sequence[1]<self.sequence[1]:
            raise BridgeError('Bridge sequence moved backwards')
        if sequence!=self.sequence:
            self.sequence,self.seen_at=sequence,self.clock()
        if self.clock()-self.seen_at>1.5:
            raise BridgeError('Bridge stopped updating')
        return data

    def heartbeat(self, state):
        atomic_json(self.folder/'origins_hunt_heartbeat.json',self.envelope(state))

    def envelope(self, state):
        return {'session':state['session'],'observed_seq':state['seq'],'controller':self.controller}

    def send(self, state, action, **payload):
        if action not in ('arm','stop','walk','attack'):
            raise BridgeError('Unsupported bridge command')
        data={**self.envelope(state),'id':uuid.uuid4().hex,'action':action,**payload}
        atomic_json(self.folder/'origins_hunt_command.json',data)
        return data['id']


def library_defaults():
    return {'version':1,'bridge_folder':'','selected':'','routes':{},
            'options':{'loop':True,'walk_only':True,'critical_at':15,'heal_enabled':False,
                       'mana_enabled':False,'heal_at':45,'mana_at':30,'heal_key':'F1','mana_key':'F2',
                       'cooldown':2,'timeout':45}}


def validate_library(data):
    from .windows import key_code
    if data['version']!=1 or not isinstance(data['routes'],dict) or len(data['routes'])>100:
        raise BridgeError('Invalid coordinate route library')
    for name, points in data['routes'].items():
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or not isinstance(points,list) or len(points)>1000:
            raise BridgeError('Invalid route name or checkpoint count')
        for point in points:
            if point.get('action')=='walk':
                position(point['position'])
            elif point.get('action')=='wait':
                if type(point.get('seconds')) not in (int,float) or not math.isfinite(point['seconds']) or not 0<point['seconds']<=300:
                    raise BridgeError('Wait must be between 0 and 300 seconds')
            else:
                raise BridgeError('Unknown waypoint action')
    o=data['options']
    for key in ('walk_only','loop','heal_enabled','mana_enabled'):
        if type(o[key]) is not bool:
            raise BridgeError('Invalid hunting toggle')
    for key,limits in {'critical_at':(0,100),'heal_at':(0,100),'mana_at':(0,100),'cooldown':(.5,30),'timeout':(5,300)}.items():
        val=o[key]
        if type(val) not in (int,float) or not math.isfinite(val) or not limits[0]<=val<=limits[1]:
            raise BridgeError(f'Invalid {key}: use {limits[0]}–{limits[1]}')
    codes=[key_code(o[key]) for key in ('heal_key','mana_key')]
    if len(set(codes))!=2 or any(c in (key_code('F8'),key_code('F10'),key_code('ESC')) for c in codes):
        raise BridgeError('Heal/mana keys must differ; F8, F10 and ESC are reserved')
    return data


def load_library(path=None):
    path=path or settings_path().with_name('coordinate_routes.json')
    if not path.exists():
        return library_defaults()
    if path.stat().st_size>2_000_000:
        raise BridgeError('Route library is too large')
    return validate_library(json.loads(path.read_text(encoding='utf-8')))


def save_library(data,path=None):
    validate_library(data)
    atomic_json(path or settings_path().with_name('coordinate_routes.json'),data)


class Recorder:
    def __init__(self, state, points, spacing=3):
        self.session=state['session']
        self.character=state['character_id']
        self.floor=state['position']['z']
        self.points=points
        self.spacing=spacing
        self.previous=dict(state['position'])
        self.direction=None
        self.add(state['position'])

    def add(self, pos):
        pos=position(pos)
        if self.points and self.points[-1].get('position')==pos:
            return False
        if len(self.points)>=1000:
            raise BridgeError('Route reached 1000 checkpoints')
        self.points.append({'action':'walk','position':pos})
        return True

    def sample(self, state, force=False):
        if not state['online'] or state['session']!=self.session or state['character_id']!=self.character:
            raise BridgeError('Recording stopped: character/bridge changed')
        pos=state['position']
        if pos['z']!=self.floor:
            raise BridgeError('Recording stopped at a floor change. This version supports single-floor routes.')
        changed=False
        if self.previous and pos!=self.previous:
            dx,dy=pos['x']-self.previous['x'],pos['y']-self.previous['y']
            if max(abs(dx),abs(dy))>8:
                raise BridgeError('Recording stopped at a teleport or missed movement. Add closer checkpoints.')
            direction=((dx>0)-(dx<0),(dy>0)-(dy<0))
            if self.direction and direction!=self.direction:
                changed=self.add(self.previous) or changed
            self.direction=direction
        last_walk=next((p['position'] for p in reversed(self.points) if p['action']=='walk'),pos)
        if force or not self.points or distance(last_walk,pos)>=self.spacing:
            changed=self.add(pos) or changed
        self.previous=dict(pos)
        return changed


class CoordinateHunter:
    def __init__(self, bridge, controls, state, points, options, clock=time.monotonic):
        self.bridge,self.controls,self.options,self.clock=bridge,controls,dict(options),clock
        self.session,self.character=state['session'],state['character_id']
        self.floor=state['position']['z']
        if not points or not any(p['action']=='walk' for p in points):
            raise BridgeError('Record a route with walking checkpoints first')
        if any(p['action']=='walk' and p['position']['z']!=self.floor for p in points):
            raise BridgeError('Route is on another floor or contains floor changes')
        caps=state.get('capabilities',{})
        if not caps.get('walk') or (not options['walk_only'] and not (caps.get('monsters') and caps.get('attack'))):
            raise BridgeError('Required client movement/targeting interfaces are unavailable')
        self.points=list(points)
        self.index=0
        self.active=True
        self.armed=False
        self.pending=None
        self.pending_since=clock()
        self.last_key={}
        self.walk_since=None
        self.last_position=None
        self.last_progress=clock()
        self.last_walk=-float('inf')
        self.wait_until=None
        self.combat=False
        self.target_id=None
        self.target_hp=None
        self.target_progress=clock()
        self.status='Arming client bridge'
        bridge.heartbeat(state)
        self.issue(state,'arm')

    def issue(self,state,action,**payload):
        self.pending=self.bridge.send(state,action,**payload)
        self.pending_since=self.clock()

    def stop(self,reason,state=None):
        was_active=self.active
        self.active=False
        self.status=reason
        if was_active and state and state['session']==self.session:
            try:
                self.bridge.send(state,'stop')
            except OSError:
                pass  # The client-side lease independently expires.

    def step(self,state):
        if not self.active:
            return
        now=self.clock()
        if (not state['online'] or state['session']!=self.session
            or state['character_id']!=self.character or state['position']['z']!=self.floor):
            self.stop('Stopped: character, floor, or bridge changed',state)
            return
        if not self.controls.ready():
            self.stop('Stopped: game lost focus or moved',state)
            return
        self.bridge.heartbeat(state)
        hp=100*state['health']/state['max_health']
        mp=100*state['mana']/state['max_mana'] if state['max_mana'] else 100
        if state.get('armed') and state.get('owner')==self.bridge.controller:
            for kind,value in (('heal',hp),('mana',mp)):
                if (self.options[kind+'_enabled'] and value<=self.options[kind+'_at']
                    and now-self.last_key.get(kind,-float('inf'))>=self.options['cooldown']):
                    self.controls.tap(self.options[kind+'_key'])
                    self.last_key[kind]=now
                    break
        if hp<=self.options['critical_at']:
            self.stop('Stopped: critical health',state)
            return
        if self.pending:
            ack=state.get('ack',{})
            if ack.get('id')!=self.pending:
                if now-self.pending_since>2:
                    self.stop('Stopped: client did not acknowledge the command',state)
                return
            if not ack.get('ok'):
                self.stop('Stopped: '+str(ack.get('error','command rejected')),state)
                return
            self.pending=None
            self.armed=True
        if not state.get('armed') or state.get('owner')!=self.bridge.controller:
            self.stop('Stopped: client bridge disarmed ('+state.get('error','')+')',state)
            return
        if not self.options['walk_only']:
            target=state.get('target')
            monsters=[c for c in state.get('monsters',[]) if allowed_monster(c) and c['position']['z']==self.floor]
            if target and allowed_monster(target) and target['position']['z']==self.floor:
                if self.target_id!=target['id'] or self.target_hp!=target['hp']:
                    self.target_progress=now
                self.target_id,self.target_hp=target['id'],target['hp']
                self.combat=True
                self.wait_until=None
                self.status='Attacking '+target['name']
                if now-self.target_progress>self.options['timeout']:
                    self.stop('Stopped: target HP is not changing',state)
                return
            if monsters:
                target=min(monsters,key=lambda c:distance(state['position'],c['position']))
                self.issue(state,'attack',target_id=target['id'])
                self.combat=True
                self.wait_until=None
                self.status='Selecting '+target['name']
                return
        if self.combat:
            self.combat=False
            self.walk_since=None
            self.last_progress=now
            self.last_walk=-float('inf')
        point=self.points[self.index]
        if point['action']=='wait':
            if self.wait_until is None:
                self.wait_until=now+point['seconds']
            self.status=f'Waiting at action {self.index+1}'
            if now>=self.wait_until:
                self.advance(state)
            return
        pos=state['position']
        if pos==point['position']:
            self.advance(state)
            return
        if distance(pos,point['position'])>80:
            self.stop('Stopped: next checkpoint is too far away',state)
            return
        if self.walk_since is None:
            self.walk_since=now
            self.last_progress=now
        if pos!=self.last_position:
            self.last_position=dict(pos)
            self.last_progress=now
        if now-self.walk_since>self.options['timeout'] or now-self.last_progress>8:
            self.stop('Stopped: walking timed out or character is stuck',state)
            return
        if now-self.last_walk>=2:
            self.issue(state,'walk',position=point['position'])
            self.last_walk=now
        self.status=f'Walking to checkpoint {self.index+1}/{len(self.points)}'

    def advance(self,state):
        self.index+=1
        self.walk_since=None
        self.last_walk=-float('inf')
        self.wait_until=None
        if self.index==len(self.points):
            if self.options['loop']:
                self.index=0
            else:
                self.stop('Route complete',state)
                return
        self.status=f'Next action {self.index+1}/{len(self.points)}'
