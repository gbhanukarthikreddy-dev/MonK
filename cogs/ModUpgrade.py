import asyncio
import copy
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
from discord.ext import commands, tasks

from cogs.modules import is_module_disabled


DATABASE_PATH = "database/advanced_moderation.json"

ACCENT = discord.Color.from_rgb(198, 145, 73)
SUCCESS = discord.Color.from_rgb(72, 190, 120)
ERROR = discord.Color.from_rgb(220, 75, 75)
WARNING = discord.Color.from_rgb(235, 175, 65)

URL_PATTERN = re.compile(
    r"(https?://|www\.)\S+",
    re.IGNORECASE,
)

INVITE_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)

DURATION_PATTERN = re.compile(r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE)

DEFAULT_GUILD_DATA: dict[str, Any] = {
    "case_counter": 0,
    "cases": [],
    "automod": {
        "enabled": False,
        "anti_spam": True,
        "anti_link": False,
        "anti_invite": True,
        "anti_mass_mention": True,
        "spam_messages": 6,
        "spam_window": 8,
        "mention_limit": 5,
        "action": "timeout",
        "timeout_seconds": 600,
        "ignored_channels": [],
        "ignored_roles": [],
    },
    "jail": {
        "role_id": None,
        "saved_roles": {},
    },
    "temporary_roles": {},
    "sticky_messages": {},
    "nickname_locks": {},
    "lockdown": {
        "active": False,
        "channels": {},
    },
}


# =========================================================
# DATABASE
# =========================================================

class AdvancedModerationDatabase:
    def __init__(self, path: str):
        self.path = path
        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(path):
            self._save({"guilds": {}})

        self.lock = asyncio.Lock()

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

    @staticmethod
    def _merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> bool:
        changed = False

        for key, default in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(default)
                changed = True

            elif isinstance(default, dict) and isinstance(target[key], dict):
                if AdvancedModerationDatabase._merge_defaults(target[key], default):
                    changed = True

        return changed

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self.lock:
            data = self._load()
            key = str(guild_id)
            guild_data = data["guilds"].setdefault(
                key,
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )

            if self._merge_defaults(guild_data, DEFAULT_GUILD_DATA):
                self._save(data)

            return copy.deepcopy(guild_data)

    async def set_value(
        self,
        guild_id: int,
        section: str,
        key: str,
        value: Any,
    ) -> None:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )
            self._merge_defaults(guild_data, DEFAULT_GUILD_DATA)

            guild_data[section][key] = value
            self._save(data)

    async def replace_section(
        self,
        guild_id: int,
        section: str,
        value: Any,
    ) -> None:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )
            self._merge_defaults(guild_data, DEFAULT_GUILD_DATA)

            guild_data[section] = value
            self._save(data)

    async def create_case(
        self,
        guild_id: int,
        *,
        action: str,
        target_id: int,
        moderator_id: int,
        reason: str,
        duration: Optional[str] = None,
        extra: Optional[str] = None,
    ) -> dict[str, Any]:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )
            self._merge_defaults(guild_data, DEFAULT_GUILD_DATA)

            guild_data["case_counter"] += 1

            case = {
                "case_id": guild_data["case_counter"],
                "action": action,
                "target_id": target_id,
                "moderator_id": moderator_id,
                "reason": reason,
                "duration": duration,
                "extra": extra,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            guild_data["cases"].append(case)
            guild_data["cases"] = guild_data["cases"][-2000:]
            self._save(data)

            return copy.deepcopy(case)

    async def get_cases(
        self,
        guild_id: int,
        *,
        target_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        guild_data = await self.get_guild(guild_id)
        cases = guild_data["cases"]

        if target_id is not None:
            cases = [
                case
                for case in cases
                if case["target_id"] == target_id
            ]

        return list(reversed(cases))

    async def get_case(
        self,
        guild_id: int,
        case_id: int,
    ) -> Optional[dict[str, Any]]:
        cases = await self.get_cases(guild_id)

        for case in cases:
            if case["case_id"] == case_id:
                return case

        return None


database = AdvancedModerationDatabase(DATABASE_PATH)


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

    mapping = {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }

    return mapping[unit]


def format_duration(value: timedelta) -> str:
    seconds = int(value.total_seconds())

    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"

    return f"{seconds}s"


def clean_reason(reason: Optional[str]) -> str:
    return (reason or "No reason provided")[:1000]


def member_hierarchy_error(
    moderator: discord.Member,
    target: discord.Member,
    bot_member: discord.Member,
) -> Optional[str]:
    if target == moderator:
        return "You cannot moderate yourself."

    if target == moderator.guild.owner:
        return "The server owner cannot be moderated."

    if target == bot_member:
        return "I cannot moderate myself."

    if (
        moderator != moderator.guild.owner
        and target.top_role >= moderator.top_role
    ):
        return "The target's highest role is equal to or above yours."

    if target.top_role >= bot_member.top_role:
        return "My role must be above the target's highest role."

    return None


def role_hierarchy_error(
    guild: discord.Guild,
    moderator: discord.Member,
    role: discord.Role,
) -> Optional[str]:
    bot_member = guild.me

    if role.is_default():
        return "The `@everyone` role cannot be used."

    if role.managed:
        return "Managed integration roles cannot be assigned manually."

    if role >= bot_member.top_role:
        return "My role must be above that role."

    if moderator != guild.owner and role >= moderator.top_role:
        return "You cannot manage a role equal to or above your highest role."

    return None


def safe_text(value: Optional[str], limit: int = 900) -> str:
    value = value or "*No content*"
    value = discord.utils.escape_mentions(value)
    return value[:limit]


def timestamp_from_iso(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return discord.utils.format_dt(dt, style="R")

    except ValueError:
        return "Unknown"


async def try_dm(user: discord.abc.User, title: str, description: str) -> None:
    try:
        await user.send(
            view=ResponseView(title, description)
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


# =========================================================
# COMPONENTS V2
# =========================================================

class ResponseView(discord.ui.LayoutView):
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


class CaseHistoryView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        cases: list[dict[str, Any]],
        member: Optional[discord.abc.User],
    ):
        super().__init__(timeout=180)

        self.ctx = ctx
        self.cases = cases
        self.member = member
        self.page = 0
        self.per_page = 5

        self.build()

    @property
    def max_page(self) -> int:
        if not self.cases:
            return 0

        return (len(self.cases) - 1) // self.per_page

    def build(self) -> None:
        self.clear_items()

        start = self.page * self.per_page
        current = self.cases[start:start + self.per_page]

        title = (
            f"Punishment History — {self.member}"
            if self.member
            else "Server Case History"
        )

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(discord.ui.TextDisplay(f"## 📚 {title}"))
        container.add_item(discord.ui.Separator())

        if not current:
            container.add_item(
                discord.ui.TextDisplay("No moderation cases were found.")
            )
        else:
            sections = []

            for case in current:
                duration = (
                    f"\n**Duration:** `{case['duration']}`"
                    if case.get("duration")
                    else ""
                )
                extra = (
                    f"\n**Details:** {safe_text(case['extra'], 300)}"
                    if case.get("extra")
                    else ""
                )

                sections.append(
                    f"### Case #{case['case_id']} — {case['action']}\n"
                    f"**Target:** <@{case['target_id']}> (`{case['target_id']}`)\n"
                    f"**Moderator:** <@{case['moderator_id']}>\n"
                    f"**Reason:** {safe_text(case['reason'], 500)}"
                    f"{duration}{extra}\n"
                    f"**Created:** {timestamp_from_iso(case['created_at'])}"
                )

            container.add_item(
                discord.ui.TextDisplay("\n\n".join(sections))
            )

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"Page `{self.page + 1}/{self.max_page + 1}` • "
                f"Total cases: `{len(self.cases)}`"
            )
        )

        row = discord.ui.ActionRow()

        previous = discord.ui.Button(
            label="Previous",
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page == 0,
        )
        next_button = discord.ui.Button(
            label="Next",
            emoji="▶️",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.max_page,
        )
        close = discord.ui.Button(
            label="Close",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
        )

        previous.callback = self.previous
        next_button.callback = self.next
        close.callback = self.close

        row.add_item(previous)
        row.add_item(next_button)
        row.add_item(close)
        container.add_item(row)

        self.add_item(container)

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                view=ResponseView(
                    "This menu is not yours",
                    "Run the history command yourself.",
                    success=False,
                ),
                ephemeral=True,
            )
            return False

        return True

    async def previous(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self.build()
        await interaction.response.edit_message(view=self)

    async def next(self, interaction: discord.Interaction) -> None:
        self.page = min(self.max_page, self.page + 1)
        self.build()
        await interaction.response.edit_message(view=self)

    async def close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# ADVANCED MODERATION COG
# =========================================================

class AdvancedModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.spam_cache: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self.deleted_messages: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=20)
        )
        self.edited_messages: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=20)
        )
        self.message_history_cache: dict[
            tuple[int, int], deque[dict[str, Any]]
        ] = defaultdict(lambda: deque(maxlen=100))

        self.sticky_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.nickname_restore_guard: set[tuple[int, int]] = set()

        self.expiration_loop.start()

    def cog_unload(self) -> None:
        self.expiration_loop.cancel()

    async def send(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        *,
        success: bool = True,
        warning: bool = False,
    ) -> None:
        await ctx.send(
            view=ResponseView(
                title,
                description,
                success=success,
                warning=warning,
            )
        )

    async def validate_target(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ) -> bool:
        error = member_hierarchy_error(
            ctx.author,
            member,
            ctx.guild.me,
        )

        if error:
            await self.send(
                ctx,
                "Action blocked",
                error,
                success=False,
            )
            return False

        return True

    async def create_case(
        self,
        guild: discord.Guild,
        *,
        action: str,
        target: discord.abc.User,
        moderator: discord.abc.User,
        reason: str,
        duration: Optional[str] = None,
        extra: Optional[str] = None,
    ) -> dict[str, Any]:
        case = await database.create_case(
            guild.id,
            action=action,
            target_id=target.id,
            moderator_id=moderator.id,
            reason=reason,
            duration=duration,
            extra=extra,
        )

        try:
            from cogs.setup import get_config_value

            channel_id = get_config_value(guild.id, "mod_logs")
            channel = guild.get_channel(channel_id) if channel_id else None

            if isinstance(channel, discord.TextChannel):
                details = (
                    f"**Case:** `#{case['case_id']}`\n"
                    f"**Action:** {action}\n"
                    f"**Target:** {target.mention} (`{target.id}`)\n"
                    f"**Moderator:** {moderator.mention}\n"
                    f"**Reason:** {reason}"
                )

                if duration:
                    details += f"\n**Duration:** `{duration}`"

                if extra:
                    details += f"\n**Details:** {extra}"

                await channel.send(
                    view=ResponseView(
                        "Monk Moderation Case",
                        details,
                    )
                )

        except (ImportError, AttributeError, discord.HTTPException):
            pass

        return case

    # =====================================================
    # AUTOMOD
    # =====================================================

    async def automod_exempt(
        self,
        message: discord.Message,
        config: dict[str, Any],
    ) -> bool:
        if not message.guild:
            return True

        if message.author.bot:
            return True

        if not isinstance(message.author, discord.Member):
            return True

        if message.author.guild_permissions.manage_messages:
            return True

        if message.channel.id in config["ignored_channels"]:
            return True

        if any(
            role.id in config["ignored_roles"]
            for role in message.author.roles
        ):
            return True

        return False

    async def apply_automod_action(
        self,
        message: discord.Message,
        reason: str,
        config: dict[str, Any],
    ) -> None:
        member = message.author

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        action = config.get("action", "timeout")

        if action == "timeout":
            seconds = max(10, int(config.get("timeout_seconds", 600)))

            try:
                await member.timeout(
                    timedelta(seconds=seconds),
                    reason=f"AutoMod: {reason}",
                )

                await self.create_case(
                    message.guild,
                    action="AutoMod Timeout",
                    target=member,
                    moderator=message.guild.me,
                    reason=reason,
                    duration=format_duration(timedelta(seconds=seconds)),
                )

            except (discord.Forbidden, discord.HTTPException):
                action = "delete"

        elif action == "warn":
            await self.create_case(
                message.guild,
                action="AutoMod Warning",
                target=member,
                moderator=message.guild.me,
                reason=reason,
            )

        try:
            notice = await message.channel.send(
                view=ResponseView(
                    "AutoMod Action",
                    f"{member.mention}, your message was removed.\n"
                    f"**Reason:** {reason}",
                    success=False,
                    warning=True,
                ),
                delete_after=6,
            )
            _ = notice

        except discord.HTTPException:
            pass

    @commands.group(
        name="automod",
        invoke_without_command=True,
        help="View or configure AutoMod.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        config = (await database.get_guild(ctx.guild.id))["automod"]

        await self.send(
            ctx,
            "AutoMod Configuration",
            f"**Enabled:** `{config['enabled']}`\n"
            f"**Anti-Spam:** `{config['anti_spam']}`\n"
            f"**Anti-Link:** `{config['anti_link']}`\n"
            f"**Anti-Invite:** `{config['anti_invite']}`\n"
            f"**Anti-Mass Mention:** `{config['anti_mass_mention']}`\n"
            f"**Spam threshold:** `{config['spam_messages']}` messages / "
            f"`{config['spam_window']}` seconds\n"
            f"**Mention limit:** `{config['mention_limit']}`\n"
            f"**Action:** `{config['action']}`\n"
            f"**Timeout:** `{config['timeout_seconds']}s`\n\n"
            "**Examples**\n"
            "`mautomod enable`\n"
            "`mautomod links on`\n"
            "`mautomod invites on`\n"
            "`mautomod spam on`\n"
            "`mautomod mentions on`\n"
            "`mautomod action timeout 10m`",
        )

    @automod.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: commands.Context):
        await database.set_value(ctx.guild.id, "automod", "enabled", True)
        await self.send(ctx, "AutoMod Enabled", "AutoMod is now active.")

    @automod.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: commands.Context):
        await database.set_value(ctx.guild.id, "automod", "enabled", False)
        await self.send(ctx, "AutoMod Disabled", "AutoMod is now inactive.")

    async def set_automod_toggle(
        self,
        ctx: commands.Context,
        key: str,
        state: str,
        title: str,
    ) -> None:
        state = state.lower()

        if state not in {"on", "off"}:
            return await self.send(
                ctx,
                "Invalid state",
                "Use `on` or `off`.",
                success=False,
            )

        enabled = state == "on"
        await database.set_value(ctx.guild.id, "automod", key, enabled)
        await self.send(ctx, title, f"Set to `{enabled}`.")

    @automod.command(name="spam")
    @commands.has_permissions(manage_guild=True)
    async def automod_spam(self, ctx: commands.Context, state: str):
        await self.set_automod_toggle(
            ctx, "anti_spam", state, "Anti-Spam Updated"
        )

    @automod.command(name="links")
    @commands.has_permissions(manage_guild=True)
    async def automod_links(self, ctx: commands.Context, state: str):
        await self.set_automod_toggle(
            ctx, "anti_link", state, "Anti-Link Updated"
        )

    @automod.command(name="invites")
    @commands.has_permissions(manage_guild=True)
    async def automod_invites(self, ctx: commands.Context, state: str):
        await self.set_automod_toggle(
            ctx, "anti_invite", state, "Anti-Invite Updated"
        )

    @automod.command(name="mentions")
    @commands.has_permissions(manage_guild=True)
    async def automod_mentions(self, ctx: commands.Context, state: str):
        await self.set_automod_toggle(
            ctx,
            "anti_mass_mention",
            state,
            "Anti-Mass Mention Updated",
        )

    @automod.command(name="action")
    @commands.has_permissions(manage_guild=True)
    async def automod_action(
        self,
        ctx: commands.Context,
        action: str,
        duration: str = "10m",
    ):
        action = action.lower()

        if action not in {"delete", "warn", "timeout"}:
            return await self.send(
                ctx,
                "Invalid AutoMod action",
                "Use `delete`, `warn`, or `timeout`.",
                success=False,
            )

        await database.set_value(ctx.guild.id, "automod", "action", action)

        if action == "timeout":
            parsed = parse_duration(duration)

            if not parsed or parsed > timedelta(days=28):
                return await self.send(
                    ctx,
                    "Invalid duration",
                    "Use a duration such as `10m`, up to 28 days.",
                    success=False,
                )

            await database.set_value(
                ctx.guild.id,
                "automod",
                "timeout_seconds",
                int(parsed.total_seconds()),
            )

        await self.send(
            ctx,
            "AutoMod Action Updated",
            f"Action set to `{action}`"
            + (
                f" for `{duration}`."
                if action == "timeout"
                else "."
            ),
        )

    # =====================================================
    # JAIL
    # =====================================================

    @commands.command(name="setjailrole")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_jail_role(
        self,
        ctx: commands.Context,
        role: discord.Role,
    ):
        error = role_hierarchy_error(ctx.guild, ctx.author, role)

        if error:
            return await self.send(
                ctx,
                "Invalid jail role",
                error,
                success=False,
            )

        await database.set_value(
            ctx.guild.id,
            "jail",
            "role_id",
            role.id,
        )

        await self.send(
            ctx,
            "Jail Role Configured",
            f"The jail role is now {role.mention}.",
        )

    @commands.command(name="jail")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def jail(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        if not await self.validate_target(ctx, member):
            return

        guild_data = await database.get_guild(ctx.guild.id)
        role_id = guild_data["jail"]["role_id"]
        jail_role = ctx.guild.get_role(role_id) if role_id else None

        if not jail_role:
            return await self.send(
                ctx,
                "Jail role missing",
                "Configure one using `msetjailrole @role`.",
                success=False,
            )

        removable_roles = [
            role
            for role in member.roles[1:]
            if not role.managed
            and role < ctx.guild.me.top_role
            and role != jail_role
        ]

        saved_roles = guild_data["jail"]["saved_roles"]
        saved_roles[str(member.id)] = [role.id for role in removable_roles]
        await database.set_value(
            ctx.guild.id,
            "jail",
            "saved_roles",
            saved_roles,
        )

        await member.remove_roles(
            *removable_roles,
            reason=f"Jailed by {ctx.author}: {reason}",
        )
        await member.add_roles(
            jail_role,
            reason=f"Jailed by {ctx.author}: {reason}",
        )

        case = await self.create_case(
            ctx.guild,
            action="Jail",
            target=member,
            moderator=ctx.author,
            reason=clean_reason(reason),
        )

        await try_dm(
            member,
            f"You were jailed in {ctx.guild.name}",
            f"**Case:** `#{case['case_id']}`\n"
            f"**Reason:** {clean_reason(reason)}",
        )

        await self.send(
            ctx,
            "Member Jailed",
            f"{member.mention} was jailed.\n"
            f"**Case:** `#{case['case_id']}`\n"
            f"**Saved roles:** `{len(removable_roles)}`",
        )

    @commands.command(name="unjail")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def unjail(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        if not await self.validate_target(ctx, member):
            return

        guild_data = await database.get_guild(ctx.guild.id)
        role_id = guild_data["jail"]["role_id"]
        jail_role = ctx.guild.get_role(role_id) if role_id else None

        if jail_role and jail_role in member.roles:
            await member.remove_roles(
                jail_role,
                reason=f"Unjailed by {ctx.author}: {reason}",
            )

        saved_roles = guild_data["jail"]["saved_roles"]
        role_ids = saved_roles.pop(str(member.id), [])

        roles = [
            role
            for role_id in role_ids
            if (role := ctx.guild.get_role(role_id))
            and not role.managed
            and role < ctx.guild.me.top_role
        ]

        if roles:
            await member.add_roles(
                *roles,
                reason=f"Roles restored by {ctx.author}",
            )

        await database.set_value(
            ctx.guild.id,
            "jail",
            "saved_roles",
            saved_roles,
        )

        case = await self.create_case(
            ctx.guild,
            action="Unjail",
            target=member,
            moderator=ctx.author,
            reason=clean_reason(reason),
            extra=f"Restored {len(roles)} roles",
        )

        await self.send(
            ctx,
            "Member Unjailed",
            f"{member.mention} was released.\n"
            f"**Case:** `#{case['case_id']}`\n"
            f"**Restored roles:** `{len(roles)}`",
        )

    # =====================================================
    # TEMPORARY ROLES
    # =====================================================

    @commands.command(name="temprole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def temporary_role(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        duration: str,
        *,
        reason: str = "No reason provided",
    ):
        if not await self.validate_target(ctx, member):
            return

        error = role_hierarchy_error(ctx.guild, ctx.author, role)

        if error:
            return await self.send(
                ctx,
                "Invalid role",
                error,
                success=False,
            )

        parsed = parse_duration(duration)

        if not parsed:
            return await self.send(
                ctx,
                "Invalid duration",
                "Use formats such as `30m`, `2h`, `3d`, or `1w`.",
                success=False,
            )

        await member.add_roles(
            role,
            reason=f"Temporary role by {ctx.author}: {reason}",
        )

        guild_data = await database.get_guild(ctx.guild.id)
        temporary_roles = guild_data["temporary_roles"]
        key = f"{member.id}:{role.id}"

        temporary_roles[key] = {
            "member_id": member.id,
            "role_id": role.id,
            "expires_at": (
                datetime.now(timezone.utc) + parsed
            ).isoformat(),
            "moderator_id": ctx.author.id,
            "reason": clean_reason(reason),
        }

        await database.replace_section(
            ctx.guild.id,
            "temporary_roles",
            temporary_roles,
        )

        case = await self.create_case(
            ctx.guild,
            action="Temporary Role",
            target=member,
            moderator=ctx.author,
            reason=clean_reason(reason),
            duration=duration,
            extra=f"Role: {role.name} ({role.id})",
        )

        await self.send(
            ctx,
            "Temporary Role Added",
            f"Added {role.mention} to {member.mention}.\n"
            f"**Duration:** `{duration}`\n"
            f"**Case:** `#{case['case_id']}`",
        )

    @commands.command(name="removetemprole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def remove_temporary_role(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        reason: str = "Removed manually",
    ):
        if role in member.roles:
            await member.remove_roles(
                role,
                reason=f"Temporary role removed by {ctx.author}: {reason}",
            )

        guild_data = await database.get_guild(ctx.guild.id)
        temporary_roles = guild_data["temporary_roles"]
        temporary_roles.pop(f"{member.id}:{role.id}", None)

        await database.replace_section(
            ctx.guild.id,
            "temporary_roles",
            temporary_roles,
        )

        case = await self.create_case(
            ctx.guild,
            action="Temporary Role Removed",
            target=member,
            moderator=ctx.author,
            reason=clean_reason(reason),
            extra=f"Role: {role.name}",
        )

        await self.send(
            ctx,
            "Temporary Role Removed",
            f"Removed {role.mention} from {member.mention}.\n"
            f"**Case:** `#{case['case_id']}`",
        )

    # =====================================================
    # STICKY MESSAGES
    # =====================================================

    @commands.command(name="sticky")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def sticky(
        self,
        ctx: commands.Context,
        *,
        message: str,
    ):
        guild_data = await database.get_guild(ctx.guild.id)
        sticky_messages = guild_data["sticky_messages"]

        old = sticky_messages.get(str(ctx.channel.id))

        if old and old.get("message_id"):
            try:
                previous = await ctx.channel.fetch_message(old["message_id"])
                await previous.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        sent = await ctx.channel.send(
            view=ResponseView(
                "📌 Sticky Message",
                safe_text(message, 3500),
            )
        )

        sticky_messages[str(ctx.channel.id)] = {
            "content": message[:3500],
            "message_id": sent.id,
        }

        await database.replace_section(
            ctx.guild.id,
            "sticky_messages",
            sticky_messages,
        )

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="unsticky")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def unsticky(self, ctx: commands.Context):
        guild_data = await database.get_guild(ctx.guild.id)
        sticky_messages = guild_data["sticky_messages"]
        data = sticky_messages.pop(str(ctx.channel.id), None)

        if data and data.get("message_id"):
            try:
                message = await ctx.channel.fetch_message(data["message_id"])
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        await database.replace_section(
            ctx.guild.id,
            "sticky_messages",
            sticky_messages,
        )

        await self.send(
            ctx,
            "Sticky Removed",
            f"Sticky messages are disabled in {ctx.channel.mention}.",
        )

    async def refresh_sticky(self, message: discord.Message) -> None:
        async with self.sticky_locks[message.channel.id]:
            guild_data = await database.get_guild(message.guild.id)
            sticky_messages = guild_data["sticky_messages"]
            sticky = sticky_messages.get(str(message.channel.id))

            if not sticky:
                return

            if message.id == sticky.get("message_id"):
                return

            try:
                old_message_id = sticky.get("message_id")

                if old_message_id:
                    try:
                        old_message = await message.channel.fetch_message(
                            old_message_id
                        )
                        await old_message.delete()
                    except (
                        discord.NotFound,
                        discord.Forbidden,
                        discord.HTTPException,
                    ):
                        pass

                new_message = await message.channel.send(
                    view=ResponseView(
                        "📌 Sticky Message",
                        safe_text(sticky["content"], 3500),
                    )
                )

                sticky["message_id"] = new_message.id
                sticky_messages[str(message.channel.id)] = sticky

                await database.replace_section(
                    message.guild.id,
                    "sticky_messages",
                    sticky_messages,
                )

            except discord.HTTPException:
                pass

    # =====================================================
    # NICKNAME LOCK
    # =====================================================

    @commands.command(name="nicklock")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_lock(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        nickname: Optional[str] = None,
    ):
        if not await self.validate_target(ctx, member):
            return

        nickname = (nickname or member.display_name)[:32]

        await member.edit(
            nick=nickname,
            reason=f"Nickname locked by {ctx.author}",
        )

        guild_data = await database.get_guild(ctx.guild.id)
        locks = guild_data["nickname_locks"]
        locks[str(member.id)] = nickname

        await database.replace_section(
            ctx.guild.id,
            "nickname_locks",
            locks,
        )

        case = await self.create_case(
            ctx.guild,
            action="Nickname Lock",
            target=member,
            moderator=ctx.author,
            reason=f"Nickname locked to {nickname}",
        )

        await self.send(
            ctx,
            "Nickname Locked",
            f"{member.mention}'s nickname is locked to **{nickname}**.\n"
            f"**Case:** `#{case['case_id']}`",
        )

    @commands.command(name="nickunlock")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_unlock(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ):
        guild_data = await database.get_guild(ctx.guild.id)
        locks = guild_data["nickname_locks"]
        existed = locks.pop(str(member.id), None)

        await database.replace_section(
            ctx.guild.id,
            "nickname_locks",
            locks,
        )

        await self.send(
            ctx,
            "Nickname Unlocked",
            (
                f"{member.mention}'s nickname lock was removed."
                if existed
                else f"{member.mention} did not have a nickname lock."
            ),
            success=bool(existed),
        )

    # =====================================================
    # VOICE MODERATION
    # =====================================================

    async def voice_edit(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        mute: Optional[bool] = None,
        deafen: Optional[bool] = None,
        action: str,
        reason: str,
    ):
        if not member.voice or not member.voice.channel:
            return await self.send(
                ctx,
                "Member not connected",
                f"{member.mention} is not in a voice channel.",
                success=False,
            )

        await member.edit(
            mute=mute,
            deafen=deafen,
            reason=f"{action} by {ctx.author}: {reason}",
        )

        case = await self.create_case(
            ctx.guild,
            action=action,
            target=member,
            moderator=ctx.author,
            reason=clean_reason(reason),
        )

        await self.send(
            ctx,
            action,
            f"Updated voice state for {member.mention}.\n"
            f"**Case:** `#{case['case_id']}`",
        )

    @commands.command(name="vmute")
    @commands.guild_only()
    @commands.has_permissions(mute_members=True)
    async def voice_mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        await self.voice_edit(
            ctx,
            member,
            mute=True,
            action="Voice Mute",
            reason=reason,
        )

    @commands.command(name="vunmute")
    @commands.guild_only()
    @commands.has_permissions(mute_members=True)
    async def voice_unmute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        await self.voice_edit(
            ctx,
            member,
            mute=False,
            action="Voice Unmute",
            reason=reason,
        )

    @commands.command(name="vdeafen")
    @commands.guild_only()
    @commands.has_permissions(deafen_members=True)
    async def voice_deafen(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        await self.voice_edit(
            ctx,
            member,
            deafen=True,
            action="Voice Deafen",
            reason=reason,
        )

    @commands.command(name="vundeafen")
    @commands.guild_only()
    @commands.has_permissions(deafen_members=True)
    async def voice_undeafen(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        await self.voice_edit(
            ctx,
            member,
            deafen=False,
            action="Voice Undeafen",
            reason=reason,
        )

    # =====================================================
    # LOCKDOWN
    # =====================================================

    @commands.command(name="lockdown")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def lockdown(
        self,
        ctx: commands.Context,
        *,
        reason: str = "Server lockdown",
    ):
        guild_data = await database.get_guild(ctx.guild.id)
        lockdown_data = guild_data["lockdown"]

        if lockdown_data["active"]:
            return await self.send(
                ctx,
                "Already Locked Down",
                "This server already has an active lockdown.",
                success=False,
            )

        stored: dict[str, Any] = {}
        changed = 0
        failed = 0

        progress = await ctx.send(
            view=ResponseView(
                "Lockdown Starting",
                "Locking text and forum channels...",
                warning=True,
            )
        )

        for channel in ctx.guild.channels:
            if not isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.ForumChannel,
                ),
            ):
                continue

            overwrite = channel.overwrites_for(ctx.guild.default_role)

            stored[str(channel.id)] = {
                "send_messages": overwrite.send_messages,
                "send_messages_in_threads": overwrite.send_messages_in_threads,
                "create_public_threads": overwrite.create_public_threads,
                "create_private_threads": overwrite.create_private_threads,
            }

            overwrite.send_messages = False
            overwrite.send_messages_in_threads = False
            overwrite.create_public_threads = False
            overwrite.create_private_threads = False

            try:
                await channel.set_permissions(
                    ctx.guild.default_role,
                    overwrite=overwrite,
                    reason=f"Lockdown by {ctx.author}: {reason}",
                )
                changed += 1

            except (discord.Forbidden, discord.HTTPException):
                failed += 1

        lockdown_data = {
            "active": True,
            "channels": stored,
        }

        await database.replace_section(
            ctx.guild.id,
            "lockdown",
            lockdown_data,
        )

        case = await self.create_case(
            ctx.guild,
            action="Server Lockdown",
            target=ctx.guild.me,
            moderator=ctx.author,
            reason=clean_reason(reason),
            extra=f"Locked {changed} channels; {failed} failed",
        )

        await progress.edit(
            view=ResponseView(
                "Server Locked Down",
                f"**Locked:** `{changed}` channels\n"
                f"**Failed:** `{failed}` channels\n"
                f"**Case:** `#{case['case_id']}`",
            )
        )

    @commands.command(name="unlockall")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unlock_all(
        self,
        ctx: commands.Context,
        *,
        reason: str = "Lockdown ended",
    ):
        guild_data = await database.get_guild(ctx.guild.id)
        lockdown_data = guild_data["lockdown"]

        if not lockdown_data["active"]:
            return await self.send(
                ctx,
                "No Active Lockdown",
                "The server is not currently locked down.",
                success=False,
            )

        restored = 0
        failed = 0

        for channel_id, values in lockdown_data["channels"].items():
            channel = ctx.guild.get_channel(int(channel_id))

            if not isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.ForumChannel,
                ),
            ):
                continue

            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = values.get("send_messages")
            overwrite.send_messages_in_threads = values.get(
                "send_messages_in_threads"
            )
            overwrite.create_public_threads = values.get(
                "create_public_threads"
            )
            overwrite.create_private_threads = values.get(
                "create_private_threads"
            )

            try:
                await channel.set_permissions(
                    ctx.guild.default_role,
                    overwrite=overwrite,
                    reason=f"Unlock all by {ctx.author}: {reason}",
                )
                restored += 1

            except (discord.Forbidden, discord.HTTPException):
                failed += 1

        await database.replace_section(
            ctx.guild.id,
            "lockdown",
            {
                "active": False,
                "channels": {},
            },
        )

        case = await self.create_case(
            ctx.guild,
            action="Server Unlock",
            target=ctx.guild.me,
            moderator=ctx.author,
            reason=clean_reason(reason),
            extra=f"Restored {restored} channels; {failed} failed",
        )

        await self.send(
            ctx,
            "Server Unlocked",
            f"**Restored:** `{restored}` channels\n"
            f"**Failed:** `{failed}` channels\n"
            f"**Case:** `#{case['case_id']}`",
        )

    # =====================================================
    # SNIPE / EDIT SNIPE / MESSAGE HISTORY
    # =====================================================

    @commands.command(name="snipe")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipe(
        self,
        ctx: commands.Context,
        index: commands.Range[int, 1, 20] = 1,
    ):
        entries = list(self.deleted_messages[ctx.channel.id])

        if len(entries) < index:
            return await self.send(
                ctx,
                "Nothing to Snipe",
                "No cached deleted message exists at that position.",
                success=False,
            )

        entry = entries[-index]
        attachments = "\n".join(entry["attachments"]) or "None"

        await self.send(
            ctx,
            f"Deleted Message — {entry['author_name']}",
            f"**Author:** <@{entry['author_id']}> (`{entry['author_id']}`)\n"
            f"**Content:**\n{safe_text(entry['content'], 2500)}\n\n"
            f"**Attachments:** {attachments}\n"
            f"**Deleted:** {timestamp_from_iso(entry['deleted_at'])}\n"
            f"**Position:** `{index}/{len(entries)}`",
        )

    @commands.command(name="editsnipe")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def edit_snipe(
        self,
        ctx: commands.Context,
        index: commands.Range[int, 1, 20] = 1,
    ):
        entries = list(self.edited_messages[ctx.channel.id])

        if len(entries) < index:
            return await self.send(
                ctx,
                "Nothing to Edit-Snipe",
                "No cached edited message exists at that position.",
                success=False,
            )

        entry = entries[-index]

        await self.send(
            ctx,
            f"Edited Message — {entry['author_name']}",
            f"**Author:** <@{entry['author_id']}>\n"
            f"**Before:**\n{safe_text(entry['before'], 1500)}\n\n"
            f"**After:**\n{safe_text(entry['after'], 1500)}\n\n"
            f"**Edited:** {timestamp_from_iso(entry['edited_at'])}\n"
            f"**Position:** `{index}/{len(entries)}`",
        )

    @commands.command(name="messagehistory")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def message_history(
        self,
        ctx: commands.Context,
        member: discord.Member,
        amount: commands.Range[int, 1, 20] = 10,
    ):
        entries = list(
            self.message_history_cache[(ctx.guild.id, member.id)]
        )[-amount:]

        if not entries:
            return await self.send(
                ctx,
                "No Cached Messages",
                f"No recent messages are cached for {member.mention}.",
                success=False,
            )

        lines = []

        for entry in reversed(entries):
            channel = ctx.guild.get_channel(entry["channel_id"])
            channel_text = channel.mention if channel else "`Deleted channel`"

            lines.append(
                f"**{channel_text} • "
                f"{timestamp_from_iso(entry['created_at'])}**\n"
                f"{safe_text(entry['content'], 500)}"
            )

        await self.send(
            ctx,
            f"Message History — {member}",
            "\n\n".join(lines),
        )

    # =====================================================
    # CASES / PUNISHMENT HISTORY
    # =====================================================

    @commands.command(name="case")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def case_lookup(
        self,
        ctx: commands.Context,
        case_id: int,
    ):
        case = await database.get_case(ctx.guild.id, case_id)

        if not case:
            return await self.send(
                ctx,
                "Case Not Found",
                f"No case exists with ID `#{case_id}`.",
                success=False,
            )

        duration = (
            f"\n**Duration:** `{case['duration']}`"
            if case.get("duration")
            else ""
        )
        extra = (
            f"\n**Details:** {safe_text(case['extra'], 500)}"
            if case.get("extra")
            else ""
        )

        await self.send(
            ctx,
            f"Case #{case_id}",
            f"**Action:** {case['action']}\n"
            f"**Target:** <@{case['target_id']}> (`{case['target_id']}`)\n"
            f"**Moderator:** <@{case['moderator_id']}>\n"
            f"**Reason:** {safe_text(case['reason'], 1000)}"
            f"{duration}{extra}\n"
            f"**Created:** {timestamp_from_iso(case['created_at'])}",
        )

    @commands.command(
    name="casehistory",
    aliases=["punishments", "modhistory"],
)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def punishment_history(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        cases = await database.get_cases(
            ctx.guild.id,
            target_id=member.id if member else None,
        )

        await ctx.send(
            view=CaseHistoryView(ctx, cases, member)
        )

    # =====================================================
    # LISTENERS
    # =====================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        advanced_disabled = is_module_disabled(
            message.guild.id,
            "advanced_moderation",
        )
        automod_disabled = is_module_disabled(message.guild.id, "automod")

        if not message.author.bot and not advanced_disabled:
            self.message_history_cache[
                (message.guild.id, message.author.id)
            ].append(
                {
                    "channel_id": message.channel.id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
            )

        guild_data = await database.get_guild(message.guild.id)
        automod = guild_data["automod"]

        if (
            not automod_disabled
            and automod["enabled"]
            and not await self.automod_exempt(
            message,
            automod,
            )
        ):
            reason = None

            if automod["anti_invite"] and INVITE_PATTERN.search(
                message.content
            ):
                reason = "Discord invite links are not allowed."

            elif (
                automod["anti_link"]
                and URL_PATTERN.search(message.content)
            ):
                reason = "Links are not allowed."

            elif automod["anti_mass_mention"]:
                mention_count = (
                    len(message.mentions)
                    + len(message.role_mentions)
                    + int(message.mention_everyone)
                )

                if mention_count >= automod["mention_limit"]:
                    reason = (
                        f"Mass mentioning is limited to "
                        f"{automod['mention_limit'] - 1} mentions."
                    )

            if not reason and automod["anti_spam"]:
                key = (message.guild.id, message.author.id)
                queue = self.spam_cache[key]
                now = time.monotonic()
                window = automod["spam_window"]

                queue.append(now)

                while queue and now - queue[0] > window:
                    queue.popleft()

                if len(queue) >= automod["spam_messages"]:
                    queue.clear()
                    reason = (
                        f"Spam detected: {automod['spam_messages']} messages "
                        f"within {window} seconds."
                    )

            if reason:
                await self.apply_automod_action(
                    message,
                    reason,
                    automod,
                )
                return

        if (
            not advanced_disabled
            and str(message.channel.id) in guild_data["sticky_messages"]
        ):
            await asyncio.sleep(1)
            await self.refresh_sticky(message)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if (
            not message.guild
            or message.author.bot
            or is_module_disabled(message.guild.id, "advanced_moderation")
        ):
            return

        self.deleted_messages[message.channel.id].append(
            {
                "author_id": message.author.id,
                "author_name": str(message.author),
                "content": message.content,
                "attachments": [
                    attachment.url
                    for attachment in message.attachments
                ],
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ):
        if (
            not before.guild
            or before.author.bot
            or is_module_disabled(before.guild.id, "advanced_moderation")
        ):
            return

        if before.content == after.content:
            return

        self.edited_messages[before.channel.id].append(
            {
                "author_id": before.author.id,
                "author_name": str(before.author),
                "before": before.content,
                "after": after.content,
                "edited_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ):
        if is_module_disabled(after.guild.id, "advanced_moderation"):
            return

        if before.nick == after.nick:
            return

        key = (after.guild.id, after.id)

        if key in self.nickname_restore_guard:
            return

        guild_data = await database.get_guild(after.guild.id)
        locked_name = guild_data["nickname_locks"].get(str(after.id))

        if not locked_name or after.nick == locked_name:
            return

        self.nickname_restore_guard.add(key)

        try:
            await after.edit(
                nick=locked_name,
                reason="Nickname lock restored",
            )
        except (discord.Forbidden, discord.HTTPException):
            pass
        finally:
            self.nickname_restore_guard.discard(key)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if is_module_disabled(member.guild.id, "advanced_moderation"):
            return

        guild_data = await database.get_guild(member.guild.id)
        role_id = guild_data["jail"]["role_id"]

        if str(member.id) in guild_data["jail"]["saved_roles"]:
            jail_role = member.guild.get_role(role_id) if role_id else None

            if jail_role:
                try:
                    await member.add_roles(
                        jail_role,
                        reason="Restored jail status after rejoin",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

    # =====================================================
    # EXPIRATION TASK
    # =====================================================

    @tasks.loop(seconds=30)
    async def expiration_loop(self):
        now = datetime.now(timezone.utc)

        for guild in self.bot.guilds:
            if is_module_disabled(guild.id, "advanced_moderation"):
                continue

            guild_data = await database.get_guild(guild.id)
            temporary_roles = guild_data["temporary_roles"]
            changed = False

            for key, entry in list(temporary_roles.items()):
                try:
                    expires_at = datetime.fromisoformat(entry["expires_at"])

                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)

                except (ValueError, TypeError):
                    temporary_roles.pop(key, None)
                    changed = True
                    continue

                if expires_at > now:
                    continue

                member = guild.get_member(entry["member_id"])
                role = guild.get_role(entry["role_id"])

                if member and role and role in member.roles:
                    try:
                        await member.remove_roles(
                            role,
                            reason="Temporary role expired",
                        )
                    except (discord.Forbidden, discord.HTTPException):
                        continue

                temporary_roles.pop(key, None)
                changed = True

            if changed:
                await database.replace_section(
                    guild.id,
                    "temporary_roles",
                    temporary_roles,
                )

    @expiration_loop.before_loop
    async def before_expiration_loop(self):
        await self.bot.wait_until_ready()

    # =====================================================
    # ERROR HANDLER
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.MissingPermissions):
            permissions = ", ".join(
                item.replace("_", " ").title()
                for item in error.missing_permissions
            )

            return await self.send(
                ctx,
                "Missing Permissions",
                f"You need: **{permissions}**.",
                success=False,
            )

        if isinstance(error, commands.BotMissingPermissions):
            permissions = ", ".join(
                item.replace("_", " ").title()
                for item in error.missing_permissions
            )

            return await self.send(
                ctx,
                "Bot Permissions Missing",
                f"I need: **{permissions}**.",
                success=False,
            )

        if isinstance(error, commands.MemberNotFound):
            return await self.send(
                ctx,
                "Member Not Found",
                "Mention a valid member or provide their ID.",
                success=False,
            )

        if isinstance(error, commands.RoleNotFound):
            return await self.send(
                ctx,
                "Role Not Found",
                "Mention a valid role or provide its ID.",
                success=False,
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await self.send(
                ctx,
                "Missing Argument",
                f"You did not provide `{error.param.name}`.",
                success=False,
            )

        if isinstance(error, commands.BadArgument):
            return await self.send(
                ctx,
                "Invalid Argument",
                "One or more supplied arguments are invalid.",
                success=False,
            )

        if isinstance(error, discord.Forbidden):
            return await self.send(
                ctx,
                "Discord Permission Error",
                "Check my permissions and ensure my role is above the target.",
                success=False,
            )

        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AdvancedModeration(bot))
