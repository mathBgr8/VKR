import ipaddress
import re
from urllib.parse import urlparse


def is_yggdrasil_url(url: str, allowed_tld: list[str], yggdrasil_ranges: list[str]) -> bool:
    """
    Проверяет, принадлежит ли URL к сети Yggdrasil.
    
    Args:
        url: URL для проверки
        allowed_tld: Список разрешенных доменных зон (например, ['.ygg'])
        yggdrasil_ranges: Список диапазонов IPv6 для Yggdrasil (например, ['200::/7'])
    
    Returns:
        True, если URL принадлежит сети Yggdrasil, иначе False
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        parsed = urlparse(url)
        
        # Проверяем схему - только http и https
        if parsed.scheme not in ('http', 'https'):
            logger.debug(f"[ФИЛЬТР] URL {url} отклонен: неверная схема {parsed.scheme}")
            return False
        
        hostname = parsed.hostname
        if not hostname:
            logger.debug(f"[ФИЛЬТР] URL {url} отклонен: нет hostname")
            return False
        
        logger.debug(f"[ФИЛЬТР] Проверка URL {url}, hostname={hostname}")
        
        # Проверяем, является ли хост IP-адресом
        try:
            addr = ipaddress.ip_address(hostname)
            
            # Если IPv4 - это клирнет, отклоняем
            if isinstance(addr, ipaddress.IPv4Address):
                logger.debug(f"[ФИЛЬТР] URL {url} отклонен: IPv4")
                return False
            
            # Если IPv6 - проверяем принадлежность к диапазонам Yggdrasil
            if isinstance(addr, ipaddress.IPv6Address):
                result = _is_in_yggdrasil_range(addr, yggdrasil_ranges)
                logger.debug(f"[ФИЛЬТР] URL {url} (IPv6 {addr}) проверен: {result}")
                return result
                
        except ValueError:
            # Это не IP-адрес, а доменное имя
            result = _is_yggdrasil_domain(hostname, allowed_tld)
            logger.debug(f"[ФИЛЬТР] URL {url} (домен {hostname}) проверен: {result}")
            return result
        
        return False
        
    except Exception as e:
        logger.debug(f"[ФИЛЬТР] URL {url} отклонен: исключение {e}")
        return False


def _is_in_yggdrasil_range(addr: ipaddress.IPv6Address, yggdrasil_ranges: list[str]) -> bool:
    """
    Проверяет, принадлежит ли IPv6-адрес к диапазонам Yggdrasil.
    
    Диапазон 200::/7 означает, что первые 7 бит равны 0010000.
    В шестнадцатеричном виде это адреса, начинающиеся с 2 или 3.
    """
    # Проверяем через ipaddress.IPv6Network
    for range_str in yggdrasil_ranges:
        try:
            network = ipaddress.IPv6Network(range_str, strict=False)
            if addr in network:
                return True
        except ValueError:
            continue
    
    # Дополнительная проверка для 200::/7
    # Адреса начинаются с 2 или 3 (первый ниббл)
    if yggdrasil_ranges and any('200::/7' in r for r in yggdrasil_ranges):
        # Проверяем, что первый символ шестнадцатеричного представления - 2 или 3
        # Убираем leading zeros и проверяем первый символ
        compressed = addr.compressed.lower()
        # Получаем первый символ после развертывания
        expanded = addr.exploded
        first_char = expanded[0]
        if first_char in ('2', '3'):
            return True
    
    return False


def _is_yggdrasil_domain(hostname: str, allowed_tld: list[str]) -> bool:
    """
    Проверяет, является ли домен доменом Yggdrasil (.ygg).
    Также исключает публичные домены клирнета.
    """
    hostname_lower = hostname.lower()
    
    # Проверяем, заканчивается ли домен на разрешенные зоны
    for tld in allowed_tld:
        if hostname_lower.endswith(tld):
            return True
    
    # Исключаем обычные домены клирнета
    clearnet_tlds = [
        '.com', '.org', '.net', '.ru', '.de', '.fr', '.edu', '.gov',
        '.io', '.dev', '.app', '.cloud', '.info', '.biz', '.cn', '.jp',
        '.uk', '.us', '.eu', '.au', '.ca', '.br', '.in', '.ir', '.nl'
    ]
    
    for tld in clearnet_tlds:
        if hostname_lower.endswith(tld):
            return False
    
    return False


def is_clearnet_url(url: str, allowed_tld: list[str] = None) -> bool:
    """
    Проверяет, является ли URL адресом клирнета.
    
    Args:
        url: URL для проверки
        allowed_tld: Список разрешенных доменных зон (если None, разрешены все публичные домены)
    
    Returns:
        True, если URL принадлежит клирнету, иначе False
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        parsed = urlparse(url)
        
        # Проверяем схему - только http и https
        if parsed.scheme not in ('http', 'https'):
            logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: неверная схема {parsed.scheme}")
            return False
        
        hostname = parsed.hostname
        if not hostname:
            logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: нет hostname")
            return False
        
        logger.debug(f"[ФИЛЬТР КЛИРНЕТ] Проверка URL {url}, hostname={hostname}")
        
        # Проверяем, является ли хост IP-адресом
        try:
            addr = ipaddress.ip_address(hostname)
            
            # Если IPv6 - проверяем, не является ли это Yggdrasil
            if isinstance(addr, ipaddress.IPv6Address):
                # Проверяем, не является ли это Yggdrasil адресом
                if _is_in_yggdrasil_range(addr, ['200::/7']):
                    logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: IPv6 Yggdrasil {addr}")
                    return False
                # Разрешаем остальные IPv6
                logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} (IPv6 {addr}) разрешен")
                return True
            
            # IPv4 - всегда разрешаем (это клирнет)
            logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} (IPv4 {addr}) разрешен")
            return True
            
        except ValueError:
            # Это не IP-адрес, а доменное имя
            hostname_lower = hostname.lower()
            
            # Проверяем, не является ли это Yggdrasil доменом
            if hostname_lower.endswith('.ygg'):
                logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: домен .ygg")
                return False
            
            # Если указаны разрешенные зоны, проверяем их
            if allowed_tld:
                for tld in allowed_tld:
                    if hostname_lower.endswith(tld):
                        logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} разрешен: домен заканчивается на {tld}")
                        return True
                logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: домен не в списке разрешенных {allowed_tld}")
                return False
            
            # Если список разрешенных зон пуст, разрешаем все публичные домены (кроме .ygg)
            logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} (домен {hostname}) разрешен")
            return True
        
    except Exception as e:
        logger.debug(f"[ФИЛЬТР КЛИРНЕТ] URL {url} отклонен: исключение {e}")
        return False


def is_url_allowed(url: str, network_type: str, allowed_tld: list[str], yggdrasil_ranges: list[str]) -> bool:
    """
    Универсальная функция проверки URL в зависимости от типа сети.
    
    Args:
        url: URL для проверки
        network_type: Тип сети ('yggdrasil' или 'clearnet')
        allowed_tld: Список разрешенных доменных зон
        yggdrasil_ranges: Список диапазонов IPv6 для Yggdrasil
    
    Returns:
        True, если URL разрешен, иначе False
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if network_type == 'clearnet':
        logger.debug(f"[ФИЛЬТР] Используется фильтр КЛИРНЕТ для {url}")
        return is_clearnet_url(url, allowed_tld)
    else:  # yggdrasil (по умолчанию)
        logger.debug(f"[ФИЛЬТР] Используется фильтр YGGDRASIL для {url}")
        return is_yggdrasil_url(url, allowed_tld, yggdrasil_ranges)


def extract_domain_or_ip(url: str) -> str | None:
    """
    Извлекает домен или IP-адрес из URL.
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname
    except Exception:
        return None
