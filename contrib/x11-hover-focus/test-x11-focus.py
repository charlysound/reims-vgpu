#!/usr/bin/python3
"""Check the EWMH focus requests on an isolated Xvfb display."""

import os
from pathlib import Path
import select
import subprocess
import sys
import time

from Xlib import X, Xatom, display
from Xlib.ext import xtest


def main():
    if (os.environ.get("REIMS_FOCUS_TEST_PARENT_DISPLAY") is None
            or os.environ.get("DISPLAY") == os.environ["REIMS_FOCUS_TEST_PARENT_DISPLAY"]):
        raise SystemExit("Run this test with xvfb-run and REIMS_FOCUS_TEST_PARENT_DISPLAY set")

    connection = display.Display()
    root = connection.screen().root
    root.change_attributes(event_mask=X.SubstructureNotifyMask)
    clients = connection.intern_atom("_NET_CLIENT_LIST")
    active = connection.intern_atom("_NET_ACTIVE_WINDOW")
    pid = connection.intern_atom("_NET_WM_PID")

    def create(x, window_class, process):
        window = root.create_window(x, 100, 140, 120, 0, X.CopyFromParent, X.InputOutput)
        window.set_wm_class(window_class, window_class)
        window.change_property(pid, Xatom.CARDINAL, 32, [process])
        window.map()
        return window

    first = create(80, "reims-vgpu", 3000)
    second = create(280, "reims-vgpu", 3000)
    another_vm = create(480, "reims-vgpu", 4000)
    editor = create(680, "editor", 5000)
    root.change_property(clients, Xatom.WINDOW, 32,
                         [first.id, second.id, another_vm.id, editor.id])

    def motion(x, y=150):
        xtest.fake_input(connection, X.MotionNotify, x=x, y=y)
        connection.sync()

    def focus(window):
        root.change_property(active, Xatom.WINDOW, 32, [window.id])
        connection.sync()

    def request(timeout):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            while connection.pending_events():
                event = connection.next_event()
                if event.type == X.ClientMessage and event.client_type == active:
                    return event.window.id
            select.select([connection.fileno()], [], [], max(0, until - time.monotonic()))
        return None

    motion(10, 10)
    focus(first)
    helper = Path(__file__).with_name("focus-reims-windows.py")
    process = subprocess.Popen([sys.executable, str(helper)])
    try:
        for _ in range(15):
            motion(10, 10)
            motion(300)
            if request(.15) == second.id:
                break
        else:
            raise AssertionError("No request for the other display of the same VM")

        focus(editor)
        motion(10, 10)
        motion(300)
        assert request(.25) is None, "Attempted to take focus from a Linux application"

        focus(first)
        motion(500)
        assert request(.25) is None, "Attempted to take focus across two VMs"

        motion(10, 10)
        xtest.fake_input(connection, X.ButtonPress, 1)
        motion(300)
        assert request(.25) is None, "Attempted to take focus during a drag"
        xtest.fake_input(connection, X.ButtonRelease, 1)
        connection.sync()
    finally:
        process.terminate()
        process.wait(timeout=2)
        connection.close()

    print("Focus follows the pointer only between windows of the same VM with no button held.")


if __name__ == "__main__":
    main()
