#!/usr/bin/env bash
set -Eeuo pipefail

# ===================================================================
#  Server B — Minimal installer for MTProxy Manager backend gateway
#  Installs: WireGuard + IP forwarding + NAT
#  No panel, no MTG — pure gateway.
# ===================================================================

BACKEND_TUNNEL_IP="${BACKEND_TUNNEL_IP:-10.0.0.1}"
FRONTEND_TUNNEL_IP="${FRONTEND_TUNNEL_IP:-10.0.0.2}"
WG_INTERFACE="${WG_INTERFACE:-wg0}"
WG_PORT="${WG_PORT:-51820}"

ask_yes_no() {
  local prompt="$1" default="${2:-y}" ans
  if [[ "$default" == "y" ]]; then
    prompt="$prompt [Y/n] "
  else
    prompt="$prompt [y/N] "
  fi
  read -r -p "$prompt" ans
  ans="${ans:-$default}"
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash install_server_b.sh"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   MTProxy Manager — Server B (backend gateway)  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

echo "[1/4] Updating packages"
apt-get update -y
apt-get install -y wireguard iptables-persistent

echo "[2/4] WireGuard configuration"

WG_PRIVATE_KEY="${WG_PRIVATE_KEY:-$(wg genkey)}"
WG_PUBLIC_KEY="$(echo "${WG_PRIVATE_KEY}" | wg pubkey)"

if [[ -z "${FRONTEND_PUBLIC_IP:-}" ]]; then
  read -r -p "Enter frontend server (Server A) public IP: " FRONTEND_PUBLIC_IP
fi

echo ""
echo "--- Frontend public key required ---"
echo "To get it, run on Server A:"
echo "  cat /etc/wireguard/${WG_INTERFACE}.conf | grep PublicKey | head -2 | tail -1"
echo ""
read -r -p "Paste frontend (Server A) WireGuard public key: " FRONTEND_PUBLIC_KEY

cat >"/etc/wireguard/${WG_INTERFACE}.conf" <<WGEOF
[Interface]
Address = ${BACKEND_TUNNEL_IP}/24
PrivateKey = ${WG_PRIVATE_KEY}
ListenPort = ${WG_PORT}

# IP forwarding
PostUp = sysctl -w net.ipv4.ip_forward=1
PostUp = iptables -t nat -A POSTROUTING -o $(ip route get 1.1.1.1 | grep -oP 'dev \K\S+') -j MASQUERADE
PostUp = iptables -A FORWARD -i ${WG_INTERFACE} -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o $(ip route get 1.1.1.1 | grep -oP 'dev \K\S+') -j MASQUERADE
PostDown = iptables -D FORWARD -i ${WG_INTERFACE} -j ACCEPT

[Peer]
PublicKey = ${FRONTEND_PUBLIC_KEY}
AllowedIPs = ${FRONTEND_TUNNEL_IP}/32
WGEOF

chmod 600 "/etc/wireguard/${WG_INTERFACE}.conf"

# Persist sysctl setting
if ! grep -q 'net.ipv4.ip_forward=1' /etc/sysctl.conf; then
  echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
fi
sysctl -w net.ipv4.ip_forward=1

echo "[3/4] Saving iptables rules"
iptables-save > /etc/iptables/rules.v4 2>/dev/null || true

echo "[4/4] Enabling WireGuard"
systemctl enable --now "wg-quick@${WG_INTERFACE}"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  Server B setup complete!                        ║"
echo "║                                                  ║"
echo "║  Share this PUBLIC KEY with Server A:            ║"
echo "║    ${WG_PUBLIC_KEY}"
echo "║                                                  ║"
echo "║  On Server A, set in /etc/wireguard/wg0.conf:    ║"
echo "║    PublicKey = ${WG_PUBLIC_KEY}"
echo "║                                                  ║"
echo "║  Then on Server A run:                           ║"
echo "║    systemctl enable --now wg-quick@${WG_INTERFACE}  ║"
echo "║                                                  ║"
echo "║  Verify tunnel: ping ${FRONTEND_TUNNEL_IP}        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
