"""Системный плеер Windows (GSMTC — Global System Media Transport Controls).

Показывает реальный трек, исполнителя и обложку из Spotify, Яндекс Музыки, браузеров и т.д.
Управляет воспроизведением через сессию Windows; если это не вышло или библиотек нет —
отправляет обычные системные медиаклавиши. Без winrt-пакетов приложение работает как раньше.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import threading
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal

from . import winapi


@dataclass
class TrackInfo:
    available: bool = False  # есть ли активная медиа-сессия
    title: str = ""
    artist: str = ""
    album: str = ""
    playing: bool = False
    thumb: bytes | None = None  # обложка (PNG/JPEG), если есть
    app: str = ""


def _load_winrt():
    """Пробует winrt-* (pywinrt), затем winsdk. Возвращает (media.control, storage.streams) или None."""
    if not winapi.IS_WIN:
        return None
    last: Exception | None = None
    for root in ("winrt", "winsdk"):
        try:
            control = importlib.import_module(f"{root}.windows.media.control")
            streams = importlib.import_module(f"{root}.windows.storage.streams")
            return control, streams
        except Exception as e:  # ImportError и ошибки загрузки проекций
            last = e
    print("EyeBar: Windows media session is unavailable:", last, file=sys.stderr)
    return None


class MediaService(QObject):
    updated = pyqtSignal(object)  # TrackInfo

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.info = TrackInfo()
        self._mods = _load_winrt()
        self.backend_ok = self._mods is not None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._manager = None
        self._stop = threading.Event()
        self._thumb_key: tuple | None = None
        self._thumb: bytes | None = None
        self._thumb_tries = 0

    # ---------- жизненный цикл ----------
    def start(self) -> None:
        if not self._mods:
            return
        threading.Thread(target=self._run, name="eyebar-media", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._poll())
        except Exception as e:
            print("EyeBar: media loop stopped:", e, file=sys.stderr)
            self.backend_ok = False
        finally:
            self._loop = None
            loop.close()

    async def _poll(self) -> None:
        control, _ = self._mods
        self._manager = await control.GlobalSystemMediaTransportControlsSessionManager.request_async()
        while not self._stop.is_set():
            await self._refresh()
            await asyncio.sleep(1.0)

    async def _refresh(self) -> None:
        try:
            info = await self._read()
        except Exception:
            info = TrackInfo()  # плеер закрылся посреди чтения — считаем, что ничего не играет
        if info != self.info:
            self.info = info
            self.updated.emit(info)

    # ---------- чтение ----------
    async def _read(self) -> TrackInfo:
        control, streams = self._mods
        session = self._manager.get_current_session() if self._manager else None
        if session is None:
            self._thumb_key = None
            return TrackInfo()
        props = await session.try_get_media_properties_async()
        status = session.get_playback_info().playback_status
        playing = status == control.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING

        key = (props.title, props.artist, props.album_title)
        if key != self._thumb_key:
            self._thumb_key, self._thumb, self._thumb_tries = key, None, 0
        if self._thumb is None and self._thumb_tries < 6:  # обложка у некоторых плееров приходит позже
            self._thumb_tries += 1
            self._thumb = await self._read_thumb(props.thumbnail, streams)

        return TrackInfo(
            available=True, title=props.title or "", artist=props.artist or "",
            album=props.album_title or "", playing=playing, thumb=self._thumb,
            app=session.source_app_user_model_id or "",
        )

    @staticmethod
    async def _read_thumb(ref, streams) -> bytes | None:
        if ref is None:
            return None
        try:
            stream = await ref.open_read_async()
            buf = streams.Buffer(5_000_000)
            await stream.read_async(buf, buf.capacity, streams.InputStreamOptions.READ_AHEAD)
            reader = streams.DataReader.from_buffer(buf)
            data = bytearray(reader.unconsumed_buffer_length)
            reader.read_bytes(data)
            return bytes(data) or None
        except Exception:
            return None

    # ---------- управление ----------
    def command(self, action: str) -> None:
        """action: 'play' (пауза/воспроизведение) | 'next' | 'prev'."""
        loop = self._loop
        if loop is None or self._manager is None:
            winapi.send_media_key(action)
            return
        try:
            coro = self._command(action)
            try:
                asyncio.run_coroutine_threadsafe(coro, loop)
            except RuntimeError:
                coro.close()
                winapi.send_media_key(action)
        except Exception:
            winapi.send_media_key(action)

    async def _command(self, action: str) -> None:
        ok = False
        try:
            session = self._manager.get_current_session()
            if session is not None:
                if action == "play":
                    ok = await session.try_toggle_play_pause_async()
                elif action == "next":
                    ok = await session.try_skip_next_async()
                elif action == "prev":
                    ok = await session.try_skip_previous_async()
        except Exception:
            ok = False
        if not ok:
            winapi.send_media_key(action)  # запасной путь: системная медиаклавиша
        await asyncio.sleep(0.35)
        await self._refresh()  # сразу обновить кнопку и название, не ждать секунду опроса
