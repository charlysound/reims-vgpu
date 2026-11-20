#!/usr/bin/python3
"""Toggle the active Reims display window, without closing the guest."""
import subprocess
windows=subprocess.check_output(['/usr/bin/wmctrl','-lx'],text=True)
candidates=[]
for line in windows.splitlines():
 fields=line.split(None,4)
 if len(fields)>=5 and fields[2].lower().endswith('.reims-vgpu'):
  candidates.append(fields[0])
if candidates:
 active=subprocess.run(['/usr/bin/xdotool','getactivewindow'],capture_output=True,text=True)
 active_id=int(active.stdout.strip()) if active.returncode==0 else None
 target=next((wid for wid in candidates if int(wid,16)==active_id),candidates[0])
 subprocess.run(['/usr/bin/wmctrl','-i','-a',target],check=True)
 subprocess.run(['/usr/bin/wmctrl','-i','-r',target,'-b','toggle,fullscreen'],check=True)
else:
 subprocess.run(['/usr/bin/notify-send','Reims','La fenêtre Reims est fermée.'])
