"""The Xdnd peer for the Reims file-drag prototype."""

import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from Xlib import X, Xatom
from Xlib.error import BadWindow
from Xlib.protocol import event


class Xdnd:
    def __init__(self, display):
        self.display = display
        self.root = display.screen().root
        self.window = self.root.create_window(
            -1, -1, 1, 1, 0, X.CopyFromParent,
            X.InputOutput, X.CopyFromParent, override_redirect=True,
            event_mask=X.PropertyChangeMask,
        )
        self.atoms = {
            name: display.intern_atom(name) for name in (
                "XdndAware", "XdndProxy", "XdndEnter", "XdndPosition",
                "XdndStatus", "XdndLeave", "XdndDrop", "XdndFinished",
                "XdndSelection", "XdndTypeList", "XdndActionList",
                "XdndActionCopy", "text/uri-list", "TARGETS", "_REIMS_DRAG_DATA",
            )
        }
        self.window.change_property(
            self.atom("XdndActionList"), Xatom.ATOM, 32, [self.atom("XdndActionCopy")]
        )
        self.window.change_property(self.atom("XdndAware"), Xatom.ATOM, 32, [5])
        self.display.flush()
        self.target = None
        self.point = None
        self.sent_at = 0.0
        self.accepted = False
        self.waiting = False
        self.files = []

    def atom(self, name):
        return self.atoms[name]

    def pointer(self):
        pointer = self.root.query_pointer()
        return pointer.root_x, pointer.root_y, bool(pointer.mask & X.Button1Mask)

    def target_at(self, x, y):
        window = self.root.translate_coords(self.root, x, y).child
        while window:
            version = window.get_full_property(self.atom("XdndAware"), Xatom.ATOM)
            if version is not None and len(version.value) and version.value[0] >= 3:
                target = window
                proxy = window.get_full_property(self.atom("XdndProxy"), Xatom.WINDOW)
                if proxy is not None and len(proxy.value) == 1:
                    other = self.display.create_resource_object("window", proxy.value[0])
                    try:
                        pointer = other.get_full_property(self.atom("XdndProxy"), Xatom.WINDOW)
                        if pointer is not None and list(pointer.value) == [other.id]:
                            target = other
                    except BadWindow:
                        pass
                return window, target, min(5, int(version.value[0]))
            window = window.translate_coords(self.root, x, y).child
        return None

    def message(self, receiver, window, name, values):
        receiver.send_event(event.ClientMessage(window=window, client_type=self.atom(name),
                                                data=(32, values)))
        self.display.flush()

    def begin(self, files):
        self.files = files
        self.window.set_selection_owner(self.atom("XdndSelection"), X.CurrentTime)
        self.display.sync()

    def end(self):
        self.leave()
        selection = self.atom("XdndSelection")
        if self.display.get_selection_owner(selection) == self.window:
            none = self.display.create_resource_object("window", X.NONE)
            none.set_selection_owner(selection, X.CurrentTime)
        self.files = []
        self.display.flush()

    def leave(self):
        if self.target is not None:
            window, receiver, _ = self.target
            self.message(receiver, window, "XdndLeave", [self.window.id, 0, 0, 0, 0])
        self.target = self.point = None
        self.accepted = self.waiting = False

    def position(self, point, target):
        if target != self.target:
            self.leave()
            if target is not None:
                self.target = target
                window, receiver, version = target
                self.message(receiver, window, "XdndEnter", [
                    self.window.id, version << 24, self.atom("text/uri-list"), 0, 0,
                ])
        if target is None or self.waiting:
            return
        now = time.monotonic()
        if point == self.point and (self.accepted or now - self.sent_at < .08):
            return
        self.sent_at = now
        self.point = point
        self.accepted = False
        self.waiting = True
        x, y = point
        window, receiver, _ = target
        self.message(receiver, window, "XdndPosition", [
            self.window.id, 0, ((x & 0xffff) << 16) | (y & 0xffff),
            X.CurrentTime, self.atom("XdndActionCopy"),
        ])

    def drop(self):
        if self.target is None or not self.accepted:
            self.leave()
            return False
        window, receiver, _ = self.target
        self.message(receiver, window, "XdndDrop", [self.window.id, 0, X.CurrentTime, 0, 0])
        return True

    def source_event(self, message):
        if message.type == X.SelectionRequest:
            self.send_selection(message)
            return None
        if message.type != X.ClientMessage or self.target is None:
            return None
        values = message.data[1]
        if values[0] != self.target[0].id:
            return None
        if message.client_type == self.atom("XdndStatus"):
            self.accepted = bool(values[1] & 1) and values[4] == self.atom("XdndActionCopy")
            self.waiting = False
        elif message.client_type == self.atom("XdndFinished"):
            self.target = None
            return bool(values[1] & 1)
        return None

    def send_selection(self, request):
        property_id = request.property or request.target
        if request.target == self.atom("text/uri-list"):
            contents = "".join(path.as_uri() + "\r\n" for path in self.files).encode()
            request.requestor.change_property(property_id, request.target, 8, contents)
        elif request.target == self.atom("TARGETS"):
            request.requestor.change_property(property_id, Xatom.ATOM, 32, [
                self.atom("TARGETS"), self.atom("text/uri-list"),
            ])
        else:
            property_id = X.NONE
        request.requestor.send_event(event.SelectionNotify(
            time=request.time, requestor=request.requestor, selection=request.selection,
            target=request.target, property=property_id,
        ))
        self.display.flush()

    def drain_source(self):
        while self.display.pending_events():
            result = self.source_event(self.display.next_event())
            if result is not None:
                return result
        return None

    def finish(self, point, target, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain_source()
            self.position(point, target)
            if self.point == point and self.accepted and not self.waiting:
                break
            if target is None:
                return False
            time.sleep(.005)
        if not self.drop():
            return False
        while time.monotonic() < deadline:
            result = self.drain_source()
            if result is not None:
                return result
            time.sleep(.005)
        return False


class IncomingDrop:
    """Receive the host file selection on the Reims window's Xdnd proxy."""

    def __init__(self, dnd, reims, notify):
        self.dnd = dnd
        self.reims = reims
        self.notify = notify
        self.source = None
        self.version = 0
        self.point = None
        self.paths = None
        self.requested = False
        self.dropped = False
        self.ready = False
        self.proxy = dnd.atom("XdndProxy")
        if reims.get_full_property(self.proxy, Xatom.WINDOW) is not None:
            raise RuntimeError("the Reims window already has an Xdnd proxy")
        dnd.window.change_property(self.proxy, Xatom.WINDOW, 32, [dnd.window.id])
        reims.change_property(self.proxy, Xatom.WINDOW, 32, [dnd.window.id])
        dnd.display.sync()

    def finish(self, accepted):
        if self.source is not None and self.dropped:
            action = self.dnd.atom("XdndActionCopy") if accepted else 0
            self.dnd.message(self.source, self.source, "XdndFinished", [
                self.reims.id, int(accepted), action, 0, 0,
            ])
        self.reset()

    def reset(self):
        self.source = None
        self.point = None
        self.paths = None
        self.requested = self.dropped = self.ready = False

    def close(self):
        prop = self.reims.get_full_property(self.proxy, Xatom.WINDOW)
        if prop is not None and list(prop.value) == [self.dnd.window.id]:
            self.reims.delete_property(self.proxy)
        self.dnd.display.flush()

    def handle(self, message):
        if message.type == X.SelectionNotify:
            self.selection(message)
            return True
        if message.type != X.ClientMessage or message.window.id != self.reims.id:
            return False
        command = message.client_type
        atom = self.dnd.atom
        data = message.data[1]
        if command == atom("XdndEnter"):
            self.reset()
            source = self.dnd.display.create_resource_object("window", data[0])
            version = data[1] >> 24
            if not 3 <= version <= 5:
                return True
            types = data[2:]
            if data[1] & 1:
                prop = source.get_full_property(atom("XdndTypeList"), Xatom.ATOM)
                types = prop.value if prop is not None else ()
            self.source = source
            self.version = version
            self.ready = atom("text/uri-list") in types
            if self.ready:
                self.notify("enter")
            return True

        if self.source is None or data[0] != self.source.id:
            return True
        if command == atom("XdndPosition"):
            self.point = (data[2] >> 16, data[2] & 0xffff)
            if self.ready and not self.requested:
                self.dnd.window.convert_selection(
                    atom("XdndSelection"), atom("text/uri-list"), atom("_REIMS_DRAG_DATA"),
                    data[3],
                )
                self.requested = True
            self.dnd.message(self.source, self.source, "XdndStatus", [
                self.reims.id, 3 if self.ready else 2, 0, 0,
                atom("XdndActionCopy") if self.ready else 0,
            ])
            if self.ready:
                self.notify("position")
        elif command == atom("XdndDrop"):
            self.dropped = True
            if self.ready:
                self.notify("drop")
            else:
                self.finish(False)
        elif command == atom("XdndLeave"):
            self.notify("leave")
            self.reset()
        return True

    def selection(self, message):
        if self.source is None or message.property != self.dnd.atom("_REIMS_DRAG_DATA"):
            return
        prop = self.dnd.window.get_full_property(message.property, self.dnd.atom("text/uri-list"))
        if prop is None:
            return
        self.dnd.window.delete_property(message.property)
        paths = []
        for line in prop.value.decode().splitlines():
            uri = urlsplit(line)
            if uri.scheme == "file" and uri.netloc in ("", "localhost"):
                path = Path(unquote(uri.path))
                if path.is_absolute() and path.exists():
                    paths.append(path)
        if paths:
            self.paths = paths
            self.notify("files")
