import asyncio
import copy
import json
import logging
import math
import os
import random
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlsplit

import discord
from discord.ext import commands
import wavelink


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_PATH = "database/music.json"

log = logging.getLogger(__name__)


def _env_list(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


def _expand(values: list[str], count: int, name: str) -> list[str]:
    if len(values) == 1:
        return values * count
    if len(values) != count:
        raise RuntimeError(
            f"{name} must contain either one value or {count} comma-separated values"
        )
    return values


def lavalink_configs() -> list[tuple[str, str, str]]:
    hosts = _env_list("LAVALINK_HOSTS")
    if not hosts:
        raise RuntimeError("LAVALINK_HOSTS must be set in .env")

    ports = _expand(_env_list("LAVALINK_PORTS"), len(hosts), "LAVALINK_PORTS")
    passwords = _expand(
        _env_list("LAVALINK_PASSWORDS"),
        len(hosts),
        "LAVALINK_PASSWORDS",
    )
    secures = _expand(
        _env_list("LAVALINK_SECURES") or ["false"],
        len(hosts),
        "LAVALINK_SECURES",
    )

    configs = []
    for index, (host, port_text, password, secure_text) in enumerate(
        zip(hosts, ports, passwords, secures),
        start=1,
    ):
        try:
            port = int(port_text)
        except ValueError as error:
            raise RuntimeError(f"Invalid Lavalink port: {port_text}") from error
        if not 1 <= port <= 65535:
            raise RuntimeError(f"Invalid Lavalink port: {port}")

        secure_value = secure_text.lower()
        if secure_value not in {"true", "false"}:
            raise RuntimeError("LAVALINK_SECURES values must be true or false")

        # Hosts are expected without a protocol, but accepting one makes the
        # configuration tolerant of values copied from hosting dashboards.
        parsed_host = urlsplit(host if "://" in host else f"//{host}")
        clean_host = parsed_host.hostname
        if not clean_host:
            raise RuntimeError(f"Invalid Lavalink host: {host}")
        if ":" in clean_host:
            clean_host = f"[{clean_host}]"
        scheme = "https" if secure_value == "true" else "http"
        identifier = f"main-{index}"
        configs.append((identifier, f"{scheme}://{clean_host}:{port}", password))

    return configs

ACCENT = discord.Color.from_rgb(198, 145, 73)
SUCCESS = discord.Color.from_rgb(70, 190, 120)
ERROR = discord.Color.from_rgb(220, 75, 75)
WARNING = discord.Color.from_rgb(235, 175, 65)

DEFAULT_VOLUME = 70
MAX_VOLUME = 150
SEARCH_RESULTS = 10
QUEUE_PAGE_SIZE = 8
MAX_PLAYLISTS = 25
MAX_PLAYLIST_TRACKS = 200
PLAYER_UPDATE_SECONDS = 10
MUSIC_BUILD = "custom-emojis-v4"

DEFAULT_ARTWORK = (
    "https://cdn.discordapp.com/embed/avatars/0.png"
)


# =========================================================
# CUSTOM EMOJIS
# =========================================================
# Accepted values:
#   123456789012345678
#   "123456789012345678"
#   "<:emoji_name:123456789012345678>"
#   "<a:animated_name:123456789012345678>"
#
# Leave a value as None to use the Unicode fallback.
# The bot must share a server with each custom emoji.

CUSTOM_EMOJIS = {
    # General
    "music": '<:music:1527041142544142426>',
    "success": '<:circlecheck:1527050613379043478>',
    "error": '<:circlex:1527045249598492944>',
    "search": '<:search:1527044316965372134>',
    "song": '<:music:1527041142544142426>',

    # Main player controls
    "previous": '<:stepback:1527081537043042474>',
    "back_10": '<:rewind:1527081801682649268>',
    "pause_resume": '<:pause:1527082136161616024>',
    "forward_10": '<:fastforward:1527081983732224102>',
    "skip": '<:stepforward:1527081240350425139>',
    "stop": '<:square:1527082255900606534>',
    "volume": '<:volume2:1527082370207973498>',
    "loop": '<:repeat:1527082512994533476>',
    "replay": '<:rotateccw:1527082632314224790>',
    "favorite": '<:heartplus:1527082742477623557>',
    "queue": '<:logs:1527082846861398216>',
    "autoplay": '<:bot:1527043822104875208>',
    "shuffle": '<:shuffle:1527083245055770817>',
    "filters": '<:slidershorizontal:1527083360856313896>',
    "playlists": '<:folderopen:1527044004020092958>',
    "history": '<:list:1527044575158341732>',
    "refresh": '<:refreshcw:1527083602502746264>',
    "disconnect": '<:unplug:1527083816588414986>',

    # Queue controls
    "page_previous": None,
    "page_next": None,
    "clear": None,
    "close": None,

    # Filter presets
    "bass_boost": None,
    "nightcore": None,
    "vaporwave": None,
    "eight_d": None,
    "karaoke": None,
    "tremolo": None,
    "vibrato": None,
    "reset": None,

    # Playlist controls
    "create": '<:plus:1527051178662432768>',
    "add_current": '<:heartplus:1527082742477623557>',
    "play": '<:play:1527084172907118643>',
    "shuffle_play": '<:diamond:1527084401677308027>',
    "delete": '<:trash:1527084534527688806>',
    "playlist_folder": '<:folder:1527033394372939798>',
}

EMOJI_FALLBACKS = {
    # General
    "music": "🎵",
    "success": "✅",
    "error": "❌",
    "search": "🔎",
    "song": "🎶",

    # Main player controls
    "previous": "⏮",
    "back_10": "⏪",
    "pause_resume": "⏯",
    "forward_10": "⏩",
    "skip": "⏭",
    "stop": "⏹",
    "volume": "🔊",
    "loop": "🔁",
    "replay": "🔄",
    "favorite": "❤️",
    "queue": "📃",
    "autoplay": "🤖",
    "shuffle": "🔀",
    "filters": "🎚️",
    "playlists": "📂",
    "history": "📜",
    "refresh": "🔃",
    "disconnect": "🔌",

    # Queue controls
    "page_previous": "◀️",
    "page_next": "▶️",
    "clear": "🧹",
    "close": "✖️",

    # Filter presets
    "bass_boost": "🔊",
    "nightcore": "⚡",
    "vaporwave": "🌊",
    "eight_d": "🎧",
    "karaoke": "🎤",
    "tremolo": "〰️",
    "vibrato": "🎶",
    "reset": "♻️",

    # Playlist controls
    "create": "➕",
    "add_current": "❤️",
    "play": "▶️",
    "shuffle_play": "🔀",
    "delete": "🗑️",
    "playlist_folder": "📂",
}


def get_custom_emoji(
    bot: Optional[commands.Bot],
    key: str,
) -> Optional[discord.Emoji | discord.PartialEmoji]:
    """Return only a valid custom emoji object, never a Unicode string."""
    configured = CUSTOM_EMOJIS.get(key)

    if not configured:
        return None

    if isinstance(
        configured,
        (discord.Emoji, discord.PartialEmoji),
    ):
        return configured

    if isinstance(configured, int) or str(configured).isdigit():
        emoji_id = int(configured)
        cached = bot.get_emoji(emoji_id) if bot else None

        if cached:
            return cached

        # Numeric IDs alone have no name. Use a safe placeholder name.
        return discord.PartialEmoji(
            name="monk",
            id=emoji_id,
        )

    if isinstance(configured, str):
        try:
            partial = discord.PartialEmoji.from_str(
                configured.strip()
            )

            if partial.id and partial.name:
                return (bot.get_emoji(partial.id) if bot else None) or partial

        except (TypeError, ValueError):
            return None

    return None


def emoji_text(
    bot: Optional[commands.Bot],
    key: str,
) -> str:
    custom = get_custom_emoji(bot, key)

    if custom:
        return str(custom)

    return EMOJI_FALLBACKS.get(key, "•")


def button_parts(
    bot: commands.Bot,
    key: str,
    text: str,
) -> tuple[str, Optional[discord.Emoji | discord.PartialEmoji]]:
    """
    Custom emoji configured:
        Discord emoji field + clean text label.

    No custom emoji:
        Unicode fallback inside label + no emoji field.

    This prevents Invalid Form Body errors from risky Unicode button emojis.
    """
    custom = get_custom_emoji(bot, key)

    if custom:
        return text, custom

    fallback = EMOJI_FALLBACKS.get(key)

    if fallback:
        return f"{fallback} {text}", None

    return text, None


# =========================================================
# DATABASE
# =========================================================

DEFAULT_DATA: dict[str, Any] = {
    "users": {},
    "guilds": {},
}


class MusicDatabase:
    def __init__(self, path: str):
        self.path = path
        self.lock = asyncio.Lock()

        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(path):
            self._save(copy.deepcopy(DEFAULT_DATA))

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError

            data.setdefault("users", {})
            data.setdefault("guilds", {})
            return data

        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = copy.deepcopy(DEFAULT_DATA)
            self._save(data)
            return data

    def _save(self, data: dict[str, Any]) -> None:
        temporary = f"{self.path}.tmp"

        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

        os.replace(temporary, self.path)

    async def get_user(self, user_id: int) -> dict[str, Any]:
        async with self.lock:
            data = self._load()

            user = data["users"].setdefault(
                str(user_id),
                {
                    "favorites": [],
                    "playlists": {},
                    "tracks_requested": 0,
                },
            )

            self._save(data)
            return copy.deepcopy(user)

    async def save_user(
        self,
        user_id: int,
        user_data: dict[str, Any],
    ) -> None:
        async with self.lock:
            data = self._load()
            data["users"][str(user_id)] = user_data
            self._save(data)

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self.lock:
            data = self._load()

            default_guild = {
                "volume": DEFAULT_VOLUME,
                "autoplay": True,
                "player_channel_id": None,
                "player_message_id": None,
                "history": [],
                "tracks_played": 0,
            }

            guild = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(default_guild),
            )

            # Automatically migrate old music.json guild entries.
            changed = False

            for key, value in default_guild.items():
                if key not in guild:
                    guild[key] = copy.deepcopy(value)
                    changed = True

            if changed:
                self._save(data)

            return copy.deepcopy(guild)

    async def save_guild(
        self,
        guild_id: int,
        guild_data: dict[str, Any],
    ) -> None:
        async with self.lock:
            data = self._load()
            data["guilds"][str(guild_id)] = guild_data
            self._save(data)


music_db = MusicDatabase(DATABASE_PATH)


# =========================================================
# HELPERS
# =========================================================

def format_time(milliseconds: int) -> str:
    total_seconds = max(0, int(milliseconds // 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


def progress_bar(
    position: int,
    total: int,
    size: int = 17,
) -> str:
    if total <= 0:
        return "━" * size

    ratio = min(1, max(0, position / total))
    point = min(size - 1, round(ratio * (size - 1)))

    return (
        "━" * point
        + "●"
        + "━" * (size - point - 1)
    )


def track_to_data(
    track: wavelink.Playable,
) -> dict[str, Any]:
    return {
        "title": track.title,
        "author": track.author,
        "uri": track.uri,
        "length": track.length,
        "source": track.source,
        "artwork": getattr(track, "artwork", None),
    }


def get_extra(
    track: wavelink.Playable,
    name: str,
    default: Any = None,
) -> Any:
    extras = getattr(track, "extras", None)

    if extras is None:
        return default

    if isinstance(extras, dict):
        return extras.get(name, default)

    return getattr(extras, name, default)


def artwork_for(
    track: Optional[wavelink.Playable],
) -> str:
    if not track:
        return DEFAULT_ARTWORK

    artwork = getattr(track, "artwork", None)

    if artwork:
        return artwork

    identifier = getattr(track, "identifier", None)
    source = str(getattr(track, "source", "")).lower()

    if identifier and "youtube" in source:
        return f"https://img.youtube.com/vi/{identifier}/maxresdefault.jpg"

    return DEFAULT_ARTWORK


def is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


def playlist_name(value: str) -> str:
    return " ".join(value.strip().split())[:40]


# =========================================================
# SIMPLE RESPONSES
# =========================================================

class MusicResponse(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        success: bool = True,
        warning: bool = False,
        bot: Optional[commands.Bot] = None,
    ):
        super().__init__(timeout=60)
        self._bot = bot

        colour = (
            WARNING
            if warning
            else SUCCESS if success else ERROR
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {emoji_text(self._bot, 'music' if success else 'error')} {title}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=colour,
            )
        )


# =========================================================
# BASE INTERACTION VIEW
# =========================================================

class MusicInteractionView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "Music",
        *,
        timeout: Optional[float] = 300,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog

    async def get_player(
        self,
        interaction: discord.Interaction,
    ) -> Optional[wavelink.Player]:
        if not interaction.guild:
            return None

        player = interaction.guild.voice_client

        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message(
                view=MusicResponse(
                    "No Active Player",
                    "Monk is not connected to a voice channel.",
                    success=False,
                ),
                ephemeral=True,
            )
            return None

        member = interaction.user

        if (
            not isinstance(member, discord.Member)
            or not member.voice
            or member.voice.channel != player.channel
        ):
            await interaction.response.send_message(
                view=MusicResponse(
                    "Join Monk's Voice Channel",
                    "You must be in the same voice channel to use this control.",
                    success=False,
                ),
                ephemeral=True,
            )
            return None

        return player


# =========================================================
# SEARCH RESULTS
# =========================================================

class SearchSelect(discord.ui.Select):
    def __init__(
        self,
        cog: "Music",
        author_id: int,
        tracks: list[wavelink.Playable],
    ):
        self.cog = cog
        self.author_id = author_id
        self.tracks = tracks

        options = [
            discord.SelectOption(
                label=track.title[:100],
                value=str(index),
                description=(
                    f"{track.author} • "
                    f"{format_time(track.length)}"
                )[:100],
            )
            for index, track in enumerate(
                tracks[:SEARCH_RESULTS]
            )
        ]

        super().__init__(
            placeholder="Choose a song",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                view=MusicResponse(
                    "Not Your Search",
                    "Run the play command yourself.",
                    success=False,
                ),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        player = await self.cog.ensure_player_interaction(
            interaction
        )

        if not player:
            return

        track = self.tracks[int(self.values[0])]

        await self.cog.enqueue(
            player,
            track,
            interaction.user,
            interaction.channel,
        )

        await self.cog.move_player_message(
            interaction.guild,
            interaction.channel,
        )

        await interaction.followup.send(
            view=MusicResponse(
                "Song Added",
                f"**{track.title}** was added.",
            ),
            ephemeral=True,
        )

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass


class SearchResultsView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "Music",
        author_id: int,
        tracks: list[wavelink.Playable],
    ):
        super().__init__(timeout=120)

        container = discord.ui.Container(
            accent_colour=ACCENT
        )

        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(cog.bot, 'search')} Search Results"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose the exact song you want to play."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(
            SearchSelect(
                cog,
                author_id,
                tracks,
            )
        )

        container.add_item(row)
        self.add_item(container)


# =========================================================
# QUEUE
# =========================================================

class QueueView(MusicInteractionView):
    def __init__(
        self,
        cog: "Music",
        player: wavelink.Player,
    ):
        super().__init__(cog, timeout=300)

        self.player = player
        self.page = 0
        self.build()

    @property
    def tracks(self) -> list[wavelink.Playable]:
        return list(self.player.queue)

    @property
    def max_page(self) -> int:
        if not self.tracks:
            return 0

        return max(
            0,
            math.ceil(
                len(self.tracks) / QUEUE_PAGE_SIZE
            ) - 1,
        )

    def build(self):
        self.clear_items()

        tracks = self.tracks

        container = discord.ui.Container(
            accent_colour=ACCENT
        )

        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(cog.bot, 'queue')} Queue"
            )
        )
        container.add_item(discord.ui.Separator())

        if tracks:
            start = self.page * QUEUE_PAGE_SIZE
            page_tracks = tracks[
                start:start + QUEUE_PAGE_SIZE
            ]

            lines = []

            for index, track in enumerate(
                page_tracks,
                start=start + 1,
            ):
                requester = get_extra(
                    track,
                    "requester_id",
                )

                lines.append(
                    f"`{index}.` **{track.title}**\n"
                    f"{track.author} • "
                    f"`{format_time(track.length)}` • "
                    f"{f'<@{requester}>' if requester else 'Unknown'}"
                )

            container.add_item(
                discord.ui.TextDisplay(
                    "\n\n".join(lines)
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    "The queue is empty."
                )
            )

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"Page `{self.page + 1}/{self.max_page + 1}` • "
                f"Tracks `{len(tracks)}`"
            )
        )

        row = discord.ui.ActionRow()

        controls = [
            (
                "◀ Previous",
                "◀️",
                self.previous_page,
                self.page <= 0,
            ),
            (
                "▶ Next",
                "▶️",
                self.next_page,
                self.page >= self.max_page,
            ),
            (
                "🔀 Shuffle",
                "🔀",
                self.shuffle,
                not tracks,
            ),
            (
                "🧹 Clear",
                "🧹",
                self.clear_queue,
                not tracks,
            ),
            (
                "✖ Close",
                "✖️",
                self.close,
                False,
            ),
        ]

        for label, emoji, callback, disabled in controls:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                disabled=disabled,
            )

            button.callback = callback
            row.add_item(button)

        container.add_item(row)
        self.add_item(container)

    async def previous_page(
        self,
        interaction: discord.Interaction,
    ):
        self.page = max(0, self.page - 1)
        self.build()
        await interaction.response.edit_message(
            view=self
        )

    async def next_page(
        self,
        interaction: discord.Interaction,
    ):
        self.page = min(
            self.max_page,
            self.page + 1,
        )
        self.build()
        await interaction.response.edit_message(
            view=self
        )

    async def shuffle(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.queue.shuffle()
        self.build()

        await interaction.response.edit_message(
            view=self
        )

        await self.cog.update_player_message(
            interaction.guild
        )

    async def clear_queue(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.queue.clear()
        self.page = 0
        self.build()

        await interaction.response.edit_message(
            view=self
        )

        await self.cog.update_player_message(
            interaction.guild
        )

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(
            view=None
        )
        self.stop()


# =========================================================
# FILTERS
# =========================================================

class FiltersView(MusicInteractionView):
    def __init__(
        self,
        cog: "Music",
    ):
        super().__init__(cog, timeout=300)

        container = discord.ui.Container(
            accent_colour=ACCENT
        )

        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(cog.bot, 'filters')} Audio Filters"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose a filter preset."
            )
        )

        rows = [
            discord.ui.ActionRow(),
            discord.ui.ActionRow(),
        ]

        presets = [
            ("bass_boost", "Bass Boost", self.bass_boost),
            ("nightcore", "Nightcore", self.nightcore),
            ("vaporwave", "Vaporwave", self.vaporwave),
            ("eight_d", "8D", self.eight_d),
            ("karaoke", "Karaoke", self.karaoke),
            ("tremolo", "Tremolo", self.tremolo),
            ("vibrato", "Vibrato", self.vibrato),
            ("reset", "Reset", self.reset_filters),
        ]

        for index, (
            emoji_key,
            label_text,
            callback,
        ) in enumerate(presets):
            label, custom_emoji = button_parts(
                self.cog.bot,
                emoji_key,
                label_text,
            )

            button = discord.ui.Button(
                label=label,
                emoji=custom_emoji,
                style=discord.ButtonStyle.secondary,
            )

            button.callback = callback

            rows[0 if index < 4 else 1].add_item(
                button
            )

        container.add_item(rows[0])
        container.add_item(rows[1])

        self.add_item(container)

    async def apply(
        self,
        interaction: discord.Interaction,
        name: str,
        builder,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        filters = wavelink.Filters()
        builder(filters)

        await player.set_filters(
            filters,
            seek=True,
        )

        await interaction.response.send_message(
            view=MusicResponse(
                "Filter Applied",
                f"Applied **{name}**.",
            ),
            ephemeral=True,
        )

    async def bass_boost(self, interaction):
        await self.apply(
            interaction,
            "Bass Boost",
            lambda filters: filters.equalizer.set(
                bands=[
                    {"band": 0, "gain": 0.25},
                    {"band": 1, "gain": 0.20},
                    {"band": 2, "gain": 0.15},
                    {"band": 3, "gain": 0.10},
                ]
            ),
        )

    async def nightcore(self, interaction):
        await self.apply(
            interaction,
            "Nightcore",
            lambda filters: filters.timescale.set(
                speed=1.18,
                pitch=1.18,
                rate=1.0,
            ),
        )

    async def vaporwave(self, interaction):
        await self.apply(
            interaction,
            "Vaporwave",
            lambda filters: filters.timescale.set(
                speed=0.85,
                pitch=0.80,
                rate=1.0,
            ),
        )

    async def eight_d(self, interaction):
        await self.apply(
            interaction,
            "8D Rotation",
            lambda filters: filters.rotation.set(
                rotation_hz=0.2
            ),
        )

    async def karaoke(self, interaction):
        await self.apply(
            interaction,
            "Karaoke",
            lambda filters: filters.karaoke.set(
                level=1.0,
                mono_level=1.0,
                filter_band=220.0,
                filter_width=100.0,
            ),
        )

    async def tremolo(self, interaction):
        await self.apply(
            interaction,
            "Tremolo",
            lambda filters: filters.tremolo.set(
                frequency=4.0,
                depth=0.75,
            ),
        )

    async def vibrato(self, interaction):
        await self.apply(
            interaction,
            "Vibrato",
            lambda filters: filters.vibrato.set(
                frequency=4.0,
                depth=0.75,
            ),
        )

    async def reset_filters(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        await player.set_filters()

        await interaction.response.send_message(
            view=MusicResponse(
                "Filters Reset",
                "All audio filters were removed.",
            ),
            ephemeral=True,
        )


# =========================================================
# PLAYLISTS
# =========================================================

class CreatePlaylistModal(
    discord.ui.Modal,
    title="Create Private Playlist",
):
    name_input = discord.ui.TextInput(
        label="Playlist name",
        placeholder="Chill",
        required=True,
        max_length=40,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        name = playlist_name(
            self.name_input.value
        )

        user_data = await music_db.get_user(
            interaction.user.id
        )

        playlists = user_data["playlists"]

        if len(playlists) >= MAX_PLAYLISTS:
            return await interaction.response.send_message(
                view=MusicResponse(
                    "Playlist Limit Reached",
                    f"You can create up to "
                    f"`{MAX_PLAYLISTS}` playlists.",
                    success=False,
                ),
                ephemeral=True,
            )

        if name.lower() in {
            existing.lower()
            for existing in playlists
        }:
            return await interaction.response.send_message(
                view=MusicResponse(
                    "Playlist Already Exists",
                    f"**{name}** already exists.",
                    success=False,
                ),
                ephemeral=True,
            )

        playlists[name] = {
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "tracks": [],
        }

        await music_db.save_user(
            interaction.user.id,
            user_data,
        )

        await interaction.response.send_message(
            view=MusicResponse(
                "Playlist Created",
                f"Created private playlist **{name}**.",
            ),
            ephemeral=True,
        )


class PlaylistSelect(discord.ui.Select):
    def __init__(
        self,
        parent: "PlaylistsView",
        playlists: dict[str, Any],
    ):
        self.parent_view = parent

        options = [
            discord.SelectOption(
                label=name[:100],
                value=name,
                description=(
                    f"{len(data['tracks'])} tracks"
                ),
                default=name == parent.selected,
            )
            for name, data in list(
                playlists.items()
            )[:25]
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="No playlists",
                    value="__none__",
                    description="Create a playlist first",
                )
            ]

        super().__init__(
            placeholder="Choose a private playlist",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not bool(playlists),
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if self.values[0] == "__none__":
            return

        self.parent_view.selected = self.values[0]

        await self.parent_view.refresh()

        await interaction.response.edit_message(
            view=self.parent_view
        )


class PlaylistsView(MusicInteractionView):
    def __init__(
        self,
        cog: "Music",
        owner_id: int,
    ):
        super().__init__(cog, timeout=300)

        self.owner_id = owner_id
        self.user_data: dict[str, Any] = {}
        self.selected: Optional[str] = None

    async def prepare(self):
        self.user_data = await music_db.get_user(
            self.owner_id
        )

        if not self.selected:
            self.selected = next(
                iter(self.user_data["playlists"]),
                None,
            )

        self.build()

    async def refresh(self):
        self.user_data = await music_db.get_user(
            self.owner_id
        )

        if (
            self.selected
            not in self.user_data["playlists"]
        ):
            self.selected = next(
                iter(self.user_data["playlists"]),
                None,
            )

        self.build()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                view=MusicResponse(
                    "Private Playlist",
                    "This playlist manager belongs to another user.",
                    success=False,
                ),
                ephemeral=True,
            )
            return False

        return True

    def build(self):
        self.clear_items()

        playlists = self.user_data.get(
            "playlists",
            {},
        )

        container = discord.ui.Container(
            accent_colour=ACCENT
        )

        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(self.cog.bot, 'playlists')} Private Playlists"
            )
        )
        container.add_item(discord.ui.Separator())

        selected_data = (
            playlists.get(self.selected)
            if self.selected
            else None
        )

        if selected_data:
            lines = []

            for index, track in enumerate(
                selected_data["tracks"][:10],
                start=1,
            ):
                lines.append(
                    f"`{index}.` **{track['title']}**\n"
                    f"{track['author']} • "
                    f"`{format_time(track['length'])}`"
                )

            container.add_item(
                discord.ui.TextDisplay(
                    f"**Selected:** {self.selected}\n"
                    f"**Tracks:** "
                    f"`{len(selected_data['tracks'])}`\n\n"
                    + (
                        "\n\n".join(lines)
                        if lines
                        else "This playlist is empty."
                    )
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    "You have no private playlists."
                )
            )

        container.add_item(discord.ui.Separator())

        select_row = discord.ui.ActionRow()
        select_row.add_item(
            PlaylistSelect(
                self,
                playlists,
            )
        )
        container.add_item(select_row)

        row = discord.ui.ActionRow()

        actions = [
            ("create", "Create", self.create, False),
            ("add_current", "Add Current", self.add_current, not self.selected),
            ("play", "Play", self.play, not self.selected),
            ("shuffle_play", "Shuffle Play", self.shuffle_play, not self.selected),
            ("delete", "Delete", self.delete, not self.selected),
        ]

        for emoji_key, label_text, callback, disabled in actions:
            label, custom_emoji = button_parts(
                self.cog.bot,
                emoji_key,
                label_text,
            )

            button = discord.ui.Button(
                label=label,
                emoji=custom_emoji,
                style=discord.ButtonStyle.secondary,
                disabled=disabled,
            )

            button.callback = callback
            row.add_item(button)

        container.add_item(row)
        self.add_item(container)

    async def create(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(
            CreatePlaylistModal()
        )

    async def add_current(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player or not player.current:
            return

        user_data = await music_db.get_user(
            interaction.user.id
        )

        playlist = user_data["playlists"].get(
            self.selected
        )

        if not playlist:
            return

        if len(playlist["tracks"]) >= MAX_PLAYLIST_TRACKS:
            return await interaction.response.send_message(
                view=MusicResponse(
                    "Playlist Full",
                    f"A playlist can hold up to "
                    f"`{MAX_PLAYLIST_TRACKS}` tracks.",
                    success=False,
                ),
                ephemeral=True,
            )

        current = track_to_data(
            player.current
        )

        if any(
            saved["uri"] == current["uri"]
            for saved in playlist["tracks"]
        ):
            return await interaction.response.send_message(
                view=MusicResponse(
                    "Already Saved",
                    "That track is already in this playlist.",
                    success=False,
                ),
                ephemeral=True,
            )

        playlist["tracks"].append(current)

        await music_db.save_user(
            interaction.user.id,
            user_data,
        )

        await self.refresh()

        await interaction.response.edit_message(
            view=self
        )

    async def resolve_tracks(
        self,
        interaction: discord.Interaction,
    ) -> list[wavelink.Playable]:
        user_data = await music_db.get_user(
            interaction.user.id
        )

        playlist = user_data["playlists"].get(
            self.selected,
            {"tracks": []},
        )

        resolved = []

        for saved in playlist["tracks"]:
            try:
                result = await wavelink.Playable.search(
                    saved["uri"]
                )

                if isinstance(
                    result,
                    wavelink.Playlist,
                ):
                    resolved.extend(result.tracks)
                elif result:
                    resolved.append(result[0])

            except Exception:
                continue

        return resolved

    async def play_playlist(
        self,
        interaction: discord.Interaction,
        *,
        shuffled: bool,
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        player = await self.cog.ensure_player_interaction(
            interaction
        )

        if not player:
            return

        tracks = await self.resolve_tracks(
            interaction
        )

        if shuffled:
            random.shuffle(tracks)

        for track in tracks:
            track.extras = {
                "requester_id": interaction.user.id,
                "request_channel_id": interaction.channel.id,
            }

        if tracks:
            await player.queue.put_wait(tracks)

            if not player.playing:
                await player.play(
                    player.queue.get(),
                    volume=player.volume or DEFAULT_VOLUME,
                    populate=True,
                )

        await self.cog.move_player_message(
            interaction.guild,
            interaction.channel,
        )

        await interaction.followup.send(
            view=MusicResponse(
                "Playlist Queued",
                f"Added `{len(tracks)}` tracks.",
            ),
            ephemeral=True,
        )

    async def play(
        self,
        interaction: discord.Interaction,
    ):
        await self.play_playlist(
            interaction,
            shuffled=False,
        )

    async def shuffle_play(
        self,
        interaction: discord.Interaction,
    ):
        await self.play_playlist(
            interaction,
            shuffled=True,
        )

    async def delete(
        self,
        interaction: discord.Interaction,
    ):
        user_data = await music_db.get_user(
            interaction.user.id
        )

        user_data["playlists"].pop(
            self.selected,
            None,
        )

        await music_db.save_user(
            interaction.user.id,
            user_data,
        )

        self.selected = None
        await self.refresh()

        await interaction.response.edit_message(
            view=self
        )


# =========================================================
# PLAYER PANEL
# =========================================================

class PlayerPanel(MusicInteractionView):
    def __init__(
        self,
        cog: "Music",
        guild_id: int,
    ):
        super().__init__(cog, timeout=None)
        self.guild_id = guild_id
        self.build()

    def current_player(
        self,
    ) -> Optional[wavelink.Player]:
        guild = self.cog.bot.get_guild(
            self.guild_id
        )

        if not guild:
            return None

        player = guild.voice_client

        return (
            player
            if isinstance(player, wavelink.Player)
            else None
        )

    def build(self):
        self.clear_items()

        player = self.current_player()
        current = player.current if player else None

        container = discord.ui.Container(
            accent_colour=ACCENT
        )

        if current:
            artwork = artwork_for(current)

            try:
                container.add_item(
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            artwork,
                            description=current.title[:256],
                        )
                    )
                )
                container.add_item(
                    discord.ui.Separator()
                )
            except Exception:
                pass

            requester = get_extra(
                current,
                "requester_id",
            )

            status = (
                "Paused"
                if player.paused
                else "Playing"
            )

            details = (
                f"## {emoji_text(self.cog.bot, 'music')} Now Playing....\n"
                f"**[{current.title}]({current.uri})**\n\n"
                f"Autoplay: **"
                f"{'Enabled' if player.autoplay != wavelink.AutoPlayMode.disabled else 'Disabled'}"
                f"**\n"
                f"Loop: **{player.queue.mode.name}**\n"
                f"Status: **{status}**\n"
                f"Duration: "
                f"`{format_time(player.position)} / "
                f"{format_time(current.length)}`\n"
                f"Source: **{current.source}**\n"
                f"Requester: "
                f"{f'<@{requester}>' if requester else 'Unknown'}\n\n"
                f"`{format_time(player.position)}` "
                f"{progress_bar(player.position, current.length)} "
                f"`{format_time(current.length)}`"
            )

            container.add_item(
                discord.ui.TextDisplay(details)
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    f"## {emoji_text(self.cog.bot, 'music')} Monk Music Player\n"
                    "Nothing is currently playing."
                )
            )

        container.add_item(discord.ui.Separator())

        row_one = discord.ui.ActionRow()
        row_two = discord.ui.ActionRow()
        row_three = discord.ui.ActionRow()
        row_four = discord.ui.ActionRow()

        controls = [
            (row_one, "previous", "Previous", self.previous),
            (row_one, "back_10", "Back 10s", self.back_ten),
            (row_one, "pause_resume", "Pause / Resume", self.pause_resume),
            (row_one, "forward_10", "Forward 10s", self.forward_ten),
            (row_one, "skip", "Skip", self.skip),

            (row_two, "stop", "Stop", self.stop),
            (row_two, "volume", "Volume", self.volume_cycle),
            (row_two, "loop", "Loop", self.loop),
            (row_two, "replay", "Replay", self.replay),
            (row_two, "favorite", "Favorite", self.favorite),

            (row_three, "queue", "Queue", self.queue),
            (row_three, "autoplay", "Autoplay", self.autoplay),
            (row_three, "shuffle", "Shuffle", self.shuffle),
            (row_three, "filters", "Filters", self.filters),
            (row_three, "playlists", "Playlists", self.playlists),

            (row_four, "history", "History", self.history),
            (row_four, "refresh", "Refresh", self.refresh),
            (row_four, "disconnect", "Disconnect", self.disconnect),
        ]

        for row, emoji_key, label_text, callback in controls:
            label, custom_emoji = button_parts(
                self.cog.bot,
                emoji_key,
                label_text,
            )

            button = discord.ui.Button(
                emoji=custom_emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=(
                    f"monk_music:{self.guild_id}:{emoji_key}"
                ),
            )

            button.callback = callback
            row.add_item(button)

        container.add_item(row_one)
        container.add_item(row_two)
        container.add_item(row_three)
        container.add_item(row_four)

        self.add_item(container)

    async def refresh_panel(
        self,
        interaction: discord.Interaction,
    ):
        self.build()

        await interaction.response.edit_message(
            view=self
        )

    async def previous(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        try:
            previous_track = player.queue.history.get()
        except Exception:
            return await interaction.response.send_message(
                view=MusicResponse(
                    "No Previous Track",
                    "There is no track in history.",
                    success=False,
                ),
                ephemeral=True,
            )

        if player.current:
            await player.queue.put_at(
                0,
                player.current,
            )

        await player.play(
            previous_track,
            populate=True,
        )

        await asyncio.sleep(0.3)
        await self.refresh_panel(interaction)

    async def back_ten(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player or not player.current:
            return

        await player.seek(
            max(0, player.position - 10_000)
        )

        await self.refresh_panel(interaction)

    async def pause_resume(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        await player.pause(
            not player.paused
        )

        await self.refresh_panel(interaction)

    async def forward_ten(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player or not player.current:
            return

        maximum = max(
            0,
            player.current.length - 1000,
        )

        await player.seek(
            min(
                maximum,
                player.position + 10_000,
            )
        )

        await self.refresh_panel(interaction)

    async def skip(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        await player.skip(force=True)

        await asyncio.sleep(0.5)
        await self.refresh_panel(interaction)

    async def stop(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.queue.clear()
        await player.stop()

        await asyncio.sleep(0.2)
        await self.refresh_panel(interaction)

    async def volume_cycle(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        levels = [
            30,
            50,
            70,
            100,
            120,
            150,
        ]

        next_volume = next(
            (
                level
                for level in levels
                if level > player.volume
            ),
            30,
        )

        await player.set_volume(
            next_volume
        )

        guild_data = await music_db.get_guild(
            interaction.guild.id
        )
        guild_data["volume"] = next_volume
        await music_db.save_guild(
            interaction.guild.id,
            guild_data,
        )

        await interaction.response.send_message(
            view=MusicResponse(
                "Volume Updated",
                f"Volume is now `{next_volume}%`.",
            ),
            ephemeral=True,
        )

        await self.cog.update_player_message(
            interaction.guild
        )

    async def loop(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        modes = [
            wavelink.QueueMode.normal,
            wavelink.QueueMode.loop,
            wavelink.QueueMode.loop_all,
        ]

        player.queue.mode = modes[
            (
                modes.index(player.queue.mode)
                + 1
            )
            % len(modes)
        ]

        await self.refresh_panel(interaction)

    async def replay(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player or not player.current:
            return

        await player.seek(0)
        await self.refresh_panel(interaction)

    async def favorite(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player or not player.current:
            return

        user_data = await music_db.get_user(
            interaction.user.id
        )

        current = track_to_data(
            player.current
        )

        favorites = user_data["favorites"]

        if any(
            item["uri"] == current["uri"]
            for item in favorites
        ):
            favorites[:] = [
                item
                for item in favorites
                if item["uri"] != current["uri"]
            ]
            action = "Removed from"
        else:
            favorites.append(current)
            action = "Added to"

        await music_db.save_user(
            interaction.user.id,
            user_data,
        )

        await interaction.response.send_message(
            view=MusicResponse(
                "Favorites Updated",
                f"{action} favorites: "
                f"**{current['title']}**",
            ),
            ephemeral=True,
        )

    async def queue(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        await interaction.response.send_message(
            view=QueueView(
                self.cog,
                player,
            ),
            ephemeral=True,
        )

    async def autoplay(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.autoplay = (
            wavelink.AutoPlayMode.disabled
            if player.autoplay
            != wavelink.AutoPlayMode.disabled
            else wavelink.AutoPlayMode.enabled
        )

        guild_data = await music_db.get_guild(
            interaction.guild.id
        )
        guild_data["autoplay"] = (
            player.autoplay
            != wavelink.AutoPlayMode.disabled
        )
        await music_db.save_guild(
            interaction.guild.id,
            guild_data,
        )

        await self.refresh_panel(interaction)

    async def shuffle(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.queue.shuffle()

        await interaction.response.send_message(
            view=MusicResponse(
                "Queue Shuffled",
                "The queue order was randomized.",
            ),
            ephemeral=True,
        )

    async def filters(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=FiltersView(self.cog),
            ephemeral=True,
        )

    async def playlists(
        self,
        interaction: discord.Interaction,
    ):
        view = PlaylistsView(
            self.cog,
            interaction.user.id,
        )
        await view.prepare()

        await interaction.response.send_message(
            view=view,
            ephemeral=True,
        )

    async def history(
        self,
        interaction: discord.Interaction,
    ):
        guild_data = await music_db.get_guild(
            interaction.guild.id
        )

        history = guild_data["history"][-10:]

        if not history:
            description = "No tracks have been played yet."
        else:
            lines = []

            for index, track in enumerate(
                reversed(history),
                start=1,
            ):
                lines.append(
                    f"`{index}.` **{track['title']}**\n"
                    f"{track['author']} • "
                    f"`{format_time(track['length'])}`"
                )

            description = "\n\n".join(lines)

        await interaction.response.send_message(
            view=MusicResponse(
                "Recent History",
                description,
            ),
            ephemeral=True,
        )

    async def refresh(
        self,
        interaction: discord.Interaction,
    ):
        await self.refresh_panel(interaction)

    async def disconnect(
        self,
        interaction: discord.Interaction,
    ):
        player = await self.get_player(interaction)

        if not player:
            return

        player.queue.clear()
        await player.disconnect()

        await interaction.response.edit_message(
            view=MusicResponse(
                "Disconnected",
                "Monk left the voice channel.",
            )
        )


# =========================================================
# MUSIC COG
# =========================================================

class Music(commands.Cog):
    """
    Premium Components V2 music player.

    One player message per guild.
    The message stays in the channel where mplay was used.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.node_tasks: list[asyncio.Task] = []
        self.panel_updater: Optional[asyncio.Task] = None

    async def cog_load(self):
        configs = lavalink_configs()
        self.node_tasks = [
            asyncio.create_task(
                self.connect_node(identifier, uri, password),
                name=f"monk-lavalink-{identifier}",
            )
            for identifier, uri, password in configs
        ]
        self.panel_updater = asyncio.create_task(
            self.player_update_loop(),
            name="monk-player-panel-updater",
        )

    def cog_unload(self):
        for task in (
            *self.node_tasks,
            self.panel_updater,
        ):
            if task and not task.done():
                task.cancel()

    async def connect_node(self, identifier: str, uri: str, password: str):
        await self.bot.wait_until_ready()

        retry_delay = 5
        while not self.bot.is_closed():
            try:
                node = wavelink.Node(
                    identifier=identifier,
                    uri=uri,
                    password=password,
                )

                nodes = await wavelink.Pool.connect(
                    nodes=[node],
                    client=self.bot,
                    cache_capacity=500,
                )
                if identifier not in nodes:
                    raise ConnectionError(
                        "Lavalink rejected the connection; check the URI and password"
                    )

                log.info(
                    "Music connected to Lavalink node %s (%s)",
                    identifier,
                    MUSIC_BUILD,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception(
                    "Lavalink connection failed; retrying in %s seconds",
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    @staticmethod
    def lavalink_ready() -> bool:
        return any(
            node.status is wavelink.NodeStatus.CONNECTED
            for node in wavelink.Pool.nodes.values()
        )

    async def player_update_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            await asyncio.sleep(
                PLAYER_UPDATE_SECONDS
            )

            for guild in self.bot.guilds:
                player = guild.voice_client

                if (
                    isinstance(player, wavelink.Player)
                    and player.current
                ):
                    try:
                        await self.update_player_message(
                            guild
                        )
                    except Exception:
                        pass

    async def ensure_player(
        self,
        ctx: commands.Context,
    ) -> Optional[wavelink.Player]:
        if not self.lavalink_ready():
            await ctx.send(
                view=MusicResponse(
                    "Music Node Unavailable",
                    "The Lavalink node is still connecting. Try again shortly.",
                    success=False,
                )
            )
            return None

        if (
            not isinstance(ctx.author, discord.Member)
            or not ctx.author.voice
            or not ctx.author.voice.channel
        ):
            await ctx.send(
                view=MusicResponse(
                    "Join a Voice Channel",
                    "Join a voice channel first.",
                    success=False,
                )
            )
            return None

        existing = ctx.guild.voice_client

        if isinstance(existing, wavelink.Player):
            if (
                existing.channel
                != ctx.author.voice.channel
            ):
                await ctx.send(
                    view=MusicResponse(
                        "Different Voice Channel",
                        "Join Monk's current voice channel.",
                        success=False,
                    )
                )
                return None

            return existing

        guild_data = await music_db.get_guild(
            ctx.guild.id
        )

        player = await ctx.author.voice.channel.connect(
            cls=wavelink.Player,
            self_deaf=True,
        )

        player.autoplay = (
            wavelink.AutoPlayMode.enabled
            if guild_data["autoplay"]
            else wavelink.AutoPlayMode.disabled
        )

        await player.set_volume(
            guild_data["volume"]
        )

        return player

    async def ensure_player_interaction(
        self,
        interaction: discord.Interaction,
    ) -> Optional[wavelink.Player]:
        if not interaction.guild:
            return None

        if not self.lavalink_ready():
            await interaction.followup.send(
                view=MusicResponse(
                    "Music Node Unavailable",
                    "The Lavalink node is still connecting. Try again shortly.",
                    success=False,
                ),
                ephemeral=True,
            )
            return None

        member = interaction.user

        if (
            not isinstance(member, discord.Member)
            or not member.voice
            or not member.voice.channel
        ):
            await interaction.followup.send(
                view=MusicResponse(
                    "Join a Voice Channel",
                    "Join a voice channel first.",
                    success=False,
                ),
                ephemeral=True,
            )
            return None

        existing = interaction.guild.voice_client

        if isinstance(existing, wavelink.Player):
            if existing.channel != member.voice.channel:
                await interaction.followup.send(
                    view=MusicResponse(
                        "Different Voice Channel",
                        "Join Monk's current voice channel.",
                        success=False,
                    ),
                    ephemeral=True,
                )
                return None

            return existing

        guild_data = await music_db.get_guild(
            interaction.guild.id
        )

        player = await member.voice.channel.connect(
            cls=wavelink.Player,
            self_deaf=True,
        )

        player.autoplay = (
            wavelink.AutoPlayMode.enabled
            if guild_data["autoplay"]
            else wavelink.AutoPlayMode.disabled
        )

        await player.set_volume(
            guild_data["volume"]
        )

        return player

    async def search_tracks(
        self,
        query: str,
    ):
        if is_url(query):
            return await wavelink.Playable.search(
                query
            )

        for source in (
            wavelink.TrackSource.YouTubeMusic,
            wavelink.TrackSource.YouTube,
            wavelink.TrackSource.SoundCloud,
        ):
            try:
                results = await wavelink.Playable.search(
                    query,
                    source=source,
                )

                if results:
                    return results

            except Exception:
                continue

        return []

    async def enqueue(
        self,
        player: wavelink.Player,
        track: wavelink.Playable,
        requester: discord.abc.User,
        channel: discord.abc.Messageable,
    ):
        track.extras = {
            "requester_id": requester.id,
            "request_channel_id": channel.id,
        }

        if player.playing:
            await player.queue.put_wait(track)
        else:
            await player.play(
                track,
                volume=player.volume or DEFAULT_VOLUME,
                populate=True,
            )

        user_data = await music_db.get_user(
            requester.id
        )
        user_data["tracks_requested"] += 1
        await music_db.save_user(
            requester.id,
            user_data,
        )

    async def ensure_player_message(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
    ) -> Optional[discord.Message]:
        guild_data = await music_db.get_guild(
            guild.id
        )

        stored_channel = guild.get_channel(
            guild_data.get("player_channel_id")
        )

        if (
            stored_channel
            and guild_data.get("player_message_id")
        ):
            try:
                message = await stored_channel.fetch_message(
                    guild_data.get("player_message_id")
                )

                await message.edit(
                    view=PlayerPanel(
                        self,
                        guild.id,
                    )
                )

                return message

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass

        if not hasattr(channel, "send"):
            return None

        try:
            message = await channel.send(
                view=PlayerPanel(
                    self,
                    guild.id,
                )
            )
        except discord.HTTPException as error:
            # Clear stale state so the next play attempt can create a panel.
            guild_data["player_channel_id"] = None
            guild_data["player_message_id"] = None
            await music_db.save_guild(
                guild.id,
                guild_data,
            )

            print(
                f"❌ Player panel send failed in guild {guild.id}: "
                f"{type(error).__name__}: {error}"
            )

            # Last-resort reliable panel without artwork.
            try:
                fallback = discord.ui.LayoutView(timeout=None)
                fallback.add_item(
                    discord.ui.Container(
                        discord.ui.TextDisplay(
                            f"## {emoji_text(self.bot, 'music')} Monk Music Player"
                        ),
                        discord.ui.Separator(),
                        discord.ui.TextDisplay(
                            "A song is playing. Use `mplayer` to refresh "
                            "the full control panel."
                        ),
                        accent_colour=ACCENT,
                    )
                )
                message = await channel.send(view=fallback)
            except discord.HTTPException:
                return None

        guild_data["player_channel_id"] = channel.id
        guild_data["player_message_id"] = message.id

        await music_db.save_guild(
            guild.id,
            guild_data,
        )

        return message

    async def move_player_message(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
    ):
        guild_data = await music_db.get_guild(
            guild.id
        )

        old_channel = guild.get_channel(
            guild_data.get("player_channel_id")
        )

        if (
            old_channel
            and guild_data.get("player_message_id")
        ):
            try:
                old_message = await old_channel.fetch_message(
                    guild_data.get("player_message_id")
                )
                await old_message.delete()
            except discord.HTTPException:
                pass

        guild_data["player_channel_id"] = None
        guild_data["player_message_id"] = None

        await music_db.save_guild(
            guild.id,
            guild_data,
        )

        return await self.ensure_player_message(
            guild,
            channel,
        )

    async def update_player_message(
        self,
        guild: discord.Guild,
    ):
        guild_data = await music_db.get_guild(
            guild.id
        )

        channel = guild.get_channel(
            guild_data.get("player_channel_id")
        )

        if (
            not channel
            or not guild_data.get("player_message_id")
        ):
            return

        try:
            message = await channel.fetch_message(
                guild_data.get("player_message_id")
            )

            await message.edit(
                view=PlayerPanel(
                    self,
                    guild.id,
                )
            )

        except discord.NotFound:
            guild_data["player_message_id"] = None
            await music_db.save_guild(
                guild.id,
                guild_data,
            )

        except discord.HTTPException:
            pass

    @commands.command(
        name="play",
        aliases=["p"],
    )
    @commands.guild_only()
    async def play(
        self,
        ctx: commands.Context,
        *,
        query: str,
    ):
        player = await self.ensure_player(ctx)

        if not player:
            return

        loading = await ctx.send(
            view=MusicResponse(
                "Searching",
                f"Searching for **{query[:200]}**...",
            )
        )

        try:
            results = await self.search_tracks(
                query
            )

        except Exception as error:
            return await loading.edit(
                view=MusicResponse(
                    "Search Failed",
                    f"```py\n"
                    f"{type(error).__name__}: {error}"
                    f"\n```",
                    success=False,
                )
            )

        if not results:
            return await loading.edit(
                view=MusicResponse(
                    "No Results",
                    "No playable songs were found.",
                    success=False,
                )
            )

        if isinstance(
            results,
            wavelink.Playlist,
        ):
            tracks = list(
                results.tracks[:100]
            )

            for track in tracks:
                track.extras = {
                    "requester_id": ctx.author.id,
                    "request_channel_id": ctx.channel.id,
                }

            await player.queue.put_wait(tracks)

            if not player.playing:
                await player.play(
                    player.queue.get(),
                    volume=player.volume or DEFAULT_VOLUME,
                    populate=True,
                )

            await loading.delete()

            await self.move_player_message(
                ctx.guild,
                ctx.channel,
            )
            return

        tracks = list(results)

        if is_url(query) or len(tracks) == 1:
            track = tracks[0]

            await self.enqueue(
                player,
                track,
                ctx.author,
                ctx.channel,
            )

            await loading.delete()

            await self.move_player_message(
                ctx.guild,
                ctx.channel,
            )
            return

        await loading.edit(
            view=SearchResultsView(
                self,
                ctx.author.id,
                tracks[:SEARCH_RESULTS],
            )
        )

    @commands.command(
        name="player",
        aliases=["panel", "music"],
    )
    @commands.guild_only()
    async def player_command(
        self,
        ctx: commands.Context,
    ):
        player = ctx.guild.voice_client

        if not isinstance(
            player,
            wavelink.Player,
        ):
            return await ctx.send(
                view=MusicResponse(
                    "No Active Player",
                    "Play a song first.",
                    success=False,
                )
            )

        await self.move_player_message(
            ctx.guild,
            ctx.channel,
        )

    @commands.command(
        name="playlist",
        aliases=["playlists", "pl"],
    )
    @commands.guild_only()
    async def playlists_command(
        self,
        ctx: commands.Context,
    ):
        view = PlaylistsView(
            self,
            ctx.author.id,
        )
        await view.prepare()

        await ctx.send(view=view)

    @commands.command(
        name="favorites",
        aliases=["favs"],
    )
    @commands.guild_only()
    async def favorites_command(
        self,
        ctx: commands.Context,
    ):
        user_data = await music_db.get_user(
            ctx.author.id
        )

        favorites = user_data["favorites"]

        if not favorites:
            return await ctx.send(
                view=MusicResponse(
                    "Favorites",
                    "You have no saved favorites.",
                    success=False,
                )
            )

        lines = []

        for index, track in enumerate(
            favorites[:20],
            start=1,
        ):
            lines.append(
                f"`{index}.` **{track['title']}**\n"
                f"{track['author']} • "
                f"`{format_time(track['length'])}`"
            )

        await ctx.send(
            view=MusicResponse(
                f"Favorites ({len(favorites)})",
                "\n\n".join(lines),
            )
        )

    @commands.Cog.listener()
    async def on_wavelink_track_start(
        self,
        payload: wavelink.TrackStartEventPayload,
    ):
        player = payload.player
        track = payload.track

        if not player or not player.guild:
            return

        guild_data = await music_db.get_guild(
            player.guild.id
        )

        guild_data["tracks_played"] += 1
        guild_data["history"].append(
            {
                **track_to_data(track),
                "requester_id": get_extra(
                    track,
                    "requester_id",
                ),
                "played_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
        )
        guild_data["history"] = (
            guild_data["history"][-100:]
        )

        await music_db.save_guild(
            player.guild.id,
            guild_data,
        )

        await self.update_player_message(
            player.guild
        )

    @commands.Cog.listener()
    async def on_wavelink_track_end(
        self,
        payload: wavelink.TrackEndEventPayload,
    ):
        player = payload.player

        if not player:
            return

        if (
            player.autoplay
            == wavelink.AutoPlayMode.disabled
            and not player.queue.is_empty
        ):
            try:
                await player.play(
                    player.queue.get(),
                    populate=True,
                )
            except Exception:
                pass

        if player.guild:
            await self.update_player_message(
                player.guild
            )

    @commands.Cog.listener()
    async def on_wavelink_track_exception(
        self,
        payload: wavelink.TrackExceptionEventPayload,
    ):
        player = payload.player

        if not player:
            return

        if not player.queue.is_empty:
            try:
                await player.play(
                    player.queue.get(),
                    populate=True,
                )
            except Exception:
                pass

        if player.guild:
            await self.update_player_message(
                player.guild
            )

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(
            error,
            commands.MissingRequiredArgument,
        ):
            return await ctx.send(
                view=MusicResponse(
                    "Missing Argument",
                    f"You did not provide "
                    f"`{error.param.name}`.",
                    success=False,
                )
            )

        if isinstance(
            error,
            commands.BadArgument,
        ):
            return await ctx.send(
                view=MusicResponse(
                    "Invalid Argument",
                    "One or more arguments are invalid.",
                    success=False,
                )
            )

        await ctx.send(
            view=MusicResponse(
                "Music Error",
                f"```py\n"
                f"{type(error).__name__}: {error}"
                f"\n```",
                success=False,
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
