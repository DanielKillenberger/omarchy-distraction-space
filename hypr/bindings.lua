-- Add to ~/.config/hypr/bindings.lua
-- Super+Ctrl+Shift+F is unbound in stock Omarchy.

local helper = os.getenv("HOME") .. "/.config/omarchy/plugins/distraction-space/distractions"

o.bind("SUPER + CTRL + SHIFT + F", "Toggle focus mode", helper .. " focus")

hl.unbind("SUPER + TAB")
hl.unbind("SUPER + SHIFT + TAB")
hl.unbind("SUPER + mouse_down")
hl.unbind("SUPER + mouse_up")
o.bind("SUPER + TAB", "Next workspace", helper .. " next")
o.bind("SUPER + SHIFT + TAB", "Previous workspace", helper .. " prev")
o.bind("SUPER + mouse_down", "Scroll active workspace forward", helper .. " next")
o.bind("SUPER + mouse_up", "Scroll active workspace backward", helper .. " prev")
o.bind("SUPER + D", "Toggle distraction space", helper .. " toggle")
o.bind("SUPER + ALT + D", "Move window to distraction space", hl.dsp.window.move({ workspace = "name:distraction", follow = false }))
