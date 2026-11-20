# File drag between Reims and the Linux desktop

The prototype bridges native file drags between a single Reims window on X11
and a single macOS display. Finder and Nemo choose the destination from the
pointer position. Copies preserve the source. The Finder-to-Linux handoff
currently uses the right edge of the guest display.

## Run

On the Linux host, use the X11 window ID from `xdotool search --name '^Reims vGPU'`:

```sh
REIMS_DRAG_GUEST=macos-vm-ssh-alias REIMS_DRAG_DOMAIN=macos-test \
  scripts/prototypes/file-drag/run.sh REIMS_X11_WINDOW_ID
```

Set `REIMS_DRAG_GUEST` to an SSH alias or destination and `REIMS_DRAG_DOMAIN` to
the libvirt domain name. The launcher uses SSH port 22 and `qemu:///session`
by default. Override them with `REIMS_DRAG_PORT` and `REIMS_DRAG_LIBVIRT_URI`.
Set `REIMS_DRAG_HOST_KEY_ALIAS` if you use a separate name in known_hosts. The
VM needs passwordless SSH with a verified host key and the macOS command line
tools. The Linux host needs Python 3 with Xlib and the libvirt bindings.

The launcher starts a temporary AppKit helper in the guest's graphical
session. The Linux process installs an XDND proxy on the selected Reims
window and restores the property when it exits. Keep Reims and the other
drop target visible. Stop the bridge with Ctrl+C. Transfer caches are kept
for file copies still running after a drop. The launcher prints the paths.

## Verify

Run `scripts/prototypes/file-drag/test-x11.sh` for the GTK-to-XDND protocol
check on a separate Xvfb display. That test exercises the file URI and
release coordinate, with no input on the active desktop.

For a live check, open a temporary source folder with a file and a destination
window with two visible folders `A` and `B`. Drag onto `A`, keep holding the
button, move to `B` and release. Check that `B` contains the file, `A` is
empty, the hash matches and the original is present. Repeat the test in the
other direction. `drag-test.py` replays a drag on the current graphical
desktop and requires exclusive use of the pointer during the test.

The same prototype passed the single-file `A → B` test in both directions
with Finder on macOS Tahoe 26.6.2 and Nemo 6.6.3 on Linux. For the final run,
Nemo used an isolated Xvfb display and the bridge drove Tahoe's real virtual
tablet. In both runs, `B` contained the copy, `A` had no copy, and the source
still existed with the same SHA-256.

| Direction | Release and result | SHA-256 |
| --- | --- | --- |
| Finder → Nemo | Host `(2313, 418)` accepted by Nemo | `0953776d7cf1d27a837b6b325e7988c9e834523e8b0a6b99f4dd8d51463b4d5d` |
| Nemo → Finder | Guest target `(1389, 463)`; AppKit release `(1388.994, 462.975)` | `d05f4a42d024e1c415d77ad2193f2c7f431075604634909684bdc5db49090418` |

Large files, multiple selection, and cancellation across window boundaries
have not been qualified end to end. The prototype stages data over SSH
before starting the native drag on the destination.


## Pick up the prototype

The observed results come from a Tahoe 26.6.2 guest on the legacy Reims/QEMU
stack. The packaging above makes the endpoints configurable. Start with the
existing Xvfb protocol test, then try the two-folder test on the current
`reims-graphics-pci` device using a disposable guest copy. Record the display
layout, both drop targets and the resulting hashes. The bridge uses native
AppKit and XDND so Finder and Nemo resolve the destination from the pointer.
A current-driver report or a narrow patch that removes the fixed right-edge
assumption would help move it toward a general guest-tools feature.
