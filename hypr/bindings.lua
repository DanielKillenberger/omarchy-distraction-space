-- Add to ~/.config/hypr/bindings.lua
-- Super+Ctrl+Shift+F is unbound in stock Omarchy.

local helper = os.getenv("HOME") .. "/.config/omarchy/plugins/distraction-space/distractions"

hl.unbind("SUPER + TAB")
hl.unbind("SUPER + SHIFT + TAB")
o.bind("SUPER + D", "Toggle distraction space", helper .. " toggle")
o.bind("SUPER + ALT + D", "Move window to distraction space", hl.dsp.window.move({ workspace = "name:distraction", follow = false }))
o.bind("SUPER + CTRL + SHIFT + F", "Lock or unlock the space",
  helper .. [[ status --json | grep -F '"locked": true' && ]] .. helper .. " unlock || " .. helper .. " lock")
o.bind("SUPER + TAB", "Next workspace", helper .. " next")
o.bind("SUPER + SHIFT + TAB", "Previous workspace", helper .. " prev")
