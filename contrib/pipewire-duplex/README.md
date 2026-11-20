# A stereo PipeWire send and return for a macOS guest

Treat the guest like an audio device with a send and a return. In the Linux
Patchbay, connect whatever signal you choose to a dedicated stereo send bus.
QEMU can read the remapped monitor of that bus as its capture source. The
guest's playback remains a separate node to route to a host destination.

## Setup

The two example configurations create a stereo 48 kHz
[`reims_input` sink](pipewire.conf.d/reims-input.conf) and a
[`reims_microphone` source](pipewire-pulse.conf.d/reims-input.conf) that follows
its monitor. Place the snippets in the corresponding directories under
`~/.config/pipewire`. Reload the appropriate user audio services at a time
that suits your audio session. In the QEMU PulseAudio backend, select
`reims_microphone` as the input source. Route the VM playback node separately
in the patchbay.

## Recorded results

On the tested Sequoia Intel guest, Apple Virtual Sound Device recorded a
997 Hz signal on both channels of the Linux-to-macOS path. A guest-generated
997 Hz signal was captured on both Linux return channels. The
[measurements](stereo-997hz.json) contain the channel peaks and RMS values
during the tone. A physical microphone and a particular output mix are
choices for each user.

Try sending a generated tone and verify each channel independently. A routing
recipe for the contemporary QEMU setup or a short script that selects the
two endpoints would make this useful to other audio workflows.
