import aiosqlite
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

class AsyncStorage:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.links_file = self.output_dir / 'links.csv'
        self.scripts_dir = self.output_dir / 'scripts'
        self.scripts_db = self.output_dir / 'scripts.db'
        self.scripts_table = 'scripts'
        self.links_table = 'links'
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        
        self._link_id_counter = 0
        
        self.logger = logging.getLogger(__name__)
        
        self.logger.debug(f"AsyncStorage initialized with output_dir: {self.output_dir}")

    async def _init_db(self):
        self.logger.debug("Starting database initialization")
        async with aiosqlite.connect(self.scripts_db) as db:
            await db.execute(f"CREATE TABLE IF NOT EXISTS {self.links_table} ("
                             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                             "source_url TEXT,"
                             "discovered_url TEXT,"
                             "page_title TEXT,"
                             "discovery_time TEXT,"
                             "status TEXT,"
                             "site_id TEXT,"
                             "static_result TEXT,"
                             "dynamic_result TEXT)"
                             )
            await db.execute(f"CREATE TABLE IF NOT EXISTS {self.scripts_table} ("
                             "url_hash TEXT PRIMARY KEY,"
                             "content TEXT)"
                             )
            await db.commit()
        self.logger.debug("Database initialization completed")
    async def _get_last_link_id(self) -> int:
        self.logger.debug("Fetching last link ID from database")
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"SELECT MAX(id) FROM {self.links_table}") as cursor:
                result = await cursor.fetchone()
                last_id = result[0] or 0
        self.logger.debug(f"Last link ID: {last_id}")
        return last_id
    async def save_link(self, source_url: str, discovered_url: str, page_title: str, status: str, site_id: str, static_result: str = '', dynamic_result: str = '') -> int:
        self.logger.debug(f"Attempting to save link: {discovered_url}")
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"INSERT OR IGNORE INTO {self.links_table} (source_url, discovered_url, page_title, discovery_time, status, site_id, static_result, dynamic_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                source_url, discovered_url, page_title, datetime.utcnow().isoformat(), status, site_id, static_result, dynamic_result
            )) as cursor:
                await db.commit()
                self.logger.debug(f"Link saved successfully: {discovered_url}")
                # Use cursor.lastrowid for the inserted row ID
                return cursor.lastrowid

    async def link_exists(self, source_url: str, discovered_url: str, site_id: str) -> bool:
        async with aiosqlite.connect(self.scripts_db) as db:
            url_hash = hashlib.sha256(discovered_url.encode('utf-8')).hexdigest()
            async with db.execute(f"SELECT 1 FROM {self.links_table} WHERE source_url=? AND discovered_url=? AND site_id=?", (source_url, discovered_url, site_id)) as cursor:
                result = await cursor.fetchone()
                return result is not None
    
    async def is_link_processed(self, url: str) -> bool:
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"SELECT 1 FROM {self.links_table} WHERE discovered_url=? AND status='processed'", (url,)) as cursor:
                result = await cursor.fetchone()
                return result is not None

    async def save_script(self, script_url: str, script_content: str, site_id: str) -> str:
        url_hash = hashlib.sha256(script_url.encode('utf-8')).hexdigest()
        async with aiosqlite.connect(self.scripts_db) as db:
            await db.execute(f"INSERT OR REPLACE INTO {self.scripts_table} (url_hash, content) VALUES (?, ?)", (url_hash, script_content))
            await db.commit()
        # Also save to file system for compatibility
        site_dir = self.scripts_dir / site_id
        site_dir.mkdir(parents=True, exist_ok=True)
        filepath = site_dir / f"{url_hash}.js"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(script_content)
        return str(filepath.relative_to(self.output_dir))

    async def script_exists(self, script_url: str) -> bool:
        url_hash = hashlib.sha256(script_url.encode('utf-8')).hexdigest()
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"SELECT 1 FROM {self.scripts_table} WHERE url_hash=?", (url_hash,)) as cursor:
                result = await cursor.fetchone()
                return result is not None

    async def get_links_count(self) -> int:
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"SELECT COUNT(*) FROM {self.links_table}") as cursor:
                result = await cursor.fetchone()
                return result[0]

    async def get_scripts_count(self) -> int:
        async with aiosqlite.connect(self.scripts_db) as db:
            async with db.execute(f"SELECT COUNT(*) FROM {self.scripts_table}") as cursor:
                result = await cursor.fetchone()
                return result[0]

    async def start(self):
        self.logger.debug("AsyncStorage start: initializing database")
        await self._init_db()
        self._link_id_counter = await self._get_last_link_id()
        self.logger.debug("AsyncStorage start completed, link_id_counter set")
    async def close(self):
        pass
