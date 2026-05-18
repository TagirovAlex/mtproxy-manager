#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="${APP_USER:-mtproxy}"
APP_GROUP="${APP_GROUP:-mtproxy}"
APP_DIR="${APP_DIR:-/opt/mtproxy-manager}"
VENV_DIR="${APP_DIR}/.venv"
MANAGER_SERVICE="mtproxy-manager"

NGINX_CONF_NAME="mtproxy-manager"
NGINX_AVAILABLE="/etc/nginx/sites-available/${NGINX_CONF_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${NGINX_CONF_NAME}"

ask_yes_no() {
  local prompt="$1" default="${2:-n}" ans
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
  echo "Run as root: sudo bash uninstall.sh"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     MTProxy Manager — Uninstall                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "This will remove MTProxy Manager and optionally its data."
echo ""

if ! ask_yes_no "Are you sure you want to proceed?" "n"; then
  echo "Cancelled."
  exit 0
fi

# ---- 1. Stop panel service ----
echo ""
echo "[1/7] Stopping panel service"
if systemctl is-active --quiet "${MANAGER_SERVICE}" 2>/dev/null; then
  systemctl stop "${MANAGER_SERVICE}"
  echo "  Stopped ${MANAGER_SERVICE}"
fi
if systemctl is-enabled --quiet "${MANAGER_SERVICE}" 2>/dev/null; then
  systemctl disable "${MANAGER_SERVICE}"
  echo "  Disabled ${MANAGER_SERVICE}"
fi

# ---- 2. Stop all MTG instances ----
echo "[2/7] Stopping MTG instances"
for unit in $(systemctl list-units --type=service --all --no-legend 'mtg@*.service' 2>/dev/null | awk '{print $1}'); do
  systemctl stop "$unit" 2>/dev/null || true
  systemctl disable "$unit" 2>/dev/null || true
  echo "  Stopped $unit"
done

# ---- 3. Remove systemd files ----
echo "[3/7] Removing systemd files"
rm -f /etc/systemd/system/mtg@.service
rm -f "/etc/systemd/system/${MANAGER_SERVICE}.service"
systemctl daemon-reload
echo "  Removed systemd unit files"

# ---- 4. Remove sudoers config ----
echo "[4/7] Removing sudoers config"
rm -f /etc/sudoers.d/mtproxy-systemctl
echo "  Removed /etc/sudoers.d/mtproxy-systemctl"

# ---- 5. Remove Nginx config (if exists) ----
echo "[5/7] Checking Nginx configuration"
if [[ -f "$NGINX_AVAILABLE" || -f "$NGINX_ENABLED" || -L "$NGINX_ENABLED" ]]; then
  echo "  Found Nginx config: $NGINX_CONF_NAME"
  if ask_yes_no "Remove Nginx config for mtproxy-manager?" "y"; then
    rm -f "$NGINX_ENABLED"
    rm -f "$NGINX_AVAILABLE"
    echo "  Removed Nginx config files"

    # Remove certbot SSL dir if present
    local server_domain
    if [[ -f "${APP_DIR}/.env" ]]; then
      server_domain="$(grep -oP '^SERVER_DOMAIN\s*=\s*\K.*' "${APP_DIR}/.env" | head -n1 | tr -d '[:space:]"' | tr -d "'")"
      if [[ -n "$server_domain" && -d "/etc/letsencrypt/live/${server_domain}" ]]; then
        echo "  Let's Encrypt certificates found for ${server_domain}"
        if ask_yes_no "Remove Let's Encrypt certificates for ${server_domain}?" "n"; then
          certbot delete --non-interactive --cert-name "$server_domain" 2>/dev/null || \
            rm -rf "/etc/letsencrypt/live/${server_domain}" \
                   "/etc/letsencrypt/archive/${server_domain}" \
                   "/etc/letsencrypt/renewal/${server_domain}.conf"
          echo "  Removed Let's Encrypt certificates"
        fi
      fi
    fi

    if command -v nginx &>/dev/null; then
      nginx -t 2>/dev/null && systemctl reload nginx && echo "  Nginx reloaded" || echo "  Warning: nginx config test failed, check manually"
    fi
  fi
else
  echo "  No Nginx config found for mtproxy-manager"
fi

# ---- 6. Remove application data ----
echo "[6/7] Application data"
echo "  Directory: ${APP_DIR}"
echo "  User:      ${APP_USER}"
echo "  Group:     ${APP_GROUP}"

if ask_yes_no "Remove ALL application files (${APP_DIR})?" "n"; then
  systemctl stop "${MANAGER_SERVICE}" 2>/dev/null || true
  rm -rf "${APP_DIR}"
  echo "  Removed ${APP_DIR}"

  if ask_yes_no "Remove system user '${APP_USER}'?" "n"; then
    userdel -r "${APP_USER}" 2>/dev/null || userdel "${APP_USER}" 2>/dev/null || echo "  Warning: could not remove user"
    groupdel "${APP_GROUP}" 2>/dev/null || true
    echo "  Removed user/group ${APP_USER}:${APP_GROUP}"
  fi

  if ask_yes_no "Remove MTG binary (/usr/local/bin/mtg)?" "y"; then
    rm -f /usr/local/bin/mtg
    echo "  Removed /usr/local/bin/mtg"
  fi
else
  echo "  Skipped — files remain at ${APP_DIR}"
  echo "  To clean up manually:"
  echo "    sudo rm -rf ${APP_DIR}"
  echo "    sudo userdel -r ${APP_USER}"
  echo "    sudo groupdel ${APP_GROUP}"
  echo "    sudo rm -f /usr/local/bin/mtg"
fi

# ---- 7. Cleanup logs ----
echo "[7/7] Cleanup"
echo "  Optionally remove logs and data at /var/log/mtproxy* or similar."
echo ""

echo "╔══════════════════════════════════════════════════╗"
echo "║     Uninstall complete.                          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
