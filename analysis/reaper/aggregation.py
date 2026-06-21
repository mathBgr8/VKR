import json
from collections import Counter, defaultdict

def aggregate_results(input_json_file, output_summary_file='aggregated_report.json'):
    with open(input_json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_domains = len(data)
    total_js_files = 0
    total_indicators_by_type = Counter()
    # Для подсчёта количества уникальных доменов по каждому типу индикатора
    domains_by_indicator_type = defaultdict(set)

    threatening_indicators = []   # угрожающие: EVAL, DYNAMIC EXEC
    domains_without_any_indicator = []
    domains_with_indicators = set()

    for domain, content in data.items():
        domain_has_any_indicator = False
        for key, indicators in content.items():
            # Пропускаем служебные ключи
            if key in ["", "﻿"] or key.startswith("Scanned"):
                continue
            if not isinstance(indicators, list) or len(indicators) == 0:
                continue

            total_js_files += 1
            domain_has_any_indicator = True
            domains_with_indicators.add(domain)

            for ind in indicators:
                itype = ind.get("position", "").strip()   # здесь хранится тип (EVAL, OBFUSCATION...)
                position = ind.get("type", "")
                description = ind.get("value", "")
                if not itype:
                    continue

                total_indicators_by_type[itype] += 1
                domains_by_indicator_type[itype].add(domain)

                if itype in ("EVAL", "DYNAMIC EXEC"):
                    threatening_indicators.append({
                        "domain": domain,
                        "file": key,
                        "position": position,
                        "threat_type": itype,
                        "description": description
                    })

        if not domain_has_any_indicator:
            domains_without_any_indicator.append(domain)

    domains_count_by_indicator_type = {
        itype: len(domains_set) for itype, domains_set in domains_by_indicator_type.items()
    }

    report = {
        "summary": {
            "total_domains": total_domains,
            "total_js_files_with_indicators": total_js_files,
            "domains_without_any_indicators": len(domains_without_any_indicator),
            "domains_with_indicators": len(domains_with_indicators),
            "indicators_count_by_type": dict(total_indicators_by_type),
            "domains_count_by_indicator_type": domains_count_by_indicator_type,
            "threatening_indicators_count": len(threatening_indicators)
        },
        "threatening_indicators_list": threatening_indicators,
        "domains_without_any_indicators_list": domains_without_any_indicator
    }

    with open(output_summary_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=== АГРЕГИРОВАННЫЙ ОТЧЁТ ===")
    print(f"Всего доменов: {total_domains}")
    print(f"JS-файлов, содержащих индикаторы: {total_js_files}")
    print(f"Доменов без индикаторов: {len(domains_without_any_indicator)}")
    print(f"Доменов с индикаторами: {len(domains_with_indicators)}")
    print("\nТипы индикаторов (общее количество вхождений и количество сайтов):")
    # Сортируем по названию типа для удобства
    for itype, cnt in sorted(total_indicators_by_type.items()):
        domains_cnt = domains_count_by_indicator_type.get(itype, 0)
        print(f"  {itype}: {cnt} вхождений, {domains_cnt} сайтов")

    print(f"\nОбнаружено угрожающих индикаторов (EVAL, DYNAMIC EXEC): {len(threatening_indicators)}")
    if threatening_indicators:
        print("\nСписок угрожающих индикаторов (первые 10):")
        for item in threatening_indicators[:10]:
            print(f"  {item['domain']} / {item['file']} [{item['position']}] {item['threat_type']}: {item['description'][:80]}")
        if len(threatening_indicators) > 10:
            print(f"  ... и ещё {len(threatening_indicators)-10}")
    else:
        print("  Угрожающих индикаторов не найдено.")

    # Список сайтов с EVAL
    eval_domains = set()
    for item in threatening_indicators:
        if item['threat_type'] == "EVAL":
            eval_domains.add(item['domain'])
    eval_domains = sorted(eval_domains)

    print("\n=== СПИСОК САЙТОВ (ДОМЕНОВ), СОДЕРЖАЩИХ EVAL ===")
    if eval_domains:
        for domain in eval_domains:
            print(f"  {domain}")
        print(f"\nВсего доменов с EVAL: {len(eval_domains)}")
    else:
        print("  Домены с EVAL не обнаружены.")

    print(f"\nПолный отчёт сохранён в {output_summary_file}")

if __name__ == '__main__':
    aggregate_results(r'.\parsed_analysis.json')
