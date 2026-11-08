import glob,os,pstats
for path in sorted(glob.glob('build/software-profile/web-thread-*.pstats')):
    if not os.path.getsize(path):continue
    print(path);pstats.Stats(path).strip_dirs().sort_stats('time').print_stats(20)
