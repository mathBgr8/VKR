import asyncio
import json
import logging
from typing import List, Dict, Callable, Tuple
from core.fetcher import Fetcher
from core.parser import Parser
from collector.filter import is_url_allowed
from collector.queue_manager import AsyncQueueManager
from collector.storage import AsyncStorage
from collector.state_manager import StateManager
from urllib.parse import urlparse

class Crawler:
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        
        # Initialize async components
        self.queue = AsyncQueueManager()
        self.storage = AsyncStorage(config.get('output_dir', './data'))
        self.parser = Parser()
        
        # Initialize StateManager
        self.state_manager = StateManager(config.get('state_dir', 'state_backup'))
        
        # Playwright configuration
        playwright_config = config.get('playwright', {})
        self.fetcher = Fetcher(
            headless=playwright_config.get('headless', True),
            timeout_ms=playwright_config.get('timeout_ms', 30000),
            browserless_url=config.get('browserless_url', "ws://localhost:3000")
        )
        
        # State will be loaded in the crawl method
        self._state_loaded = False
        
        # Configuration parameters
        self.allowed_tld = config.get('allowed_tld', [])
        self.yggdrasil_ranges = config.get('yggdrasil_ranges', ['200::/7'])
        self.network_type = config.get('network_type', 'yggdrasil')
        self.max_pages_per_domain = config.get('max_pages_per_domain', 10)
        self.max_links = config.get('max_links', 1000)
        
        # Tracking counters
        self.links_discovered = 0
        self.scripts_saved = 0
        self.links_processed = 0
        self.domain_processed_links = {}
    
    async def _filter_url(self, url: str) -> bool:
        self.logger.debug(f"[FILTER_DEBUG] Checking URL: {url}")
        self.logger.debug(f"[FILTER_DEBUG] network_type: {self.network_type}, allowed_tld: {self.allowed_tld}, yggdrasil_ranges: {self.yggdrasil_ranges}")
        result = is_url_allowed(url, self.network_type, self.allowed_tld, self.yggdrasil_ranges)
        self.logger.debug(f"[FILTER] URL: {url}, network: {self.network_type}, result: {result}")
        return result

    async def _should_process_link(self, base_url: str, link_url: str, is_seed: bool = False) -> bool:
        self.logger.debug(f"[DIAGNOSTIC] Checking link: {link_url} (base: {base_url})")
        
        # Check URL filter
        if not await self._filter_url(link_url):
            self.logger.debug(f"[FILTERED] URL rejected: {link_url}")
            return False
        
        # Check global link limit
        if self.links_processed >= self.max_links:
            self.logger.debug(f"[LIMIT] Max links reached: {self.links_processed}/{self.max_links}")
            return False
        
        # Check domain limits
        try:
            base_parsed = urlparse(base_url)
            link_parsed = urlparse(link_url)
            
            self.logger.debug(f"[DOMAIN] base_netloc: {base_parsed.netloc}, link_netloc: {link_parsed.netloc}")
            
            if base_parsed.netloc == link_parsed.netloc:
                domain = base_parsed.netloc
                
                # Используем простой счётчик вместо хранения URL (экономия памяти)
                current_count = self.domain_processed_links.get(domain, 0)
                if current_count >= self.max_pages_per_domain:
                    self.logger.debug(f"[DOMAIN_LIMIT] {domain} reached max: {current_count}/{self.max_pages_per_domain}")
                    return False
                
                
                self.domain_processed_links[domain]+=1
                self.logger.debug(f"[DOMAIN_ACCEPTED] {domain}, count: {len(self.domain_processed_links[domain])}")
                return True
            
            # External links always get priority
            self.logger.debug(f"[EXTERNAL] Accepting external link: {link_url}")
            return True
            
        except Exception as e:
            self.logger.debug(f"[ERROR] Link validation failed: {e}")
            return False

    
    async def _count_external_links(self, links: List[str], base_url: str) -> int:
        count = 0
        for link in links:
            if await self._is_external_link(base_url, link):
                count += 1
        return count

    async def _is_external_link(self, base_url: str, link_url: str) -> bool:
        try:
            base_parsed = urlparse(base_url)
            link_parsed = urlparse(link_url)
            return base_parsed.netloc != link_parsed.netloc
        except Exception:
            return False

    async def _worker(self, worker_id: int) -> None:
        self.logger.debug(f"Worker {worker_id} started")
        
        # Storage is already initialized in the main crawler, no need to initialize per worker
        self.logger.debug(f"Worker {worker_id}: Using shared storage instance")
        
        while self.links_processed < self.max_links:
            self.logger.debug(f"[WORKER {worker_id}] Attempting to dequeue URL...")
            dequeue_result = await self.queue.dequeue()
            
            if dequeue_result is None:
                self.logger.debug(f"[WORKER {worker_id}] No URL available, sleeping...")
                await asyncio.sleep(1)
                continue
            
            url, source_url = dequeue_result
            self.logger.debug(f"[WORKER {worker_id}] Dequeue returned: url={url}, source_url={source_url}")
            
            #             # Mark as visited
            # await self.queue.mark_visited(url)
            
            #             # Mark as visited only if status is 'processed'
            # if status == 'processed':
            # Check if URL was already successfully processed
            is_processed = await self.storage.is_link_processed(url)
            if is_processed:
                await self.queue.mark_visited(url)
                self.logger.debug(f"[QUEUE] URL already processed: {url}")
                continue
            # else:
            #     self.logger.debug(f"[QUEUE] URL not processed, re-enqueueing: {url}")
            #     # Re-enqueue with lower priority for retry
            #     await self.queue.enqueue(url, priority=-1)
            #     continue  # Skip to next iteration without processing
            self.logger.info(f"[WORKER {worker_id}] Processing: {url}")
            
            # Save state periodically
            if self.links_processed % 200 == 0:
                await self.state_manager.save_state(self)
                self.logger.debug(f"State saved after processing {self.links_processed} links")
            
            # Add diagnostic logging for queue and database status
            queue_size = await self.queue.size()
            visited_count = self.queue.visited_count()
            self.logger.debug(f"[WORKER {worker_id}] Queue status: size={queue_size}, visited={visited_count}, processed={self.links_processed}")
            
            try:
                # Fetch page with scripts
                html_content, page_title, final_url, scripts = await self.fetcher.fetch_page_with_scripts(url)
                #print(html_content,"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

                # Save main link - используем source_url из очереди
                # Если source_url is None (для seeds), используем url как source_url
                actual_source_url = source_url if source_url is not None else url
                parsed = urlparse(final_url)
                site_id = parsed.netloc if parsed.netloc else 'unknown'
                await self.storage.save_link(
                    source_url=actual_source_url,
                    discovered_url=final_url,
                    page_title=page_title,
                    status='processed',
                    site_id=site_id
                )
                
                # Save scripts
                for script in scripts:
                    if script['content'] and not await self.storage.script_exists(script['url']):
                        saved_path = await self.storage.save_script(
                            script_url=script['url'],
                            script_content=script['content'],
                            site_id=site_id
                        )
                        self.scripts_saved += 1
                        self.logger.debug(f"Saved script: {saved_path}")
                
                # Extract and enqueue new links
                links = self.parser.extract_links(html_content, final_url)
                self.logger.debug(f"[WORKER {worker_id}] Found {len(links)} links")
                
                if links:
                    self.logger.debug(f"[WORKER {worker_id}] First 5 links: {links[:5]}")
                    
                    # Filter Yggdrasil links
                    ygg_links = []
                    for link in links:
                        should_process = await self._should_process_link(final_url, link)
                        self.logger.debug(f"[WORKER {worker_id}] Checking link {link}: should_process={should_process}")
                        if should_process:
                            # Check if link already exists in storage
                            if not await self.storage.link_exists(final_url, link, site_id):
                                ygg_links.append(link)
                            else:
                                self.logger.debug(f"Link already exists: {link}")
                    
                    # Calculate priorities и передаем final_url как source_url для новых ссылок
                    url_priority_pairs = [(link, await self._count_external_links([link], final_url), final_url) for link in ygg_links]
                    
                    # Enqueue with priorities
                    added = await self.queue.enqueue_many(url_priority_pairs)
                    self.links_discovered += added
                    self.links_processed += 1
                    
                    self.logger.info(f"[WORKER {worker_id}] Found {len(ygg_links)} Yggdrasil links, added {added} new")
                    
                    # Mark as visited after successful processing
                    await self.queue.mark_visited(url)
                    self.logger.debug(f"[WORKER {worker_id}] URL marked as visited: {url}")
                    
            except Exception as e:
                    self.logger.error(f"[WORKER {worker_id}] Error processing {url}: {e}")
                    self.logger.debug(f"[WORKER {worker_id}] Attempting to save error link to database")
                    parsed = urlparse(url)
                    actual_source_url = source_url if source_url is not None else url
                    try:
                        await self.storage.save_link(
                            actual_source_url, url, '', 'error', parsed.netloc if parsed.netloc else 'unknown'
                        )
                        self.logger.debug(f"[WORKER {worker_id}] Error link saved successfully")
                    except Exception as db_error:
                        self.logger.error(f"[WORKER {worker_id}] Failed to save error link: {db_error}")
                    
                    # Mark as visited even on error to avoid infinite retry
                    await self.queue.mark_visited(url)
                    self.logger.debug(f"[WORKER {worker_id}] URL marked as visited (after error): {url}")
                    
                    # Increment processed count even on error to avoid infinite loop
                    self.links_processed += 1
                    self.logger.debug(f"[WORKER {worker_id}] links_processed incremented to {self.links_processed} (after error)")
            
        self.logger.debug(f"Worker {worker_id} finished")

    async def crawl(self, seed_links: List[str]) -> None:
        self.logger.info(f"=== STARTING CRAWL ===")
        self.logger.info(f"Received {len(seed_links)} seed links")
        
        # Initialize storage before starting workers
        self.logger.debug("Initializing storage before crawl")
        await self.storage.start()
        self.logger.debug("Storage initialization completed")
        
        # Try to restore state from backup
        self.logger.debug("Attempting to restore state from backup")
        state_restored = await self.state_manager.restore_state(self)
        if state_restored:
            self.logger.info(f"State restored from backup. Links processed: {self.links_processed}")
        else:
            self.logger.info("No existing state found, starting fresh")
        
        # Filter and enqueue seed links (seeds имеют source_url=None)
        filtered_count = 0
        rejected_seeds = []
        accepted_seeds = []
        
        for link in seed_links:
            self.logger.debug(f"[SEED_DEBUG] Processing seed: {link}")
            passes_filter = await self._filter_url(link)
            self.logger.info(f"[SEED_FILTER] {link}: passes_filter={passes_filter}")
            
            if passes_filter:
                self.logger.debug(f"[SEED_DEBUG] Attempting to enqueue: {link}")
                
                # Check if URL is in visited but not actually processed
                if link in self.queue.visited:
                    is_processed = await self.storage.is_link_processed(link)
                    if not is_processed:
                        self.logger.debug(f"[SEED_DEBUG] URL in visited but not processed, removing from visited: {link}")
                        self.queue.visited.discard(link)
                
                # Seeds передаются с source_url=None
                enqueue_success = await self.queue.enqueue(link, priority=0, source_url=None)
                self.logger.debug(f"[SEED_DEBUG] Enqueue result: {enqueue_success}")
                
                if enqueue_success:
                    filtered_count += 1
                    accepted_seeds.append(link)
                else:
                    self.logger.warning(f"[SEED_DEBUG] Failed to enqueue seed: {link}")
                    rejected_seeds.append(link)
            else:
                rejected_seeds.append(link)
                self.logger.debug(f"Seed rejected: {link}")
        
        self.logger.info(f"Accepted {len(accepted_seeds)} seeds: {accepted_seeds[:5]}")
        self.logger.info(f"Rejected {len(rejected_seeds)} seeds: {rejected_seeds[:5]}")
        
        # Diagnostic: check queue status after enqueuing seeds
        queue_size = await self.queue.size()
        visited_count = self.queue.visited_count()
        self.logger.info(f"[QUEUE_DIAG] After seeding: queue_size={queue_size}, visited_count={visited_count}")
        
        # Start crawling
        self.logger.debug("Starting fetcher")
        await self.fetcher.start()
        
        try:
            # Create worker tasks
            max_workers = self.config.get('max_workers', 2)
            self.logger.info(f"Starting {max_workers} workers")
            
            tasks = [asyncio.create_task(self._worker(i + 1)) for i in range(max_workers)]
            
            # Wait for all workers to complete
            self.logger.debug("Waiting for all workers to complete")
            await asyncio.gather(*tasks)
            self.logger.debug("All workers completed")
        finally:
            # Cleanup
            self.logger.debug("Starting cleanup")
            await self.storage.close()
            await self.fetcher.close()
            await self.state_manager.cleanup()
            self.logger.debug("Cleanup completed")
        
        self.logger.info(f"Crawler finished. Discovered {self.links_discovered} links, saved {self.scripts_saved} scripts")
        self.logger.info(f"Visited {self.queue.visited_count()} links, saved {self.storage.get_links_count()} links")

    def load_seeds(self, filepath: str) -> List[str]:
        seeds = []
        total_lines = 0
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    total_lines += 1
                    line = line.strip()
                    if line and not line.startswith('#'):
                        seeds.append(line)
            self.logger.info(f"Loaded {total_lines} lines from {filepath}, found {len(seeds)} valid seeds")
        except FileNotFoundError:
            self.logger.error(f"Seed file not found: {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading seeds: {e}")
        
        self.logger.info(f"load_seeds returning {len(seeds)} seeds")
        return seeds

# Example usage
if __name__ == '__main__':
    config = {
        'output_dir': './data',
        'playwright': {
            'headless': True,
            'timeout_ms': 30000
        },
        'allowed_tld': ['.ygg'],
        'yggdrasil_ranges': ['200::/7'],
        'network_type': 'yggdrasil',
        'max_pages_per_domain': 10,
        'max_links': 1000,
        'max_workers': 4
    }
    
    logger = logging.getLogger('crawler')
    crawler = Crawler(config, logger)
    seeds = crawler.load_seeds('seeds.txt')
    asyncio.run(crawler.crawl(seeds))
