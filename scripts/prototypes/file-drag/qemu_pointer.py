"""Send mouse input through the existing QEMU HID tablet."""

import json

import libvirt
import libvirt_qemu


def guest_point(bounds, size, point):
    left, top, right, bottom = bounds
    width, height = size
    scale = min((right - left) / width, (bottom - top) / height)
    image_x = left + (right - left - width * scale) / 2
    image_y = top + (bottom - top - height * scale) / 2
    px, py = point
    return (min(width - 1, max(0, round((px - image_x) / scale))),
            min(height - 1, max(0, round((py - image_y) / scale))))


class Tablet:
    def __init__(self, uri, domain):
        self.connection = libvirt.open(uri)
        self.domain = self.connection.lookupByName(domain)
        self.held = False

    def send(self, events):
        request = {"execute": "input-send-event", "arguments": {"events": events}}
        response = json.loads(libvirt_qemu.qemuMonitorCommand(self.domain, json.dumps(request), 0))
        if "return" not in response:
            raise RuntimeError(f"QEMU rejected pointer input: {response.get('error')}")

    def move(self, point, size):
        self.send([{"type": "abs", "data": {"axis": axis, "value": round(value * 32767 / extent)}}
                   for axis, value, extent in zip(("x", "y"), point, size)])

    def button(self, pressed):
        self.send([{"type": "btn", "data": {"button": "left", "down": pressed}}])
        self.held = pressed

    def cancel(self):
        if self.held:
            key = {"type": "qcode", "data": "esc"}
            try:
                self.send([{"type": "key", "data": {"key": key, "down": down}}
                           for down in (True, False)])
            finally:
                self.button(False)

    def close(self):
        try:
            self.cancel()
        finally:
            self.connection.close()
