#!/usr/bin/python3
"""Run a foreground file-drag bridge for a single Reims X11 window."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import queue
import shlex
import signal
import subprocess
import tempfile
import threading
import time

from Xlib import XK, display
from Xlib.error import BadWindow

from qemu_pointer import Tablet, guest_point
from x11 import IncomingDrop, Xdnd


def log(event, **details):
    print(json.dumps({"event": event, **details}, ensure_ascii=False), flush=True)


class Guest:
    def __init__(self, host, port, host_key_alias, directory):
        options = [
            "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", "-oConnectTimeout=4",
        ]
        if host_key_alias:
            options.append(f"-oHostKeyAlias={host_key_alias}")
        self.host = host
        self.scp = ["scp", "-q", *options, "-P", str(port)]
        self.ssh = ["ssh", "-T", *options, "-p", str(port), host]
        self.directory = directory
        command = "/usr/bin/nc -U " + shlex.quote(directory + "/bridge.sock")
        self.connection = subprocess.Popen(
            [*self.ssh, command], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        self.messages = queue.SimpleQueue()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in self.connection.stdout:
                self.messages.put(json.loads(line))
        finally:
            self.messages.put({"event": "disconnected"})

    def send(self, event, **fields):
        self.connection.stdin.write(json.dumps({"event": event, **fields}) + "\n")
        self.connection.stdin.flush()

    def download(self, paths, folder):
        files = []
        for index, text in enumerate(paths):
            remote = Path(text)
            if not remote.is_absolute() or len(remote.parts) < 2:
                raise ValueError("Finder did not supply an absolute file path")
            branch = folder / str(index)
            branch.mkdir(parents=True)
            local = branch / remote.name
            subprocess.run([*self.scp, "-r", f"{self.host}:{remote}", str(local)],
                           check=True, timeout=120)
            files.append(local)
        return files

    def upload(self, paths):
        template = shlex.quote(self.directory + "/incoming.XXXXXXXX")
        folder = subprocess.run(
            [*self.ssh, f"/usr/bin/mktemp -d {template}"], check=True, text=True,
            capture_output=True, timeout=10,
        ).stdout.strip()
        files = []
        for index, path in enumerate(paths):
            branch = folder + "/" + str(index)
            subprocess.run([*self.ssh, "/bin/mkdir " + shlex.quote(branch)],
                           check=True, timeout=10)
            remote = branch + "/" + path.name
            subprocess.run([*self.scp, "-r", str(path), f"{self.host}:{remote}"],
                           check=True, timeout=120)
            files.append(remote)
        return files

    def close(self):
        self.connection.stdin.close()
        try:
            self.connection.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.connection.terminate()
            self.connection.wait(timeout=2)


def within(point, bounds):
    x, y = point
    left, top, right, bottom = bounds
    return left <= x < right and top <= y < bottom


def window_bounds(root, window):
    geometry = window.get_geometry()
    origin = root.translate_coords(window, 0, 0)
    return origin.x, origin.y, origin.x + geometry.width, origin.y + geometry.height


def escape_held(server, keycode):
    keys = server.query_keymap()
    return bool(keys[keycode // 8] & (1 << (keycode % 8)))


class IntoFinder:
    def __init__(self, bridge, reims, guest, tablet, transfers):
        self.bridge = bridge
        self.reims = reims
        self.guest = guest
        self.tablet = tablet
        self.transfers = transfers
        self.size = None
        self.generation = 0
        self.clear()
        self.drop = IncomingDrop(bridge, reims, self.notify)

    def clear(self):
        self.stage = self.entry = self.last = self.deadline = self.prepare_at = None
        self.prepared = self.began = self.released = False

    def point(self, raw):
        return guest_point(window_bounds(self.bridge.root, self.reims), self.size, raw)

    def notify(self, name):
        if name == "enter":
            self.cancel()
            self.generation += 1
            log("nemo-enter")
        elif name == "position" and self.entry is None and self.size is not None:
            x, y = self.point(self.drop.point)
            w, h = self.size
            self.entry = min(w - 54, max(54, x)), min(h - 54, max(54, y))
        elif name == "files":
            log("nemo-files", count=len(self.drop.paths))
            self.stage = self.transfers.submit(self.guest.upload, self.drop.paths)
        elif name == "drop":
            self.deadline = time.monotonic() + 3
            log("nemo-release", position=self.drop.point)
        elif name == "leave":
            self.cancel()

    def cancel(self):
        if self.prepared:
            self.tablet.cancel()
            self.guest.send("hide-source")
        self.clear()

    def on_guest(self, message):
        name = message["event"]
        if name == "connected":
            self.size = int(message["width"]), int(message["height"])
            return
        if message.get("generation") != self.generation or not self.prepared:
            return
        if name == "source-ready":
            log("finder-source-panel", x=message["x"], y=message["y"],
                window=message["window"], under_pointer=message["underPointer"])
            self.tablet.button(True)
        elif name == "source-press":
            log("finder-press", button=message["button"])
        elif name == "source-began":
            self.began = True
            log("finder-gesture")
        elif name == "source-done":
            accepted = bool(message["accepted"]) and self.released
            self.drop.finish(accepted)
            log("mac-drop", accepted=accepted, x=message.get("x"), y=message.get("y"))
            self.cancel()

    def tick(self, now):
        if self.drop.source is None:
            return
        if self.deadline is not None and now >= self.deadline:
            self.drop.finish(False)
            self.cancel()
            log("mac-drop", accepted=False, reason="timeout")
            return
        if not self.prepared and self.stage is not None and self.stage.done() and self.entry:
            try:
                files = self.stage.result()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                log("transfer-error", reason=str(exc))
                self.drop.finish(False)
                self.cancel()
                return
            if self.prepare_at is None:
                self.tablet.move(self.entry, self.size)
                self.prepare_at = now + .08
            elif now >= self.prepare_at:
                self.prepared = True
                self.guest.send("prepare-source", files=files, generation=self.generation)
        if not self.began or self.released or self.drop.point is None:
            return
        current = self.point(self.drop.point)
        if current != self.last:
            self.tablet.move(current, self.size)
            self.last = current
            # Let WindowServer observe the position before releasing the button.
            return
        if self.drop.dropped:
            self.released = True
            log("finder-release", position=current)
            self.tablet.button(False)


def run_bridge(bridge, reims, guest, tablet, cache):
    server = bridge.display
    escape_key = server.keysym_to_keycode(XK.XK_Escape)
    bounds = window_bounds(bridge.root, reims)
    with ThreadPoolExecutor(max_workers=2) as transfers:
        inbound = IntoFinder(bridge, reims, guest, tablet, transfers) if tablet else None
        try:
            event_loop(bridge, reims, guest, cache, inbound, transfers, escape_key, bounds)
        finally:
            if inbound is not None:
                inbound.drop.close()
                inbound.cancel()


def event_loop(bridge, reims, guest, cache, inbound, transfers, escape_key, bounds):
    server = bridge.display
    previous_pressed = False
    press_point = None
    source_in_guest = False
    armed = False
    stage = None
    generation = 0
    files_ready = False
    release = None
    next_bounds = 0
    while guest.connection.poll() is None:
        time.sleep(.009)
        now = time.monotonic()
        if now >= next_bounds:
            bounds = window_bounds(bridge.root, reims)
            next_bounds = now + .25
        while server.pending_events():
            message = server.next_event()
            if inbound is None or not inbound.drop.handle(message):
                bridge.source_event(message)
        x, y, pressed = bridge.pointer()
        inside = within((x, y), bounds)
        ended = previous_pressed and not pressed
        if pressed and not previous_pressed:
            candidate = bridge.target_at(x, y) if inside and release is None else None
            source_in_guest = candidate is not None and candidate[0].id == reims.id
            if release is None:
                generation += 1
                stage = None
                files_ready = False
            press_point = (x, y)
        previous_pressed = pressed

        try:
            while True:
                message = guest.messages.get_nowait()
                if inbound is not None:
                    inbound.on_guest(message)
                if message["event"] == "connected":
                    log("ready", window=hex(reims.id), bidirectional=inbound is not None)
                if message["event"] == "enter" and armed and source_in_guest and stage is None:
                    paths = message["paths"]
                    if paths:
                        log("finder-files", count=len(paths))
                        stage = transfers.submit(guest.download, paths, cache / str(generation))
        except queue.Empty:
            pass

        if inbound is not None:
            inbound.tick(now)
        if (source_in_guest and pressed and not armed and press_point is not None and
                abs(x - press_point[0]) + abs(y - press_point[1]) > 16):
            guest.send("arm")
            armed = True
        if armed and (ended or escape_held(server, escape_key)):
            guest.send("disarm")
            armed = False

        if source_in_guest and pressed and escape_held(server, escape_key):
            source_in_guest = False
            stage = None
            bridge.end()
            continue
        if stage is not None and stage.done() and not files_ready:
            try:
                bridge.begin(stage.result())
                files_ready = True
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                log("transfer-error", reason=str(exc))
                source_in_guest = False
                stage = None
                release = None

        if source_in_guest and ((pressed and files_ready) or ended):
            try:
                target = None if inside else bridge.target_at(x, y)
            except BadWindow:
                target = None
            if target is not None and target[0].id == reims.id:
                target = None
            if pressed:
                bridge.position((x, y), target)
            if ended:
                if target is not None and stage is not None:
                    release = ((x, y), target, time.monotonic() + 2)
                else:
                    bridge.end()
                    stage = None
                source_in_guest = False

        if release is not None and (files_ready or now > release[2]):
            point, target, deadline = release
            accepted = False
            if files_ready and now <= deadline:
                try:
                    if bridge.target_at(*point) == target:
                        accepted = bridge.finish(point, target, timeout=1)
                except BadWindow:
                    pass
            bridge.end()
            log("linux-drop", x=point[0], y=point[1], window=hex(target[0].id),
                accepted=accepted)
            release = None
            stage = None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--guest", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host-key-alias")
    parser.add_argument("--domain", help="libvirt domain for the Nemo-to-Finder direction")
    parser.add_argument("--libvirt-uri", default="qemu:///session")
    parser.add_argument("--guest-dir", required=True)
    parser.add_argument("--cache", type=Path, required=True,
                        help="private directory retained while destination copies complete")
    args = parser.parse_args()
    args.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache = Path(tempfile.mkdtemp(prefix="session-", dir=args.cache))
    if cache.stat().st_uid != os.getuid():
        parser.error("staging must be owned by the current user")
    server = display.Display()
    bridge = Xdnd(server)
    reims = server.create_resource_object("window", args.window)
    guest = Guest(args.guest, args.port, args.host_key_alias, args.guest_dir)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    tablet = Tablet(args.libvirt_uri, args.domain) if args.domain else None
    try:
        run_bridge(bridge, reims, guest, tablet, cache)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.end()
        if tablet is not None:
            tablet.close()
        guest.close()
        server.close()


if __name__ == "__main__":
    main()
