#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1
BLUE=$'\033[34m'; RESET=$'\033[0m'
if ! /usr/bin/python3 -c 'import PyQt6' 2>/dev/null; then
  printf '%sMissing python3-pyqt6.%s\n' "$BLUE" "$RESET"
  exit 1
fi
mkdir -p logs
PERF="$HERE/logs/performance.csv"
APPLOG="$HERE/logs/application.log"
CRASH="$HERE/logs/crash.log"
LAUNCH="$HERE/logs/launcher.log"
REPORT="$HERE/logs/crash-report.txt"
# Overwrite all diagnostic files on each launch to avoid unbounded retention.
printf 'timestamp,pid,cpu_percent,rss_kib,vsz_kib,threads\n' > "$PERF"
: > "$APPLOG"; : > "$CRASH"; : > "$LAUNCH"; : > "$REPORT"
START="$(date '+%Y-%m-%dT%H:%M:%S%z')"
printf 'start=%s\n' "$START" >> "$LAUNCH"
printf '%sStarting portable SDS100 Manager diagnostic build.%s\n' "$BLUE" "$RESET"
# -u flushes stdout/stderr, -X faulthandler captures Python fatal errors.
PYTHONFAULTHANDLER=1 PYTHONUNBUFFERED=1 /usr/bin/python3 -u -X faulthandler database_favorites_manager.py "$@" > >(tee -a "$APPLOG") 2> >(tee -a "$APPLOG" "$CRASH" >&2) &
APP_PID=$!
printf 'pid=%s\n' "$APP_PID" >> "$LAUNCH"
(
 while kill -0 "$APP_PID" 2>/dev/null; do
  SAMPLE="$(ps -p "$APP_PID" -o pid=,pcpu=,rss=,vsz=,nlwp= 2>/dev/null || true)"
  if [[ -n "${SAMPLE//[[:space:]]/}" ]]; then
   read -r PID CPU RSS VSZ THREADS <<< "$SAMPLE"
   printf '%s,%s,%s,%s,%s,%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$PID" "$CPU" "$RSS" "$VSZ" "$THREADS" >> "$PERF"
  fi
  sleep 5 & wait $! || break
 done
) &
MONITOR_PID=$!
trap 'kill "$MONITOR_PID" 2>/dev/null || true' EXIT
trap 'kill "$APP_PID" 2>/dev/null || true' INT TERM
wait "$APP_PID"; STATUS=$?
END="$(date '+%Y-%m-%dT%H:%M:%S%z')"
kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true
printf 'end=%s\nexit_code=%s\n' "$END" "$STATUS" >> "$LAUNCH"
if (( STATUS >= 128 )); then printf 'signal_number=%s\n' "$((STATUS-128))" >> "$LAUNCH"; fi
if (( STATUS != 0 )); then
 {
  printf 'SDS100 Manager abnormal exit\nStart: %s\nEnd: %s\nPID: %s\nExit code: %s\n\n' "$START" "$END" "$APP_PID" "$STATUS"
  printf 'Last resource samples:\n'; tail -n 12 "$PERF"
  printf '\nLast application messages:\n'; tail -n 100 "$APPLOG"
  printf '\nFatal error / stderr output:\n'; tail -n 100 "$CRASH"
 } > "$REPORT"
 printf '%sApplication exited abnormally (%s). See logs/crash-report.txt%s\n' "$BLUE" "$STATUS" "$RESET"
else
 printf '%sApplication exited normally.%s\n' "$BLUE" "$RESET"
fi
exit "$STATUS"
