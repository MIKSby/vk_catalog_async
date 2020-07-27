import asyncio
import random
from typing import NamedTuple, Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup
from httpcore import ConnectTimeout

from vk_catalog_async.user_agents import USER_AGENTS


class SectionLink(NamedTuple):
    url: str
    nesting_lvl: int
    last_response: Optional[str]


QUEUE__SECTION = 'queue__section_links'
QUEUE__WEB = 'queue__web'


async def get_links_from_catalog_by_class_name(all_queues: Dict[str, Any]) -> None:
    while True:
        section_link: SectionLink = await all_queues[QUEUE__SECTION].get()
        soup = BeautifulSoup(section_link.last_response, 'html.parser')
        for section in soup.find_all(class_='column2' if section_link.nesting_lvl == 3 else 'column4'):
            for tag in section.childGenerator():
                if str(tag) in ['', ' ', '\n', '<br/>']:
                    continue
                try:
                    if section_link.nesting_lvl == 3:
                        print(f'https://vk.com/{tag["href"]}')
                        return
                    else:
                        new_section_link = SectionLink(url=f'https://vk.com/{tag["href"]}', nesting_lvl=section_link.nesting_lvl + 1, last_response=None)
                        await all_queues[QUEUE__WEB].put(new_section_link)
                except KeyError:
                    pass


async def fetch(all_queues: Dict[str, Any], user_agent: str) -> None:
    while True:
        section_obj: SectionLink = await all_queues[QUEUE__WEB].get()
        async with httpx.AsyncClient() as client:
            try:
                client.headers['User-Agent'] = user_agent
                response = await client.get(url=section_obj.url, headers=client.headers)
            except ConnectTimeout:
                await all_queues[QUEUE__WEB].put(section_obj)
                continue
        all_queues[QUEUE__WEB].task_done()
        await all_queues[QUEUE__SECTION].put(SectionLink(url=str(section_obj.url), nesting_lvl=int(section_obj.nesting_lvl), last_response=str(response.text)))
        print(f'web task complete! in web queue: {all_queues[QUEUE__WEB].qsize()}; in sector queue: {all_queues[QUEUE__SECTION].qsize()} tasks')


async def main() -> None:
    queue__section_links: Any = asyncio.Queue()
    queue__web: Any = asyncio.Queue()

    all_queues = {
        QUEUE__SECTION: queue__section_links,
        QUEUE__WEB: queue__web,
    }

    await queue__web.put(SectionLink(url='https://vk.com/catalog.php', nesting_lvl=0, last_response=None))

    local_scan_worker = asyncio.create_task(get_links_from_catalog_by_class_name(all_queues))
    web_workers = [asyncio.create_task(fetch(all_queues, user_agent=random.choice(USER_AGENTS))) for _ in range(300)]

    await asyncio.gather(local_scan_worker, *web_workers)


if __name__ == '__main__':
    asyncio.run(main())
