import json
import re
from pathlib import Path
from collections import defaultdict

def normalize_domain_name(name: str) -> str:
    if re.match(r'^[a-fA-F0-9]{1,4}(?:-[a-fA-F0-9]{1,4}){7}$', name):
        return name.replace('-', ':')
    return name

def normalize_ipv6_folder(folder_name: str) -> str:
    """
    Преобразует имя папки в читаемый IPv6-адрес (или домен) с квадратными скобками.
    """
    # Убираем квадратные скобки, если они есть
    name = folder_name.strip('[]')
    
    # Отделяем порт (последний дефис, после которого только цифры)
    port = None
    parts = name.rsplit('-', 1)
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]
        port = parts[1]
    
    # Заменяем дефисы на двоеточия
    name = name.replace('-', ':')
    # Восстанавливаем двойное двоеточие (из двух дефисов подряд -> ::)
    name = name.replace('::', '::')  # оставляем как есть, если уже есть
    
    # Собираем результат: квадратные скобки + IPv6, затем порт
    result = f"[{name}]"
    if port:
        result += f":{port}"
    return result

def extract_domain_from_path(file_path: str) -> str:
    """Извлекает домен/IPv6 из поля 'file', путь содержит /scripts/[имя_папки]/..."""
    # Ищем часть между '/scripts/' и следующим слэшем
    match = re.search(r'/scripts/([^/]+)/', file_path.replace('\\', '/'))
    if match:
        raw_folder = match.group(1)
        return normalize_ipv6_folder(raw_folder)
    parent = Path(file_path).parent.name
    return normalize_ipv6_folder(parent)

def load_jsons(input_path):
    """Загружает JSON-объекты из файла или папки."""
    data_list = []
    input_path = Path(input_path)
    if input_path.is_file():
        with open(input_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
            if isinstance(content, list):
                data_list.extend(content)
            else:
                data_list.append(content)
    elif input_path.is_dir():
        for json_file in input_path.glob('*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data_list.append(json.load(f))
            except Exception as e:
                print(f"Ошибка чтения {json_file}: {e}")
    return data_list

def aggregate_by_domain(data_list):
    """
    Агрегирует данные по доменам.
    Возвращает словарь:
        domain -> {
            'script_count': int,
            'total_score': int,
            'obfuscated_scripts': int,
            'scripts_with_eval': int,
            'has_data_leak': bool,
            'categories': dict
        }
    """
    domain_stats = defaultdict(lambda: {
        'script_count': 0,
        'total_score': 0,
        'obfuscated_scripts': 0,
        'scripts_with_eval': 0,
        'has_data_leak': False,
        'categories_summary': defaultdict(int)
    })

    for item in data_list:
        file_path = item.get('file', '')
        domain = extract_domain_from_path(file_path)
        stats = domain_stats[domain]

        stats['script_count'] += 1
        stats['total_score'] += item.get('score', 0)

        if item.get('is_obfuscated'):
            stats['obfuscated_scripts'] += 1

        obf_indicators = item.get('obfuscation_indicators', [])
        if any('eval' in ind.lower() or 'function constructor' in ind.lower() for ind in obf_indicators):
            stats['scripts_with_eval'] += 1

        detections = item.get('detections', {})
        if 'data_leak' in detections and detections['data_leak']:
            stats['has_data_leak'] = True
            for leak_item in detections['data_leak']:
                stats['categories_summary']['data_leak'] += leak_item.get('count', 0)

        # Остальные категории
        for cat, cat_data in detections.items():
            if cat == 'data_leak':
                continue
            if isinstance(cat_data, list):
                total_count = sum(d.get('count', 0) for d in cat_data)
                if total_count:
                    stats['categories_summary'][cat] += total_count

    # Преобразуем defaultdict в обычный dict
    result = {}
    for domain, stats in domain_stats.items():
        result[domain] = {
            'script_count': stats['script_count'],
            'total_score': stats['total_score'],
            'obfuscated_scripts': stats['obfuscated_scripts'],
            'scripts_with_eval': stats['scripts_with_eval'],
            'has_data_leak': stats['has_data_leak'],
            'categories': dict(stats['categories_summary'])
        }
    return result

def is_dangerous(domain_stats, score_threshold=500):
    """Определяет, является ли сайт опасным (порог настраивается)."""
    stats = domain_stats
    if stats['total_score'] >= score_threshold:
        return True
    if stats['scripts_with_eval'] > 0 and stats['has_data_leak']:
        return True
    if stats['obfuscated_scripts'] > 2:
        return True
    return False

def main(input_path, score_threshold=500, output_json=None):
    print(f"Загрузка данных из {input_path}...")
    data_list = load_jsons(input_path)
    if not data_list:
        print("Не найдено данных для анализа.")
        return

    print(f"Обработано {len(data_list)} JSON-объектов.")
    domain_stats = aggregate_by_domain(data_list)

    print("\n=== СТАТИСТИКА ПО ДОМЕНАМ ===")
    for domain, stats in sorted(domain_stats.items()):
        print(f"{domain}:")
        print(f"  Скриптов: {stats['script_count']}, общий score: {stats['total_score']}")
        print(f"  Обфусцированных: {stats['obfuscated_scripts']}, скриптов с eval: {stats['scripts_with_eval']}, data_leak: {stats['has_data_leak']}")
        if stats['categories']:
            cats = ', '.join(f"{k}:{v}" for k, v in stats['categories'].items())
            print(f"  Категории: {cats}")

    dangerous_sites = []
    for domain, stats in domain_stats.items():
        if is_dangerous(stats, score_threshold):
            dangerous_sites.append((domain, stats))

    total_dangerous = len(dangerous_sites)
    total_eval_scripts = sum(stats['scripts_with_eval'] for stats in domain_stats.values())

    print(f"\n=== ПОТЕНЦИАЛЬНО ОПАСНЫЕ САЙТЫ (порог score >= {score_threshold} или eval+data_leak или obf_scripts>2) ===")
    if dangerous_sites:
        for domain, stats in dangerous_sites:
            indicators = (f"score={stats['total_score']}, obf_scripts={stats['obfuscated_scripts']}, "
                          f"eval_scripts={stats['scripts_with_eval']}, data_leak={stats['has_data_leak']}")
            print(f"  {domain} ({indicators})")
    else:
        print("  Не найдено.")

    print(f"\nВсего опасных сайтов: {total_dangerous}")
    print(f"Всего скриптов, содержащих eval/Function: {total_eval_scripts}")

    if output_json:
        output_data = {
            'domains': domain_stats,
            'dangerous_domains': [{'domain': d, 'stats': s} for d, s in dangerous_sites],
            'score_threshold': score_threshold,
            'total_dangerous_sites': total_dangerous,
            'total_scripts_with_eval': total_eval_scripts
        }
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nРезультаты сохранены в {output_json}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Использование: python fingerprint_parser.py <путь_к_папке_или_JSON> [порог_score] [выходной_JSON]")
        sys.exit(1)
    input_path = sys.argv[1]
    threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    main(input_path, threshold, output_file)
