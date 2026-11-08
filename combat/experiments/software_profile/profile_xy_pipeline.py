"""Whole moving-game A/B/A test; restores the deployed executable afterward."""
from __future__ import print_function
import os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';exe='combat/dist/Flighting.Headless.exe'
subprocess.check_call(['python','combat/board/stop_service.py'])
rollback=folder+'/before-xy-game.exe';shutil.copyfile(exe,rollback)
try:
    shutil.copyfile(folder+'/XY.Headless.exe',exe+'.next');os.rename(exe+'.next',exe)
    for name,enabled in [('xy-pipeline-before','0'),('xy-pipeline-enabled','1'),('xy-pipeline-after','0')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',name],env=dict(os.environ,FLIGHTING_CITY_XY_CACHE=enabled,SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1'))
finally:
    shutil.copyfile(rollback,exe+'.next');os.rename(exe+'.next',exe)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
