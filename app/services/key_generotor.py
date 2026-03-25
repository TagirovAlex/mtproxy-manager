"""
Генератор ключей для MTProxy с поддержкой FakeTLS
Только для MTG v2+ с обязательным FakeTLS
"""

import secrets
import base64
from typing import Tuple, Optional


class KeyGenerator:
    """
    Генератор секретов для MTG Proxy v2 с FakeTLS.
    
    MTG v2 использует секреты формата:
    - Префикс 'ee' (1 байт = 2 hex символа) - указывает на FakeTLS
    - 16 случайных байт (32 hex символа)
    - Закодированный домен в hex
    
    Итоговая длина: 2 + 32 + (длина домена * 2) hex символов
    Например для www.google.com: 2 + 32 + 28 = 62 символа
    """
    
    # Префикс для FakeTLS (обязательный для MTG v2)
    FAKE_TLS_PREFIX = 'ee'
    
    # Длина случайной части в байтах
    RANDOM_BYTES_LENGTH = 16
    
    # Список проверенных доменов для маскировки
    ALLOWED_DOMAINS = [
        'www.google.com',
        'www.microsoft.com',
        'www.apple.com',
        'www.cloudflare.com',
        'www.amazon.com',
        'www.youtube.com',
        'www.facebook.com',
        'www.instagram.com',
        'www.twitter.com',
        'www.linkedin.com',
        'www.netflix.com',
        'www.spotify.com'
    ]
    
    DEFAULT_DOMAIN = 'www.google.com'
    
    @classmethod
    def generate_secret(cls, domain: Optional[str] = None) -> Tuple[str, str]:
        """
        Генерация секрета FakeTLS для MTG Proxy v2.
        
        Формат секрета MTG v2 FakeTLS:
        ee + [16 random bytes hex] + [domain encoded hex]
        
        Args:
            domain: Домен для FakeTLS маскировки (если None - выбирается случайный)
            
        Returns:
            Tuple[str, str]: (секрет в hex, использованный домен)
        """
        # Выбор домена
        if domain is None:
            domain = secrets.choice(cls.ALLOWED_DOMAINS)
        elif domain not in cls.ALLOWED_DOMAINS:
            # Если домен не в списке разрешенных, используем дефолтный
            domain = cls.DEFAULT_DOMAIN
        
        # Генерируем 16 случайных байт
        random_bytes = secrets.token_bytes(cls.RANDOM_BYTES_LENGTH)
        random_hex = random_bytes.hex()
        
        # Кодируем домен в hex
        domain_bytes = domain.encode('utf-8')
        domain_hex = domain_bytes.hex()
        
        # Собираем секрет: ee + random_hex + domain_hex
        secret = cls.FAKE_TLS_PREFIX + random_hex + domain_hex
        
        return secret, domain
    
    @classmethod
    def decode_domain_from_secret(cls, secret: str) -> Optional[str]:
        """
        Извлечение домена из секрета FakeTLS.
        
        Args:
            secret: Секрет в hex формате
            
        Returns:
            Optional[str]: Домен или None если не удалось извлечь
        """
        try:
            if not cls.validate_secret(secret)[0]:
                return None
            
            # Пропускаем префикс (2 символа) и случайную часть (32 символа)
            domain_hex = secret[34:]
            if not domain_hex:
                return None
            
            domain_bytes = bytes.fromhex(domain_hex)
            return domain_bytes.decode('utf-8')
        except Exception:
            return None
    
    @classmethod
    def validate_secret(cls, secret: str) -> Tuple[bool, str]:
        """
        Валидация секрета MTG v2 FakeTLS.
        
        Требования:
        - Начинается с 'ee'
        - Минимальная длина: 2 (префикс) + 32 (random) + минимум 2 (домен) = 36
        - Содержит только hex символы после префикса
        
        Args:
            secret: Секрет для проверки
            
        Returns:
            Tuple[bool, str]: (валиден, сообщение)
        """
        if not secret:
            return False, "Секрет не может быть пустым"
        
        # Приводим к нижнему регистру для проверки
        secret_lower = secret.lower()
        
        # Проверка префикса FakeTLS
        if not secret_lower.startswith('ee'):
            return False, "Секрет должен начинаться с 'ee' (FakeTLS)"
        
        # Минимальная длина: ee(2) + random(32) + минимальный домен(2) = 36
        if len(secret) < 36:
            return False, f"Секрет слишком короткий (минимум 36 символов, получено {len(secret)})"
        
        # Проверка что всё после префикса - валидный hex
        hex_part = secret[2:]
        try:
            bytes.fromhex(hex_part)
        except ValueError:
            return False, "Секрет содержит невалидные hex символы"
        
        # Проверка длины случайной части (должна быть минимум 32 hex = 16 байт)
        if len(hex_part) < 32:
            return False, "Недостаточная длина случайной части секрета"
        
        # Попытка декодировать домен
        domain = cls.decode_domain_from_secret(secret)
        if domain is None:
            return False, "Не удалось декодировать домен из секрета"
        
        return True, f"OK (домен: {domain})"
    
    @classmethod
    def get_secret_info(cls, secret: str) -> dict:
        """
        Получение информации о секрете.
        
        Args:
            secret: Секрет для анализа
            
        Returns:
            dict: Информация о секрете
        """
        is_valid, message = cls.validate_secret(secret)
        
        info = {
            'valid': is_valid,
            'message': message,
            'type': 'fake-tls',
            'length': len(secret),
            'domain': None,
            'prefix': secret[:2] if len(secret) >= 2 else None
        }
        
        if is_valid:
            info['domain'] = cls.decode_domain_from_secret(secret)
        
        return info
    
    @classmethod
    def format_secret_for_display(cls, secret: str, show_chars: int = 8) -> str:
        """
        Форматирование секрета для безопасного отображения.
        
        Args:
            secret: Полный секрет
            show_chars: Количество видимых символов с каждой стороны
            
        Returns:
            str: Частично скрытый секрет
        """
        if len(secret) <= show_chars * 2:
            return secret
        return f"{secret[:show_chars]}...{secret[-show_chars:]}"
    
    @classmethod
    def generate_proxy_links(cls, secret: str, server: str, port: int = 443) -> dict:
        """
        Генерация всех типов ссылок для прокси.
        
        Args:
            secret: Секрет прокси
            server: Адрес сервера (домен или IP)
            port: Порт прокси
            
        Returns:
            dict: Словарь с тремя типами ссылок
        """
        # Базовые параметры
        params = f"server={server}&port={port}&secret={secret}"
        
        return {
            'tg': f"tg://proxy?{params}",
            'https': f"https://t.me/proxy?{params}",
            'tme': f"t.me/proxy?{params}"
        }
    
    @classmethod
    def get_allowed_domains(cls) -> list:
        """
        Получение списка разрешенных доменов для FakeTLS.
        
        Returns:
            list: Список доменов
        """
        return cls.ALLOWED_DOMAINS.copy()
    
    @classmethod
    def regenerate_secret_with_domain(cls, new_domain: str) -> Tuple[str, str]:
        """
        Генерация нового секрета с указанным доменом.
        
        Args:
            new_domain: Домен для FakeTLS
            
        Returns:
            Tuple[str, str]: (новый секрет, использованный домен)
        """
        if new_domain not in cls.ALLOWED_DOMAINS:
            raise ValueError(f"Домен {new_domain} не в списке разрешенных")
        
        return cls.generate_secret(new_domain)