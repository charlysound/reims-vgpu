# Let the keyboard follow the pointer between Reims windows

When a Reims VM spans two X11 windows, you can point at the other display and
type there straight away. The optional helper requests focus only when the
current and destination windows have the same Reims process ID and the mouse
buttons are up. This keeps a host application focused if it already had focus.

## Run

This helper needs X11, Python 3 with python-xlib and a window manager that handles
EWMH activation requests. Verify the desktop is the one intended before running:

```sh
python3 focus-reims-windows.py
```

An example [user unit](reims-window-focus.service) is included. It expects the
script at `~/.local/libexec/reims-window-focus.py` and a user service environment
that can reach the graphical session. Running in the foreground is enough to
try it.

The optional [fullscreen helper](reims-fullscreen.py) toggles fullscreen on
the active Reims window through the X11 window manager. It can be bound to a
desktop shortcut. The recorded setup used Alt+F11.

## Test on an isolated display

```sh
REIMS_FOCUS_TEST_PARENT_DISPLAY="${DISPLAY:-}" \
  xvfb-run -a /usr/bin/python3 test-x11-focus.py
```

The test checks EWMH requests for matching windows and covers a focused Linux
application, another VM and a button held during the crossing.

## Recorded results

On Linux X11 with two Reims windows for Intel Sequoia, keys reached macOS after
hovering over port 1 and then port 0, with no click in either direction. An
existing Linux application's focus was preserved. The earlier tests also
checked dragging Finder and edge tiling. [Summary](evidence.json)

Try it first with two windows of one VM, then with two different VMs. The
second case should retain the current keyboard focus. A report on the current
Reims window class and your window manager would help identify where the helper
can be packaged as is. Wayland activation is left to a future implementation.
