"""Menu UI through omarchy-menu-* (later task)."""


class Unavailable(Exception):
    """Menu binary missing or failed to launch."""


def select(prompt, rows, timeout=None): raise NotImplementedError
def input(prompt, timeout=None): raise NotImplementedError
def notify(title, body, *, glyph=None, action=None, urgent=False): raise NotImplementedError
def confirm_enter(timeout=30): raise NotImplementedError
def prompt_lock(cfg): raise NotImplementedError
def prompt_reason(min_chars): raise NotImplementedError
def menu(): raise NotImplementedError
def cmd_menu(args): raise NotImplementedError
