import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin, urlparse

class Parser:
    def __init__(self):
        pass  # No need for regex patterns anymore

    def extract_links(self, html_content: str, base_url: str) -> List[str]:
        links = set()
        soup = BeautifulSoup(html_content, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # Skip empty, relative, or javascript links
            if not href or href.startswith('#') or href.lower().startswith('javascript:'):
                continue
            # Handle relative URLs
            if not href.startswith(('http://', 'https://')):
                absolute_url = urljoin(base_url, href)
            else:
                absolute_url = href
            # Normalize URL
            parsed = urlparse(absolute_url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            links.add(normalized)
        return list(links)

    def extract_scripts(self, html_content: str, base_url: str) -> List[Dict[str, str]]:
        scripts = []
        soup = BeautifulSoup(html_content, 'html.parser')
        # Process external scripts
        for script_tag in soup.find_all('script', src=True):
            src = script_tag['src']
            absolute_url = urljoin(base_url, src)
            scripts.append({
                'url': absolute_url,
                'content': '',  # Will be fetched separately
                'type':'external'
            })
        # Process inline scripts
        for i, script_tag in enumerate(soup.find_all('script')):
            if script_tag.get('src'):  # Skip external scripts already processed
                continue
            content = script_tag.string or ''
            if not content.strip():
                continue
            scripts.append({
                'url': f"{base_url}#inline-{i}",
                'content': content,
                'type': 'inline'
            })
        return scripts

    def extract_all(self, html_content: str, base_url: str) -> Dict[str, List]:
        return {
            'links': self.extract_links(html_content, base_url),
            'scripts': self.extract_scripts(html_content, base_url)
        }

    def filter_yggdrasil_links(self, links: List[str], filter_func) -> List[str]:
        return [link for link in links if filter_func(link)]
