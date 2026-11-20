#!/usr/bin/python3
"""Follow the pointer between windows of the same Reims VM on X11."""

from Xlib import X, Xatom, display, error
from Xlib.protocol import event


def main():
    connection = display.Display()
    root = connection.screen().root
    clients = connection.intern_atom('_NET_CLIENT_LIST')
    active = connection.intern_atom('_NET_ACTIVE_WINDOW')
    pid = connection.intern_atom('_NET_WM_PID')
    mouse_buttons = (
        X.Button1Mask | X.Button2Mask | X.Button3Mask | X.Button4Mask | X.Button5Mask
    )
    windows = {}
    # SDL windows can disappear while processing a notification.
    connection.set_error_handler(
        lambda exc, _request: None if isinstance(exc, error.BadWindow) else
        print(exc, flush=True)
    )

    def values(window, atom, kind):
        data = window.get_full_property(atom, kind)
        return data.value if data is not None else ()

    def update_clients():
        latest = {}
        for window_id in values(root, clients, Xatom.WINDOW):
            if window_id in windows:
                latest[window_id] = windows[window_id]
                continue
            window = connection.create_resource_object('window', window_id)
            try:
                classes = window.get_wm_class() or ()
                if not any(name.lower() == 'reims-vgpu' for name in classes):
                    continue
                ids = values(window, pid, Xatom.CARDINAL)
                if len(ids) == 1:
                    window.change_attributes(event_mask=X.EnterWindowMask)
                    latest[window_id] = ids[0]
            except error.BadWindow:
                continue
        windows.clear()
        windows.update(latest)
        connection.flush()

    root.change_attributes(event_mask=X.PropertyChangeMask)
    update_clients()
    while True:
        notice = connection.next_event()
        if notice.type == X.PropertyNotify and notice.atom == clients:
            update_clients()
        elif (notice.type == X.EnterNotify and notice.mode == X.NotifyNormal
              and notice.detail != X.NotifyInferior and not notice.state & mouse_buttons):
            target = notice.window.id
            if target not in windows:
                continue
            focused = values(root, active, Xatom.WINDOW)
            if len(focused) != 1 or focused[0] == target:
                continue
            if windows.get(focused[0]) != windows[target]:
                continue
            root.send_event(
                event.ClientMessage(
                    window=target, client_type=active,
                    data=(32, [1, notice.time, focused[0], 0, 0]),
                ),
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )
            connection.flush()


if __name__ == '__main__':
    main()
