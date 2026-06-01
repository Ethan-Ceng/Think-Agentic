#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Storage extension - Tencent Cloud COS (Cloud Object Storage)
"""
import logging
from functools import lru_cache
from typing import Optional

from qcloud_cos import CosS3Client, CosConfig

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Storage:
    """腾讯云COS对象存储管理类"""

    def __init__(self):
        self._settings = get_settings()
        self._client: Optional[CosS3Client] = None

    async def init(self) -> None:
        """初始化COS客户端"""
        if self._client is not None:
            logger.warning("COS对象存储已初始化，无需重复操作")
            return

        if not self._settings.cos_secret_id or not self._settings.cos_secret_key:
            logger.warning("COS对象存储未配置，跳过初始化")
            return

        try:
            logger.info("正在初始化COS对象存储...")
            config = CosConfig(
                Region=self._settings.cos_region,
                SecretId=self._settings.cos_secret_id,
                SecretKey=self._settings.cos_secret_key,
                Token=None,
                Scheme=self._settings.cos_scheme,
            )
            self._client = CosS3Client(config)
            logger.info("COS对象存储初始化成功")
        except Exception as e:
            logger.error(f"COS对象存储初始化失败: {str(e)}")
            raise

    async def shutdown(self) -> None:
        """关闭COS客户端"""
        if self._client is not None:
            self._client = None
            logger.info("COS对象存储成功关闭")

        get_storage.cache_clear()

    @property
    def client(self) -> CosS3Client:
        """获取COS客户端"""
        if self._client is None:
            raise RuntimeError("COS对象存储未初始化，请先调用init()")
        return self._client

    @property
    def client_or_none(self) -> Optional[CosS3Client]:
        """Return the COS client when configured, otherwise None."""
        return self._client


@lru_cache()
def get_storage() -> Storage:
    """获取Storage实例（单例）"""
    return Storage()
