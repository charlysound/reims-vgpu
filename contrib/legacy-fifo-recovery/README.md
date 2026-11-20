# Recover a missed wake on the legacy Linux child FIFO

The macOS GUI could stop updating while SSH still worked. The stalled child
had published work that was visible in the FIFO but its consumer remained
asleep. Giving it a normal FIFO wake resumed the session. The fix rechecks
publication on a bounded 50 ms wait on the affected Linux child path and lets
the usual FIFO handling process any work found.

The [patch](patches/01-recheck-child-fifo.patch) targets Reims
`f3cbad7fa3203cce9ae4d66a3e9887ad3c52573c` (`arm64-last-capable`). It includes the
regression test for a publication that lacks a wake. Developers can inspect
or run the FIFO tests from the patched core crate.

## Recorded results

- [97 FIFO tests passed](fifo-results.txt). The recorded core and video
  regression checks also passed with the documented isolated core trace test
  run in a separate process.
- No recurrence was seen in roughly 10 minutes after reinstalling and
  rebooting on Sequoia 15.7.7. The trial ended before the planned 15 minutes.
- The cause of the original missed or early notification was unresolved.
  [Recorded limitations](limitations.json)

The first follow-up on any similar freeze is to distinguish queued FIFO work
from GPU or guest errors. Current `reims-graphics` uses a different device
architecture. This report and patch are a reference for the legacy branch.
