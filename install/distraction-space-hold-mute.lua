-- Distraction space (io.github.danielkillenberger.distraction-space):
-- a stream from the distraction browser starts muted while the hold flag
-- exists, and unmuted while it does not, whatever WirePlumber saved for it.
-- `distractions setup` installs this script; `setup --remove` deletes it.
-- The flag path is filled in by setup; the listener writes and removes it.

local APP_ID = "io.github.danielkillenberger.distraction-space"
local FLAG = @HOLD_FLAG@

local log = Log.open_topic ("s-distraction-space")

-- A flag that cannot be read is an absent one.
local function holdOn ()
  local f = io.open (FLAG, "r")
  if not f then
    return false
  end
  f:close ()
  return true
end

hold_mute_hook = SimpleEventHook {
  name = "node/distraction-space-hold-mute",
  -- After the saved per-identity state, so the flag has the last word.
  after = "node/restore-stream",
  interests = {
    EventInterest {
      Constraint { "event.type", "=", "node-added" },
      Constraint { "media.class", "=", "Stream/Output/Audio" },
      Constraint { "application.id", "=", APP_ID },
    },
  },
  execute = function (event)
    local node = event:get_subject ()
    local muted = holdOn ()
    node:set_param ("Props", Pod.Object {
      "Spa:Pod:Object:Param:Props", "Props",
      mute = muted,
    })
    log:info (node, (muted and "muted" or "unmuted") .. " at creation: "
        .. tostring (node.properties ["node.name"]))
  end
}
hold_mute_hook:register ()

-- A metadata object of the plugin's name is how the listener sees the hook loaded.
loaded_metadata = ImplMetadata (APP_ID)
loaded_metadata:activate (Features.ALL, function (m, e)
  if e then
    log:warning ("failed to activate the " .. APP_ID .. " metadata: " .. tostring (e))
  else
    m:set (0, "hold-mute", "Spa:String:JSON", "\"loaded\"")
  end
end)
