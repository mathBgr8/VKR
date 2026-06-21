import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
import re
import dns.resolver
from urllib.parse import urlparse
from collector.filter import is_url_allowed
import ipaddress




class Fetcher:
    """
    Класс для загрузки веб-страниц с использованием Playwright.
    Поддерживает как локальный запуск браузера, так и подключение к Docker-контейнеру browserless.
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 60000, browserless_url: Optional[str] = None):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.browserless_url = browserless_url
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._logger = logging.getLogger(__name__)
        self._retry_count = 0

    async def __aenter__(self):
        """Контекстный менеджер для асинхронного использования."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self) -> None:
        if self._browser:
            self._logger.debug("Браузер уже запущен")
            return
            
        load_dns_servers(file_path='..\\dns_servers.txt')

        self._logger.info("Запуск Playwright...")
        self._playwright = await async_playwright().start()
        

        if self.browserless_url:
            self._logger.info(f"Подключение к browserless: {self.browserless_url}")
            try:
                self._browser = await self._playwright.chromium.connect(self.browserless_url)
                self._logger.info(f"Успешно подключено к browserless, браузер: {self._browser}")
            except Exception as e:
                self._logger.error(f"Ошибка подключения к browserless: {e}")
                if self._playwright:
                    await self._playwright.stop()
                    self._playwright = None
                raise
        else:
            # Локальный запуск браузера
            self._logger.info("Запуск локального браузера Playwright")
            try:
                self._browser = await self._playwright.chromium.launch(headless=self.headless)
                self._logger.info(f"Локальный браузер запущен: {self._browser}")
            except Exception as e:
                self._logger.error(f"Ошибка запуска локального браузера: {e}")
                if self._playwright:
                    await self._playwright.stop()
                    self._playwright = None
                raise
        
        self._logger.info("Браузер запущен/подключен")

    async def close(self) -> None:
        if self._browser:
            if self.browserless_url:
                # Для browserless просто обнуляем ссылку, соединение закроется само при stop()
                self._logger.info("Отключение от browserless (браузер остается живым на сервере)")
                self._browser = None
            else:
                try:
                    await self._browser.close()
                    self._logger.info("Локальный браузер закрыт")
                except Exception as e:
                    self._logger.debug(f"Ошибка при закрытии локального браузера: {e}")
        
        if self._playwright:
            try:
                await self._playwright.stop()
                self._logger.info("Playwright остановлен")
            except Exception as e:
                self._logger.debug(f"Ошибка при остановке Playwright: {e}")
            finally:
                self._playwright = None
        
        self._logger.info("Ресурсы Playwright освобождены")

    async def fetch_page(self, url: str) -> tuple[str, str, str]:
        # Убеждаемся, что браузер доступен (переподключаемся, если необходимо)
        if not self._browser:
            await self.start()
        
        page: Optional[Page] = None
        context = None
        try:
            # Создаем новый контекст и страницу
            context = await self._browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Переходим на страницу с ожиданием networkidle
            response = await page.goto(url, wait_until='networkidle', timeout=self.timeout_ms)
            
            if not response:
                raise Exception(f"Нет ответа от сервера для {url}")
            
            # Получаем HTML содержимое
            html_content = await page.content()
            
            # Получаем заголовок страницы
            page_title = await page.title()
            
            # Получаем финальный URL (после возможных редиректов)
            final_url = page.url
            
            return html_content, page_title, final_url
            
        except Exception as e:
            self._logger.error(f"Ошибка при загрузке {url}: {e}")
            # Если браузер закрыт, переподключаемся
            if "closed" in str(e).lower():
                self._retry_count += 1
                if self._retry_count > 3:
                    self._retry_count = 0
                    raise  # Не долбим бесконечно
                self._logger.warning(f"Соединение разорвано, переподключение (попытка {self._retry_count})")
                self._browser = None
                await asyncio.sleep(2)  # Даем контейнеру время освободить сессии
                await self.start()
                return await self.fetch_page_with_scripts(url)
            raise
        finally:
            # Закрываем страницу и контекст (изоляция)
            self._retry_count = 0  # Сброс при успехе
            if page:
                try:
                    await page.close()
                except Exception as e:
                    self._logger.debug(f"Ошибка при закрытии страницы {url}: {e}")
            if context:
                try:
                    await context.close()
                except Exception as e:
                    self._logger.debug(f"Ошибка при закрытии контекста для {url}: {e}")
    
    async def fetch_page_with_scripts(self, url: str) -> tuple:
        # Убеждаемся, что браузер доступен (переподключаемся, если необходимо)
        if not self._browser:
            await self.start()
        
        page: Optional[Page] = None
        context = None
        if is_domain_url(url):
            url = resolve_url_with_fallback(url)
        try:
            # Создаем новый контекст и страницу (полная изоляция)
            context = await self._browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Переходим на страницу с ожиданием networkidle
            response = await page.goto(url, wait_until='networkidle', timeout=self.timeout_ms)
            
            if not response:
                raise Exception(f"Нет ответа от сервера для {url}")
            
            # Получаем HTML содержимое
            html_content = await page.content()
            
            # Получаем заголовок страницы
            page_title = await page.title()
            
            # Получаем финальный URL (после возможных редиректов)
            final_url = page.url
            
            # Извлекаем скрипты со страницы
            scripts = await self._extract_scripts(page, final_url)
            
            return html_content, page_title, final_url, scripts
            
        except Exception as e:
            self._logger.error(f"Ошибка при загрузке {url}: {e}")
            # Если браузер закрыт, переподключаемся
            if "closed" in str(e).lower():
                self._logger.error(f"[ДИАГНОСТИКА] Браузер закрыт, переподключаемся...")
                self._browser = None
                await self.start()  # Повторный запуск браузера
                # Пытаемся выполнить запрос снова
                return await self.fetch_page_with_scripts(url)
            raise
        finally:
            # Закрываем страницу и контекст (изоляция)
            if page:
                try:
                    await page.close()
                except Exception as e:
                    self._logger.debug(f"Ошибка при закрытии страницы {url}: {e}")
            if context:
                try:
                    await context.close()
                except Exception as e:
                    self._logger.debug(f"Ошибка при закрытии контекста для {url}: {e}")
    
    async def _extract_scripts(self, page: Page, base_url: str) -> list:

        scripts = []
        
        script_data = await page.evaluate('''() => {
            const scripts = Array.from(document.querySelectorAll('script'));
            return scripts.map((s, index) => {
                if (s.src) {
                    return { type: 'external', url: s.src, content: '' };
                } else {
                    const content = s.textContent || '';
                    return { type: 'inline', url: window.location.href + '#inline-' + index, content: content };
                }
            });
        }''')
        
        for script in script_data:
            if script['type'] == 'inline':
                if script['content'].strip():
                    scripts.append({
                        'url': script['url'],
                        'content': script['content']
                    })
            elif script['type'] == 'external':
                try:
                    content = await page.evaluate('''(scriptUrl) => {
                        return fetch(scriptUrl)
                            .then(r => {
                                if (r.ok) return r.text();
                                return '';
                            })
                            .catch(e => '');
                    }''', script['url'])
                    
                    scripts.append({
                        'url': script['url'],
                        'content': content if content else ''
                    })
                except Exception as e:
                    self._logger.warning(f"Не удалось загрузить содержимое скрипта {script['url']}: {e}")
                    scripts.append({
                        'url': script['url'],
                        'content': ''
                    })
        
        self._logger.debug(f"Извлечено {len(scripts)} скриптов со страницы {base_url}")
        return scripts


from urllib.parse import urljoin

async def _extract_scriptsCDP(self, page: Page, base_url: str) -> list:
    cdp = await page.context.new_cdp_session(page)
    script_map = {}  # scriptId -> {'url': str, 'event': dict}
    seen_urls = set()  

    def on_script_parsed(event):
        script_id = event['scriptId']
        raw_url = event.get('url', '')
        
        if not raw_url:
            raw_url = f"cdp:{script_id}"
        
        if raw_url.startswith(('http://', 'https://')):
            if raw_url in seen_urls:
                return
            seen_urls.add(raw_url)
        
        script_map[script_id] = {
            'url': raw_url,
            'event': event
        }

    await cdp.send('Debugger.enable')
    cdp.on('Debugger.scriptParsed', on_script_parsed)

    await page.reload(wait_until='networkidle')
    
    await page.wait_for_timeout(500)

    await cdp.send('Debugger.disable')

    result = []
    for script_id, info in script_map.items():
        try:
            resp = await cdp.send('Debugger.getScriptSource', {'scriptId': script_id})
            content = resp.get('scriptSource', '')
        except Exception as e:
            self._logger.warning(f"Не удалось получить содержимое скрипта {info['url']}: {e}")
            content = ''
        
        url = info['url']
        if url and not url.startswith(('http://', 'https://', 'cdp:', 'eval:', 'function:')):
            url = urljoin(base_url, url)
        
        if content.strip():
            result.append({'url': url, 'content': content})
        else:
            result.append({'url': url, 'content': ''})
    
    await cdp.close()
    
    self._logger.debug(f"CDP: извлечено {len(result)} скриптов (включая eval/new Function)")
    return result


def load_dns_servers(file_path='..\\dns_servers.txt'):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def is_domain_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True

def resolve_url_with_fallback(url):
    dns_servers = load_dns_servers()
    for server in dns_servers:
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [server]
            answers = resolver.resolve(url, 'A')
            return [rdata.address for rdata in answers]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
            continue  
    raise Exception('DNS resolution failed for all configured servers')
