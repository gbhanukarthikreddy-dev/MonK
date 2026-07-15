import asyncio
import json
import os
import re
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_FOLDER = "database"
DATABASE_FILE = os.path.join(DATABASE_FOLDER, "moderation.json")

DEFAULT_REASON = "No reason provided"
ACCENT_COLOR = discord.Color.from_rgb(198, 145, 73)


# =========================================================
# JSON DATABASE
# =========================================================

class ModerationDatabase:
    def __init__(self, file_path: str):
        self.file_path = file_path

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if not os.path.exists(file_path):
            self.save({
                "guilds": {}
            })

    def load(self) -> dict:
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                return json.load(file)

        except (json.JSONDecodeError, FileNotFoundError):
            data = {"guilds": {}}
            self.save(data)
            return data

    def save(self, data: dict):
        temporary_file = f"{self.file_path}.tmp"

        with open(temporary_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

        os.replace(temporary_file, self.file_path)

    def get_guild(self, guild_id: int) -> dict:
        data = self.load()
        guild_id = str(guild_id)

        if guild_id not in data["guilds"]:
            data["guilds"][guild_id] = {
                "log_channel": None,
                "warnings": {},
                "history": {},
                "locked_channels": {}
            }
            self.save(data)

        return data["guilds"][guild_id]

    def set_log_channel(self, guild_id: int, channel_id: Optional[int]):
        data = self.load()
        guild_id = str(guild_id)

        if guild_id not in data["guilds"]:
            data["guilds"][guild_id] = {
                "log_channel": None,
                "warnings": {},
                "history": {},
                "locked_channels": {}
            }

        data["guilds"][guild_id]["log_channel"] = channel_id
        self.save(data)

    def add_warning(
        self,
        guild_id: int,
        member_id: int,
        moderator_id: int,
        reason: str
    ) -> int:
        data = self.load()
        guild_id = str(guild_id)
        member_id = str(member_id)

        guild_data = data["guilds"].setdefault(
            guild_id,
            {
                "log_channel": None,
                "warnings": {},
                "history": {},
                "locked_channels": {}
            }
        )

        warnings = guild_data["warnings"].setdefault(member_id, [])

        warning_id = warnings[-1]["id"] + 1 if warnings else 1

        warning = {
            "id": warning_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": discord.utils.utcnow().isoformat()
        }

        warnings.append(warning)
        self.save(data)

        return warning_id

    def get_warnings(self, guild_id: int, member_id: int) -> list:
        guild_data = self.get_guild(guild_id)

        return guild_data["warnings"].get(str(member_id), [])

    def remove_warning(
        self,
        guild_id: int,
        member_id: int,
        warning_id: int
    ) -> bool:
        data = self.load()
        guild_id = str(guild_id)
        member_id = str(member_id)

        guild_data = data["guilds"].get(guild_id)

        if not guild_data:
            return False

        warnings = guild_data["warnings"].get(member_id, [])

        for warning in warnings:
            if warning["id"] == warning_id:
                warnings.remove(warning)
                self.save(data)
                return True

        return False

    def clear_warnings(self, guild_id: int, member_id: int) -> int:
        data = self.load()
        guild_id = str(guild_id)
        member_id = str(member_id)

        guild_data = data["guilds"].get(guild_id)

        if not guild_data:
            return 0

        warnings = guild_data["warnings"].get(member_id, [])
        amount = len(warnings)

        guild_data["warnings"][member_id] = []
        self.save(data)

        return amount

    def add_history(
        self,
        guild_id: int,
        member_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration: Optional[str] = None
    ):
        data = self.load()
        guild_id = str(guild_id)
        member_id = str(member_id)

        guild_data = data["guilds"].setdefault(
            guild_id,
            {
                "log_channel": None,
                "warnings": {},
                "history": {},
                "locked_channels": {}
            }
        )

        history = guild_data["history"].setdefault(member_id, [])

        history.append({
            "action": action,
            "moderator_id": moderator_id,
            "reason": reason,
            "duration": duration,
            "timestamp": discord.utils.utcnow().isoformat()
        })

        # Prevent the JSON file from growing forever.
        guild_data["history"][member_id] = history[-100:]

        self.save(data)

    def get_history(self, guild_id: int, member_id: int) -> list:
        guild_data = self.get_guild(guild_id)

        return guild_data["history"].get(str(member_id), [])

    def save_lock_permissions(
        self,
        guild_id: int,
        channel_id: int,
        send_messages: Optional[bool]
    ):
        data = self.load()
        guild_id = str(guild_id)
        channel_id = str(channel_id)

        guild_data = data["guilds"].setdefault(
            guild_id,
            {
                "log_channel": None,
                "warnings": {},
                "history": {},
                "locked_channels": {}
            }
        )

        guild_data["locked_channels"][channel_id] = {
            "send_messages": send_messages
        }

        self.save(data)

    def get_lock_permissions(
        self,
        guild_id: int,
        channel_id: int
    ) -> Optional[dict]:
        guild_data = self.get_guild(guild_id)

        return guild_data["locked_channels"].get(str(channel_id))

    def remove_lock_permissions(self, guild_id: int, channel_id: int):
        data = self.load()
        guild_id = str(guild_id)
        channel_id = str(channel_id)

        guild_data = data["guilds"].get(guild_id)

        if not guild_data:
            return

        guild_data["locked_channels"].pop(channel_id, None)
        self.save(data)


database = ModerationDatabase(DATABASE_FILE)


# =========================================================
# GENERAL HELPERS
# =========================================================

def parse_duration(duration: str) -> Optional[timedelta]:
    """
    Supported:
    30s
    10m
    2h
    3d
    1w
    """

    duration = duration.lower().strip()

    match = re.fullmatch(r"(\d+)(s|m|h|d|w)", duration)

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if amount <= 0:
        return None

    values = {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount)
    }

    result = values[unit]

    # Discord timeout limit is 28 days.
    if result > timedelta(days=28):
        return None

    return result


def format_timestamp(timestamp: str) -> str:
    try:
        date = discord.utils.parse_time(timestamp)

        if date:
            return discord.utils.format_dt(date, style="R")
    except Exception:
        pass

    return "Unknown time"


def clean_reason(reason: Optional[str]) -> str:
    if not reason:
        return DEFAULT_REASON

    return reason[:1000]


async def safe_dm(
    member: discord.User,
    title: str,
    description: str
):
    try:
        view = discord.ui.LayoutView()

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## {title}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(description),
            accent_colour=ACCENT_COLOR
        )

        view.add_item(container)

        await member.send(view=view)

    except (discord.Forbidden, discord.HTTPException):
        pass


def hierarchy_error(
    moderator: discord.Member,
    target: discord.Member,
    bot_member: discord.Member
) -> Optional[str]:

    if target == moderator:
        return "You cannot moderate yourself."

    if target == moderator.guild.owner:
        return "The server owner cannot be moderated."

    if target == bot_member:
        return "I cannot moderate myself."

    if moderator != moderator.guild.owner:
        if target.top_role >= moderator.top_role:
            return (
                "You cannot moderate this member because their highest role "
                "is equal to or higher than yours."
            )

    if target.top_role >= bot_member.top_role:
        return (
            "I cannot moderate this member because their highest role is "
            "equal to or higher than my role."
        )

    return None


# =========================================================
# COMPONENTS V2 RESPONSE VIEW
# =========================================================

class ResponseView(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        success: bool = True,
        thumbnail: Optional[str] = None
    ):
        super().__init__(timeout=60)

        color = (
            discord.Color.from_rgb(73, 190, 122)
            if success
            else discord.Color.from_rgb(220, 75, 75)
        )

        container = discord.ui.Container(accent_colour=color)

        if thumbnail:
            section = discord.ui.Section(
                discord.ui.TextDisplay(f"## {title}"),
                discord.ui.TextDisplay(description),
                accessory=discord.ui.Thumbnail(thumbnail)
            )
            container.add_item(section)

        else:
            container.add_item(
                discord.ui.TextDisplay(f"## {title}")
            )
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(description)
            )

        self.add_item(container)


# =========================================================
# MODERATION LOG VIEW
# =========================================================

class ModerationLogView(discord.ui.LayoutView):
    def __init__(
        self,
        action: str,
        target: discord.abc.User,
        moderator: discord.abc.User,
        reason: str,
        *,
        duration: Optional[str] = None,
        extra: Optional[str] = None
    ):
        super().__init__(timeout=None)

        information = (
            f"**Action:** {action}\n"
            f"**Target:** {target.mention} (`{target.id}`)\n"
            f"**Moderator:** {moderator.mention} (`{moderator.id}`)\n"
            f"**Reason:** {reason}"
        )

        if duration:
            information += f"\n**Duration:** {duration}"

        if extra:
            information += f"\n{extra}"

        information += (
            f"\n**Time:** "
            f"{discord.utils.format_dt(discord.utils.utcnow(), style='F')}"
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay("## Monk Moderation Log"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(information),
            accent_colour=ACCENT_COLOR
        )

        self.add_item(container)


# =========================================================
# MODERATION PANEL MODALS
# =========================================================

class BaseModerationModal(discord.ui.Modal):
    def __init__(
        self,
        moderation_cog,
        title: str,
        action: str,
        *,
        require_duration: bool = False
    ):
        super().__init__(title=title)

        self.moderation_cog = moderation_cog
        self.action = action
        self.require_duration = require_duration

        self.member_input = discord.ui.TextInput(
            label="Member ID",
            placeholder="Enter the member's Discord ID",
            required=True,
            max_length=25
        )

        self.reason_input = discord.ui.TextInput(
            label="Reason",
            placeholder="Enter the reason",
            required=False,
            max_length=1000,
            style=discord.TextStyle.paragraph
        )

        self.add_item(
            discord.ui.Label(
                text="Member",
                description="The ID of the member you want to moderate.",
                component=self.member_input
            )
        )

        if require_duration:
            self.duration_input = discord.ui.TextInput(
                label="Duration",
                placeholder="Examples: 10m, 2h, 3d, 1w",
                required=True,
                max_length=10
            )

            self.add_item(
                discord.ui.Label(
                    text="Duration",
                    description="Maximum Discord timeout duration is 28 days.",
                    component=self.duration_input
                )
            )

        self.add_item(
            discord.ui.Label(
                text="Reason",
                description="Why this moderation action is being performed.",
                component=self.reason_input
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message(
                "This panel can only be used inside a server.",
                ephemeral=True
            )

        try:
            member_id = int(self.member_input.value)
        except ValueError:
            return await interaction.response.send_message(
                view=ResponseView(
                    "Invalid member ID",
                    "The member ID must contain numbers only.",
                    success=False
                ),
                ephemeral=True
            )

        member = interaction.guild.get_member(member_id)

        if not member:
            try:
                member = await interaction.guild.fetch_member(member_id)
            except (discord.NotFound, discord.HTTPException):
                member = None

        if not member:
            return await interaction.response.send_message(
                view=ResponseView(
                    "Member not found",
                    "I could not find that member in this server.",
                    success=False
                ),
                ephemeral=True
            )

        moderator = interaction.user

        if not isinstance(moderator, discord.Member):
            return

        error = hierarchy_error(
            moderator,
            member,
            interaction.guild.me
        )

        if error:
            return await interaction.response.send_message(
                view=ResponseView(
                    "Action blocked",
                    error,
                    success=False
                ),
                ephemeral=True
            )

        reason = clean_reason(self.reason_input.value)

        await interaction.response.defer(ephemeral=True)

        try:
            if self.action == "warn":
                await self.moderation_cog.perform_warn(
                    interaction.guild,
                    moderator,
                    member,
                    reason
                )

            elif self.action == "timeout":
                duration_text = self.duration_input.value
                duration = parse_duration(duration_text)

                if not duration:
                    return await interaction.followup.send(
                        view=ResponseView(
                            "Invalid duration",
                            "Use `30s`, `10m`, `2h`, `3d` or `1w`. "
                            "The maximum timeout is 28 days.",
                            success=False
                        ),
                        ephemeral=True
                    )

                await self.moderation_cog.perform_timeout(
                    interaction.guild,
                    moderator,
                    member,
                    duration,
                    duration_text,
                    reason
                )

            elif self.action == "kick":
                await self.moderation_cog.perform_kick(
                    interaction.guild,
                    moderator,
                    member,
                    reason
                )

            elif self.action == "ban":
                await self.moderation_cog.perform_ban(
                    interaction.guild,
                    moderator,
                    member,
                    reason
                )

            await interaction.followup.send(
                view=ResponseView(
                    "Action completed",
                    f"Successfully performed **{self.action}** on "
                    f"{member.mention}."
                ),
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                view=ResponseView(
                    "Missing permissions",
                    "I do not have permission to perform this action. "
                    "Check my role and channel permissions.",
                    success=False
                ),
                ephemeral=True
            )

        except discord.HTTPException as error:
            await interaction.followup.send(
                view=ResponseView(
                    "Discord API error",
                    f"The action failed:\n```py\n{error}\n```",
                    success=False
                ),
                ephemeral=True
            )


class WarnModal(BaseModerationModal):
    def __init__(self, moderation_cog):
        super().__init__(
            moderation_cog,
            "Warn member",
            "warn"
        )


class TimeoutModal(BaseModerationModal):
    def __init__(self, moderation_cog):
        super().__init__(
            moderation_cog,
            "Timeout member",
            "timeout",
            require_duration=True
        )


class KickModal(BaseModerationModal):
    def __init__(self, moderation_cog):
        super().__init__(
            moderation_cog,
            "Kick member",
            "kick"
        )


class BanModal(BaseModerationModal):
    def __init__(self, moderation_cog):
        super().__init__(
            moderation_cog,
            "Ban member",
            "ban"
        )


# =========================================================
# MODERATION PANEL
# =========================================================

class ModerationPanel(discord.ui.LayoutView):
    def __init__(self, moderation_cog, author_id: int):
        super().__init__(timeout=300)

        self.moderation_cog = moderation_cog
        self.author_id = author_id

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        container.add_item(
            discord.ui.TextDisplay(
                "## 🛡️ Monk Moderation Panel"
            )
        )

        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                "Use the buttons below to perform moderation actions.\n\n"
                "Only members with the required moderation permissions "
                "can use these controls."
            )
        )

        first_row = discord.ui.ActionRow()

        warn_button = discord.ui.Button(
            label="Warn",
            emoji="⚠️",
            style=discord.ButtonStyle.secondary
        )

        timeout_button = discord.ui.Button(
            label="Timeout",
            emoji="⏳",
            style=discord.ButtonStyle.primary
        )

        kick_button = discord.ui.Button(
            label="Kick",
            emoji="👢",
            style=discord.ButtonStyle.danger
        )

        ban_button = discord.ui.Button(
            label="Ban",
            emoji="🔨",
            style=discord.ButtonStyle.danger
        )

        warn_button.callback = self.warn_callback
        timeout_button.callback = self.timeout_callback
        kick_button.callback = self.kick_callback
        ban_button.callback = self.ban_callback

        first_row.add_item(warn_button)
        first_row.add_item(timeout_button)
        first_row.add_item(kick_button)
        first_row.add_item(ban_button)

        second_row = discord.ui.ActionRow()

        refresh_button = discord.ui.Button(
            label="Refresh",
            emoji="🔄",
            style=discord.ButtonStyle.secondary
        )

        close_button = discord.ui.Button(
            label="Close",
            emoji="✖️",
            style=discord.ButtonStyle.secondary
        )

        refresh_button.callback = self.refresh_callback
        close_button.callback = self.close_callback

        second_row.add_item(refresh_button)
        second_row.add_item(close_button)

        container.add_item(discord.ui.Separator())
        container.add_item(first_row)
        container.add_item(second_row)

        self.add_item(container)

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ) -> bool:
        if not interaction.guild:
            return False

        if not isinstance(interaction.user, discord.Member):
            return False

        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                view=ResponseView(
                    "Permission denied",
                    "You need the **Moderate Members** permission "
                    "to use this panel.",
                    success=False
                ),
                ephemeral=True
            )
            return False

        return True

    async def warn_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            WarnModal(self.moderation_cog)
        )

    async def timeout_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            TimeoutModal(self.moderation_cog)
        )

    async def kick_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message(
                view=ResponseView(
                    "Permission denied",
                    "You need the **Kick Members** permission.",
                    success=False
                ),
                ephemeral=True
            )

        await interaction.response.send_modal(
            KickModal(self.moderation_cog)
        )

    async def ban_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message(
                view=ResponseView(
                    "Permission denied",
                    "You need the **Ban Members** permission.",
                    success=False
                ),
                ephemeral=True
            )

        await interaction.response.send_modal(
            BanModal(self.moderation_cog)
        )

    async def refresh_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            view=ModerationPanel(
                self.moderation_cog,
                interaction.user.id
            )
        )

    async def close_callback(self, interaction: discord.Interaction):
        if (
            interaction.user.id != self.author_id
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "Only the panel creator or an administrator can close it.",
                ephemeral=True
            )

        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# CONFIRMATION VIEW
# =========================================================

class ConfirmationView(discord.ui.LayoutView):
    def __init__(
        self,
        author_id: int,
        title: str,
        description: str
    ):
        super().__init__(timeout=30)

        self.author_id = author_id
        self.confirmed = False

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## {title}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(description),
            accent_colour=discord.Color.orange()
        )

        row = discord.ui.ActionRow()

        confirm = discord.ui.Button(
            label="Confirm",
            emoji="✅",
            style=discord.ButtonStyle.danger
        )

        cancel = discord.ui.Button(
            label="Cancel",
            emoji="✖️",
            style=discord.ButtonStyle.secondary
        )

        confirm.callback = self.confirm_callback
        cancel.callback = self.cancel_callback

        row.add_item(confirm)
        row.add_item(cancel)

        container.add_item(discord.ui.Separator())
        container.add_item(row)

        self.add_item(container)

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation does not belong to you.",
                ephemeral=True
            )
            return False

        return True

    async def confirm_callback(
        self,
        interaction: discord.Interaction
    ):
        self.confirmed = True

        await interaction.response.edit_message(
            view=ResponseView(
                "Confirmed",
                "The action has been confirmed."
            )
        )

        self.stop()

    async def cancel_callback(
        self,
        interaction: discord.Interaction
    ):
        self.confirmed = False

        await interaction.response.edit_message(
            view=ResponseView(
                "Cancelled",
                "The action was cancelled.",
                success=False
            )
        )

        self.stop()


# =========================================================
# MODERATION COG
# =========================================================

class Moderation(commands.Cog):
    """Advanced moderation system for Monk."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------------------------------
    # INTERNAL METHODS
    # -----------------------------------------------------

    async def send_log(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.abc.User,
        moderator: discord.abc.User,
        reason: str,
        *,
        duration: Optional[str] = None,
        extra: Optional[str] = None
    ):
        guild_data = database.get_guild(guild.id)
        channel_id = guild_data.get("log_channel")

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(
                view=ModerationLogView(
                    action,
                    target,
                    moderator,
                    reason,
                    duration=duration,
                    extra=extra
                )
            )

        except discord.HTTPException:
            pass

    async def perform_warn(
        self,
        guild: discord.Guild,
        moderator: discord.Member,
        member: discord.Member,
        reason: str
    ):
        warning_id = database.add_warning(
            guild.id,
            member.id,
            moderator.id,
            reason
        )

        database.add_history(
            guild.id,
            member.id,
            moderator.id,
            "Warn",
            reason
        )

        await safe_dm(
            member,
            f"You were warned in {guild.name}",
            f"**Warning ID:** `{warning_id}`\n"
            f"**Moderator:** {moderator}\n"
            f"**Reason:** {reason}"
        )

        await self.send_log(
            guild,
            "Warn",
            member,
            moderator,
            reason,
            extra=f"**Warning ID:** `{warning_id}`"
        )

        return warning_id

    async def perform_timeout(
        self,
        guild: discord.Guild,
        moderator: discord.Member,
        member: discord.Member,
        duration: timedelta,
        duration_text: str,
        reason: str
    ):
        await safe_dm(
            member,
            f"You were timed out in {guild.name}",
            f"**Moderator:** {moderator}\n"
            f"**Duration:** {duration_text}\n"
            f"**Reason:** {reason}"
        )

        await member.timeout(
            duration,
            reason=f"{reason} | Moderator: {moderator}"
        )

        database.add_history(
            guild.id,
            member.id,
            moderator.id,
            "Timeout",
            reason,
            duration_text
        )

        await self.send_log(
            guild,
            "Timeout",
            member,
            moderator,
            reason,
            duration=duration_text
        )

    async def perform_kick(
        self,
        guild: discord.Guild,
        moderator: discord.Member,
        member: discord.Member,
        reason: str
    ):
        await safe_dm(
            member,
            f"You were kicked from {guild.name}",
            f"**Moderator:** {moderator}\n"
            f"**Reason:** {reason}"
        )

        database.add_history(
            guild.id,
            member.id,
            moderator.id,
            "Kick",
            reason
        )

        await member.kick(
            reason=f"{reason} | Moderator: {moderator}"
        )

        await self.send_log(
            guild,
            "Kick",
            member,
            moderator,
            reason
        )

    async def perform_ban(
        self,
        guild: discord.Guild,
        moderator: discord.Member,
        member: discord.Member,
        reason: str,
        delete_seconds: int = 0
    ):
        await safe_dm(
            member,
            f"You were banned from {guild.name}",
            f"**Moderator:** {moderator}\n"
            f"**Reason:** {reason}"
        )

        database.add_history(
            guild.id,
            member.id,
            moderator.id,
            "Ban",
            reason
        )

        await guild.ban(
            member,
            reason=f"{reason} | Moderator: {moderator}",
            delete_message_seconds=delete_seconds
        )

        await self.send_log(
            guild,
            "Ban",
            member,
            moderator,
            reason
        )

    async def send_command_response(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        *,
        success: bool = True,
        thumbnail: Optional[str] = None
    ):
        await ctx.send(
            view=ResponseView(
                title,
                description,
                success=success,
                thumbnail=thumbnail
            )
        )

    async def validate_target(
        self,
        ctx: commands.Context,
        member: discord.Member
    ) -> bool:
        error = hierarchy_error(
            ctx.author,
            member,
            ctx.guild.me
        )

        if error:
            await self.send_command_response(
                ctx,
                "Action blocked",
                error,
                success=False
            )
            return False

        return True

    # -----------------------------------------------------
    # PANEL
    # -----------------------------------------------------

    @commands.command(
        name="modpanel",
        aliases=["moderation", "mod"]
    )
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def modpanel(self, ctx: commands.Context):
        """Open the Components V2 moderation panel."""

        await ctx.send(
            view=ModerationPanel(self, ctx.author.id)
        )

    # -----------------------------------------------------
    # LOG CHANNEL
    # -----------------------------------------------------

    @commands.command(name="setmodlog")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setmodlog(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None
    ):
        """Set the server moderation log channel."""

        channel = channel or ctx.channel

        database.set_log_channel(ctx.guild.id, channel.id)

        await self.send_command_response(
            ctx,
            "Moderation logs configured",
            f"Moderation logs will now be sent to {channel.mention}."
        )

    @commands.command(name="removemodlog")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def removemodlog(self, ctx: commands.Context):
        """Disable moderation logging."""

        database.set_log_channel(ctx.guild.id, None)

        await self.send_command_response(
            ctx,
            "Moderation logs disabled",
            "Moderation actions will no longer be sent to a log channel."
        )

    # -----------------------------------------------------
    # WARNINGS
    # -----------------------------------------------------

    @commands.command(name="warn")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Warn a server member."""

        if not await self.validate_target(ctx, member):
            return

        reason = clean_reason(reason)

        warning_id = await self.perform_warn(
            ctx.guild,
            ctx.author,
            member,
            reason
        )

        await self.send_command_response(
            ctx,
            "Member warned",
            f"{member.mention} has been warned.\n\n"
            f"**Warning ID:** `{warning_id}`\n"
            f"**Reason:** {reason}",
            thumbnail=member.display_avatar.url
        )

    @commands.command(
        name="warnings",
        aliases=["warns"]
    )
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warnings(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None
    ):
        """View a member's warnings."""

        member = member or ctx.author

        warning_list = database.get_warnings(
            ctx.guild.id,
            member.id
        )

        if not warning_list:
            return await self.send_command_response(
                ctx,
                "No warnings",
                f"{member.mention} has no warnings.",
                thumbnail=member.display_avatar.url
            )

        lines = []

        for warning in warning_list[-15:]:
            moderator = ctx.guild.get_member(
                warning["moderator_id"]
            )

            moderator_text = (
                moderator.mention
                if moderator
                else f"`{warning['moderator_id']}`"
            )

            lines.append(
                f"### Warning #{warning['id']}\n"
                f"**Moderator:** {moderator_text}\n"
                f"**Reason:** {warning['reason']}\n"
                f"**Date:** {format_timestamp(warning['timestamp'])}"
            )

        await self.send_command_response(
            ctx,
            f"Warnings for {member}",
            "\n\n".join(lines),
            thumbnail=member.display_avatar.url
        )

    @commands.command(name="delwarn")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def delete_warning(
        self,
        ctx: commands.Context,
        member: discord.Member,
        warning_id: int
    ):
        """Delete one warning by its ID."""

        removed = database.remove_warning(
            ctx.guild.id,
            member.id,
            warning_id
        )

        if not removed:
            return await self.send_command_response(
                ctx,
                "Warning not found",
                f"Warning `{warning_id}` was not found for "
                f"{member.mention}.",
                success=False
            )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Warning removed",
            f"Removed warning #{warning_id}"
        )

        await self.send_command_response(
            ctx,
            "Warning removed",
            f"Warning `{warning_id}` was removed from "
            f"{member.mention}."
        )

    @commands.command(name="clearwarns")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def clear_warnings(
        self,
        ctx: commands.Context,
        member: discord.Member
    ):
        """Clear all warnings from a member."""

        view = ConfirmationView(
            ctx.author.id,
            "Clear all warnings?",
            f"This will remove every warning from {member.mention}."
        )

        message = await ctx.send(view=view)

        await view.wait()

        if not view.confirmed:
            return

        amount = database.clear_warnings(
            ctx.guild.id,
            member.id
        )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Warnings cleared",
            f"Cleared {amount} warning(s)"
        )

        await message.edit(
            view=ResponseView(
                "Warnings cleared",
                f"Removed **{amount}** warning(s) from "
                f"{member.mention}."
            )
        )

    # -----------------------------------------------------
    # TIMEOUT
    # -----------------------------------------------------

    @commands.command(
        name="timeout",
        aliases=["mute"]
    )
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Timeout a member. Example: mtimeout @user 2h spam"""

        if not await self.validate_target(ctx, member):
            return

        parsed_duration = parse_duration(duration)

        if not parsed_duration:
            return await self.send_command_response(
                ctx,
                "Invalid duration",
                "Use one of these formats:\n"
                "`30s`, `10m`, `2h`, `3d`, `1w`\n\n"
                "The maximum timeout duration is 28 days.",
                success=False
            )

        reason = clean_reason(reason)

        await self.perform_timeout(
            ctx.guild,
            ctx.author,
            member,
            parsed_duration,
            duration,
            reason
        )

        await self.send_command_response(
            ctx,
            "Member timed out",
            f"{member.mention} has been timed out.\n\n"
            f"**Duration:** {duration}\n"
            f"**Reason:** {reason}",
            thumbnail=member.display_avatar.url
        )

    @commands.command(
        name="untimeout",
        aliases=["unmute", "removetimeout"]
    )
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def remove_timeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Remove a member's timeout."""

        if not await self.validate_target(ctx, member):
            return

        reason = clean_reason(reason)

        await member.timeout(
            None,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Timeout removed",
            reason
        )

        await self.send_log(
            ctx.guild,
            "Timeout removed",
            member,
            ctx.author,
            reason
        )

        await self.send_command_response(
            ctx,
            "Timeout removed",
            f"The timeout was removed from {member.mention}.\n\n"
            f"**Reason:** {reason}",
            thumbnail=member.display_avatar.url
        )

    # -----------------------------------------------------
    # KICK
    # -----------------------------------------------------

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Kick a member."""

        if not await self.validate_target(ctx, member):
            return

        reason = clean_reason(reason)

        await self.perform_kick(
            ctx.guild,
            ctx.author,
            member,
            reason
        )

        await self.send_command_response(
            ctx,
            "Member kicked",
            f"**Member:** {member} (`{member.id}`)\n"
            f"**Reason:** {reason}"
        )

    # -----------------------------------------------------
    # BAN / UNBAN
    # -----------------------------------------------------

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Ban a member."""

        if not await self.validate_target(ctx, member):
            return

        reason = clean_reason(reason)

        await self.perform_ban(
            ctx.guild,
            ctx.author,
            member,
            reason
        )

        await self.send_command_response(
            ctx,
            "Member banned",
            f"**Member:** {member} (`{member.id}`)\n"
            f"**Reason:** {reason}"
        )

    @commands.command(name="softban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def softban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Ban and immediately unban a member to clear messages."""

        if not await self.validate_target(ctx, member):
            return

        reason = clean_reason(reason)

        await safe_dm(
            member,
            f"You were soft-banned from {ctx.guild.name}",
            f"**Moderator:** {ctx.author}\n"
            f"**Reason:** {reason}"
        )

        await ctx.guild.ban(
            member,
            reason=f"{reason} | Moderator: {ctx.author}",
            delete_message_seconds=604800
        )

        await ctx.guild.unban(
            member,
            reason=f"Softban completed | Moderator: {ctx.author}"
        )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Softban",
            reason
        )

        await self.send_log(
            ctx.guild,
            "Softban",
            member,
            ctx.author,
            reason
        )

        await self.send_command_response(
            ctx,
            "Member soft-banned",
            f"{member} was banned and immediately unbanned.\n\n"
            f"**Reason:** {reason}"
        )

    @commands.command(name="unban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(
        self,
        ctx: commands.Context,
        user_id: int,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Unban a user using their Discord ID."""

        try:
            user = await self.bot.fetch_user(user_id)

        except discord.NotFound:
            return await self.send_command_response(
                ctx,
                "User not found",
                "I could not find a Discord user with that ID.",
                success=False
            )

        try:
            await ctx.guild.fetch_ban(user)

        except discord.NotFound:
            return await self.send_command_response(
                ctx,
                "User is not banned",
                f"{user} is not banned from this server.",
                success=False
            )

        reason = clean_reason(reason)

        await ctx.guild.unban(
            user,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        database.add_history(
            ctx.guild.id,
            user.id,
            ctx.author.id,
            "Unban",
            reason
        )

        await self.send_log(
            ctx.guild,
            "Unban",
            user,
            ctx.author,
            reason
        )

        await self.send_command_response(
            ctx,
            "User unbanned",
            f"**User:** {user} (`{user.id}`)\n"
            f"**Reason:** {reason}"
        )

    # -----------------------------------------------------
    # MESSAGE MANAGEMENT
    # -----------------------------------------------------

    @commands.command(
        name="clear",
        aliases=["purge"]
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clear(
        self,
        ctx: commands.Context,
        amount: commands.Range[int, 1, 500],
        member: Optional[discord.Member] = None
    ):
        """
        Clear messages without deleting pinned messages.

        mclear 20
        mclear 20 @member
        """

        await ctx.message.delete()

        def message_check(message: discord.Message):
            if message.pinned:
                return False

            if member:
                return message.author.id == member.id

            return True

        deleted = await ctx.channel.purge(
            limit=amount,
            check=message_check,
            bulk=True
        )

        target_text = (
            f" from {member.mention}"
            if member
            else ""
        )

        response = await ctx.send(
            view=ResponseView(
                "Messages cleared",
                f"Deleted **{len(deleted)}** message(s)"
                f"{target_text}.\n\n"
                "Pinned messages were ignored."
            )
        )

        await self.send_log(
            ctx.guild,
            "Message purge",
            member or ctx.author,
            ctx.author,
            f"Deleted {len(deleted)} messages in "
            f"#{ctx.channel.name}",
            extra=f"**Channel:** {ctx.channel.mention}"
        )

        await asyncio.sleep(5)

        try:
            await response.delete()
        except discord.HTTPException:
            pass

    # -----------------------------------------------------
    # CHANNEL MANAGEMENT
    # -----------------------------------------------------

    @commands.command(name="lock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Lock a text channel."""

        channel = channel or ctx.channel
        role = ctx.guild.default_role

        overwrite = channel.overwrites_for(role)

        database.save_lock_permissions(
            ctx.guild.id,
            channel.id,
            overwrite.send_messages
        )

        overwrite.send_messages = False

        await channel.set_permissions(
            role,
            overwrite=overwrite,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        await self.send_command_response(
            ctx,
            "Channel locked",
            f"{channel.mention} has been locked.\n\n"
            f"**Reason:** {reason}"
        )

        await self.send_log(
            ctx.guild,
            "Channel locked",
            ctx.author,
            ctx.author,
            reason,
            extra=f"**Channel:** {channel.mention}"
        )

    @commands.command(name="unlock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Restore a channel's previous send-message permission."""

        channel = channel or ctx.channel
        role = ctx.guild.default_role

        overwrite = channel.overwrites_for(role)

        stored = database.get_lock_permissions(
            ctx.guild.id,
            channel.id
        )

        if stored:
            overwrite.send_messages = stored.get("send_messages")
        else:
            overwrite.send_messages = None

        await channel.set_permissions(
            role,
            overwrite=overwrite,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        database.remove_lock_permissions(
            ctx.guild.id,
            channel.id
        )

        await self.send_command_response(
            ctx,
            "Channel unlocked",
            f"{channel.mention} has been unlocked.\n\n"
            f"**Reason:** {reason}"
        )

        await self.send_log(
            ctx.guild,
            "Channel unlocked",
            ctx.author,
            ctx.author,
            reason,
            extra=f"**Channel:** {channel.mention}"
        )

    @commands.command(name="hide")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def hide(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None
    ):
        """Hide a channel from the default role."""

        channel = channel or ctx.channel
        role = ctx.guild.default_role

        overwrite = channel.overwrites_for(role)
        overwrite.view_channel = False

        await channel.set_permissions(
            role,
            overwrite=overwrite,
            reason=f"Hidden by {ctx.author}"
        )

        await self.send_command_response(
            ctx,
            "Channel hidden",
            f"{channel.mention} is now hidden from `@everyone`."
        )

    @commands.command(name="unhide")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unhide(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None
    ):
        """Make a channel visible to the default role."""

        channel = channel or ctx.channel
        role = ctx.guild.default_role

        overwrite = channel.overwrites_for(role)
        overwrite.view_channel = None

        await channel.set_permissions(
            role,
            overwrite=overwrite,
            reason=f"Unhidden by {ctx.author}"
        )

        await self.send_command_response(
            ctx,
            "Channel visible",
            f"{channel.mention} is now visible to `@everyone`."
        )

    @commands.command(name="slowmode")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: commands.Context,
        seconds: commands.Range[int, 0, 21600]
    ):
        """Set slowmode between 0 and 21600 seconds."""

        await ctx.channel.edit(
            slowmode_delay=seconds,
            reason=f"Changed by {ctx.author}"
        )

        description = (
            "Slowmode has been disabled."
            if seconds == 0
            else f"Slowmode has been set to **{seconds} seconds**."
        )

        await self.send_command_response(
            ctx,
            "Slowmode updated",
            description
        )

    # -----------------------------------------------------
    # ROLE MANAGEMENT
    # -----------------------------------------------------

    @commands.command(name="addrole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def add_role(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Add a role to a member."""

        if not await self.validate_target(ctx, member):
            return

        if role >= ctx.guild.me.top_role:
            return await self.send_command_response(
                ctx,
                "Role hierarchy error",
                "That role is equal to or higher than my highest role.",
                success=False
            )

        if (
            ctx.author != ctx.guild.owner
            and role >= ctx.author.top_role
        ):
            return await self.send_command_response(
                ctx,
                "Role hierarchy error",
                "You cannot manage a role equal to or higher than "
                "your highest role.",
                success=False
            )

        if role in member.roles:
            return await self.send_command_response(
                ctx,
                "Role already assigned",
                f"{member.mention} already has {role.mention}.",
                success=False
            )

        await member.add_roles(
            role,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Role added",
            f"{role.name}: {reason}"
        )

        await self.send_command_response(
            ctx,
            "Role added",
            f"Added {role.mention} to {member.mention}."
        )

    @commands.command(name="removerole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def remove_role(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        reason: str = DEFAULT_REASON
    ):
        """Remove a role from a member."""

        if not await self.validate_target(ctx, member):
            return

        if role >= ctx.guild.me.top_role:
            return await self.send_command_response(
                ctx,
                "Role hierarchy error",
                "That role is equal to or higher than my highest role.",
                success=False
            )

        if (
            ctx.author != ctx.guild.owner
            and role >= ctx.author.top_role
        ):
            return await self.send_command_response(
                ctx,
                "Role hierarchy error",
                "You cannot manage a role equal to or higher than "
                "your highest role.",
                success=False
            )

        if role not in member.roles:
            return await self.send_command_response(
                ctx,
                "Role not assigned",
                f"{member.mention} does not have {role.mention}.",
                success=False
            )

        await member.remove_roles(
            role,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        database.add_history(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "Role removed",
            f"{role.name}: {reason}"
        )

        await self.send_command_response(
            ctx,
            "Role removed",
            f"Removed {role.mention} from {member.mention}."
        )

    # -----------------------------------------------------
    # NICKNAME
    # -----------------------------------------------------

    @commands.command(name="nick")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        nickname: str
    ):
        """Change a member's nickname."""

        if not await self.validate_target(ctx, member):
            return

        nickname = nickname[:32]

        await member.edit(
            nick=nickname,
            reason=f"Changed by {ctx.author}"
        )

        await self.send_command_response(
            ctx,
            "Nickname updated",
            f"{member.mention}'s nickname is now **{nickname}**."
        )

    @commands.command(name="resetnick")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def reset_nickname(
        self,
        ctx: commands.Context,
        member: discord.Member
    ):
        """Reset a member's nickname."""

        if not await self.validate_target(ctx, member):
            return

        await member.edit(
            nick=None,
            reason=f"Reset by {ctx.author}"
        )

        await self.send_command_response(
            ctx,
            "Nickname reset",
            f"{member.mention}'s nickname has been reset."
        )

    # -----------------------------------------------------
    # INFORMATION
    # -----------------------------------------------------

    @commands.command(
        name="userinfo",
        aliases=["whois", "ui"]
    )
    @commands.guild_only()
    async def userinfo(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None
    ):
        """View detailed information about a member."""

        member = member or ctx.author

        roles = [
            role.mention
            for role in reversed(member.roles[1:])
        ]

        roles_text = ", ".join(roles[:15]) or "No roles"

        if len(roles) > 15:
            roles_text += f" and {len(roles) - 15} more"

        timeout_text = "No"

        if member.is_timed_out():
            timeout_text = (
                f"Yes, until "
                f"{discord.utils.format_dt(member.timed_out_until, style='R')}"
            )

        warning_count = len(
            database.get_warnings(ctx.guild.id, member.id)
        )

        history_count = len(
            database.get_history(ctx.guild.id, member.id)
        )

        description = (
            f"**Username:** {member}\n"
            f"**Display name:** {member.display_name}\n"
            f"**User ID:** `{member.id}`\n"
            f"**Bot account:** {'Yes' if member.bot else 'No'}\n"
            f"**Created:** "
            f"{discord.utils.format_dt(member.created_at, style='R')}\n"
            f"**Joined:** "
            f"{discord.utils.format_dt(member.joined_at, style='R') if member.joined_at else 'Unknown'}\n"
            f"**Highest role:** {member.top_role.mention}\n"
            f"**Timed out:** {timeout_text}\n"
            f"**Warnings:** {warning_count}\n"
            f"**History entries:** {history_count}\n\n"
            f"**Roles:** {roles_text}"
        )

        await self.send_command_response(
            ctx,
            f"User information — {member}",
            description,
            thumbnail=member.display_avatar.url
        )

    @commands.command(name="history")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def punishment_history(
        self,
        ctx: commands.Context,
        member: discord.Member
    ):
        """View a member's punishment history."""

        history = database.get_history(
            ctx.guild.id,
            member.id
        )

        if not history:
            return await self.send_command_response(
                ctx,
                "No moderation history",
                f"{member.mention} has no stored moderation history."
            )

        lines = []

        for entry in history[-15:]:
            moderator = ctx.guild.get_member(
                entry["moderator_id"]
            )

            moderator_text = (
                moderator.mention
                if moderator
                else f"`{entry['moderator_id']}`"
            )

            duration = (
                f"\n**Duration:** {entry['duration']}"
                if entry.get("duration")
                else ""
            )

            lines.append(
                f"### {entry['action']}\n"
                f"**Moderator:** {moderator_text}\n"
                f"**Reason:** {entry['reason']}"
                f"{duration}\n"
                f"**Date:** {format_timestamp(entry['timestamp'])}"
            )

        await self.send_command_response(
            ctx,
            f"Moderation history — {member}",
            "\n\n".join(lines),
            thumbnail=member.display_avatar.url
        )

    @commands.command(name="serverinfo")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        """View server information."""

        guild = ctx.guild

        humans = len([
            member
            for member in guild.members
            if not member.bot
        ])

        bots = len([
            member
            for member in guild.members
            if member.bot
        ])

        description = (
            f"**Server name:** {guild.name}\n"
            f"**Server ID:** `{guild.id}`\n"
            f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"**Created:** "
            f"{discord.utils.format_dt(guild.created_at, style='R')}\n"
            f"**Members:** {guild.member_count}\n"
            f"**Humans:** {humans}\n"
            f"**Bots:** {bots}\n"
            f"**Text channels:** {len(guild.text_channels)}\n"
            f"**Voice channels:** {len(guild.voice_channels)}\n"
            f"**Roles:** {len(guild.roles)}\n"
            f"**Boosts:** {guild.premium_subscription_count}\n"
            f"**Boost level:** {guild.premium_tier}"
        )

        thumbnail = guild.icon.url if guild.icon else None

        await self.send_command_response(
            ctx,
            f"Server information — {guild.name}",
            description,
            thumbnail=thumbnail
        )

    # -----------------------------------------------------
    # ERROR HANDLER
    # -----------------------------------------------------

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(
                view=ResponseView(
                    "Server only",
                    "This command can only be used inside a server.",
                    success=False
                )
            )

        if isinstance(error, commands.MissingPermissions):
            permissions = ", ".join(
                permission.replace("_", " ").title()
                for permission in error.missing_permissions
            )

            return await ctx.send(
                view=ResponseView(
                    "Missing permissions",
                    f"You need the following permission(s):\n"
                    f"**{permissions}**",
                    success=False
                )
            )

        if isinstance(error, commands.BotMissingPermissions):
            permissions = ", ".join(
                permission.replace("_", " ").title()
                for permission in error.missing_permissions
            )

            return await ctx.send(
                view=ResponseView(
                    "Bot permissions missing",
                    f"I need the following permission(s):\n"
                    f"**{permissions}**",
                    success=False
                )
            )

        if isinstance(error, commands.MemberNotFound):
            return await ctx.send(
                view=ResponseView(
                    "Member not found",
                    "Mention a valid member or provide their ID.",
                    success=False
                )
            )

        if isinstance(error, commands.RoleNotFound):
            return await ctx.send(
                view=ResponseView(
                    "Role not found",
                    "Mention a valid role or provide its ID.",
                    success=False
                )
            )

        if isinstance(error, commands.ChannelNotFound):
            return await ctx.send(
                view=ResponseView(
                    "Channel not found",
                    "Mention a valid text channel.",
                    success=False
                )
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(
                view=ResponseView(
                    "Missing argument",
                    f"You did not provide `{error.param.name}`.\n\n"
                    f"Use `mhelp` to check the command usage.",
                    success=False
                )
            )

        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                view=ResponseView(
                    "Invalid argument",
                    "One of the provided arguments is invalid.",
                    success=False
                )
            )

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                view=ResponseView(
                    "Command on cooldown",
                    f"Try again in **{error.retry_after:.1f} seconds**.",
                    success=False
                )
            )

        if isinstance(error, discord.Forbidden):
            return await ctx.send(
                view=ResponseView(
                    "Permission error",
                    "Discord blocked this action. Make sure my role is "
                    "above the target's role and that I have the required "
                    "permissions.",
                    success=False
                )
            )

        print(
            f"Error in command {ctx.command}: "
            f"{type(error).__name__}: {error}"
        )

        await ctx.send(
            view=ResponseView(
                "Unexpected error",
                f"An unexpected error occurred:\n"
                f"```py\n{type(error).__name__}: {error}\n```",
                success=False
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))