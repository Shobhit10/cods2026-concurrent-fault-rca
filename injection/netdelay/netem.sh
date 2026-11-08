#!/bin/sh
# CODS 2026 network-delay injector. Adapted from the WWW 2027 study's verified injector (inj_v2c_eph.sh, ops
# netem_on / netem_off / state, archive_data/live_webshop.zip): same qdisc layout, same transactional rollback,
# same self-limiting watchdog. Changed: it runs in the NODE debug pod (nicolaka/netshoot, --profile=sysadmin,
# hostPID) and enters the target pod's network namespace with nsenter; the namespace is found from the pod
# sandbox (pause) PID, so a restart of the app container cannot orphan the qdisc.
#
#   kubectl exec -i -n default <node-debug-pod> -- sh -s -- <op> <container-id> <pod-name> [args...] < netem.sh
#
# ops:
#   state <cid> <pod>                          read-only read-back: qdisc, filter count, token, watchdog, fail marks
#   on    <cid> <pod> <nonce> <wd_s> <ms>      egress (eth0) delay: prio root (3 bands, priomap -> band 3) + netem
#                                              delay <ms> on band 3; tcp sport 15020/15021/15090 (Istio agent health
#                                              and probes, Envoy stats) bypass to band 1. A backstop watchdog in the
#                                              debug pod removes the qdisc after <wd_s> s if the driver has not.
#                                              Prints ARMED <epoch> on success; any failure rolls everything back.
#   off   <cid> <pod>                          remove the root qdisc, verify, stop the watchdog; prints REMOVED <epoch>
set -u
OP=$1; CID=$2; POD=$3; shift 3
SB=$(chroot /host crictl inspect "$CID" 2>/dev/null | jq -r '.info.sandboxID' 2>/dev/null)
PID=$(chroot /host crictl inspectp "$SB" 2>/dev/null | jq -r '.info.pid' 2>/dev/null)
case "$PID" in ''|null|*[!0-9]*) echo "ERR_PID cid=$CID sandbox=$SB pid=$PID"; exit 2 ;; esac
HN=$(nsenter -t "$PID" -u hostname 2>/dev/null)
[ "$HN" = "$POD" ] || { echo "ERR_POD_MISMATCH hostname=$HN pod=$POD pid=$PID"; exit 2; }
NSI=$(readlink /proc/$PID/ns/net)
X="nsenter -t $PID -n"
echo "TARGET pod=$POD sandbox_pid=$PID netns=$NSI"

netem_present() { $X tc qdisc show dev eth0 2>/dev/null | grep -q -E 'netem|prio'; }
nfilt() { $X tc filter show dev eth0 2>/dev/null | grep -c 'flowid 1:1'; }
wd_pids() {
  ps -eo pid,args 2>/dev/null | awk -v n="codsnd-sleeper-netem-$POD" -v c="${1:-}" '
    $2 == "sh" && $3 == "-c" && index($0, n) { if (c != "" && index($0, " " c) == 0) next; print $1 }'
}
wd_kill() { for p in $(wd_pids "$@"); do kill "$p" 2>/dev/null; done; }
wd_wait() { i=0; while [ $i -lt 5 ]; do [ -n "$(wd_pids "$1")" ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
readback() {
  echo "RB_QDISC: $($X tc qdisc show dev eth0 | tr '\n' ';')"
  echo "RB_FILTERS: $(nfilt)"
  echo "RB_TOKEN: $(cat /tmp/codsnd_netem_$POD 2>/dev/null)"
  echo "RB_WATCHDOGS: $(wd_pids | tr '\n' ' ')"
  echo "RB_FAILMARKS: $(cat /tmp/codsnd_FAIL_netem_$POD 2>/dev/null)"
}

NETEM_WD='sleep "$DUR"
T=/tmp/codsnd_netem_$POD
[ "$(cat "$T" 2>/dev/null)" = "$NONCE" ] || exit 0
if [ "$(readlink /proc/$PID/ns/net 2>/dev/null)" != "$NSI" ]; then echo "$NONCE netns-gone" > /tmp/codsnd_FAIL_netem_$POD; rm -f "$T"; exit 1; fi
i=0
while [ $i -lt 5 ]; do
  nsenter -t "$PID" -n tc qdisc del dev eth0 root >/dev/null 2>&1
  if ! nsenter -t "$PID" -n tc qdisc show dev eth0 2>/dev/null | grep -q -E "netem|prio"; then
    rm -f "$T"; echo "$NONCE removed-by-watchdog $(date +%s)" > /tmp/codsnd_WD_netem_$POD; exit 0
  fi
  i=$((i+1)); sleep $((i*2))
done
echo "$NONCE removal-failed" > /tmp/codsnd_FAIL_netem_$POD
exit 1'

ARMED=1
WDPID=""
on_exit() {
  rc=$?
  trap - EXIT
  if [ "$ARMED" = 0 ]; then
    echo "ERR_ROLLBACK op=$OP pod=$POD rc=$rc"
    rm -f "/tmp/codsnd_netem_${POD}"
    [ -n "$WDPID" ] && kill "$WDPID" 2>/dev/null
    wd_kill; sleep 1; wd_kill
    j=0; while netem_present && [ $j -lt 3 ]; do $X tc qdisc del dev eth0 root >/dev/null 2>&1; j=$((j+1)); done
    readback
    netem_present && echo "ERR_ROLLBACK_RESIDUE netem"
    [ "$rc" -eq 0 ] && rc=3
  fi
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT TERM HUP

case "$OP" in
  state)
    readback ;;
  on)
    NONCE=$1; DUR=$2; DMS=$3
    if netem_present; then echo "ERR_PREEXISTING_QDISC"; readback; exit 3; fi
    rm -f /tmp/codsnd_FAIL_netem_$POD /tmp/codsnd_WD_netem_$POD
    ARMED=0
    $X tc qdisc replace dev eth0 root handle 1: prio bands 3 priomap 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 || { echo ERR_TC_ROOT; exit 3; }
    $X tc qdisc replace dev eth0 parent 1:3 handle 30: netem delay "${DMS}ms" || { echo ERR_TC_NETEM; exit 3; }
    for port in 15020 15021 15090; do
      $X tc filter add dev eth0 protocol ip parent 1: prio 1 u32 match ip protocol 6 0xff match ip sport $port 0xffff flowid 1:1 || { echo ERR_TC_FILTER; exit 3; }
    done
    echo "$NONCE" > "/tmp/codsnd_netem_${POD}" || { echo ERR_TOKEN; exit 3; }
    POD="$POD" NONCE="$NONCE" PID="$PID" NSI="$NSI" DUR="$DUR" setsid sh -c "$NETEM_WD" "codsnd-sleeper-netem-$POD" "$NONCE" </dev/null >/dev/null 2>&1 &
    WDPID=$!
    wd_wait "$NONCE" || { echo ERR_WATCHDOG; exit 3; }
    { netem_present && [ "$(nfilt)" = 3 ] && [ "$(cat "/tmp/codsnd_netem_${POD}" 2>/dev/null)" = "$NONCE" ]; } || { echo ERR_VERIFY; exit 3; }
    ARMED=1
    echo "ARMED $(date +%s)"
    readback ;;
  off)
    j=0; while netem_present && [ $j -lt 3 ]; do $X tc qdisc del dev eth0 root >/dev/null 2>&1; j=$((j+1)); done
    if netem_present; then echo "ERR_TC_DEL"; readback; exit 3; fi
    rm -f "/tmp/codsnd_netem_${POD}"; wd_kill
    echo "REMOVED $(date +%s)"
    readback ;;
  *)
    echo "ERR_OP $OP"; exit 4 ;;
esac
exit 0
