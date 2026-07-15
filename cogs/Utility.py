import asyncio
import copy
import json
import math
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
from discord.ext import commands, tasks


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_PATH = "database/utility.json"

ACCENT = discord.Color.from_rgb(198, 145, 73)
SUCCESS = discord.Color.from_rgb(72, 190, 120)
ERROR = discord.Color.from_rgb(220, 75, 75)
WARNING = discord.Color.from_rgb(235, 175, 65)

DURATION_PATTERN = re.compile(r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE)

DEFAULT_GUILD_DATA: dict[str, Any] = {
    "starboard": {
        "enabled": False,
        "channel_id": None,
        "emoji": "⭐",
        "threshold": 3,
        "allow_self_star": False,
        "posts": {},
    },
    "counting": {
        "enabled": False,
        "channel_id": None,
        "current": 0,
        "last_user_id": None,
        "high_score": 0,
        "fails": 0,
    },
    "leveling": {
        "enabled": True,
        "xp_min": 15,
        "xp_max": 25,
        "cooldown": 60,
        "announce_channel_id": None,
        "role_rewards": {},
        "users": {},
    },
    "economy": {
        "enabled": False,
        "currency_name": "coins",
        "currency_symbol": "🪙",
        "daily_min": 200,
        "daily_max": 500,
        "work_min": 100,
        "work_max": 300,
        "users": {},
        "shop": {},
    },
    "temporary_voice": {
        "enabled": False,
        "lobby_channel_id": None,
        "category_id": None,
        "channels": {},
    },
    "afk": {},
    "reminders": {},
    "polls": {},
}


# =========================================================
# DATABASE
# =========================================================

class UtilityDatabase:
    def __init__(self, path: str):
        self.path = path
        self.lock = asyncio.Lock()

        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(path):
            self._save({"guilds": {}})

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError

            data.setdefault("guilds", {})
            return data

        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = {"guilds": {}}
            self._save(data)
            return data

    def _save(self, data: dict[str, Any]) -> None:
        temporary = f"{self.path}.tmp"

        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

        os.replace(temporary, self.path)

    @classmethod
    def _merge_defaults(
        cls,
        target: dict[str, Any],
        defaults: dict[str, Any],
    ) -> bool:
        changed = False

        for key, default in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(default)
                changed = True

            elif isinstance(default, dict) and isinstance(target[key], dict):
                if cls._merge_defaults(target[key], default):
                    changed = True

        return changed

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )

            if self._merge_defaults(guild_data, DEFAULT_GUILD_DATA):
                self._save(data)

            return copy.deepcopy(guild_data)

    async def save_guild(
        self,
        guild_id: int,
        guild_data: dict[str, Any],
    ) -> None:
        async with self.lock:
            data = self._load()
            self._merge_defaults(guild_data, DEFAULT_GUILD_DATA)
            data["guilds"][str(guild_id)] = guild_data
            self._save(data)


utility_db = UtilityDatabase(DATABASE_PATH)


# =========================================================
# HELPERS
# =========================================================

def parse_duration(value: str) -> Optional[timedelta]:
    match = DURATION_PATTERN.fullmatch(value.strip())

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()

    if amount <= 0:
        return None

    return {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }[unit]


def readable_duration(value: timedelta) -> str:
    seconds = max(0, int(value.total_seconds()))

    units = [
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]

    parts = []

    for name, size in units:
        amount, seconds = divmod(seconds, size)

        if amount:
            parts.append(
                f"{amount} {name}{'s' if amount != 1 else ''}"
            )

        if len(parts) == 2:
            break

    return ", ".join(parts) or "0 seconds"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def format_relative(value: str) -> str:
    try:
        return discord.utils.format_dt(parse_iso(value), style="R")
    except (TypeError, ValueError):
        return "Unknown"


def xp_for_level(level: int) -> int:
    return 100 * level * level


def calculate_level(total_xp: int) -> int:
    return int(math.sqrt(max(0, total_xp) / 100))


def progress_bar(current: int, required: int, length: int = 12) -> str:
    if required <= 0:
        return "█" * length

    ratio = min(1, max(0, current / required))
    filled = round(ratio * length)
    return "█" * filled + "░" * (length - filled)


def safe_channel_name(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "voice"


def economy_user(section: dict[str, Any], user_id: int) -> dict[str, Any]:
    users = section.setdefault("users", {})
    key = str(user_id)

    users.setdefault(
        key,
        {
            "wallet": 0,
            "bank": 0,
            "last_daily": None,
            "last_work": None,
            "inventory": {},
            "total_earned": 0,
        },
    )

    return users[key]


def leveling_user(section: dict[str, Any], user_id: int) -> dict[str, Any]:
    users = section.setdefault("users", {})
    key = str(user_id)

    users.setdefault(
        key,
        {
            "xp": 0,
            "messages": 0,
            "last_xp_at": 0.0,
        },
    )

    return users[key]


# =========================================================
# COMPONENTS V2
# =========================================================

class UtilityResponse(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        success: bool = True,
        warning: bool = False,
    ):
        super().__init__(timeout=90)

        colour = WARNING if warning else (SUCCESS if success else ERROR)

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=colour,
            )
        )


async def interaction_reply(
    interaction: discord.Interaction,
    title: str,
    description: str,
    *,
    success: bool = True,
    warning: bool = False,
    ephemeral: bool = True,
):
    view = UtilityResponse(
        title,
        description,
        success=success,
        warning=warning,
    )

    if interaction.response.is_done():
        await interaction.followup.send(
            view=view,
            ephemeral=ephemeral,
        )
    else:
        await interaction.response.send_message(
            view=view,
            ephemeral=ephemeral,
        )


# =========================================================
# POLLS
# =========================================================

class PollVoteButton(discord.ui.Button):
    def __init__(
        self,
        cog: "UtilitySuite",
        guild_id: int,
        poll_id: str,
        option_index: int,
        label: str,
        emoji: str,
    ):
        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.option_index = option_index

        super().__init__(
            label=label[:80],
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=(
                f"monk_poll:{guild_id}:{poll_id}:{option_index}"
            ),
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.cog.vote_poll(
            interaction,
            self.poll_id,
            self.option_index,
        )


class PollView(discord.ui.LayoutView):
    EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    def __init__(
        self,
        cog: "UtilitySuite",
        guild_id: int,
        poll_id: str,
        poll: dict[str, Any],
    ):
        super().__init__(timeout=None)

        self.cog = cog
        self.guild_id = guild_id
        self.poll_id = poll_id
        self.poll = poll
        self.build()

    def build(self):
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(
            discord.ui.TextDisplay(
                f"## 📊 {self.poll['question']}"
            )
        )
        container.add_item(discord.ui.Separator())

        option_lines = []

        for index, option in enumerate(self.poll["options"]):
            voters = self.poll["votes"].get(str(index), [])
            option_lines.append(
                f"{self.EMOJIS[index]} **{option}** — `{len(voters)}` vote"
                f"{'s' if len(voters) != 1 else ''}"
            )

        container.add_item(
            discord.ui.TextDisplay(
                "\n".join(option_lines)
                + f"\n\n**Created by:** <@{self.poll['creator_id']}>"
                + (
                    f"\n**Ends:** {format_relative(self.poll['ends_at'])}"
                    if self.poll.get("ends_at")
                    else ""
                )
            )
        )

        container.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()

        for index, option in enumerate(self.poll["options"]):
            row.add_item(
                PollVoteButton(
                    self.cog,
                    self.guild_id,
                    self.poll_id,
                    index,
                    option,
                    self.EMOJIS[index],
                )
            )

        container.add_item(row)
        self.add_item(container)


# =========================================================
# UTILITY CONFIG PANEL
# =========================================================

class UtilityConfigView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "UtilitySuite",
        guild: discord.Guild,
        author_id: int,
    ):
        super().__init__(timeout=300)

        self.cog = cog
        self.guild = guild
        self.author_id = author_id
        self.build()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.author_id:
            await interaction_reply(
                interaction,
                "This Panel Is Not Yours",
                "Run the utility configuration command yourself.",
                success=False,
            )
            return False

        if not isinstance(interaction.user, discord.Member):
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction_reply(
                interaction,
                "Permission Denied",
                "You need **Administrator** permission.",
                success=False,
            )
            return False

        return True

    def build(self):
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(
            discord.ui.TextDisplay("## 📈 Monk Utility Configuration")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Configure Starboard, Counting, Leveling, Economy, "
                "and temporary voice channels using commands shown below."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "### Quick Setup Commands\n"
                "`mstarboard setup #channel 3`\n"
                "`mcounting setup #channel`\n"
                "`mleveling enable`\n"
                "`meconomy enable`\n"
                "`mtempvc setup <voice_channel_id> <category_id>`\n\n"
                "Use `mutilitystatus` to view the complete configuration."
            )
        )

        row = discord.ui.ActionRow()

        status = discord.ui.Button(
            label="View Status",
            emoji="📋",
            style=discord.ButtonStyle.primary,
        )
        close = discord.ui.Button(
            label="Close",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
        )

        status.callback = self.status
        close.callback = self.close

        row.add_item(status)
        row.add_item(close)
        container.add_item(row)

        self.add_item(container)

    async def status(
        self,
        interaction: discord.Interaction,
    ):
        description = await self.cog.build_status(
            interaction.guild
        )

        await interaction_reply(
            interaction,
            "Utility Status",
            description,
        )

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# UTILITY SUITE COG
# =========================================================

class UtilitySuite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.restore_task: Optional[asyncio.Task] = None

        self.reminder_loop.start()
        self.poll_loop.start()
        self.temp_vc_cleanup.start()

    async def cog_load(self):
        self.restore_task = asyncio.create_task(
            self.restore_persistent_views()
        )

    def cog_unload(self):
        self.reminder_loop.cancel()
        self.poll_loop.cancel()
        self.temp_vc_cleanup.cancel()

        if self.restore_task and not self.restore_task.done():
            self.restore_task.cancel()

    async def restore_persistent_views(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            guild_data = await utility_db.get_guild(guild.id)

            for poll_id, poll in guild_data["polls"].items():
                if poll.get("ended"):
                    continue

                message_id = poll.get("message_id")

                if not message_id:
                    continue

                self.bot.add_view(
                    PollView(
                        self,
                        guild.id,
                        poll_id,
                        poll,
                    ),
                    message_id=message_id,
                )

    async def build_status(
        self,
        guild: discord.Guild,
    ) -> str:
        data = await utility_db.get_guild(guild.id)

        starboard_channel = guild.get_channel(
            data["starboard"]["channel_id"]
        )
        counting_channel = guild.get_channel(
            data["counting"]["channel_id"]
        )
        level_channel = guild.get_channel(
            data["leveling"]["announce_channel_id"]
        )
        lobby = guild.get_channel(
            data["temporary_voice"]["lobby_channel_id"]
        )
        category = guild.get_channel(
            data["temporary_voice"]["category_id"]
        )

        return (
            f"⭐ **Starboard:** `{data['starboard']['enabled']}` • "
            f"{starboard_channel.mention if starboard_channel else '`Not set`'} • "
            f"Threshold `{data['starboard']['threshold']}`\n"
            f"🔢 **Counting:** `{data['counting']['enabled']}` • "
            f"{counting_channel.mention if counting_channel else '`Not set`'} • "
            f"Current `{data['counting']['current']}` • "
            f"High `{data['counting']['high_score']}`\n"
            f"📈 **Leveling:** `{data['leveling']['enabled']}` • "
            f"Announcement "
            f"{level_channel.mention if level_channel else '`Current channel`'}\n"
            f"🪙 **Economy:** `{data['economy']['enabled']}` • "
            f"Currency `{data['economy']['currency_symbol']} "
            f"{data['economy']['currency_name']}`\n"
            f"🔊 **Temporary VC:** `{data['temporary_voice']['enabled']}` • "
            f"Lobby {lobby.mention if lobby else '`Not set`'} • "
            f"Category `{category.name if isinstance(category, discord.CategoryChannel) else 'Not set'}`\n"
            f"⏰ **Reminders:** `{len(data['reminders'])}` active\n"
            f"📊 **Polls:** `{sum(not p.get('ended') for p in data['polls'].values())}` active"
        )

    # =====================================================
    # CONFIG
    # =====================================================

    @commands.command(
        name="utilityconfig",
        aliases=["uconfig"],
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def utility_config(
        self,
        ctx: commands.Context,
    ):
        await ctx.send(
            view=UtilityConfigView(
                self,
                ctx.guild,
                ctx.author.id,
            )
        )

    @commands.command(name="utilitystatus")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def utility_status(
        self,
        ctx: commands.Context,
    ):
        await ctx.send(
            view=UtilityResponse(
                "Utility Status",
                await self.build_status(ctx.guild),
            )
        )

    # =====================================================
    # AFK
    # =====================================================

    @commands.command(name="afk")
    @commands.guild_only()
    async def afk(
        self,
        ctx: commands.Context,
        *,
        reason: str = "AFK",
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["afk"][str(ctx.author.id)] = {
            "reason": reason[:500],
            "since": iso_now(),
        }
        await utility_db.save_guild(ctx.guild.id, guild_data)

        try:
            if isinstance(ctx.author, discord.Member):
                await ctx.author.edit(
                    nick=f"[AFK] {ctx.author.display_name}"[:32],
                    reason="AFK status enabled",
                )
        except discord.HTTPException:
            pass

        await ctx.send(
            view=UtilityResponse(
                "AFK Enabled",
                f"{ctx.author.mention}, you are now AFK.\n"
                f"**Reason:** {reason[:500]}",
            )
        )

    @commands.command(name="afklist")
    @commands.guild_only()
    async def afk_list(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        afk_users = guild_data["afk"]

        if not afk_users:
            return await ctx.send(
                view=UtilityResponse(
                    "AFK Members",
                    "Nobody is currently AFK.",
                )
            )

        lines = []

        for user_id, entry in list(afk_users.items())[:30]:
            lines.append(
                f"<@{user_id}> — {entry['reason']} • "
                f"{format_relative(entry['since'])}"
            )

        await ctx.send(
            view=UtilityResponse(
                f"AFK Members ({len(afk_users)})",
                "\n".join(lines),
            )
        )

    # =====================================================
    # REMINDERS
    # =====================================================

    @commands.command(
        name="remind",
        aliases=["reminder", "remindme"],
    )
    @commands.guild_only()
    async def remind(
        self,
        ctx: commands.Context,
        duration: str,
        *,
        reminder: str,
    ):
        parsed = parse_duration(duration)

        if not parsed:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Duration",
                    "Use formats such as `30s`, `10m`, `2h`, `3d`, or `1w`.",
                    success=False,
                )
            )

        if parsed > timedelta(days=365):
            return await ctx.send(
                view=UtilityResponse(
                    "Duration Too Long",
                    "Reminders can be scheduled up to one year ahead.",
                    success=False,
                )
            )

        guild_data = await utility_db.get_guild(ctx.guild.id)
        reminder_id = str(int(time.time() * 1000))

        due_at = utc_now() + parsed

        guild_data["reminders"][reminder_id] = {
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message": reminder[:1500],
            "created_at": iso_now(),
            "due_at": due_at.isoformat(),
        }

        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Reminder Created",
                f"I will remind you {discord.utils.format_dt(due_at, style='R')}.\n"
                f"**Reminder:** {reminder[:1500]}\n"
                f"**ID:** `{reminder_id}`",
            )
        )

    @commands.command(name="reminders")
    @commands.guild_only()
    async def reminders(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)

        user_reminders = [
            (reminder_id, reminder)
            for reminder_id, reminder in guild_data["reminders"].items()
            if reminder["user_id"] == ctx.author.id
        ]

        if not user_reminders:
            return await ctx.send(
                view=UtilityResponse(
                    "Your Reminders",
                    "You have no active reminders.",
                )
            )

        lines = []

        for reminder_id, reminder in user_reminders[:20]:
            lines.append(
                f"`{reminder_id}` • {format_relative(reminder['due_at'])}\n"
                f"{reminder['message']}"
            )

        await ctx.send(
            view=UtilityResponse(
                f"Your Reminders ({len(user_reminders)})",
                "\n\n".join(lines),
            )
        )

    @commands.command(name="cancelreminder")
    @commands.guild_only()
    async def cancel_reminder(
        self,
        ctx: commands.Context,
        reminder_id: str,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        reminder = guild_data["reminders"].get(reminder_id)

        if not reminder or reminder["user_id"] != ctx.author.id:
            return await ctx.send(
                view=UtilityResponse(
                    "Reminder Not Found",
                    "That reminder does not exist or does not belong to you.",
                    success=False,
                )
            )

        guild_data["reminders"].pop(reminder_id, None)
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Reminder Cancelled",
                f"Reminder `{reminder_id}` was removed.",
            )
        )

    # =====================================================
    # POLLS
    # =====================================================

    @commands.command(name="poll")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def poll(
        self,
        ctx: commands.Context,
        duration: str,
        question: str,
        *options: str,
    ):
        """
        Example:
        mpoll 1h "Best language?" "Python" "JavaScript" "Java"
        """

        parsed = parse_duration(duration)

        if not parsed:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Duration",
                    "Use `30m`, `2h`, `1d`, and similar formats.",
                    success=False,
                )
            )

        if len(options) < 2 or len(options) > 5:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Options",
                    "A poll requires between 2 and 5 quoted options.",
                    success=False,
                )
            )

        poll_id = str(int(time.time() * 1000))
        ends_at = utc_now() + parsed

        poll_data = {
            "question": question[:300],
            "options": [option[:80] for option in options],
            "creator_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message_id": None,
            "created_at": iso_now(),
            "ends_at": ends_at.isoformat(),
            "votes": {
                str(index): []
                for index in range(len(options))
            },
            "ended": False,
        }

        view = PollView(
            self,
            ctx.guild.id,
            poll_id,
            poll_data,
        )

        message = await ctx.send(view=view)
        poll_data["message_id"] = message.id

        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["polls"][poll_id] = poll_data
        await utility_db.save_guild(ctx.guild.id, guild_data)

        self.bot.add_view(view, message_id=message.id)

    async def vote_poll(
        self,
        interaction: discord.Interaction,
        poll_id: str,
        option_index: int,
    ):
        if not interaction.guild:
            return

        guild_data = await utility_db.get_guild(interaction.guild.id)
        poll = guild_data["polls"].get(poll_id)

        if not poll or poll.get("ended"):
            return await interaction_reply(
                interaction,
                "Poll Closed",
                "This poll is no longer accepting votes.",
                success=False,
            )

        user_id = interaction.user.id

        for voters in poll["votes"].values():
            if user_id in voters:
                voters.remove(user_id)

        poll["votes"][str(option_index)].append(user_id)
        guild_data["polls"][poll_id] = poll
        await utility_db.save_guild(interaction.guild.id, guild_data)

        view = PollView(
            self,
            interaction.guild.id,
            poll_id,
            poll,
        )

        await interaction.response.edit_message(view=view)

    # =====================================================
    # TEMPORARY VOICE
    # =====================================================

    @commands.group(
        name="tempvc",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def temp_vc(
        self,
        ctx: commands.Context,
    ):
        data = (await utility_db.get_guild(ctx.guild.id))[
            "temporary_voice"
        ]

        lobby = ctx.guild.get_channel(data["lobby_channel_id"])
        category = ctx.guild.get_channel(data["category_id"])

        await ctx.send(
            view=UtilityResponse(
                "Temporary Voice Configuration",
                f"**Enabled:** `{data['enabled']}`\n"
                f"**Lobby:** {lobby.mention if lobby else '`Not set`'}\n"
                f"**Category:** "
                f"`{category.name if isinstance(category, discord.CategoryChannel) else 'Not set'}`\n"
                f"**Active temporary channels:** `{len(data['channels'])}`\n\n"
                "`mtempvc setup <lobby_voice_id> <category_id>`\n"
                "`mtempvc disable`",
            )
        )

    @temp_vc.command(name="setup")
    @commands.has_permissions(manage_channels=True)
    async def temp_vc_setup(
        self,
        ctx: commands.Context,
        lobby_channel_id: int,
        category_id: int,
    ):
        lobby = ctx.guild.get_channel(lobby_channel_id)
        category = ctx.guild.get_channel(category_id)

        if not isinstance(lobby, discord.VoiceChannel):
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Lobby",
                    "The lobby ID must belong to a voice channel.",
                    success=False,
                )
            )

        if not isinstance(category, discord.CategoryChannel):
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Category",
                    "The category ID must belong to a category.",
                    success=False,
                )
            )

        guild_data = await utility_db.get_guild(ctx.guild.id)
        data = guild_data["temporary_voice"]
        data["enabled"] = True
        data["lobby_channel_id"] = lobby.id
        data["category_id"] = category.id
        guild_data["temporary_voice"] = data
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Temporary Voice Enabled",
                f"Joining {lobby.mention} now creates a private voice channel "
                f"inside `{category.name}`.",
            )
        )

    @temp_vc.command(name="disable")
    @commands.has_permissions(manage_channels=True)
    async def temp_vc_disable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["temporary_voice"]["enabled"] = False
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Temporary Voice Disabled",
                "New temporary voice channels will no longer be created.",
            )
        )

    @commands.command(name="vclock")
    @commands.guild_only()
    async def vc_lock(
        self,
        ctx: commands.Context,
    ):
        await self.manage_owned_vc(ctx, "lock")

    @commands.command(name="vcunlock")
    @commands.guild_only()
    async def vc_unlock(
        self,
        ctx: commands.Context,
    ):
        await self.manage_owned_vc(ctx, "unlock")

    @commands.command(name="vclimit")
    @commands.guild_only()
    async def vc_limit(
        self,
        ctx: commands.Context,
        limit: commands.Range[int, 0, 99],
    ):
        await self.manage_owned_vc(ctx, "limit", limit)

    @commands.command(name="vcrename")
    @commands.guild_only()
    async def vc_rename(
        self,
        ctx: commands.Context,
        *,
        name: str,
    ):
        await self.manage_owned_vc(ctx, "rename", name)

    async def manage_owned_vc(
        self,
        ctx: commands.Context,
        action: str,
        value: Any = None,
    ):
        if not isinstance(ctx.author, discord.Member):
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(
                view=UtilityResponse(
                    "Not Connected",
                    "Join your temporary voice channel first.",
                    success=False,
                )
            )

        guild_data = await utility_db.get_guild(ctx.guild.id)
        temp_data = guild_data["temporary_voice"]
        channel = ctx.author.voice.channel
        channel_data = temp_data["channels"].get(str(channel.id))

        if not channel_data or channel_data["owner_id"] != ctx.author.id:
            return await ctx.send(
                view=UtilityResponse(
                    "Not Channel Owner",
                    "Only the temporary voice channel owner can use this command.",
                    success=False,
                )
            )

        if action == "lock":
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.connect = False
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
            )
            result = "The voice channel is now locked."

        elif action == "unlock":
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.connect = None
            await channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
            )
            result = "The voice channel is now unlocked."

        elif action == "limit":
            await channel.edit(user_limit=value)
            result = f"The user limit is now `{value or 'Unlimited'}`."

        else:
            name = safe_channel_name(str(value)).replace("-", " ")[:100]
            await channel.edit(name=name)
            result = f"The voice channel was renamed to **{name}**."

        await ctx.send(
            view=UtilityResponse(
                "Voice Channel Updated",
                result,
            )
        )

    # =====================================================
    # STARBOARD
    # =====================================================

    @commands.group(
        name="starboard",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def starboard(
        self,
        ctx: commands.Context,
    ):
        data = (await utility_db.get_guild(ctx.guild.id))["starboard"]
        channel = ctx.guild.get_channel(data["channel_id"])

        await ctx.send(
            view=UtilityResponse(
                "Starboard Configuration",
                f"**Enabled:** `{data['enabled']}`\n"
                f"**Channel:** {channel.mention if channel else '`Not set`'}\n"
                f"**Emoji:** {data['emoji']}\n"
                f"**Threshold:** `{data['threshold']}`\n"
                f"**Self-star allowed:** `{data['allow_self_star']}`\n\n"
                "`mstarboard setup #channel 3`\n"
                "`mstarboard disable`",
            )
        )

    @starboard.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def starboard_setup(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        threshold: commands.Range[int, 1, 50] = 3,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        data = guild_data["starboard"]
        data["enabled"] = True
        data["channel_id"] = channel.id
        data["threshold"] = threshold
        guild_data["starboard"] = data
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Starboard Enabled",
                f"Messages with at least `{threshold}` ⭐ reactions will appear "
                f"in {channel.mention}.",
            )
        )

    @starboard.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def starboard_disable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["starboard"]["enabled"] = False
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Starboard Disabled",
                "Starboard posting has been disabled.",
            )
        )

    # =====================================================
    # COUNTING
    # =====================================================

    @commands.group(
        name="counting",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def counting(
        self,
        ctx: commands.Context,
    ):
        data = (await utility_db.get_guild(ctx.guild.id))["counting"]
        channel = ctx.guild.get_channel(data["channel_id"])

        await ctx.send(
            view=UtilityResponse(
                "Counting Configuration",
                f"**Enabled:** `{data['enabled']}`\n"
                f"**Channel:** {channel.mention if channel else '`Not set`'}\n"
                f"**Current number:** `{data['current']}`\n"
                f"**High score:** `{data['high_score']}`\n"
                f"**Failed runs:** `{data['fails']}`\n\n"
                "`mcounting setup #channel`\n"
                "`mcounting reset`\n"
                "`mcounting disable`",
            )
        )

    @counting.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def counting_setup(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        data = guild_data["counting"]
        data["enabled"] = True
        data["channel_id"] = channel.id
        data["current"] = 0
        data["last_user_id"] = None
        guild_data["counting"] = data
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Counting Enabled",
                f"Counting will begin at `1` in {channel.mention}. "
                "The same user cannot count twice in a row.",
            )
        )

    @counting.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def counting_reset(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["counting"]["current"] = 0
        guild_data["counting"]["last_user_id"] = None
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Counting Reset",
                "The next valid number is `1`.",
            )
        )

    @counting.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def counting_disable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["counting"]["enabled"] = False
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Counting Disabled",
                "The counting system is now disabled.",
            )
        )

    # =====================================================
    # LEVELING
    # =====================================================

    @commands.group(
        name="leveling",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def leveling(
        self,
        ctx: commands.Context,
    ):
        data = (await utility_db.get_guild(ctx.guild.id))["leveling"]

        await ctx.send(
            view=UtilityResponse(
                "Leveling Configuration",
                f"**Enabled:** `{data['enabled']}`\n"
                f"**XP per message:** `{data['xp_min']}-{data['xp_max']}`\n"
                f"**Cooldown:** `{data['cooldown']}s`\n"
                f"**Tracked users:** `{len(data['users'])}`\n"
                f"**Role rewards:** `{len(data['role_rewards'])}`\n\n"
                "`mleveling enable`\n"
                "`mleveling disable`\n"
                "`mlevelrole 10 @role`",
            )
        )

    @leveling.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def leveling_enable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["leveling"]["enabled"] = True
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Leveling Enabled",
                "Members will now earn XP from messages.",
            )
        )

    @leveling.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def leveling_disable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["leveling"]["enabled"] = False
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Leveling Disabled",
                "Members will no longer earn XP.",
            )
        )

    @commands.command(
        name="rank",
        aliases=["level"],
    )
    @commands.guild_only()
    async def rank(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        member = member or ctx.author

        guild_data = await utility_db.get_guild(ctx.guild.id)
        section = guild_data["leveling"]
        user = leveling_user(section, member.id)

        level = calculate_level(user["xp"])
        current_base = xp_for_level(level)
        next_base = xp_for_level(level + 1)
        current_progress = user["xp"] - current_base
        needed = next_base - current_base

        await ctx.send(
            view=UtilityResponse(
                f"Rank — {member}",
                f"**Level:** `{level}`\n"
                f"**Total XP:** `{user['xp']}`\n"
                f"**Messages:** `{user['messages']}`\n"
                f"**Progress:** `{progress_bar(current_progress, needed)}` "
                f"`{current_progress}/{needed}`",
            )
        )

    @commands.command(name="levelboard")
    @commands.guild_only()
    async def level_board(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        users = guild_data["leveling"]["users"]

        ranking = sorted(
            users.items(),
            key=lambda item: item[1]["xp"],
            reverse=True,
        )[:10]

        if not ranking:
            return await ctx.send(
                view=UtilityResponse(
                    "Level Leaderboard",
                    "Nobody has earned XP yet.",
                )
            )

        lines = []

        for position, (user_id, data) in enumerate(ranking, start=1):
            lines.append(
                f"`#{position}` <@{user_id}> — Level "
                f"`{calculate_level(data['xp'])}` • `{data['xp']} XP`"
            )

        await ctx.send(
            view=UtilityResponse(
                "🏆 Level Leaderboard",
                "\n".join(lines),
            )
        )

    @commands.command(name="levelrole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def level_role(
        self,
        ctx: commands.Context,
        level: commands.Range[int, 1, 500],
        role: discord.Role,
    ):
        if role >= ctx.guild.me.top_role or role.managed:
            return await ctx.send(
                view=UtilityResponse(
                    "Role Hierarchy Error",
                    "My highest role must be above the reward role.",
                    success=False,
                )
            )

        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["leveling"]["role_rewards"][str(level)] = role.id
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Level Reward Added",
                f"{role.mention} will be awarded at level `{level}`.",
            )
        )

    # =====================================================
    # ECONOMY
    # =====================================================

    @commands.group(
        name="economy",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def economy(
        self,
        ctx: commands.Context,
    ):
        section = (await utility_db.get_guild(ctx.guild.id))["economy"]

        await ctx.send(
            view=UtilityResponse(
                "Economy Configuration",
                f"**Enabled:** `{section['enabled']}`\n"
                f"**Currency:** {section['currency_symbol']} "
                f"`{section['currency_name']}`\n"
                f"**Users:** `{len(section['users'])}`\n"
                f"**Shop items:** `{len(section['shop'])}`\n\n"
                "`meconomy enable`\n"
                "`meconomy disable`\n"
                "`meconomy currency 🪙 coins`",
            )
        )

    @economy.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def economy_enable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["economy"]["enabled"] = True
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Economy Enabled",
                "Economy commands are now available.",
            )
        )

    @economy.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def economy_disable(
        self,
        ctx: commands.Context,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["economy"]["enabled"] = False
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Economy Disabled",
                "Economy commands are now disabled.",
            )
        )

    @economy.command(name="currency")
    @commands.has_permissions(manage_guild=True)
    async def economy_currency(
        self,
        ctx: commands.Context,
        symbol: str,
        *,
        name: str,
    ):
        guild_data = await utility_db.get_guild(ctx.guild.id)
        guild_data["economy"]["currency_symbol"] = symbol[:20]
        guild_data["economy"]["currency_name"] = name[:30]
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Currency Updated",
                f"The currency is now {symbol[:20]} **{name[:30]}**.",
            )
        )

    async def require_economy(
        self,
        ctx: commands.Context,
    ) -> Optional[dict[str, Any]]:
        guild_data = await utility_db.get_guild(ctx.guild.id)

        if not guild_data["economy"]["enabled"]:
            await ctx.send(
                view=UtilityResponse(
                    "Economy Disabled",
                    "An administrator must run `meconomy enable` first.",
                    success=False,
                )
            )
            return None

        return guild_data

    @commands.command(
        name="balance",
        aliases=["bal", "wallet"],
    )
    @commands.guild_only()
    async def balance(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        member = member or ctx.author
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        user = economy_user(section, member.id)
        symbol = section["currency_symbol"]

        await ctx.send(
            view=UtilityResponse(
                f"Balance — {member}",
                f"**Wallet:** {symbol} `{user['wallet']:,}`\n"
                f"**Bank:** {symbol} `{user['bank']:,}`\n"
                f"**Net worth:** {symbol} "
                f"`{user['wallet'] + user['bank']:,}`\n"
                f"**Total earned:** {symbol} `{user['total_earned']:,}`",
            )
        )

    @commands.command(name="daily")
    @commands.guild_only()
    async def daily(
        self,
        ctx: commands.Context,
    ):
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        user = economy_user(section, ctx.author.id)
        now = utc_now()

        if user["last_daily"]:
            last = parse_iso(user["last_daily"])
            remaining = timedelta(hours=24) - (now - last)

            if remaining.total_seconds() > 0:
                return await ctx.send(
                    view=UtilityResponse(
                        "Daily Already Claimed",
                        f"Try again in **{readable_duration(remaining)}**.",
                        success=False,
                    )
                )

        reward = random.randint(
            section["daily_min"],
            section["daily_max"],
        )

        user["wallet"] += reward
        user["total_earned"] += reward
        user["last_daily"] = now.isoformat()
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Daily Reward",
                f"You received {section['currency_symbol']} `{reward:,}`.",
            )
        )

    @commands.command(name="work")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def work(
        self,
        ctx: commands.Context,
    ):
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        user = economy_user(section, ctx.author.id)

        reward = random.randint(
            section["work_min"],
            section["work_max"],
        )

        jobs = [
            "fixed a production bug",
            "moderated a busy server",
            "designed a shiny Discord panel",
            "helped a confused developer",
            "trained an extremely stubborn bot",
        ]

        user["wallet"] += reward
        user["total_earned"] += reward
        user["last_work"] = iso_now()
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Work Completed",
                f"You {random.choice(jobs)} and earned "
                f"{section['currency_symbol']} `{reward:,}`.",
            )
        )

    @commands.command(name="deposit")
    @commands.guild_only()
    async def deposit(
        self,
        ctx: commands.Context,
        amount: int,
    ):
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        user = economy_user(section, ctx.author.id)

        if amount <= 0 or amount > user["wallet"]:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Amount",
                    "Enter an amount available in your wallet.",
                    success=False,
                )
            )

        user["wallet"] -= amount
        user["bank"] += amount
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Deposit Complete",
                f"Deposited {section['currency_symbol']} `{amount:,}`.",
            )
        )

    @commands.command(name="withdraw")
    @commands.guild_only()
    async def withdraw(
        self,
        ctx: commands.Context,
        amount: int,
    ):
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        user = economy_user(section, ctx.author.id)

        if amount <= 0 or amount > user["bank"]:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Amount",
                    "Enter an amount available in your bank.",
                    success=False,
                )
            )

        user["bank"] -= amount
        user["wallet"] += amount
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Withdrawal Complete",
                f"Withdrew {section['currency_symbol']} `{amount:,}`.",
            )
        )

    @commands.command(name="pay")
    @commands.guild_only()
    async def pay(
        self,
        ctx: commands.Context,
        member: discord.Member,
        amount: int,
    ):
        if member.bot or member == ctx.author:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Recipient",
                    "Choose another non-bot member.",
                    success=False,
                )
            )

        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]
        sender = economy_user(section, ctx.author.id)
        recipient = economy_user(section, member.id)

        if amount <= 0 or amount > sender["wallet"]:
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Amount",
                    "Enter an amount available in your wallet.",
                    success=False,
                )
            )

        sender["wallet"] -= amount
        recipient["wallet"] += amount
        await utility_db.save_guild(ctx.guild.id, guild_data)

        await ctx.send(
            view=UtilityResponse(
                "Payment Sent",
                f"Sent {section['currency_symbol']} `{amount:,}` "
                f"to {member.mention}.",
            )
        )

    @commands.command(name="economyboard")
    @commands.guild_only()
    async def economy_board(
        self,
        ctx: commands.Context,
    ):
        guild_data = await self.require_economy(ctx)

        if not guild_data:
            return

        section = guild_data["economy"]

        ranking = sorted(
            section["users"].items(),
            key=lambda item: item[1]["wallet"] + item[1]["bank"],
            reverse=True,
        )[:10]

        if not ranking:
            return await ctx.send(
                view=UtilityResponse(
                    "Economy Leaderboard",
                    "Nobody has earned currency yet.",
                )
            )

        lines = []

        for position, (user_id, user) in enumerate(ranking, start=1):
            net = user["wallet"] + user["bank"]
            lines.append(
                f"`#{position}` <@{user_id}> — "
                f"{section['currency_symbol']} `{net:,}`"
            )

        await ctx.send(
            view=UtilityResponse(
                "💰 Economy Leaderboard",
                "\n".join(lines),
            )
        )

    # =====================================================
    # EVENTS
    # =====================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):
        if not message.guild or message.author.bot:
            return

        guild_data = await utility_db.get_guild(message.guild.id)
        changed = False

        # AFK return
        afk_entry = guild_data["afk"].pop(
            str(message.author.id),
            None,
        )

        if afk_entry:
            changed = True

            try:
                if isinstance(message.author, discord.Member):
                    nickname = message.author.display_name

                    if nickname.startswith("[AFK] "):
                        nickname = nickname[6:]

                    await message.author.edit(
                        nick=nickname[:32],
                        reason="AFK status removed",
                    )
            except discord.HTTPException:
                pass

            try:
                await message.channel.send(
                    view=UtilityResponse(
                        "Welcome Back",
                        f"{message.author.mention}, your AFK status was removed. "
                        f"You were away since {format_relative(afk_entry['since'])}.",
                    ),
                    delete_after=8,
                )
            except discord.HTTPException:
                pass

        # AFK mentions
        mentioned_afk = []

        for member in message.mentions[:10]:
            entry = guild_data["afk"].get(str(member.id))

            if entry:
                mentioned_afk.append(
                    f"{member.mention} is AFK: **{entry['reason']}** • "
                    f"{format_relative(entry['since'])}"
                )

        if mentioned_afk:
            try:
                await message.reply(
                    view=UtilityResponse(
                        "AFK Notice",
                        "\n".join(mentioned_afk),
                        warning=True,
                    ),
                    mention_author=False,
                    delete_after=12,
                )
            except discord.HTTPException:
                pass

        # Counting
        counting = guild_data["counting"]

        if (
            counting["enabled"]
            and message.channel.id == counting["channel_id"]
        ):
            await self.handle_counting(
                message,
                guild_data,
            )
            return

        # Leveling
        leveling = guild_data["leveling"]

        if leveling["enabled"]:
            user = leveling_user(
                leveling,
                message.author.id,
            )

            user["messages"] += 1
            now = time.time()

            if now - user["last_xp_at"] >= leveling["cooldown"]:
                old_level = calculate_level(user["xp"])
                gained = random.randint(
                    leveling["xp_min"],
                    leveling["xp_max"],
                )

                user["xp"] += gained
                user["last_xp_at"] = now
                new_level = calculate_level(user["xp"])
                changed = True

                if new_level > old_level:
                    await self.handle_level_up(
                        message,
                        guild_data,
                        new_level,
                    )
            else:
                changed = True

        if changed:
            await utility_db.save_guild(
                message.guild.id,
                guild_data,
            )

    async def handle_counting(
        self,
        message: discord.Message,
        guild_data: dict[str, Any],
    ):
        data = guild_data["counting"]
        expected = data["current"] + 1

        try:
            supplied = int(message.content.strip())
        except ValueError:
            await message.delete()
            return

        valid = (
            supplied == expected
            and data["last_user_id"] != message.author.id
        )

        if valid:
            data["current"] = supplied
            data["last_user_id"] = message.author.id
            data["high_score"] = max(
                data["high_score"],
                supplied,
            )

            await utility_db.save_guild(
                message.guild.id,
                guild_data,
            )

            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass

            if supplied % 100 == 0:
                await message.channel.send(
                    view=UtilityResponse(
                        "Counting Milestone",
                        f"The server reached **{supplied:,}**! 🎉",
                    )
                )

        else:
            data["fails"] += 1
            previous = data["current"]
            data["current"] = 0
            data["last_user_id"] = None

            await utility_db.save_guild(
                message.guild.id,
                guild_data,
            )

            try:
                await message.add_reaction("❌")
                await message.channel.send(
                    view=UtilityResponse(
                        "Counting Failed",
                        f"{message.author.mention} broke the count at "
                        f"`{previous}`.\nThe next number is `1`.",
                        success=False,
                    )
                )
            except discord.HTTPException:
                pass

    async def handle_level_up(
        self,
        message: discord.Message,
        guild_data: dict[str, Any],
        new_level: int,
    ):
        leveling = guild_data["leveling"]
        reward_role_id = leveling["role_rewards"].get(
            str(new_level)
        )
        reward_text = ""

        if reward_role_id and isinstance(
            message.author,
            discord.Member,
        ):
            role = message.guild.get_role(reward_role_id)

            if role and role < message.guild.me.top_role:
                try:
                    await message.author.add_roles(
                        role,
                        reason=f"Reached level {new_level}",
                    )
                    reward_text = f"\n**Reward:** {role.mention}"
                except discord.HTTPException:
                    pass

        announce_channel = message.guild.get_channel(
            leveling["announce_channel_id"]
        )

        if not isinstance(announce_channel, discord.TextChannel):
            announce_channel = message.channel

        try:
            await announce_channel.send(
                view=UtilityResponse(
                    "Level Up!",
                    f"🎉 {message.author.mention} reached level "
                    f"**{new_level}**!{reward_text}",
                )
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return

        await self.update_starboard(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        if not payload.guild_id:
            return

        await self.update_starboard(payload)

    async def update_starboard(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        guild = self.bot.get_guild(payload.guild_id)

        if not guild:
            return

        guild_data = await utility_db.get_guild(guild.id)
        data = guild_data["starboard"]

        if not data["enabled"]:
            return

        if str(payload.emoji) != data["emoji"]:
            return

        source_channel = guild.get_channel(payload.channel_id)
        starboard_channel = guild.get_channel(data["channel_id"])

        if (
            not isinstance(source_channel, discord.TextChannel)
            or not isinstance(starboard_channel, discord.TextChannel)
            or source_channel.id == starboard_channel.id
        ):
            return

        try:
            message = await source_channel.fetch_message(
                payload.message_id
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if (
            not data["allow_self_star"]
            and payload.user_id == message.author.id
        ):
            return

        reaction = discord.utils.get(
            message.reactions,
            emoji=data["emoji"],
        )
        count = reaction.count if reaction else 0
        existing_id = data["posts"].get(str(message.id))

        if count < data["threshold"]:
            if existing_id:
                try:
                    existing = await starboard_channel.fetch_message(
                        existing_id
                    )
                    await existing.delete()
                except discord.HTTPException:
                    pass

                data["posts"].pop(str(message.id), None)
                await utility_db.save_guild(guild.id, guild_data)

            return

        content = message.content or "*No text content*"
        attachment_text = ""

        if message.attachments:
            attachment_text = (
                f"\n\n**Attachment:** {message.attachments[0].url}"
            )

        view = UtilityResponse(
            f"{data['emoji']} {count} • #{source_channel.name}",
            f"**Author:** {message.author.mention}\n"
            f"**Message:** {content[:2500]}{attachment_text}\n\n"
            f"[Jump to message]({message.jump_url})",
        )

        if existing_id:
            try:
                existing = await starboard_channel.fetch_message(
                    existing_id
                )
                await existing.edit(view=view)
                return
            except discord.HTTPException:
                data["posts"].pop(str(message.id), None)

        posted = await starboard_channel.send(view=view)
        data["posts"][str(message.id)] = posted.id
        await utility_db.save_guild(guild.id, guild_data)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        guild_data = await utility_db.get_guild(member.guild.id)
        data = guild_data["temporary_voice"]

        if not data["enabled"]:
            return

        if (
            after.channel
            and after.channel.id == data["lobby_channel_id"]
        ):
            category = member.guild.get_channel(
                data["category_id"]
            )

            if not isinstance(category, discord.CategoryChannel):
                return

            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                ),
                member: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                ),
                member.guild.me: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    manage_channels=True,
                    move_members=True,
                ),
            }

            try:
                channel = await member.guild.create_voice_channel(
                    name=f"{member.display_name}'s VC"[:100],
                    category=category,
                    overwrites=overwrites,
                    reason=f"Temporary VC for {member}",
                )

                data["channels"][str(channel.id)] = {
                    "owner_id": member.id,
                    "created_at": iso_now(),
                }

                guild_data["temporary_voice"] = data
                await utility_db.save_guild(
                    member.guild.id,
                    guild_data,
                )

                await member.move_to(channel)

            except discord.HTTPException:
                pass

        if before.channel:
            channel_data = data["channels"].get(
                str(before.channel.id)
            )

            if channel_data and not before.channel.members:
                try:
                    await before.channel.delete(
                        reason="Empty temporary voice channel",
                    )
                except discord.HTTPException:
                    return

                data["channels"].pop(
                    str(before.channel.id),
                    None,
                )
                guild_data["temporary_voice"] = data
                await utility_db.save_guild(
                    member.guild.id,
                    guild_data,
                )

    # =====================================================
    # BACKGROUND TASKS
    # =====================================================

    @tasks.loop(seconds=15)
    async def reminder_loop(self):
        now = utc_now()

        for guild in self.bot.guilds:
            guild_data = await utility_db.get_guild(guild.id)
            changed = False

            for reminder_id, reminder in list(
                guild_data["reminders"].items()
            ):
                try:
                    due_at = parse_iso(reminder["due_at"])
                except (TypeError, ValueError):
                    guild_data["reminders"].pop(reminder_id, None)
                    changed = True
                    continue

                if due_at > now:
                    continue

                channel = guild.get_channel(reminder["channel_id"])
                user = guild.get_member(reminder["user_id"])

                if user is None:
                    try:
                        user = await self.bot.fetch_user(
                            reminder["user_id"]
                        )
                    except discord.HTTPException:
                        user = None

                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(
                            content=user.mention if user else None,
                            view=UtilityResponse(
                                "⏰ Reminder",
                                f"**Reminder:** {reminder['message']}\n"
                                f"**Created:** "
                                f"{format_relative(reminder['created_at'])}",
                            ),
                            allowed_mentions=discord.AllowedMentions(
                                users=True,
                            ),
                        )
                    except discord.HTTPException:
                        pass
                elif user:
                    try:
                        await user.send(
                            view=UtilityResponse(
                                "⏰ Reminder",
                                reminder["message"],
                            )
                        )
                    except discord.HTTPException:
                        pass

                guild_data["reminders"].pop(reminder_id, None)
                changed = True

            if changed:
                await utility_db.save_guild(
                    guild.id,
                    guild_data,
                )

    @tasks.loop(seconds=20)
    async def poll_loop(self):
        now = utc_now()

        for guild in self.bot.guilds:
            guild_data = await utility_db.get_guild(guild.id)
            changed = False

            for poll_id, poll in guild_data["polls"].items():
                if poll.get("ended") or not poll.get("ends_at"):
                    continue

                try:
                    ends_at = parse_iso(poll["ends_at"])
                except (TypeError, ValueError):
                    continue

                if ends_at > now:
                    continue

                poll["ended"] = True
                changed = True

                channel = guild.get_channel(poll["channel_id"])

                if isinstance(channel, discord.TextChannel):
                    totals = {
                        int(index): len(voters)
                        for index, voters in poll["votes"].items()
                    }
                    max_votes = max(totals.values(), default=0)
                    winners = [
                        poll["options"][index]
                        for index, votes in totals.items()
                        if votes == max_votes
                    ]

                    result = (
                        ", ".join(f"**{winner}**" for winner in winners)
                        if max_votes
                        else "No votes were cast"
                    )

                    try:
                        message = await channel.fetch_message(
                            poll["message_id"]
                        )
                        await message.edit(view=None)

                        await channel.send(
                            view=UtilityResponse(
                                "Poll Ended",
                                f"**Question:** {poll['question']}\n"
                                f"**Winner:** {result}\n"
                                f"**Winning votes:** `{max_votes}`",
                            )
                        )
                    except discord.HTTPException:
                        pass

            if changed:
                await utility_db.save_guild(
                    guild.id,
                    guild_data,
                )

    @tasks.loop(minutes=5)
    async def temp_vc_cleanup(self):
        for guild in self.bot.guilds:
            guild_data = await utility_db.get_guild(guild.id)
            data = guild_data["temporary_voice"]
            changed = False

            for channel_id in list(data["channels"]):
                channel = guild.get_channel(int(channel_id))

                if not isinstance(channel, discord.VoiceChannel):
                    data["channels"].pop(channel_id, None)
                    changed = True
                    continue

                if not channel.members:
                    try:
                        await channel.delete(
                            reason="Temporary VC cleanup",
                        )
                    except discord.HTTPException:
                        continue

                    data["channels"].pop(channel_id, None)
                    changed = True

            if changed:
                guild_data["temporary_voice"] = data
                await utility_db.save_guild(
                    guild.id,
                    guild_data,
                )

    @reminder_loop.before_loop
    @poll_loop.before_loop
    @temp_vc_cleanup.before_loop
    async def before_background_tasks(self):
        await self.bot.wait_until_ready()

    # =====================================================
    # ERRORS
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                view=UtilityResponse(
                    "Command On Cooldown",
                    f"Try again in `{error.retry_after:.1f}` seconds.",
                    success=False,
                )
            )

        if isinstance(error, commands.MissingPermissions):
            permissions = ", ".join(
                permission.replace("_", " ").title()
                for permission in error.missing_permissions
            )

            return await ctx.send(
                view=UtilityResponse(
                    "Missing Permissions",
                    f"You need: **{permissions}**.",
                    success=False,
                )
            )

        if isinstance(error, commands.MemberNotFound):
            return await ctx.send(
                view=UtilityResponse(
                    "Member Not Found",
                    "Mention a valid server member.",
                    success=False,
                )
            )

        if isinstance(error, commands.ChannelNotFound):
            return await ctx.send(
                view=UtilityResponse(
                    "Channel Not Found",
                    "Mention a valid channel.",
                    success=False,
                )
            )

        if isinstance(error, commands.RoleNotFound):
            return await ctx.send(
                view=UtilityResponse(
                    "Role Not Found",
                    "Mention a valid role.",
                    success=False,
                )
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(
                view=UtilityResponse(
                    "Missing Argument",
                    f"You did not provide `{error.param.name}`.",
                    success=False,
                )
            )

        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                view=UtilityResponse(
                    "Invalid Argument",
                    "One or more supplied arguments are invalid.",
                    success=False,
                )
            )

        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilitySuite(bot))