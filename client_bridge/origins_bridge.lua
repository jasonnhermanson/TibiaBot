-- Origins Bridge v1. Loaded explicitly from the client's Lua terminal.
-- File-only protocol: no networking, arbitrary code execution, or startup edits.
if OriginsBridge and OriginsBridge.shutdown then OriginsBridge.shutdown() end
local B = {running=true, seq=0, armed=false, owner=nil, lastCommand='', error='', ack={}}
OriginsBridge = B
B.folder = g_resources.getWriteDir()
B.session = tostring(os.time()) .. '-' .. tostring(math.random(100000,999999))
local prefix = '/origins_hunt_'
local lastHeartbeat, lastObserved, identity = nil, -1, nil
local lastWall = os.time()
local blocked = {'training machine', 'training dummy'}
local function allowed(name)
  name = string.lower(name or '')
  for _, word in ipairs(blocked) do if string.find(name, word, 1, true) then return false end end
  return true
end
local function now() return os.time() end
local function read(kind)
  local ok, text = pcall(g_resources.readFileContents, prefix..kind..'.json')
  if not ok or type(text) ~= 'string' or #text > 65536 then return nil end
  local valid, value = pcall(json.decode, text)
  if valid and type(value) == 'table' then return value end
end
local function cancel()
  local p = g_game.getLocalPlayer()
  if p and type(p.stopAutoWalk) == 'function' then pcall(function() p:stopAutoWalk() end) end
  if type(g_game.stop) == 'function' then pcall(g_game.stop) end
  if type(g_game.cancelAttackAndFollow) == 'function' then pcall(g_game.cancelAttackAndFollow) end
end
function B.stop(reason)
  local wasArmed = B.armed
  B.armed, B.owner = false, nil
  B.error = reason or 'Stopped'
  if wasArmed then cancel() end
end
function B.shutdown()
  B.stop('Bridge unloaded')
  B.running = false
  if B.key and g_keyboard and type(g_keyboard.unbindKeyDown) == 'function' then
    pcall(g_keyboard.unbindKeyDown, 'F10')
  end
end
local function creature(c)
  local pos = c:getPosition()
  return {id=c:getId(), name=c:getName(), hp=c:getHealthPercent() or 0,
          monster=c:isMonster(), position={x=pos.x,y=pos.y,z=pos.z}}
end
local function snapshot()
  local p = g_game.getLocalPlayer()
  local s = {version=1, session=B.session, seq=B.seq, online=p~=nil, armed=B.armed,
             owner=B.owner or '', error=B.error, ack=B.ack,
             capabilities={walk=p~=nil and type(p.autoWalk)=='function' and type(p.stopAutoWalk)=='function' and type(g_game.stop)=='function',
                           monsters=g_map~=nil and type(g_map.getSpectators)=='function',
                           attack=type(g_game.attack)=='function'}}
  if not p then return s end
  local pos = p:getPosition()
  s.character_id = p:getId()
  s.position = {x=pos.x,y=pos.y,z=pos.z}
  s.health, s.max_health = p:getHealth(), p:getMaxHealth()
  s.mana, s.max_mana = p:getMana(), p:getMaxMana()
  local target = g_game.getAttackingCreature()
  if target then s.target = creature(target) end
  s.monsters = {}
  if s.capabilities.monsters then
    for _, c in ipairs(g_map.getSpectators(pos, false)) do
      if c:isMonster() and (c:getHealthPercent() or 0) > 0 and allowed(c:getName()) then
        table.insert(s.monsters, creature(c))
      end
    end
  end
  return s
end
local function validFresh(message)
  return message and message.session == B.session and type(message.observed_seq)=='number'
    and message.observed_seq <= B.seq and message.observed_seq >= B.seq-8
    and type(message.controller)=='string' and #message.controller > 0
end
local function command(c, s)
  if not c or type(c.id)~='string' or c.id == B.lastCommand then return end
  -- Old-session and expired files are never replayed.
  if not validFresh(c) then return end
  B.lastCommand = c.id
  B.ack = {id=c.id, ok=false, error=''}
  local ok, err = pcall(function()
    if c.action == 'stop' then
      if not B.owner or c.controller == B.owner then B.stop('Stopped by app') end
      return
    end
    if not s.online then error('Character is not logged in') end
    if c.action == 'arm' then
      if B.armed and B.owner ~= c.controller then error('Another controller owns this bridge') end
      if not lastHeartbeat or now()-lastHeartbeat > 1 or c.controller ~= B.heartbeatOwner then
        error('No fresh controller heartbeat')
      end
      if not s.capabilities.walk then error('Client does not expose LocalPlayer:autoWalk') end
      cancel()
      B.owner, B.armed, B.error = c.controller, true, ''
      return
    end
    if not B.armed or c.controller ~= B.owner then error('Bridge is not armed by this controller') end
    if c.action == 'walk' then
      local d, pos = c.position, s.position
      if type(d)~='table' or type(d.x)~='number' or type(d.y)~='number'
        or type(d.z)~='number' or d.x~=math.floor(d.x) or d.y~=math.floor(d.y)
        or d.x<0 or d.y<0 or d.x>65535 or d.y>65535 or d.z~=pos.z
        or math.max(math.abs(d.x-pos.x),math.abs(d.y-pos.y))>80 then
        error('Walk destination is invalid, too far, or on another floor')
      end
      -- LocalPlayer:autoWalk accepts a destination; g_game.autoWalk takes directions.
      local result = g_game.getLocalPlayer():autoWalk({x=d.x,y=d.y,z=d.z})
      if result == false then error('Client rejected the walk destination') end
    elseif c.action == 'attack' then
      local found = nil
      for _, value in ipairs(s.monsters or {}) do if value.id==c.target_id then found=value end end
      if not found or not allowed(found.name) then error('Target is not a visible allowed monster') end
      local p = g_game.getLocalPlayer()
      for _, target in ipairs(g_map.getSpectators(p:getPosition(),false)) do
        if target:getId()==c.target_id and target:isMonster() and allowed(target:getName()) then
          cancel()
          g_game.attack(target)
          return
        end
      end
      error('Target disappeared')
    else
      error('Unknown bridge action')
    end
  end)
  B.ack.ok = ok
  B.ack.error = ok and '' or tostring(err)
  if not ok then B.stop(B.ack.error) end
end
local function tick()
  if not B.running then return end
  B.seq = B.seq + 1
  local ok, value = pcall(function()
    local wall = now()
    if B.armed and (wall<lastWall or wall-lastWall>3) then B.stop('Clock jump or suspended client') end
    lastWall = wall
    local s = snapshot()
    if B.armed and (not s.online or identity ~= s.character_id) then B.stop('Character disconnected or changed') end
    identity = s.character_id
    local h = read('heartbeat')
    if validFresh(h) and h.observed_seq>lastObserved then
      if not B.owner or B.owner==h.controller then
        lastObserved, lastHeartbeat, B.heartbeatOwner = h.observed_seq, now(), h.controller
      end
    end
    if B.armed and (not lastHeartbeat or now()-lastHeartbeat>1) then B.stop('Controller heartbeat expired') end
    command(read('command'), s)
    return snapshot()
  end)
  if not ok then
    B.stop(tostring(value))
    value={version=1,session=B.session,seq=B.seq,online=false,armed=false,error=B.error,ack=B.ack}
  end
  local written, err = pcall(function()
    local result=g_resources.writeFileContents(prefix..'state.json',json.encode(value))
    if result==false then error('File write returned false') end
  end)
  if not written then B.stop('Could not write bridge state: '..tostring(err)) end
  if B.running then B.event = scheduleEvent(tick,200) end
end
if g_keyboard and type(g_keyboard.bindKeyDown)=='function' then
  B.key=function() B.stop('Stopped by F10') end
  pcall(g_keyboard.bindKeyDown,'F10',B.key)
end
tick()
return B.folder
