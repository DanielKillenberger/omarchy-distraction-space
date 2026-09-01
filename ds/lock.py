"""Lock state, hooks, and enter/leave/toggle (later task)."""


def is_locked(): raise NotImplementedError
def lock(minutes, purpose): raise NotImplementedError
def unlock(reason): raise NotImplementedError
def expire_if_due(): raise NotImplementedError
def run_hook(name, env): raise NotImplementedError
def enter(): raise NotImplementedError
def leave(): raise NotImplementedError
def toggle(): raise NotImplementedError
def cmd_lock(args): raise NotImplementedError
def cmd_unlock(args): raise NotImplementedError
def cmd_enter(args): raise NotImplementedError
def cmd_leave(args): raise NotImplementedError
def cmd_toggle(args): raise NotImplementedError
