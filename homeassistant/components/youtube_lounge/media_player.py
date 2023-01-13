"""Defines media player entity for youtube lounge integration."""

from __future__ import annotations

import asyncio
from asyncio import Task
import datetime as dt
import logging
from typing import TypedDict

from aiogoogle import Aiogoogle
from pyytlounge import PlaybackState, State as YtState, YtLoungeApi, get_thumbnail_url

import homeassistant
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the media player entity for the given configuration."""
    api: YtLoungeApi = hass.data[DOMAIN][entry.entry_id]

    api_key: str | None = entry.data.get("google_api_key")
    async_add_entities([YtMediaPlayer(api, api_key)])


class _VideoSnippet(TypedDict):
    """Data schema as it comes from API."""

    title: str
    description: str
    channelTitle: str


class _VideoInfo:
    """Class to store video info from YouTube Data API."""

    id: str
    title: str
    description: str
    channel_title: str

    def __init__(self, video_id: str, snippet: _VideoSnippet) -> None:
        self.id = video_id
        self.title = snippet["title"]
        self.description = snippet["description"]
        self.channel_title = snippet["channelTitle"]


class YtMediaPlayer(MediaPlayerEntity):
    """Media player entity for YouTube Lounge integration."""

    def __init__(self, api: YtLoungeApi, api_key: str | None) -> None:
        """Initialize media player entity with api and optional api key."""
        self._api = api
        self._google_api_key = api_key
        self._yt_api = None

        if self._google_api_key:
            asyncio.create_task(self.__setup_youtube_api())

        self._state_time = homeassistant.util.dt.utcnow()
        self._state = PlaybackState()
        self._video_info: _VideoInfo | None = None
        self._subscription: Task | None = None

    async def __setup_youtube_api(self):
        async with Aiogoogle(api_key=self._google_api_key) as aiogoogle:
            self._yt_api = await aiogoogle.discover("youtube", "v3")
        if self._state.videoId:
            await self.__update_video_snippet()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect and subscribe to dispatcher signals and state updates."""
        await super().async_added_to_hass()

        self._subscription = asyncio.create_task(self._api.subscribe(self.__new_state))

        self.async_on_remove(self.__removed_from_hass)

    def __removed_from_hass(self) -> None:
        if self._subscription:
            self._subscription.cancel()

    async def __update_video_snippet(self):
        if self._yt_api and self._state.videoId:
            if self._video_info and self._state.videoId == self._video_info.id:
                return  # already have this video info

            async with Aiogoogle(api_key=self._google_api_key) as aiogoogle:
                request = self._yt_api.videos.list(
                    part="snippet", id=self._state.videoId
                )
                response = await aiogoogle.as_api_key(request)
                snippet = response["items"][0]["snippet"]
                self._video_info = _VideoInfo(self._state.videoId, snippet)
        else:
            self._video_info = None

    async def __new_state(self, state: PlaybackState):
        self._state_time = homeassistant.util.dt.utcnow()
        self._state = state
        await self.__update_video_snippet()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._api.auth.screen_id

    @property
    def has_entity_name(self) -> bool:
        """Return if the name of the entity is describing only the entity itself."""
        return True

    @property
    def state(self) -> MediaPlayerState:
        """State of the player."""
        if self._state.state in [YtState.Playing, YtState.Starting, YtState.Buffering]:
            return MediaPlayerState.PLAYING
        if self._state.state == YtState.Paused:
            return MediaPlayerState.PAUSED
        if self._state.state == YtState.Stopped:
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        return (
            MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.SEEK
        )

    @property
    def device_class(self) -> MediaPlayerDeviceClass | None:
        """Return the class of this entity."""
        return MediaPlayerDeviceClass.TV

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._api.auth.screen_id)},
            manufacturer="YouTube",
            name=self._api.screen_name,
        )

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self._video_info and self._video_info.title or ""

    @property
    def media_channel(self) -> str | None:
        """Channel currently playing."""
        return self._video_info and self._video_info.channel_title or ""

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        return int(self._state.currentTime)

    @property
    def media_position_updated_at(self) -> dt.datetime | None:
        """When was the position of the current playing media valid.

        Returns value from homeassistant.util.dt.utcnow().
        """
        return self._state_time

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return int(self._state.duration)

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        if self._state.videoId:
            return get_thumbnail_url(self._state.videoId)

        return None

    async def async_media_pause(self) -> None:
        """Send pause command."""
        return await self._api.pause()

    async def async_media_play(self) -> None:
        """Send play command."""
        return await self._api.play()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        return await self._api.previous()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        return await self._api.next()

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        return await self._api.seek_to(position)
