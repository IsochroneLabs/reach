#!/usr/bin/env bash
# Sample `docker stats` of one container every second; print the peak memory (MiB) on exit.
# Usage: memwatch.sh <container> <outfile>   (stop with kill; the trap writes the peak)
set -u
C=$1; OUT=$2; PEAK=0
trap 'echo "$C peak_mem_mib=$PEAK" | tee "$OUT"; exit 0' TERM INT
while docker inspect "$C" >/dev/null 2>&1; do
  M=$(docker stats --no-stream --format '{{.MemUsage}}' "$C" 2>/dev/null | awk '{print $1}')
  V=$(python3 -I -c "import re,sys;s='$M';m=re.match(r'([\d.]+)([KMG]i?B)',s);f={'KiB':1/1024,'MiB':1,'GiB':1024,'kB':1/1024,'MB':1,'GB':1024};print(int(float(m[1])*f[m[2]]) if m else 0)")
  [ "$V" -gt "$PEAK" ] && PEAK=$V
  sleep 1
done
echo "$C peak_mem_mib=$PEAK" | tee "$OUT"
