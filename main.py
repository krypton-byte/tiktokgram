from __future__ import annotations
import re
from io import BytesIO
from typing import Any, Union
from tiktok_downloader.tiktok_async import VideoInfoAsync
from tiktok_downloader.utils import DownloadAsync, DownloadCallback
from snapsave import Fb, FacebookVideo
from snapsave.snapsave import DownloadCallback as DownloadFB, Type
from httpx import AsyncClient
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types.message import Message
from aiogram.types.input_file import InputFile
from dotenv import load_dotenv, dotenv_values
import time
import asyncio
import math
load_dotenv()
requests = AsyncClient()
bot = Bot(token=dotenv_values()['API_TOKEN'])
dp = Dispatcher(bot)


class DownloadFBVid(DownloadFB):
    message: Message

    def __init__(self, q: Message, length: int) -> None:
        super().__init__()
        self.q = q
        self.io = BytesIO()
        self.message = None
        self.timestamp = 0
        self.total = 0
        self.total_length = length

    async def on_open(self, client, response):
        self.message = await bot.send_message(
            self.q.from_user.id, 'Starting Download.....')

    async def on_progress(self, binaries):
        self.io.write(binaries)
        self.total += binaries.__len__()
        if time.time() - self.timestamp > 1.5:  # flood control
            self.timestamp = time.time()
            await self.message.edit_text(
                (
                    'Downloading..... '+convert_size(
                        self.total)+'\nPercentage: %s' % str(int(
                            self.total/self.total_length * 100))+'%'
                ) if self.total_length else (
                    'Downloading..... '+convert_size(self.total_length)))

    async def on_finish(self, client, response):
        self.io.seek(0)
        await self.message.edit_text('Uploading')


class Download(DownloadCallback):
    message: Message

    def __init__(self, q: Message, length: int) -> None:
        super().__init__()
        self.q = q
        self.io = BytesIO()
        self.timestamp = 0
        self.message = None
        self.total = 0
        self.total_length = length

    async def on_open(self, client, response, info):
        self.message = await bot.send_message(
            self.q.from_user.id, 'Starting Download.....')

    async def on_progress(self, binaries):
        self.io.write(binaries)
        self.total += binaries.__len__()
        if time.time() - self.timestamp > 1.5:
            self.timestamp = time.time()
            await self.message.edit_text(
                'Downloading..... '+convert_size(
                    self.total)+'\nPercentage: %s' % str(int(
                        self.total/self.total_length * 100))+'%')

    async def on_finish(self, client, response):
        self.io.seek(0)
        await self.message.edit_text('Uploading')


class Caching:
    def __init__(self) -> None:
        print('create caching instance')
        self.data: dict[str, Any] = {}

    def set(self, data: Union[DownloadAsync, FacebookVideo], size: int):
        keys = hex(int(time.time().__str__().replace('.', '')))
        self.data.update({keys: {
            'expired': int(time.time() + 60 * 10),  # 10 minute
            'data': data,
            'size': size
        }})
        return keys

    async def run(self):
        while True:
            for k, v in self.data.items():
                if v['expired'] < time.time():
                    del self.data[k]
            await asyncio.sleep(3)


def convert_size(size_bytes) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


@dp.message_handler(commands='start')
async def start_cmd_handler(message: types.Message):
    await message.reply(
        "Hi! send me tiktok url/id and i will download the video")


@dp.message_handler()
async def GetVideo(query: Message):
    try:
        keyboard_markup = types.InlineKeyboardMarkup(row_width=3)
        fbdown = Fb()
        if re.match(
            r'https?://fb\.watch|https?://(www.|m.)?facebook\.com',
            query.text
        ):
            result = await fbdown.from_url(query.text)
            size = await asyncio.gather(*[i.get_size() for i in result])
            for i, s in zip(result, size):
                builder = (
                    'Video ' if i.quality.type == Type.VIDEO else 'Audio ')
                if i.quality.type == Type.VIDEO:
                    builder += i.quality.value.__str__() + 'p ' + (
                        'Render' if i.render else '')
                keyboard_markup.add(
                    types.InlineKeyboardButton(
                        builder,
                        callback_data=cache.set(i, s)
                    )
                )
            await query.reply_photo(
                InputFile(BytesIO((await requests.get(result.cover)).content)),
                reply_markup=keyboard_markup
            )
        else:
            result = await VideoInfoAsync.get_info(query.text)
            size = await asyncio.gather(*[
                s.get_size() for s in result.utils()])
            for s, i in zip(size, result.utils()):
                tipe = ' '+['NOWM', 'WM'][
                    i.watermark] if i.type == 'video' else 'MUSIC'
                keyboard_markup.add(types.InlineKeyboardButton(
                    tipe + ' ' + convert_size(s),
                    callback_data=cache.set(i, s)))
            await query.reply_photo(
                InputFile(BytesIO((
                    await requests.get(result.cover)).content)),
                caption='Caption: %s\nAuthor: @%s\nDuration: %s\n' % (
                        result.desc,
                        result.author.username,
                        result.duration
                    ),
                reply_markup=keyboard_markup
            )
    except Exception as e:
        print(e)
        await query.reply('URL/ID video isn\'t valid')


@dp.callback_query_handler()
async def DownloadButton(q: Message):
    await q.answer('Wait a moment to download')
    try:
        p: dict[str, Any] = cache.data[q.data]
        downl = DownloadFBVid(q, await p['data'].get_size()) if isinstance(
            p['data'], FacebookVideo) else Download(q, p['size'])
        await p['data'].download(downl, chunk_size=int(1024 * (1024/2)))
        if isinstance(p['data'], FacebookVideo):
            if p['data'].quality.type == Type.VIDEO:
                await bot.send_video(
                    q.from_user.id,
                    InputFile(downl.io),
                    caption='Success')
            else:
                await bot.send_audio(q.from_user.id, InputFile(downl.io))
        else:
            if p['data'].type in 'video':
                await bot.send_video(
                    q.from_user.id,
                    InputFile(downl.io),
                    caption='Success')
            else:
                await bot.send_audio(q.from_user.id, InputFile(downl.io))
        await downl.message.delete()
    except KeyError as e:
        print(e)
        await bot.send_message(q.from_user.id, 'Button has expired')

if __name__ == '__main__':
    cache = Caching()
    loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(cache.run(), loop)
    executor.start_polling(dp, skip_updates=True)
