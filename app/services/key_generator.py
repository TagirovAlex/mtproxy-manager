"""
Генератор и валидатор FakeTLS-секретов для MTG.
Поддерживает произвольные валидные домены (без жесткого whitelist).
"""

from __future__ import annotations

import re
import secrets
from typing import Optional, Tuple, Dict, List


class KeyGenerator:
    FAKE_TLS_PREFIX = "ee"
    RANDOM_BYTES_LENGTH = 16
    DEFAULT_DOMAIN = "www.google.com"

    # Валидатор FQDN (упрощенный, но практичный)
    _DOMAIN_RE = re.compile(
        r"^(?=.{1,253}$)(?!-)(?:[a-zA-Z0-9-]{1,63}\.)+[A-Za-z]{2,63}$"
    )

    # Оставляем для совместимости с UI/старыми вызовами.
    # Можно использовать как подсказки в интерфейсе.
    ALLOWED_DOMAINS = [
        "www.google.com",
        "www.microsoft.com",
        "www.cloudflare.com",
        "www.amazon.com",
    ]

    @classmethod
    def _normalize_domain(cls, domain: str) -> str:
        return (domain or "").strip().lower().rstrip(".")

    @classmethod
    def _is_valid_domain(cls, domain: str) -> bool:
        d = cls._normalize_domain(domain)
        return bool(cls._DOMAIN_RE.match(d))

    @classmethod
    def generate_secret(cls, domain: Optional[str] = None) -> Tuple[str, str]:
        """
        Формат секрета:
        ee + 16 случайных байт (32 hex) + domain hex
        """
        if not domain:
            domain = cls.DEFAULT_DOMAIN

        domain = cls._normalize_domain(domain)
        if not cls._is_valid_domain(domain):
            raise ValueError(f"Invalid FakeTLS domain: {domain}")

        random_hex = secrets.token_bytes(cls.RANDOM_BYTES_LENGTH).hex()
        domain_hex = domain.encode("utf-8").hex()
        secret = f"{cls.FAKE_TLS_PREFIX}{random_hex}{domain_hex}"
        return secret, domain

    @classmethod
    def _decode_domain_raw(cls, secret: str) -> Optional[str]:
        # ee + 32 hex random + domain hex
        if not secret or len(secret) < 36:
            return None

        domain_hex = secret[34:]
        if not domain_hex or len(domain_hex) % 2 != 0:
            return None

        try:
            return bytes.fromhex(domain_hex).decode("utf-8")
        except Exception:
            return None

    @classmethod
    def decode_domain_from_secret(cls, secret: str) -> Optional[str]:
        ok, _ = cls.validate_secret(secret)
        if not ok:
            return None
        return cls._decode_domain_raw(secret)

    @classmethod
    def validate_secret(cls, secret: str) -> Tuple[bool, str]:
        if not secret:
            return False, "Secret is empty"

        s = secret.strip().lower()

        if not s.startswith(cls.FAKE_TLS_PREFIX):
            return False, "Secret must start with ee (FakeTLS)"

        if len(s) < 36:
            return False, "Secret is too short"

        try:
            bytes.fromhex(s[2:])
        except ValueError:
            return False, "Secret contains non-hex characters"

        domain = cls._decode_domain_raw(s)
        if not domain:
            return False, "Cannot decode domain from secret"

        if not cls._is_valid_domain(domain):
            return False, f"Decoded domain is invalid: {domain}"

        return True, f"OK (domain: {domain})"

    @classmethod
    def get_secret_info(cls, secret: str) -> Dict[str, object]:
        valid, message = cls.validate_secret(secret)
        return {
            "valid": valid,
            "message": message,
            "type": "fake-tls",
            "length": len(secret or ""),
            "prefix": (secret[:2] if secret else None),
            "domain": cls.decode_domain_from_secret(secret) if valid else None,
        }

    @classmethod
    def format_secret_for_display(cls, secret: str, show_chars: int = 8) -> str:
        if not secret:
            return ""
        if len(secret) <= show_chars * 2:
            return secret
        return f"{secret[:show_chars]}...{secret[-show_chars:]}"

    @classmethod
    def generate_proxy_links(cls, secret: str, server: str, port: int = 443) -> Dict[str, str]:
        params = f"server={server}&port={port}&secret={secret}"
        return {
            "tg": f"tg://proxy?{params}",
            "https": f"https://t.me/proxy?{params}",
            "tme": f"t.me/proxy?{params}",
        }

    @classmethod
    def get_allowed_domains(cls) -> List[str]:
        # Возвращаем подсказки, не ограничение.
        return list(cls.ALLOWED_DOMAINS)

    @classmethod
    def regenerate_secret_with_domain(cls, new_domain: str) -> Tuple[str, str]:
        return cls.generate_secret(new_domain)