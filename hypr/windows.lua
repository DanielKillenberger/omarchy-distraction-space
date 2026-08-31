-- Named native workspace, not a numbered 1-10 slot and not a special overlay.
-- Super+1-0 and the bar never land here; Super+D is the only entry.
hl.workspace_rule({ workspace = "name:distraction", persistent = true })
o.window("org.telegram.desktop", { workspace = "name:distraction silent" })
o.window("^chrome-discord\\.com__.*$", { workspace = "name:distraction silent" })
o.window("^chrome-web\\.whatsapp\\.com__.*$", { workspace = "name:distraction silent" })
o.window("^chrome-x\\.com__.*$", { workspace = "name:distraction silent" })
o.window("^signal$", { workspace = "name:distraction silent" })
o.window("^chrome-messages\\.google\\.com__.*$", { workspace = "name:distraction silent" })
