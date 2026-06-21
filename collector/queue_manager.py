import asyncio
from typing import Set, List, Tuple, Optional, Dict
import logging

class AsyncQueueManager:
    MAX_QUEUE_SIZE = 10000

    def __init__(self):
        self.queue = asyncio.PriorityQueue()
        self.visited: Set[str] = set()
        self.enqueued: Set[str] = set()
        self.source_map: Dict[str, str] = {}

    async def enqueue(self, url: str, priority: int = 0, source_url: Optional[str] = None) -> bool:
        if url in self.visited:
            logging.debug(f"[QUEUE_DEBUG] URL {url} already visited, skipping")
            return False
        if url in self.enqueued:
            logging.debug(f"[QUEUE_DEBUG] URL {url} already enqueued, skipping")
            return False
        if len(self.enqueued) >= self.MAX_QUEUE_SIZE:
            logging.debug(f"[QUEUE_DEBUG] Queue size limit reached, skipping {url}")
            return False
        self.enqueued.add(url)
        self.source_map[url] = source_url
        await self.queue.put((-priority, url))  # Negative for max-heap
        logging.debug(f"[QUEUE_DEBUG] URL {url} enqueued successfully")
        return True

    async def dequeue(self) -> Optional[Tuple[str, Optional[str]]]:
        while not self.queue.empty():
            neg_priority, url = await self.queue.get()
            if url not in self.visited:
                self.enqueued.discard(url)
                source_url = self.source_map.pop(url, None)
                return (url, source_url)
        return None

    async def mark_visited(self, url: str) -> None:
        self.visited.add(url)

    async def is_empty(self) -> bool:
        return self.queue.empty()

    async def size(self) -> int:
        return self.queue.qsize()

    def visited_count(self) -> int:
        """Возвращает количество посещенных ссылок"""
        return len(self.visited)

    async def enqueue_many(self, items: List[Tuple[str, int, Optional[str]]]) -> int:
        """Добавить несколько URL в очередь и вернуть количество успешно добавленных"""
        count = 0
        for url, priority, source_url in items:
            if await self.enqueue(url, priority, source_url):
                count += 1
        return count

    async def clear(self) -> None:
        self.queue = asyncio.PriorityQueue()
        self.visited.clear()
        self.enqueued.clear()
