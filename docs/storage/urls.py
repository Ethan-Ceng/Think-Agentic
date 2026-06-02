import os.path
from typing import Final

from app.config import get_settings
from app.utils.config import ConfigUtil


class UrlUtil:
    domain: Final[str] = get_settings().domain
    upload_prefix: Final[str] = get_settings().upload_prefix

    @classmethod
    async def get_storage_domain(cls, engine: str) -> str:
        config = await ConfigUtil.get_map("storage", engine)
        if not config:
            return ''
        return config.get('domain', '').rstrip('/')

    @classmethod
    async def to_absolute_url(cls, url: str, engine='') -> str:
        """
        转绝对路径
        转前: /uploads/11.png
        转后: https://127.0.0.1/uploads/11.png
        :param url: 相对路径
        :return:
        """
        if not url:
            return ''
        if url.find('/') != 0:
            url = '/' + url
        if url.startswith('/api/static/'):
            return cls.domain + url
        if not engine:
            engine = await ConfigUtil.get_val("storage", "default", "local")
        if engine == 'local':
            local_domain = await cls.get_storage_domain('local')
            prefix = cls.upload_prefix + url
            return local_domain + prefix if local_domain else prefix
        storage_domain = await cls.get_storage_domain(engine)
        return storage_domain + url

    @classmethod
    async def to_relative_url(cls, url: str, engine=None) -> str:
        """
        转相对路径
        转前: https://127.0.0.1/uploads/11.png
        转后: /uploads/11.png
        :param url:
        :return:
        """
        if not url or not url.startswith('http'):
            return url
        if not engine:
            engine = await ConfigUtil.get_val('storage', 'default', 'local')
        if engine == 'local':
            local_domain = await cls.get_storage_domain('local')
            url = url.replace(local_domain, '') if local_domain else url.replace(get_settings().domain, '')
            return url.replace(os.path.join('/', cls.upload_prefix) + '/', '/')
        storage_domain = await cls.get_storage_domain(engine)
        if storage_domain:
            return url.replace(storage_domain, '').replace(os.path.join('/', cls.upload_prefix) + '/', '')
        return url
