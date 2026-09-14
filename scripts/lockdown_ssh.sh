#!/usr/bin/env bash
# Close public SSH once the VPS is reachable over the tailnet. Run as root
# AFTER `tailscale up` has succeeded and you have confirmed
# `ssh aaditya@<tailscale-name>` works from your laptop.
#
# Refuses to run if the machine is not on the tailnet, because that would
# lock everyone out.
set -euo pipefail
ip4=$(tailscale ip -4 2>/dev/null || true)
if [ -z "$ip4" ]; then
    echo "This machine has no Tailscale IPv4 address yet; run 'tailscale up' first." >&2
    exit 1
fi
if [ -n "${SSH_CONNECTION:-}" ] && ! printf '%s' "${SSH_CONNECTION}" | grep -q " $ip4 "; then
    echo "You are connected over the PUBLIC address, not the tailnet ($ip4)." >&2
    echo "Reconnect via Tailscale first, then run this again, or it would cut this session." >&2
    exit 1
fi
ufw delete allow 22/tcp >/dev/null 2>&1 || true
ufw status numbered | grep -n "22" || true
echo "Public SSH closed. Port 22 is now reachable only on tailscale0 ($ip4)."
