#!/bin/sh
# K3 status display (#4): fetch a pre-rendered 600x800 grayscale PNG over plain HTTP and draw it
# with KOReader's fbink, every INTERVAL seconds. Meant for a K3 left on its charger.
#
#   k3dash.sh start | stop | once
#
# Written by koreader-d00901; settings are in k3dash.conf next to this folder. The device commands
# follow KOReader's own handling of FW 3.x Kindles: wifid via lipc-set-prop -i, and two key-139
# presses through /proc/keypad to make the stock UI repaint (koreader.sh, device.lua v2026.07.1).

DIR=/mnt/us/extensions/k3dash
CONF="${DIR}/k3dash.conf"
LOG="${DIR}/k3dash.log"
PIDFILE=/tmp/k3dash.pid
IMG=/tmp/k3dash.png
FBINK=/mnt/us/koreader/fbink
CURL=/mnt/us/usbnet/bin/curl

URL=""
INTERVAL=300
# shellcheck source=/dev/null
[ -r "${CONF}" ] && . "${CONF}"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"${LOG}"
}

say() {
    # One line of text at the bottom of the screen, over whatever is there.
    [ -x "${FBINK}" ] && "${FBINK}" -q -y -1 "$*"
}

fetch() {
    rm -f "${IMG}.part"
    if command -v wget >/dev/null 2>&1; then
        wget -q -T 30 -O "${IMG}.part" "${URL}" || return 1
    elif [ -x "${CURL}" ]; then
        "${CURL}" -fsS -m 30 -o "${IMG}.part" "${URL}" || return 1
    else
        log "no wget or curl found"
        return 1
    fi
    [ -s "${IMG}.part" ] && mv -f "${IMG}.part" "${IMG}"
}

draw() {
    if fetch; then
        "${FBINK}" -q -c -f -g file="${IMG}"
    else
        log "fetch failed: ${URL}"
        say "dashboard: fetch failed $(date '+%H:%M'), retrying"
    fi
}

loop() {
    lipc-set-prop -i com.lab126.powerd preventScreenSaver 1
    lipc-set-prop -i com.lab126.wifid enable 1
    log "started: ${URL} every ${INTERVAL}s"
    while :; do
        draw
        sleep "${INTERVAL}"
    done
}

running() {
    [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null
}

case "$1" in
    start)
        if [ -z "${URL}" ]; then
            say "dashboard: no URL in ${CONF}"
            exit 1
        fi
        if running; then
            say "dashboard: already running"
            exit 0
        fi
        say "dashboard: starting, first image in a few seconds"
        loop </dev/null >>"${LOG}" 2>&1 &
        echo $! >"${PIDFILE}"
        ;;
    stop)
        if running; then
            kill "$(cat "${PIDFILE}")"
            log "stopped"
        fi
        rm -f "${PIDFILE}"
        lipc-set-prop -i com.lab126.powerd preventScreenSaver 0
        echo 'send 139' >/proc/keypad
        echo 'send 139' >/proc/keypad
        ;;
    once)
        draw
        ;;
    *)
        echo "usage: $0 start|stop|once" >&2
        exit 2
        ;;
esac
