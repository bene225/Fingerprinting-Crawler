from pydantic import BaseModel, HttpUrl, Field

class CrawlerConfig(BaseModel):
    url: list[HttpUrl]
    user_agent: str = "chromium/114.0.5735.133"
    time_wait: int = 2
    