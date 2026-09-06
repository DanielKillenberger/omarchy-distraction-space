-- Distraction space (io.github.danielkillenberger.distraction-space):
-- a stream from the distraction browser starts muted while the hold key
-- is set on this script's own metadata object, and unmuted while it is
-- not, whatever WirePlumber saved for it.
-- `distractions setup` installs this script; `setup --remove` deletes it.
-- The listener sets and deletes the key through `pw-metadata`.

local APP_ID = "io.github.danielkillenberger.distraction-space"
local HOLD_KEY = "hold"

local log = Log.open_topic ("s-distraction-space")

-- A metadata object of the plugin's name is how the listener sees the hook loaded,
-- and the hold key the listener sets lives on it.
loaded_metadata = ImplMetadata (APP_ID)
loaded_metadata:activate (Features.ALL, function (m, e)
  if e then
    log:warning ("failed to activate the " .. APP_ID .. " metadata: " .. tostring (e))
  else
    m:set (0, "hold-mute", "Spa:String:JSON", "\"loaded\"")
  end
end)

-- A key that cannot be read is an absent one.
local function holdOn ()
  local ok, value = pcall (function () return loaded_metadata:find (0, HOLD_KEY) end)
  return ok and value ~= nil
end

hold_mute_hook = SimpleEventHook {
  name = "node/distraction-space-hold-mute",
  -- After the saved per-identity state, so the key has the last word.
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
