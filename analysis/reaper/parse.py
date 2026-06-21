import os
import re
import json
from pathlib import Path

def read_file_with_fallback_encoding(filepath, encodings=('utf-8', 'utf-16-le', 'utf-16-be', 'utf-32')):
    """
    Пытается открыть файл с одной из указанных кодировок.
    Возвращает содержимое в виде строки.
    """
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Не удалось прочитать файл {filepath} ни в одной из кодировок {encodings}")

def parse_indicators_from_file(filepath):
    results = {}
    current_file = None
    indicators = []

    # indicator_re = re.compile(
    #     r'^\s+(\d+:\d+)\s+\[([^\]]+)\]\s+(.+?)(?:\s+(\([^)]+\)))?$'
    # )
    indicator_re = re.compile(
    r'^\s*\S*\s*\[([^\]]+)\]\s+(\d+:\d+)\s+(.*)$'
    )

    try:
        content = read_file_with_fallback_encoding(filepath)
        lines = content.splitlines()
    except Exception as e:
        print(f"Ошибка чтения {filepath}: {e}")
        return results

    for line in lines:
        line = line.rstrip('\n')
        if not line.strip():
            continue

        if not line[0].isspace():
            if current_file is not None:
                results[current_file] = indicators if indicators else []
            current_file = line.strip()
            indicators = []
        else:
            if '(no indicators)' in line:
                if current_file is not None:
                    results[current_file] = "(no indicators)"
                    current_file = None
                    indicators = []
                continue

            match = indicator_re.match(line)
            if match and current_file is not None:
                position = match.group(1)
                itype = match.group(2).strip()
                url = match.group(3).strip()
                #extra = match.group(4) if match.group(4) else None
                indicators.append({
                    'position': position,
                    'type': itype,
                    'value': url,
                    #'extra': extra
                })

    if current_file is not None:
        results[current_file] = indicators if indicators else []

    return results

def build_structure(root_dir):
    structure = {}
    root_path = Path(root_dir)

    for domain_dir in root_path.iterdir():
        if not domain_dir.is_dir():
            continue
        analysis_file = domain_dir / 'analysis.txt'
        if not analysis_file.exists():
            print(f"Предупреждение: {analysis_file} не найден, пропускаем {domain_dir.name}")
            continue

        print(f"Обработка {domain_dir.name} ...")
        parsed = parse_indicators_from_file(analysis_file)
        if parsed:
            structure[domain_dir.name] = parsed

    return structure

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Использование: python parser.py <корневая_папка_с_доменами>")
        sys.exit(1)

    root_folder = sys.argv[1]
    data = build_structure(root_folder)

    output_file = 'parsed_analysis.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Готово. Результат сохранён в {output_file}")
