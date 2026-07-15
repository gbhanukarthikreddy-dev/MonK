import ast
import asyncio
import contextlib
import io
import json
import os
import shutil
import textwrap
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord.ext import commands


# =========================================================
# OWNER CONFIGURATION
# =========================================================

DATABASE_PATH = "database/owner.json"
BACKUP_FOLDER = "database/backups"

DEFAULT_PREFIX = "m"

TARGET_REACTION_USER_ID = 1396844211038458018

MAX_NOPREFIX_LIST = 50
MAX_GUILD_LIST = 30
MAX_BLACKLIST_LIST = 50
MAX_EVAL_OUTPUT = 3800
MAX_ERROR_OUTPUT = 3500

ACCENT_COLOR = discord.Color.from_rgb(198, 145, 73)
SUCCESS_COLOR = discord.Color.from_rgb(70, 190, 120)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 75)
WARNING_COLOR = discord.Color.from_rgb(235, 175, 65)
INFO_COLOR = discord.Color.from_rgb(80, 150, 230)


# =========================================================
# CUSTOM EMOJIS
# =========================================================
# Use any of these formats:
#
# 123456789012345678
# "123456789012345678"
# "<:name:123456789012345678>"
# "<a:name:123456789012345678>"
#
# Leave as None to use the fallback.

CUSTOM_EMOJI_IDS = {
    "owner": '<:crown:1527042562190217346>',
    "success": '<:circlecheck:1527050613379043478>',
    "error": '<:circlex:1527045249598492944>',
    "warning": '<:trianglealert:1527050768077819966>',
    "info": '<:info:1527032861348204706>',
    "loading": None,

    "noprefix": '<:user:1527043175191941211>',
    "add_noprefix": '<:plus:1527051178662432768>',
    "remove_noprefix": '<:circlex:1527045249598492944>',
    "noprefix_list": '<:list:1527044575158341732>',

    "load": None,
    "unload": None,
    "reload": None,
    "reload_all": None,
    "sync": None,

    "stats": None,
    "guild": None,
    "message": None,
    "eval": None,
    "shutdown": None,
    "restart": None,
    "maintenance": None,
    "blacklist": None,
    "status": None,
    "backup": None,
    "announce": None,

    "mention_reaction": None,
}

EMOJI_FALLBACKS = {
    "owner": "👑",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "loading": "⏳",

    "noprefix": "✨",
    "add_noprefix": "➕",
    "remove_noprefix": "➖",
    "noprefix_list": "📋",

    "load": "📥",
    "unload": "📤",
    "reload": "🔄",
    "reload_all": "♻️",
    "sync": "🔃",

    "stats": "📊",
    "guild": "🌐",
    "message": "💬",
    "eval": "🧪",
    "shutdown": "🛑",
    "restart": "🔁",
    "maintenance": "🛠️",
    "blacklist": "🚫",
    "status": "🎮",
    "backup": "💾",
    "announce": "📢",

    "mention_reaction": "<a:752588ononono:1527052268493476033>",
}


# =========================================================
# EMOJI HELPERS
# =========================================================

def get_custom_emoji(
    bot: commands.Bot,
    key: str,
) -> str | discord.Emoji | discord.PartialEmoji:
    configured = CUSTOM_EMOJI_IDS.get(key)

    if configured:
        if isinstance(
            configured,
            (discord.Emoji, discord.PartialEmoji),
        ):
            return configured

        if isinstance(configured, int) or str(configured).isdigit():
            emoji = bot.get_emoji(int(configured))

            if emoji:
                return emoji

        if isinstance(configured, str):
            try:
                partial = discord.PartialEmoji.from_str(
                    configured.strip()
                )

                if partial.id:
                    cached = bot.get_emoji(partial.id)
                    return cached or partial

            except (TypeError, ValueError):
                pass

    return EMOJI_FALLBACKS.get(key, "•")


def emoji_text(
    bot: commands.Bot,
    key: str,
) -> str:
    return str(get_custom_emoji(bot, key))


# =========================================================
# DATABASE
# =========================================================

DEFAULT_DATA: dict[str, Any] = {
    "noprefix_users": [],
    "blacklisted_users": [],
    "blacklisted_guilds": [],
    "maintenance_mode": False,
    "maintenance_reason": "Monk is currently under maintenance.",
}


class OwnerDatabase:
    def __init__(self, path: str):
        self.path = path

        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        os.makedirs(BACKUP_FOLDER, exist_ok=True)

        if not os.path.exists(path):
            self.save(DEFAULT_DATA.copy())

    def load(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError

        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = DEFAULT_DATA.copy()
            self.save(data)
            return data

        changed = False

        for key, value in DEFAULT_DATA.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, list) else value
                changed = True

        if changed:
            self.save(data)

        return data

    def save(self, data: dict[str, Any]) -> None:
        temporary = f"{self.path}.tmp"

        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

        os.replace(temporary, self.path)

    def get_ids(self, key: str) -> list[int]:
        data = self.load()

        return [
            int(item)
            for item in data.get(key, [])
        ]

    def contains(self, key: str, item_id: int) -> bool:
        return item_id in self.get_ids(key)

    def add(self, key: str, item_id: int) -> bool:
        data = self.load()
        values = data.setdefault(key, [])

        if item_id in values:
            return False

        values.append(item_id)
        self.save(data)
        return True

    def remove(self, key: str, item_id: int) -> bool:
        data = self.load()
        values = data.setdefault(key, [])

        if item_id not in values:
            return False

        values.remove(item_id)
        self.save(data)
        return True

    def set_value(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self.save(data)


owner_db = OwnerDatabase(DATABASE_PATH)


# =========================================================
# PUBLIC PREFIX HELPERS
# =========================================================

def has_noprefix(user_id: int) -> bool:
    return owner_db.contains("noprefix_users", user_id)


async def get_prefix(
    bot: commands.Bot,
    message: discord.Message,
):
    """
    Prefix rules:

    Normal user:
        mhelp

    No-prefix user:
        help
        mhelp

    Mention prefix:
        @Monk help
    """

    guild_prefix = DEFAULT_PREFIX

    try:
        from cogs.setup import get_config_value

        if message.guild:
            configured = get_config_value(
                message.guild.id,
                "prefix",
                DEFAULT_PREFIX,
            )

            if configured:
                guild_prefix = str(configured)

    except (ImportError, AttributeError, KeyError, TypeError):
        pass

    prefixes = [guild_prefix]

    # Keep the normal prefix AND add empty prefix.
    if has_noprefix(message.author.id):
        prefixes.append("")

    return commands.when_mentioned_or(*prefixes)(
        bot,
        message,
    )


# =========================================================
# GLOBAL ACCESS CHECK
# =========================================================

async def owner_global_check(ctx: commands.Context) -> bool:
    if await ctx.bot.is_owner(ctx.author):
        return True

    data = owner_db.load()

    if ctx.author.id in data["blacklisted_users"]:
        raise commands.CheckFailure(
            "You are blacklisted from using Monk."
        )

    if (
        ctx.guild
        and ctx.guild.id in data["blacklisted_guilds"]
    ):
        raise commands.CheckFailure(
            "This server is blacklisted from using Monk."
        )

    if data["maintenance_mode"]:
        raise commands.CheckFailure(
            data["maintenance_reason"]
        )

    return True


# =========================================================
# COMPONENTS V2 RESPONSE
# =========================================================

class OwnerResponseView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        title: str,
        description: str,
        *,
        emoji_key: str = "owner",
        success: bool = True,
        warning: bool = False,
    ):
        super().__init__(timeout=90)

        colour = (
            WARNING_COLOR
            if warning
            else SUCCESS_COLOR if success else ERROR_COLOR
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {emoji_text(bot, emoji_key)} {title}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=colour,
            )
        )


async def send_response(
    ctx: commands.Context,
    title: str,
    description: str,
    *,
    emoji_key: str = "owner",
    success: bool = True,
    warning: bool = False,
):
    await ctx.send(
        view=OwnerResponseView(
            ctx.bot,
            title,
            description,
            emoji_key=emoji_key,
            success=success,
            warning=warning,
        )
    )


# =========================================================
# EVAL HELPERS
# =========================================================

def cleanup_code(content: str) -> str:
    content = content.strip()

    if content.startswith("```") and content.endswith("```"):
        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines)

    return content.strip("` \n")


def insert_returns(body: list[ast.stmt]) -> None:
    if not body:
        return

    last = body[-1]

    if isinstance(last, ast.Expr):
        body[-1] = ast.Return(last.value)
        ast.fix_missing_locations(body[-1])

    elif isinstance(last, ast.If):
        insert_returns(last.body)
        insert_returns(last.orelse)

    elif isinstance(last, (ast.With, ast.AsyncWith)):
        insert_returns(last.body)


# =========================================================
# OWNER COG
# =========================================================

class Owner(commands.Cog):
    """Advanced private owner administration for Monk."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_result: Any = None

    async def cog_check(
        self,
        ctx: commands.Context,
    ) -> bool:
        return await self.bot.is_owner(ctx.author)

    # =====================================================
    # NO PREFIX
    # =====================================================

    @commands.command(
        name="np",
        aliases=["addnp", "noprefix"],
        help="Give no-prefix access using a user ID.",
    )
    async def add_noprefix(
        self,
        ctx: commands.Context,
        user_id: int,
    ):
        try:
            user = self.bot.get_user(user_id)

            if user is None:
                user = await self.bot.fetch_user(user_id)

        except (discord.NotFound, discord.HTTPException):
            return await send_response(
                ctx,
                "User Not Found",
                f"No Discord account was found with ID `{user_id}`.",
                emoji_key="error",
                success=False,
            )

        if not owner_db.add("noprefix_users", user.id):
            return await send_response(
                ctx,
                "Already No-Prefix",
                f"**User:** {user}\n"
                f"**ID:** `{user.id}`\n\n"
                "This user already has no-prefix access.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "No-Prefix Added",
            f"**User:** {user}\n"
            f"**ID:** `{user.id}`\n\n"
            "Both prefixed and no-prefix commands now work.",
            emoji_key="add_noprefix",
        )

    @commands.command(
        name="rnp",
        aliases=["removenp", "delnp"],
        help="Remove no-prefix access using a user ID.",
    )
    async def remove_noprefix(
        self,
        ctx: commands.Context,
        user_id: int,
    ):
        if not owner_db.remove("noprefix_users", user_id):
            return await send_response(
                ctx,
                "No-Prefix Not Found",
                f"User ID `{user_id}` does not have no-prefix access.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "No-Prefix Removed",
            f"User ID `{user_id}` must now use the normal prefix.",
            emoji_key="remove_noprefix",
        )

    @commands.command(
        name="nplist",
        aliases=["listnp", "noprefixlist"],
    )
    async def noprefix_list(
        self,
        ctx: commands.Context,
    ):
        user_ids = owner_db.get_ids("noprefix_users")

        if not user_ids:
            return await send_response(
                ctx,
                "No-Prefix Users",
                "No users currently have no-prefix access.",
                emoji_key="noprefix_list",
            )

        lines = []

        for index, user_id in enumerate(
            user_ids[:MAX_NOPREFIX_LIST],
            start=1,
        ):
            user = self.bot.get_user(user_id)
            label = user.mention if user else "Unknown User"

            lines.append(
                f"`{index}.` {label} — `{user_id}`"
            )

        await send_response(
            ctx,
            f"No-Prefix Users ({len(user_ids)})",
            "\n".join(lines),
            emoji_key="noprefix_list",
        )

    # =====================================================
    # BLACKLIST
    # =====================================================

    @commands.command(name="blacklistuser")
    async def blacklist_user(
        self,
        ctx: commands.Context,
        user_id: int,
    ):
        if await self.bot.is_owner(
            self.bot.get_user(user_id) or ctx.author
        ) and user_id == ctx.author.id:
            return await send_response(
                ctx,
                "Action Blocked",
                "You cannot blacklist yourself.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        if not owner_db.add("blacklisted_users", user_id):
            return await send_response(
                ctx,
                "Already Blacklisted",
                f"User ID `{user_id}` is already blacklisted.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "User Blacklisted",
            f"User ID `{user_id}` can no longer use Monk.",
            emoji_key="blacklist",
        )

    @commands.command(name="unblacklistuser")
    async def unblacklist_user(
        self,
        ctx: commands.Context,
        user_id: int,
    ):
        if not owner_db.remove("blacklisted_users", user_id):
            return await send_response(
                ctx,
                "Blacklist Entry Not Found",
                f"User ID `{user_id}` is not blacklisted.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "User Unblacklisted",
            f"User ID `{user_id}` can use Monk again.",
            emoji_key="blacklist",
        )

    @commands.command(name="blacklistguild")
    async def blacklist_guild(
        self,
        ctx: commands.Context,
        guild_id: int,
    ):
        if not owner_db.add("blacklisted_guilds", guild_id):
            return await send_response(
                ctx,
                "Already Blacklisted",
                f"Guild ID `{guild_id}` is already blacklisted.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "Guild Blacklisted",
            f"Guild ID `{guild_id}` can no longer use Monk.",
            emoji_key="blacklist",
        )

    @commands.command(name="unblacklistguild")
    async def unblacklist_guild(
        self,
        ctx: commands.Context,
        guild_id: int,
    ):
        if not owner_db.remove("blacklisted_guilds", guild_id):
            return await send_response(
                ctx,
                "Blacklist Entry Not Found",
                f"Guild ID `{guild_id}` is not blacklisted.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "Guild Unblacklisted",
            f"Guild ID `{guild_id}` can use Monk again.",
            emoji_key="blacklist",
        )

    @commands.command(name="blacklistlist")
    async def blacklist_list(
        self,
        ctx: commands.Context,
    ):
        users = owner_db.get_ids("blacklisted_users")
        guilds = owner_db.get_ids("blacklisted_guilds")

        user_lines = [
            f"<@{user_id}> — `{user_id}`"
            for user_id in users[:MAX_BLACKLIST_LIST]
        ] or ["None"]

        guild_lines = []

        for guild_id in guilds[:MAX_BLACKLIST_LIST]:
            guild = self.bot.get_guild(guild_id)

            guild_lines.append(
                f"**{guild.name if guild else 'Unknown Guild'}** — `{guild_id}`"
            )

        if not guild_lines:
            guild_lines = ["None"]

        await send_response(
            ctx,
            "Blacklist",
            "### Users\n"
            + "\n".join(user_lines)
            + "\n\n### Guilds\n"
            + "\n".join(guild_lines),
            emoji_key="blacklist",
        )

    # =====================================================
    # MAINTENANCE
    # =====================================================

    @commands.group(
        name="maintenance",
        invoke_without_command=True,
    )
    async def maintenance(
        self,
        ctx: commands.Context,
    ):
        data = owner_db.load()

        await send_response(
            ctx,
            "Maintenance Status",
            f"**Enabled:** `{data['maintenance_mode']}`\n"
            f"**Reason:** {data['maintenance_reason']}\n\n"
            "`mmaintenance on <reason>`\n"
            "`mmaintenance off`",
            emoji_key="maintenance",
        )

    @maintenance.command(name="on")
    async def maintenance_on(
        self,
        ctx: commands.Context,
        *,
        reason: str = "Monk is currently under maintenance.",
    ):
        owner_db.set_value("maintenance_mode", True)
        owner_db.set_value(
            "maintenance_reason",
            reason[:1000],
        )

        await send_response(
            ctx,
            "Maintenance Enabled",
            f"**Reason:** {reason[:1000]}",
            emoji_key="maintenance",
        )

    @maintenance.command(name="off")
    async def maintenance_off(
        self,
        ctx: commands.Context,
    ):
        owner_db.set_value("maintenance_mode", False)

        await send_response(
            ctx,
            "Maintenance Disabled",
            "All non-blacklisted users can use Monk again.",
            emoji_key="maintenance",
        )

    # =====================================================
    # EXTENSIONS
    # =====================================================

    @commands.command(name="load")
    async def load_extension(
        self,
        ctx: commands.Context,
        extension: str,
    ):
        extension = extension.removesuffix(".py")

        if not extension.startswith("cogs."):
            extension = f"cogs.{extension}"

        try:
            await self.bot.load_extension(extension)

        except commands.ExtensionAlreadyLoaded:
            return await send_response(
                ctx,
                "Already Loaded",
                f"`{extension}` is already loaded.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        except commands.ExtensionNotFound:
            return await send_response(
                ctx,
                "Extension Not Found",
                f"`{extension}` could not be found.",
                emoji_key="error",
                success=False,
            )

        except commands.ExtensionFailed as error:
            return await send_response(
                ctx,
                "Extension Failed",
                f"```py\n{type(error.original).__name__}: "
                f"{error.original}\n```",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Extension Loaded",
            f"Loaded `{extension}`.",
            emoji_key="load",
        )

    @commands.command(name="unload")
    async def unload_extension(
        self,
        ctx: commands.Context,
        extension: str,
    ):
        extension = extension.removesuffix(".py")

        if not extension.startswith("cogs."):
            extension = f"cogs.{extension}"

        if extension in {__name__, "cogs.owner"}:
            return await send_response(
                ctx,
                "Action Blocked",
                "The owner cog cannot unload itself.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        try:
            await self.bot.unload_extension(extension)

        except commands.ExtensionNotLoaded:
            return await send_response(
                ctx,
                "Extension Not Loaded",
                f"`{extension}` is not loaded.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await send_response(
            ctx,
            "Extension Unloaded",
            f"Unloaded `{extension}`.",
            emoji_key="unload",
        )

    @commands.command(
        name="reload",
        aliases=["rl"],
    )
    async def reload_extension(
        self,
        ctx: commands.Context,
        extension: str,
    ):
        extension = extension.removesuffix(".py")

        if not extension.startswith("cogs."):
            extension = f"cogs.{extension}"

        try:
            if extension in self.bot.extensions:
                await self.bot.reload_extension(extension)
            else:
                await self.bot.load_extension(extension)

        except Exception as error:
            original = getattr(error, "original", error)

            return await send_response(
                ctx,
                "Extension Reload Failed",
                f"```py\n{type(original).__name__}: {original}\n```",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Extension Reloaded",
            f"Reloaded `{extension}`.",
            emoji_key="reload",
        )

    @commands.command(
        name="reloadall",
        aliases=["rla"],
    )
    async def reload_all(
        self,
        ctx: commands.Context,
    ):
        successful = []
        failed = []

        for extension in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(extension)
                successful.append(extension)

            except Exception as error:
                failed.append(
                    f"`{extension}` — `{type(error).__name__}`"
                )

        description = (
            f"**Reloaded:** `{len(successful)}`\n"
            f"**Failed:** `{len(failed)}`"
        )

        if failed:
            description += (
                "\n\n### Failed\n"
                + "\n".join(failed[:20])
            )

        await send_response(
            ctx,
            "Reload Complete",
            description,
            emoji_key="reload_all",
            success=not failed,
            warning=bool(failed),
        )

    # =====================================================
    # SYNC
    # =====================================================

    @commands.command(name="sync")
    async def sync_commands(
        self,
        ctx: commands.Context,
        scope: str = "guild",
    ):
        scope = scope.lower()

        try:
            if scope in {"guild", "server", "local"}:
                if not ctx.guild:
                    raise commands.NoPrivateMessage

                self.bot.tree.copy_global_to(
                    guild=ctx.guild
                )
                synced = await self.bot.tree.sync(
                    guild=ctx.guild
                )
                location = ctx.guild.name

            elif scope in {"global", "all"}:
                synced = await self.bot.tree.sync()
                location = "Global"

            elif scope in {"clear", "remove"}:
                if not ctx.guild:
                    raise commands.NoPrivateMessage

                self.bot.tree.clear_commands(
                    guild=ctx.guild
                )
                synced = await self.bot.tree.sync(
                    guild=ctx.guild
                )
                location = f"Cleared in {ctx.guild.name}"

            else:
                return await send_response(
                    ctx,
                    "Invalid Scope",
                    "Use `msync guild`, `msync global`, or `msync clear`.",
                    emoji_key="warning",
                    success=False,
                    warning=True,
                )

        except Exception as error:
            return await send_response(
                ctx,
                "Sync Failed",
                f"```py\n{type(error).__name__}: {error}\n```",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Commands Synced",
            f"**Count:** `{len(synced)}`\n"
            f"**Scope:** {location}",
            emoji_key="sync",
        )

    # =====================================================
    # BOT STATUS
    # =====================================================

    @commands.command(name="setstatus")
    async def set_status(
        self,
        ctx: commands.Context,
        status_type: str,
        *,
        text: str,
    ):
        status_type = status_type.lower()

        activity_map = {
            "playing": discord.Game(name=text),
            "watching": discord.Activity(
                type=discord.ActivityType.watching,
                name=text,
            ),
            "listening": discord.Activity(
                type=discord.ActivityType.listening,
                name=text,
            ),
            "competing": discord.Activity(
                type=discord.ActivityType.competing,
                name=text,
            ),
        }

        activity = activity_map.get(status_type)

        if not activity:
            return await send_response(
                ctx,
                "Invalid Status Type",
                "Use `playing`, `watching`, `listening`, or `competing`.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await self.bot.change_presence(
            activity=activity,
        )

        await send_response(
            ctx,
            "Status Updated",
            f"**Type:** `{status_type}`\n"
            f"**Text:** {text}",
            emoji_key="status",
        )

    @commands.command(name="setpresence")
    async def set_presence(
        self,
        ctx: commands.Context,
        status: str,
    ):
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }

        selected = status_map.get(status.lower())

        if selected is None:
            return await send_response(
                ctx,
                "Invalid Presence",
                "Use `online`, `idle`, `dnd`, or `invisible`.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        await self.bot.change_presence(
            status=selected,
        )

        await send_response(
            ctx,
            "Presence Updated",
            f"Presence changed to `{status.lower()}`.",
            emoji_key="status",
        )

    # =====================================================
    # BOT INFORMATION
    # =====================================================

    @commands.command(
        name="botstats",
        aliases=["bstats"],
    )
    async def show_bot_stats(
        self,
        ctx: commands.Context,
    ):
        total_members = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )
        total_channels = sum(
            len(guild.channels)
            for guild in self.bot.guilds
        )

        await send_response(
            ctx,
            "Monk Bot Statistics",
            f"**Servers:** `{len(self.bot.guilds)}`\n"
            f"**Members:** `{total_members:,}`\n"
            f"**Channels:** `{total_channels:,}`\n"
            f"**Commands:** `{len(self.bot.commands)}`\n"
            f"**Extensions:** `{len(self.bot.extensions)}`\n"
            f"**Latency:** `{round(self.bot.latency * 1000)}ms`\n"
            f"**No-Prefix Users:** "
            f"`{len(owner_db.get_ids('noprefix_users'))}`\n"
            f"**Blacklisted Users:** "
            f"`{len(owner_db.get_ids('blacklisted_users'))}`\n"
            f"**Maintenance:** "
            f"`{owner_db.load()['maintenance_mode']}`",
            emoji_key="stats",
        )

    @commands.command(
        name="guilds",
        aliases=["servers"],
    )
    async def guilds(
        self,
        ctx: commands.Context,
    ):
        guilds = sorted(
            self.bot.guilds,
            key=lambda guild: guild.member_count or 0,
            reverse=True,
        )

        if not guilds:
            return await send_response(
                ctx,
                "Guild List",
                "Monk is not in any guilds.",
                emoji_key="guild",
            )

        lines = []

        for index, guild in enumerate(
            guilds[:MAX_GUILD_LIST],
            start=1,
        ):
            lines.append(
                f"`{index}.` **{guild.name}**\n"
                f"Members: `{guild.member_count or 0}` • "
                f"ID: `{guild.id}`"
            )

        await send_response(
            ctx,
            f"Guilds ({len(guilds)})",
            "\n\n".join(lines),
            emoji_key="guild",
        )

    @commands.command(name="guildinfo")
    async def guild_info(
        self,
        ctx: commands.Context,
        guild_id: int,
    ):
        guild = self.bot.get_guild(guild_id)

        if not guild:
            return await send_response(
                ctx,
                "Guild Not Found",
                f"Monk is not in guild `{guild_id}`.",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Guild Information",
            f"**Name:** {guild.name}\n"
            f"**ID:** `{guild.id}`\n"
            f"**Owner:** {guild.owner or 'Unknown'}\n"
            f"**Members:** `{guild.member_count or 0}`\n"
            f"**Channels:** `{len(guild.channels)}`\n"
            f"**Roles:** `{len(guild.roles)}`\n"
            f"**Created:** "
            f"{discord.utils.format_dt(guild.created_at, style='R')}",
            emoji_key="guild",
        )

    @commands.command(name="leaveguild")
    async def leave_guild(
        self,
        ctx: commands.Context,
        guild_id: int,
    ):
        guild = self.bot.get_guild(guild_id)

        if not guild:
            return await send_response(
                ctx,
                "Guild Not Found",
                f"Monk is not in guild `{guild_id}`.",
                emoji_key="error",
                success=False,
            )

        name = guild.name
        await guild.leave()

        await send_response(
            ctx,
            "Guild Left",
            f"Left **{name}** (`{guild_id}`).",
            emoji_key="guild",
        )

    # =====================================================
    # BROADCAST / DM / SAY
    # =====================================================

    @commands.command(name="say")
    async def say(
        self,
        ctx: commands.Context,
        *,
        message: str,
    ):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        await ctx.send(
            message,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="dm")
    async def direct_message(
        self,
        ctx: commands.Context,
        user_id: int,
        *,
        message: str,
    ):
        try:
            user = self.bot.get_user(user_id)

            if user is None:
                user = await self.bot.fetch_user(user_id)

            await user.send(message)

        except discord.HTTPException:
            return await send_response(
                ctx,
                "DM Failed",
                f"Could not DM user `{user_id}`.",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "DM Sent",
            f"Message sent to `{user_id}`.",
            emoji_key="message",
        )

    @commands.command(name="announceall")
    async def announce_all(
        self,
        ctx: commands.Context,
        *,
        message: str,
    ):
        sent = 0
        failed = 0

        progress = await ctx.send(
            view=OwnerResponseView(
                self.bot,
                "Broadcast Starting",
                "Sending the announcement to available system channels...",
                emoji_key="announce",
                warning=True,
            )
        )

        for guild in self.bot.guilds:
            channel = guild.system_channel

            if not channel:
                channel = next(
                    (
                        item
                        for item in guild.text_channels
                        if item.permissions_for(
                            guild.me
                        ).send_messages
                    ),
                    None,
                )

            if not channel:
                failed += 1
                continue

            try:
                await channel.send(
                    view=OwnerResponseView(
                        self.bot,
                        "Monk Announcement",
                        message[:3500],
                        emoji_key="announce",
                    )
                )
                sent += 1

            except discord.HTTPException:
                failed += 1

        await progress.edit(
            view=OwnerResponseView(
                self.bot,
                "Broadcast Complete",
                f"**Sent:** `{sent}`\n"
                f"**Failed:** `{failed}`",
                emoji_key="announce",
                success=failed == 0,
                warning=failed > 0,
            )
        )

    # =====================================================
    # BACKUPS
    # =====================================================

    @commands.command(name="backup")
    async def backup_database(
        self,
        ctx: commands.Context,
    ):
        os.makedirs(BACKUP_FOLDER, exist_ok=True)

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d-%H%M%S")

        backup_path = os.path.join(
            BACKUP_FOLDER,
            f"database-{timestamp}",
        )

        try:
            shutil.copytree(
                "database",
                backup_path,
                dirs_exist_ok=False,
            )

        except Exception as error:
            return await send_response(
                ctx,
                "Backup Failed",
                f"```py\n{type(error).__name__}: {error}\n```",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Backup Created",
            f"Database backup saved to:\n`{backup_path}`",
            emoji_key="backup",
        )

    # =====================================================
    # EVAL
    # =====================================================

    @commands.command(
        name="eval",
        aliases=["e"],
        hidden=True,
    )
    async def evaluate(
        self,
        ctx: commands.Context,
        *,
        code: str,
    ):
        code = cleanup_code(code)

        environment = {
            "bot": self.bot,
            "ctx": ctx,
            "discord": discord,
            "commands": commands,
            "asyncio": asyncio,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
            "message": ctx.message,
            "_": self._last_result,
        }

        function_code = (
            "async def __owner_eval__():\n"
            + textwrap.indent(code, "    ")
        )

        try:
            parsed = ast.parse(function_code)
            insert_returns(parsed.body[0].body)
            ast.fix_missing_locations(parsed)

            compiled = compile(
                parsed,
                filename="<owner-eval>",
                mode="exec",
            )

            exec(compiled, environment)

        except Exception:
            return await send_response(
                ctx,
                "Eval Compilation Error",
                f"```py\n"
                f"{traceback.format_exc()[-MAX_ERROR_OUTPUT:]}"
                f"\n```",
                emoji_key="error",
                success=False,
            )

        output = io.StringIO()

        try:
            with contextlib.redirect_stdout(output):
                result = await environment["__owner_eval__"]()

        except Exception:
            return await send_response(
                ctx,
                "Eval Runtime Error",
                f"```py\n"
                f"{output.getvalue()}"
                f"{traceback.format_exc()[-MAX_ERROR_OUTPUT:]}"
                f"\n```",
                emoji_key="error",
                success=False,
            )

        printed = output.getvalue()
        response = printed

        if result is not None:
            self._last_result = result
            response += repr(result)

        if not response:
            response = "No output."

        if len(response) > MAX_EVAL_OUTPUT:
            response = (
                response[:MAX_EVAL_OUTPUT]
                + "\n...output truncated"
            )

        await send_response(
            ctx,
            "Eval Result",
            f"```py\n{response}\n```",
            emoji_key="eval",
        )

    # =====================================================
    # BOT LIFECYCLE
    # =====================================================

    @commands.command(
        name="shutdown",
        aliases=["logout", "stopbot"],
    )
    async def shutdown(
        self,
        ctx: commands.Context,
    ):
        await send_response(
            ctx,
            "Shutting Down",
            "Monk is shutting down safely.",
            emoji_key="shutdown",
        )

        await self.bot.close()

    # =====================================================
    # MENTION / REPLY REACTION
    # =====================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):
        if message.author.bot:
            return

        should_react = any(
            user.id == TARGET_REACTION_USER_ID
            for user in message.mentions
        )

        if not should_react and message.reference:
            replied = message.reference.resolved

            if not isinstance(replied, discord.Message):
                try:
                    if message.reference.message_id:
                        replied = await message.channel.fetch_message(
                            message.reference.message_id
                        )
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    replied = None

            if (
                isinstance(replied, discord.Message)
                and replied.author.id == TARGET_REACTION_USER_ID
            ):
                should_react = True

        if should_react:
            try:
                await message.add_reaction(
                    get_custom_emoji(
                        self.bot,
                        "mention_reaction",
                    )
                )

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass

    # =====================================================
    # ERRORS
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.NotOwner):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            return await send_response(
                ctx,
                "Missing Argument",
                f"You did not provide `{error.param.name}`.",
                emoji_key="warning",
                success=False,
                warning=True,
            )

        if isinstance(error, commands.BadArgument):
            return await send_response(
                ctx,
                "Invalid Argument",
                "One or more supplied arguments are invalid.",
                emoji_key="error",
                success=False,
            )

        await send_response(
            ctx,
            "Owner Command Error",
            f"```py\n{type(error).__name__}: {error}\n```",
            emoji_key="error",
            success=False,
        )


async def setup(bot: commands.Bot):
    bot.add_check(owner_global_check)
    await bot.add_cog(Owner(bot))