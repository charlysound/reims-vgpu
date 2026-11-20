#!/usr/bin/python3
"""Verify live GTK-to-Xdnd proxy routing on an isolated Xvfb display."""

import os
from pathlib import Path
import subprocess
import tempfile
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk
from Xlib import X, Xatom, display

from x11 import IncomingDrop, Xdnd


def main():
    if not os.environ.get("REIMS_DND_TEST_DISPLAY") == os.environ.get("DISPLAY"):
        raise SystemExit("Run through test-x11.sh to use an isolated display.")

    with tempfile.TemporaryDirectory(prefix="reims-xdnd-") as directory:
        source_file = Path(directory) / "fichier épreuve.txt"
        source_file.write_text("Synthetic X11 drag\n")
        validate(source_file)


def validate(source_file):
    app = Gtk.Window()
    app.set_default_size(360, 250)
    app.move(20, 20)
    widget = Gtk.EventBox()
    widget.add(Gtk.Label(label="Drag this test file"))
    app.add(widget)
    widget.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
    widget.drag_source_add_uri_targets()
    widget.connect("drag-data-get", lambda _, context, selection, info, stamp:
                   selection.set_uris([source_file.as_uri()]))
    app.show_all()

    connection = display.Display()
    x11 = Xdnd(connection)
    target = x11.root.create_window(440, 100, 360, 400, 0, X.CopyFromParent,
                                    X.InputOutput, X.CopyFromParent,
                                    background_pixel=connection.screen().white_pixel)
    target.change_property(x11.atom("XdndAware"), Xatom.ATOM, 32, [5])
    target.map()
    connection.sync()
    seen = []

    def notify(event):
        seen.append((event, incoming.point, incoming.paths))
        if event == "drop":
            incoming.finish(incoming.paths == [source_file])

    incoming = IncomingDrop(x11, target, notify)
    process = subprocess.Popen([
        "xdotool", "mousemove", "130", "120", "sleep", ".1", "mousedown", "1",
        "sleep", ".13", "mousemove", "150", "140", "sleep", ".12", "mousemove",
        "510", "230", "sleep", ".25", "mousemove", "660", "340", "sleep", ".15",
        "mouseup", "1",
    ])
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            while connection.pending_events():
                incoming.handle(connection.next_event())
            time.sleep(.006)
    finally:
        incoming.close()
        process.wait(timeout=2)
        connection.close()

    assert ("files", (510, 230), [source_file]) in seen, seen
    assert ("drop", (660, 340), [source_file]) in seen, seen
    print("GTK file URI read during hover; Xdnd used release coordinates (660, 340).")


if __name__ == "__main__":
    main()
