import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Добавляем текущую директорию в sys.path для корректного импорта модулей
sys.path.insert(0, str(Path(__file__).parent))

from utils.script_collector import ScriptCollector


def setup_logging(log_dir: str = 'logs') -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger('yggdrasil_crawler')
    logger.setLevel(logging.DEBUG)
    
    # Форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Обработчик для файла
    file_handler = logging.FileHandler(
        os.path.join(log_dir, 'crawler.log'),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def load_config(config_path: str = 'config.json') -> dict:
    """
    Загружает конфигурацию из JSON файла.
    
    Args:
        config_path: Путь к файлу конфигурации
    
    Returns:
        Словарь с конфигурацией
    """
    default_config = {
        "seed_links_file": "seeds.txt",
        "max_workers": 8,
        "output_dir": "./data",
        "network_type": "yggdrasil",
        "yggdrasil_ranges": ["200::/7"],
        "allowed_tld": [".ygg"],
        "playwright": {
            "headless": True,
            "timeout_ms": 30000
        }
    }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Объединяем с дефолтными значениями
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
    except FileNotFoundError:
        print(f"Файл конфигурации не найден: {config_path}. Используется конфигурация по умолчанию.")
        return default_config
    except json.JSONDecodeError as e:
        print(f"Ошибка парсинга конфигурации: {e}. Используется конфигурация по умолчанию.")
        return default_config


def create_seeds_file_if_not_exists(filepath: str, logger: logging.Logger) -> None:
    """
    Создает файл с начальными ссылками, если он не существует.
    
    Args:
        filepath: Путь к файлу
        logger: Логгер
    """
    if not os.path.exists(filepath):
        logger.warning(f"Файл с начальными ссылками не найден: {filepath}")
        logger.info("Создается пример файла seeds.txt...")
        
        example_seeds = [
            "# Добавьте сюда начальные ссылки для краулера (по одной на строку)",
            "# Например:",
            "# http://[200:1234:5678::1]/",
            "# http://example.ygg/",
            "",
        ]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(example_seeds))
        
        logger.info(f"Создан пример файла {filepath}. Отредактируйте его и запустите краулер снова.")


async def main():
    """
    Основная асинхронная функция запуска краулера.
    """
    # Определяем пути относительно расположения main.py
    base_dir = Path(__file__).parent
    config_path = base_dir / 'config.json'
    log_dir = base_dir / 'logs'
    
    # Настраиваем логирование
    logger = setup_logging(str(log_dir))
    logger.info("=" * 60)
    logger.info("Запуск веб-краулера сети Yggdrasil")
    logger.info("=" * 60)
    
    # Загружаем конфигурацию
    config = load_config(str(config_path))
    logger.info(f"Конфигурация загружена: {config}")
    
    # Создаем экземпляр Crawler
    from core.crawler import Crawler
    crawler = Crawler(config, logger)
    
    # Загружаем начальные ссылки
    seeds_file = base_dir / config.get('seed_links_file', 'seeds.txt')
    create_seeds_file_if_not_exists(str(seeds_file), logger)
    
    # Загружаем seed-ссылки
    seed_links = crawler.load_seeds(str(seeds_file))
    
    if not seed_links:
        logger.error("Нет начальных ссылок для обхода. Проверьте файл seeds.txt")
        return
    
    logger.info(f"Загружено {len(seed_links)} начальных ссылок")
    logger.info(f"Первые 3 ссылки: {seed_links[:3]}")
    
    # Запускаем краулер
    try:
        await crawler.crawl(seed_links)
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершение работы...")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
    finally:
        logger.info("Работа краулера завершена")


if __name__ == '__main__':
    # Запускаем асинхронную main функцию
    asyncio.run(main())
