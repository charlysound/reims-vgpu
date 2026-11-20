# Two usable Reims windows on legacy Intel Sequoia

The second Reims window can show a real extended macOS desktop. With the
display handoff in these patches, a Finder window can be dragged from one
display to the other in one gesture. The pointer keeps its position across
the switch and the guest receives the release on the intended display.

## Try the historical build

The patches apply in filename order on Reims
`f3cbad7fa3203cce9ae4d66a3e9887ad3c52573c` (`arm64-last-capable`). The tested
guest was Intel macOS Sequoia 15.7.7 (24G720), using the Apple paravirtual GPU's
protocol 6. Configure two extended displays with `displays=2`,
`REIMS_VGPU_LEGACY_MULTIPLE_DISPLAYS=1` and
`REIMS_VGPU_WINDOW_SEAMLESS_INPUT=1`.

Build the small [guest display helper](guest/display-focus.c) on macOS:

```sh
mkdir -p "$HOME/Library/Application Support/Reims"
clang -Wall -Wextra -framework ApplicationServices display-focus.c \
  -o "$HOME/Library/Application Support/Reims/reims-display-focus"
```

Run the [host display helper](display-sync.py) with an SSH alias whose host key
is already verified and a fresh socket path in the private runtime directory:

```sh
python3 display-sync.py --guest macos-vm-ssh-alias \
  --socket "$XDG_RUNTIME_DIR/reims-display-sync.sock"
```

Give the Reims process the same path in `REIMS_VGPU_TABLET_DISPLAY_SOCKET`.
For a first check on a disposable guest, use two adjacent 1920 × 1080 displays.
Drag a Finder title bar across their shared edge at two speeds and release
outside each outer edge. Compare the final display and coordinates.

## Recorded results

- The second window was initially black. The legacy enumeration option
  enabled two extended 1920 × 1080 guest displays.
- Four cross-display drags reached the expected positions. [The 1,085 sampled
  positions](evidence/synchronized-drag.json) showed zero measured horizontal
  reversal and zero vertical error along those reported paths.
- Six edge cases were recorded in [windowed](evidence/edge-verified-windowed.json)
  and [fullscreen](evidence/edge-verified-fullscreen.json) modes.
- [Four selections](evidence/first-click.json) reached Finder on the first
  click during the session. The early startup case when SSH is warming up
  still needs testing.
- Thirteen Linux input tests passed in the recorded synchronization build.

## Where to take this

Current Reims already exposes several `reims-graphics-pci` displays. Start by
running the same one-gesture scenario there. A report that identifies whether
the button state or the coordinates get lost would let someone port the small
relevant part without taking the legacy display switch helper along.
