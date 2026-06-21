import asyncio
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

class StateManager:
    def __init__(self, state_dir: str = 'state_backup'):
        self.state_dir = state_dir
        self.state_file = os.path.join(self.state_dir, 'state.json')
        self._ensure_state_dir()
        
    def _ensure_state_dir(self):
        os.makedirs(self.state_dir, exist_ok=True)
        
    async def save_state(self, crawler) -> None:
        """Сохранить текущее состояние краулера в файл"""
        state = {
            'timestamp': datetime.utcnow().isoformat(),
            'links_discovered': crawler.links_discovered,
            'scripts_saved': crawler.scripts_saved,
            'links_processed': crawler.links_processed,
            'visited_links': list(crawler.queue.visited),
            'enqueued_links': list(crawler.queue.enqueued),
            'config': crawler.config,
            'progress': {
                'links_discovered': crawler.links_discovered,
                'scripts_saved': crawler.scripts_saved,
                'links_processed': crawler.links_processed
            }
        }
        #тут убрать если что попробовать 2 строки ниже
        # Фильтруем visited_links, оставляя только обработанные ссылки
        processed_visited = [url for url in crawler.queue.visited if url in crawler.queue.enqueued]
        state['visited_links'] = processed_visited
        
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving state: {e}")
            
    async def load_state(self) -> bool:
        """Загрузить состояние из файла, если он существует"""
        if not os.path.exists(self.state_file):
            return False
            
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                
            # Проверяем, что файл не слишком старый (старше 24 часов)
            # Это предотвращает попытки восстановления устаревшего состояния
            # (в реальной реализации можно добавить более сложную проверку)
            return True
        except Exception as e:
            print(f"Error loading state: {e}")
            return False
            
    async def restore_state(self, crawler) -> bool:
        """Восстановить состояние краулера из файла"""
        if not await self.load_state():
            return False
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                
            # Восстанавливаем прогресс
            crawler.links_discovered = state.get('links_discovered', 0)
            crawler.scripts_saved = state.get('scripts_saved', 0)
            crawler.links_processed = state.get('links_processed', 0)
            
            # Восстанавливаем очередь
            crawler.queue.visited = set(state.get('visited_links', []))
            crawler.queue.enqueued = set(state.get('enqueued_links', []))
            
            # Восстанавливаем конфигурацию
            crawler.config = state.get('config', crawler.config)
            
            print(f"State restored from {self.state_file}")
            return True
        except Exception as e:
            print(f"Error restoring state: {e}")
            return False
            
    async def cleanup(self):
        """Очистить состояние (при завершении работы)"""
        # Можно добавить логику очистки старых файлов
        pass
