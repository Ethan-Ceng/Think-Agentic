import os.path

from fastapi import UploadFile

from app.config import get_settings
from app.exceptions.base import AppException
from app.core.http import HttpResp
from app.plugins.storage.engine.aliyun import AliyunStorage
from app.plugins.storage.engine.local import LocalStorage
from app.plugins.storage.engine.qcloud import QCloudStorage
from app.utils.config import ConfigUtil
from app.utils.datetime import get_now_str, FORMAT_DATE2
from app.utils.tools import ToolsUtil
from app.utils.urls import UrlUtil


class StorageDriver(object):
    FILE_TYPE_IMAGE = 10
    FILE_TYPE_VIDEO = 20
    FILE_TYPE_OTHER = 30

    @classmethod
    async def upload(cls, file_in: UploadFile, folder: str, file_type: int):
        engine = await ConfigUtil.get_val("storage", "default", "local")
        file_size = cls.get_file_size(file_in)
        cls.check_file(file_in, file_size, file_type)
        key = cls.build_save_name(file_in, folder)
        if engine == 'local':
            await LocalStorage.upload(file_in, key)
            key = key.replace('\\', '/')
        elif engine == 'aliyun':
            key = await AliyunStorage().upload_data(key, file_in.file)
        elif engine == 'qcloud':
            key = await QCloudStorage().upload_data(key, file_in.file)
        else:
            raise AppException(HttpResp.FAILED, msg="engine:%s 暂未接入, 暂时不支持" % engine)

        origin_file_name = file_in.filename
        origin_ext = origin_file_name.split('.')[-1].lower()

        result = {
            'id': 0,
            'name': origin_file_name,
            'size': file_size,
            'ext': origin_ext,
            'file_type': file_type,
            'storage_engine': engine,
            'url': key,
            'path': await UrlUtil.to_absolute_url(key)
        }
        return result

    @classmethod
    async def upload_auto(cls, file_in: UploadFile, folder: str = 'file'):
        """
        自动识别文件类型并上传
        - 图片: 10
        - 视频: 20
        - 其他: 30
        """
        file_type = cls.detect_file_type(file_in)
        return await cls.upload(file_in, folder, file_type)

    @classmethod
    def detect_file_type(cls, file_in: UploadFile) -> int:
        """
        根据扩展名与 content-type 自动识别文件类型
        """
        filename = file_in.filename or ''
        content_type = (file_in.content_type or '').lower()
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        settings = get_settings()

        if ext in settings.upload_image_ext or content_type.startswith('image/'):
            return cls.FILE_TYPE_IMAGE
        if ext in settings.upload_video_ext or content_type.startswith('video/'):
            return cls.FILE_TYPE_VIDEO
        return cls.FILE_TYPE_OTHER

    @classmethod
    def build_save_name(cls, file_in: UploadFile, folder):
        """
        保存的文件名
        :return:
        """
        date = get_now_str(FORMAT_DATE2)
        filename = file_in.filename
        ext = filename.split('.')[-1].lower()
        uuid = ToolsUtil.make_uuid()
        return folder + "/" + date + "/" + uuid + '.' + ext

    @classmethod
    def check_file(cls, file_in: UploadFile, file_size: int, file_type: int):
        filename = file_in.filename
        ext = filename.split('.')[-1].lower()
        if not ext:
            raise AppException(HttpResp.FAILED, msg='未知的文件类型')
        if file_type == cls.FILE_TYPE_IMAGE:
            # 图片文件
            limit_size = get_settings().upload_image_size
            if ext not in get_settings().upload_image_ext:
                raise AppException(HttpResp.FAILED, msg='不被支持的扩展:%s' % ext)
            if file_size > limit_size:
                raise AppException(HttpResp.FAILED, msg='上传图片不能超出限制:%d M' % (limit_size / 1024 / 1024))
        elif file_type == cls.FILE_TYPE_VIDEO:
            # 视频文件
            limit_size = get_settings().upload_video_size
            if ext not in get_settings().upload_video_ext:
                raise AppException(HttpResp.FAILED, msg='不被支持的扩展:%s' % ext)
            if file_size > limit_size:
                raise AppException(HttpResp.FAILED, msg='上传视频不能超出限制:%d M' % (limit_size / 1024 / 1024))
        elif file_type == cls.FILE_TYPE_OTHER:
            # 其他文件
            limit_size = get_settings().upload_file_size
            if file_size > limit_size:
                raise AppException(HttpResp.FAILED, msg='上传文件不能超出限制:%d M' % (limit_size / 1024 / 1024))
        else:
            raise AppException(HttpResp.FAILED, msg='上传文件类型错误')

    @classmethod
    def get_file_size(cls, file_in: UploadFile):
        file_in.file.seek(0, os.SEEK_END)
        file_size = file_in.file.tell()
        file_in.file.seek(0, os.SEEK_SET)
        return file_size
