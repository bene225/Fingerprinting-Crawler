from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
from models import CrawlerConfig


class Crawler:
    
    def __init__(self,CrawlerConfig):
        self.config = CrawlerConfig