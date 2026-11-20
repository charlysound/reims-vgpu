# Legacy Sequoia hardware video from Metal-rendered surfaces

Hardware encoding could receive stale IOSurface pages after a Metal GPU
conversion. H.264 and HEVC then encoded the wrong colors, even though the
shader produced the right pixels. These patches make GPU-written surface
contents visible to the video mapper before it reads them. A separate HEVC
change preserves a 1080-line visible image when the backend encodes 1088 lines.

## Patch bases and reproduction

Apply [patch 01](patches/01-hevc-conformance-window.patch) and
[patch 02](patches/02-synchronize-surfaces-before-video-reads.patch) to Reims
`f3cbad7fa3203cce9ae4d66a3e9887ad3c52573c` (`arm64-last-capable`).
[Patch 03](patches/03-qemu-in-process-gpu-tasks.patch) applies to the
[legacy QEMU base](https://github.com/steelbrain/qemu-reims-vgpu/commit/93fb0692d50658de9efc3d47f37a41478d7fc5e5).
The recorded legacy video setup used
`-global apple-gfx-pci.process-isolation=off` with that QEMU patch.

The test guest was Sequoia 15.7.7 (24G720) with a compatible legacy Apple
paravirtual graphics and VideoToolbox setup. The [Objective-C
probe](encode-direct-gpu.m) is test source. It exercises BGRA to NV12 through
the GPU and then requires hardware encoding. Build it and read its usage
before running it on a disposable compatible guest:

```sh
clang -fobjc-arc encode-direct-gpu.m -framework Foundation \
  -framework VideoToolbox -framework CoreMedia -framework CoreVideo \
  -framework IOSurface -framework Metal -o encode-direct-gpu
```

## Recorded results

Nine hardware encoding cases produced 540 frames at 1920 × 1080.
[The measured output](native-quality.json) includes CPU buffers, RGB
conversion and direct GPU conversion without locking the result for a CPU read.
PSNR for the direct color case was 41.24 dB for H.264 and 41.55 dB for HEVC
against the reference. Two more color runs after reboot reproduced the
decoded pixels. H.264, HEVC 8-bit and HEVC 10-bit decoder outputs were also
checked. These are results for this configuration and these inputs.

The crop test is the easiest part to carry forward independently. Compare
the coded block height and the visible height reported by a decoder. The
surface-copy patch is specific to the older mapper and its GPU backing model.
