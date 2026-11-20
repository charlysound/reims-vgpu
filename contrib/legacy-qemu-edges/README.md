# Legacy QEMU tablet edges for Finder and the Dock

Two small patches make edge gestures feel like a physical Mac on the tested
dual-display legacy stack. Reaching the outer right edge lets Finder tile on
release. Holding the pointer against the lower edge can summon the Dock on the
other monitor.

The QEMU patches apply in filename order on the public
[QEMU base](https://github.com/steelbrain/qemu-reims-vgpu/commit/93fb0692d50658de9efc3d47f37a41478d7fc5e5).
They target the old `apple-gfx` code. QEMU's source license applies.

## Configuration

- Tiling is opt-in with `REIMS_VGPU_TABLET_RIGHT_EDGE_PORT=1` for a two-display
  layout whose rightmost display is port 1. Use the port that is actually at
  the right edge.
- Dock pressure is opt-in with `REIMS_VGPU_DOCK_PRESSURE=1`. Add a USB
  `usb-mouse,motion-only=on` device on the test guest's xHCI controller. It
  delivers relative motion for the bottom-edge gesture while the tablet still
  carries the buttons and ordinary pointer positioning.

## Recorded results

On Intel Sequoia 15.7.7 with two 1920 × 1080 displays, Finder tiled on the
right from either starting screen. Its window went from 700 × 440 to 948 ×
1,039 pixels. Left-side tiling succeeded too. Results are available for
[windowed mode](tile-verified-windowed.json),
[fullscreen](tile-verified-fullscreen.json), and
[the rerun after the Dock change](dock-regression-fullscreen.json).
The Dock was moved left to right and back after a reboot.

For a current-driver follow-up, try the two gestures separately. A clean report
on which gesture still needs support can lead to a focused change in the
current QEMU input path.
