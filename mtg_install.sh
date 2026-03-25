#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/mtproxy-manager}"
TMP_DIR=""

cleanup() {
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR:-}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi

detect_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "Unsupported architecture"; exit 1 ;;
  esac
}

install_mtg_secure() {
  local arch release_json asset_url checksums_url file_name expected_sha

  arch="$(detect_arch)"
  TMP_DIR="$(mktemp -d)"

  release_json="$(curl -fsSL https://api.github.com/repos/9seconds/mtg/releases/latest)"
  asset_url="$(echo "${release_json}" \
    | jq -r --arg a "${arch}" '.assets[] | select(.name | test("linux-" + $a + "\\.tar\\.gz$")) | .browser_download_url' \
    | head -n1)"
  checksums_url="$(echo "${release_json}" \
    | jq -r '.assets[] | select(.name | test("sha256|checksums"; "i")) | .browser_download_url' \
    | head -n1)"

  if [[ -z "${asset_url}" || "${asset_url}" == "null" ]]; then
    echo "Failed to resolve MTG release asset"
    exit 1
  fi

  file_name="$(basename "${asset_url}")"
  curl -fsSL "${asset_url}" -o "${TMP_DIR}/${file_name}"

  expected_sha="${MTG_SHA256:-}"
  if [[ -z "${expected_sha}" ]]; then
    if [[ -n "${checksums_url}" && "${checksums_url}" != "null" ]]; then
      curl -fsSL "${checksums_url}" -o "${TMP_DIR}/checksums.txt"
      expected_sha="$(grep " ${file_name}\$" "${TMP_DIR}/checksums.txt" | awk '{print $1}' | head -n1 || true)"
    fi
  fi

  if [[ -z "${expected_sha}" ]]; then
    echo "MTG checksum is not available."
    echo "Set MTG_SHA256 env var explicitly to continue securely."
    exit 1
  fi

  echo "${expected_sha}  ${TMP_DIR}/${file_name}" | sha256sum -c -

  tar -xzf "${TMP_DIR}/${file_name}" -C "${TMP_DIR}"
  install -m 0755 "$(find "${TMP_DIR}" -type f -name mtg | head -n1)" /usr/local/bin/mtg
}

apt-get update -y
apt-get install -y curl jq tar ca-certificates

install_mtg_secure

mkdir -p "${APP_DIR}/mtg/instances"
install -m 0644 "${APP_DIR}/app/deploy/systemd/mtg@.service" /etc/systemd/system/mtg@.service

systemctl daemon-reload
echo "MTG multi-instance runtime installed securely"
echo "Use: systemctl start mtg@<instance_id>.service"