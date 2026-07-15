import json
import os
from typing import Any, Optional

import discord
from discord.ext import commands


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_PATH = "database/config.json"
ACCENT_COLOR = discord.Color.from_rgb(198, 145, 73)
SUCCESS_COLOR = discord.Color.from_rgb(70, 190, 120)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 75)

DEFAULT_CONFIG: dict[str, Any] = {
    "mod_logs": None,
    "welcome_channel": None,
    "leave_channel": None,
    "ticket_category": None,
    "ticket_logs": None,
    "music_channel": None,
    "dj_role": None,
    "moderator_role": None,
    "auto_role": None,
    "announcement_channel": None,
    "prefix": "m",
    "ignored_channels": [],
    "verification_role": None,
    "join_to_create_category": None,
}


# =========================================================
# JSON DATABASE
# =========================================================

class ConfigDatabase:
    def __init__(self, path: str):
        self.path = path
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
                raise ValueError("Database root must be an object.")

            data.setdefault("guilds", {})
            return data

        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = {"guilds": {}}
            self._save(data)
            return data

    def _save(self, data: dict[str, Any]) -> None:
        temporary_path = f"{self.path}.tmp"

        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

        os.replace(temporary_path, self.path)

    def get_guild(self, guild_id: int) -> dict[str, Any]:
        data = self._load()
        key = str(guild_id)

        stored = data["guilds"].setdefault(key, {})
        changed = False

        for setting, default_value in DEFAULT_CONFIG.items():
            if setting not in stored:
                stored[setting] = (
                    list(default_value)
                    if isinstance(default_value, list)
                    else default_value
                )
                changed = True

        if changed:
            self._save(data)

        return stored.copy()

    def set(self, guild_id: int, setting: str, value: Any) -> None:
        if setting not in DEFAULT_CONFIG:
            raise KeyError(f"Unknown setting: {setting}")

        data = self._load()
        key = str(guild_id)
        guild_config = data["guilds"].setdefault(key, {})

        for config_key, default_value in DEFAULT_CONFIG.items():
            guild_config.setdefault(
                config_key,
                list(default_value)
                if isinstance(default_value, list)
                else default_value
            )

        guild_config[setting] = value
        self._save(data)

    def reset(self, guild_id: int) -> None:
        data = self._load()
        data["guilds"][str(guild_id)] = {
            key: list(value) if isinstance(value, list) else value
            for key, value in DEFAULT_CONFIG.items()
        }
        self._save(data)


config_db = ConfigDatabase(DATABASE_PATH)


# =========================================================
# PUBLIC CONFIG HELPERS
# Import these from other cogs when needed.
# =========================================================

def get_guild_config(guild_id: int) -> dict[str, Any]:
    return config_db.get_guild(guild_id)


def get_config_value(guild_id: int, setting: str, default: Any = None) -> Any:
    return config_db.get_guild(guild_id).get(setting, default)


# =========================================================
# DISPLAY HELPERS
# =========================================================

SETTING_LABELS = {
    "mod_logs": "Moderation Logs",
    "welcome_channel": "Welcome Channel",
    "leave_channel": "Leave Channel",
    "ticket_category": "Ticket Category",
    "ticket_logs": "Ticket Logs",
    "music_channel": "Music Channel",
    "dj_role": "DJ Role",
    "moderator_role": "Moderator Role",
    "auto_role": "Auto Role",
    "announcement_channel": "Announcement Channel",
    "prefix": "Bot Prefix",
    "ignored_channels": "Ignored Channels",
    "verification_role": "Verification Role",
    "join_to_create_category": "Join-to-Create Category",
}

SETTING_EMOJIS = {
    "mod_logs": "📜",
    "welcome_channel": "👋",
    "leave_channel": "📤",
    "ticket_category": "🎫",
    "ticket_logs": "🧾",
    "music_channel": "🎵",
    "dj_role": "🎧",
    "moderator_role": "🛡️",
    "auto_role": "⭐",
    "announcement_channel": "📢",
    "prefix": "⌨️",
    "ignored_channels": "🚫",
    "verification_role": "✅",
    "join_to_create_category": "🔊",
}


def channel_text(guild: discord.Guild, channel_id: Optional[int]) -> str:
    if not channel_id:
        return "`Not configured`"

    channel = guild.get_channel(channel_id)

    if channel:
        return channel.mention

    return f"`Deleted channel: {channel_id}`"


def category_text(guild: discord.Guild, category_id: Optional[int]) -> str:
    if not category_id:
        return "`Not configured`"

    category = guild.get_channel(category_id)

    if isinstance(category, discord.CategoryChannel):
        return f"`{category.name}`"

    return f"`Deleted category: {category_id}`"


def role_text(guild: discord.Guild, role_id: Optional[int]) -> str:
    if not role_id:
        return "`Not configured`"

    role = guild.get_role(role_id)

    if role:
        return role.mention

    return f"`Deleted role: {role_id}`"


def ignored_channels_text(guild: discord.Guild, channel_ids: list[int]) -> str:
    if not channel_ids:
        return "`None`"

    values = []

    for channel_id in channel_ids[:15]:
        channel = guild.get_channel(channel_id)
        values.append(channel.mention if channel else f"`{channel_id}`")

    if len(channel_ids) > 15:
        values.append(f"`+{len(channel_ids) - 15} more`")

    return ", ".join(values)


def format_config(guild: discord.Guild) -> str:
    config = config_db.get_guild(guild.id)

    return (
        f"📜 **Moderation Logs:** {channel_text(guild, config['mod_logs'])}\n"
        f"👋 **Welcome Channel:** {channel_text(guild, config['welcome_channel'])}\n"
        f"📤 **Leave Channel:** {channel_text(guild, config['leave_channel'])}\n"
        f"🎫 **Ticket Category:** {category_text(guild, config['ticket_category'])}\n"
        f"🧾 **Ticket Logs:** {channel_text(guild, config['ticket_logs'])}\n"
        f"🎵 **Music Channel:** {channel_text(guild, config['music_channel'])}\n"
        f"🎧 **DJ Role:** {role_text(guild, config['dj_role'])}\n"
        f"🛡️ **Moderator Role:** {role_text(guild, config['moderator_role'])}\n"
        f"⭐ **Auto Role:** {role_text(guild, config['auto_role'])}\n"
        f"📢 **Announcement Channel:** "
        f"{channel_text(guild, config['announcement_channel'])}\n"
        f"⌨️ **Prefix:** `{config['prefix']}`\n"
        f"🚫 **Ignored Channels:** "
        f"{ignored_channels_text(guild, config['ignored_channels'])}\n"
        f"✅ **Verification Role:** {role_text(guild, config['verification_role'])}\n"
        f"🔊 **Join-to-Create Category:** "
        f"{category_text(guild, config['join_to_create_category'])}"
    )


class SimpleView(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        success: bool = True,
    ):
        super().__init__(timeout=60)

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=SUCCESS_COLOR if success else ERROR_COLOR,
            )
        )


async def send_ephemeral_result(
    interaction: discord.Interaction,
    title: str,
    description: str,
    *,
    success: bool = True,
) -> None:
    view = SimpleView(title, description, success=success)

    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


def has_admin_permission(interaction: discord.Interaction) -> bool:
    return (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


# =========================================================
# CHANNEL PICKER
# =========================================================

class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(
        self,
        setting: str,
        *,
        channel_types: list[discord.ChannelType],
        max_values: int = 1,
    ):
        self.setting = setting

        super().__init__(
            placeholder=f"Select {SETTING_LABELS[setting]}",
            min_values=1,
            max_values=max_values,
            channel_types=channel_types,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        if not has_admin_permission(interaction):
            return await send_ephemeral_result(
                interaction,
                "Permission denied",
                "You need the **Administrator** permission.",
                success=False,
            )

        if self.setting == "ignored_channels":
            values = [channel.id for channel in self.values]
            config_db.set(interaction.guild.id, self.setting, values)

            mentions = ", ".join(channel.mention for channel in self.values)

            return await send_ephemeral_result(
                interaction,
                "Ignored channels updated",
                f"Commands or automatic systems can now ignore:\n{mentions}",
            )

        selected = self.values[0]
        config_db.set(interaction.guild.id, self.setting, selected.id)

        shown_value = (
            f"`{selected.name}`"
            if isinstance(selected, discord.CategoryChannel)
            else selected.mention
        )

        await send_ephemeral_result(
            interaction,
            f"{SETTING_LABELS[self.setting]} updated",
            f"Saved {shown_value}.",
        )


class ChannelPickerView(discord.ui.LayoutView):
    def __init__(
        self,
        setting: str,
        *,
        channel_types: list[discord.ChannelType],
        max_values: int = 1,
    ):
        super().__init__(timeout=120)

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        container.add_item(
            discord.ui.TextDisplay(
                f"## {SETTING_EMOJIS[setting]} Set {SETTING_LABELS[setting]}"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose the required channel below. The selection is saved "
                "immediately for this server."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(
            ChannelPicker(
                setting,
                channel_types=channel_types,
                max_values=max_values,
            )
        )
        container.add_item(row)

        self.add_item(container)


# =========================================================
# ROLE PICKER
# =========================================================

class ConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, setting: str):
        self.setting = setting

        super().__init__(
            placeholder=f"Select {SETTING_LABELS[setting]}",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        if not has_admin_permission(interaction):
            return await send_ephemeral_result(
                interaction,
                "Permission denied",
                "You need the **Administrator** permission.",
                success=False,
            )

        role = self.values[0]

        if role.is_default():
            return await send_ephemeral_result(
                interaction,
                "Invalid role",
                "The `@everyone` role cannot be used here.",
                success=False,
            )

        config_db.set(interaction.guild.id, self.setting, role.id)

        await send_ephemeral_result(
            interaction,
            f"{SETTING_LABELS[self.setting]} updated",
            f"Saved {role.mention}.",
        )


class RolePickerView(discord.ui.LayoutView):
    def __init__(self, setting: str):
        super().__init__(timeout=120)

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)
        container.add_item(
            discord.ui.TextDisplay(
                f"## {SETTING_EMOJIS[setting]} Set {SETTING_LABELS[setting]}"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose a role below. Make sure the bot's role is above any "
                "role it needs to assign or manage."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(ConfigRoleSelect(setting))
        container.add_item(row)

        self.add_item(container)


# =========================================================
# PREFIX MODAL
# =========================================================

class PrefixModal(discord.ui.Modal, title="Set Bot Prefix"):
    prefix_input = discord.ui.TextInput(
        label="New prefix",
        placeholder="Example: m, m!, >>",
        min_length=1,
        max_length=10,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        if not has_admin_permission(interaction):
            return await send_ephemeral_result(
                interaction,
                "Permission denied",
                "You need the **Administrator** permission.",
                success=False,
            )

        prefix = self.prefix_input.value.strip()

        if not prefix:
            return await send_ephemeral_result(
                interaction,
                "Invalid prefix",
                "The prefix cannot be empty.",
                success=False,
            )

        if prefix.startswith("/"):
            return await send_ephemeral_result(
                interaction,
                "Invalid prefix",
                "A text-command prefix cannot start with `/`.",
                success=False,
            )

        config_db.set(interaction.guild.id, "prefix", prefix)

        await send_ephemeral_result(
            interaction,
            "Prefix updated",
            f"The server prefix is now `{prefix}`.\n\n"
            "Your main bot file must use the dynamic prefix function included "
            "at the bottom of this file.",
        )


# =========================================================
# RESET CONFIRMATION
# =========================================================

class ResetConfirmationView(discord.ui.LayoutView):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id

        container = discord.ui.Container(accent_colour=discord.Color.orange())
        container.add_item(discord.ui.TextDisplay("## ⚠️ Reset Configuration"))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "This will remove every Monk setting for this server and "
                "restore the default prefix `m`."
            )
        )

        row = discord.ui.ActionRow()

        confirm = discord.ui.Button(
            label="Reset Everything",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
        )
        cancel = discord.ui.Button(
            label="Cancel",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
        )

        confirm.callback = self.confirm
        cancel.callback = self.cancel

        row.add_item(confirm)
        row.add_item(cancel)
        container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await send_ephemeral_result(
                interaction,
                "This confirmation is not yours",
                "Run `msetup` to open your own setup panel.",
                success=False,
            )
            return False

        return True

    async def confirm(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        config_db.reset(interaction.guild.id)

        await interaction.response.edit_message(
            view=SimpleView(
                "Configuration reset",
                "All settings were cleared and the prefix was restored to `m`.",
            )
        )
        self.stop()

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            view=SimpleView(
                "Reset cancelled",
                "No settings were changed.",
                success=False,
            )
        )
        self.stop()


# =========================================================
# MAIN SETUP SELECT
# =========================================================

class SetupOptionSelect(discord.ui.Select):
    def __init__(self, parent_view: "SetupPanel"):
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label="Moderation Logs",
                value="mod_logs",
                emoji="📜",
                description="Where moderation actions are logged.",
            ),
            discord.SelectOption(
                label="Welcome Channel",
                value="welcome_channel",
                emoji="👋",
                description="Where member welcome messages are sent.",
            ),
            discord.SelectOption(
                label="Leave Channel",
                value="leave_channel",
                emoji="📤",
                description="Where member leave messages are sent.",
            ),
            discord.SelectOption(
                label="Ticket Category",
                value="ticket_category",
                emoji="🎫",
                description="Category where new tickets are created.",
            ),
            discord.SelectOption(
                label="Ticket Logs",
                value="ticket_logs",
                emoji="🧾",
                description="Channel for ticket transcripts and logs.",
            ),
            discord.SelectOption(
                label="Music Channel",
                value="music_channel",
                emoji="🎵",
                description="Channel restricted to music commands.",
            ),
            discord.SelectOption(
                label="DJ Role",
                value="dj_role",
                emoji="🎧",
                description="Role allowed to control the music player.",
            ),
            discord.SelectOption(
                label="Moderator Role",
                value="moderator_role",
                emoji="🛡️",
                description="Main moderation staff role.",
            ),
            discord.SelectOption(
                label="Auto Role",
                value="auto_role",
                emoji="⭐",
                description="Role automatically assigned to new members.",
            ),
            discord.SelectOption(
                label="Announcement Channel",
                value="announcement_channel",
                emoji="📢",
                description="Default announcements destination.",
            ),
            discord.SelectOption(
                label="Bot Prefix",
                value="prefix",
                emoji="⌨️",
                description="Change the server text-command prefix.",
            ),
            discord.SelectOption(
                label="Ignored Channels",
                value="ignored_channels",
                emoji="🚫",
                description="Channels ignored by commands or automation.",
            ),
            discord.SelectOption(
                label="Verification Role",
                value="verification_role",
                emoji="✅",
                description="Role assigned after verification.",
            ),
            discord.SelectOption(
                label="Join-to-Create Category",
                value="join_to_create_category",
                emoji="🔊",
                description="Category used for temporary voice channels.",
            ),
        ]

        super().__init__(
            placeholder="Choose a setting to configure",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]

        if not has_admin_permission(interaction):
            return await send_ephemeral_result(
                interaction,
                "Permission denied",
                "You need the **Administrator** permission.",
                success=False,
            )

        if setting == "prefix":
            return await interaction.response.send_modal(PrefixModal())

        role_settings = {
            "dj_role",
            "moderator_role",
            "auto_role",
            "verification_role",
        }

        if setting in role_settings:
            return await interaction.response.send_message(
                view=RolePickerView(setting),
                ephemeral=True,
            )

        category_settings = {
            "ticket_category",
            "join_to_create_category",
        }

        if setting in category_settings:
            return await interaction.response.send_message(
                view=ChannelPickerView(
                    setting,
                    channel_types=[discord.ChannelType.category],
                ),
                ephemeral=True,
            )

        if setting == "ignored_channels":
            return await interaction.response.send_message(
                view=ChannelPickerView(
                    setting,
                    channel_types=[
                        discord.ChannelType.text,
                        discord.ChannelType.news,
                        discord.ChannelType.voice,
                        discord.ChannelType.stage_voice,
                        discord.ChannelType.forum,
                    ],
                    max_values=10,
                ),
                ephemeral=True,
            )

        await interaction.response.send_message(
            view=ChannelPickerView(
                setting,
                channel_types=[
                    discord.ChannelType.text,
                    discord.ChannelType.news,
                ],
            ),
            ephemeral=True,
        )


# =========================================================
# MAIN SETUP PANEL
# =========================================================

class SetupPanel(discord.ui.LayoutView):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id
        self.build()

    def build(self):
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        icon_url = self.guild.icon.url if self.guild.icon else None

        if icon_url:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay("## ⚙️ Monk Server Setup"),
                    discord.ui.TextDisplay(
                        f"Configure Monk for **{self.guild.name}**."
                    ),
                    accessory=discord.ui.Thumbnail(icon_url),
                )
            )
        else:
            container.add_item(discord.ui.TextDisplay("## ⚙️ Monk Server Setup"))
            container.add_item(
                discord.ui.TextDisplay(
                    f"Configure Monk for **{self.guild.name}**."
                )
            )

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose a setting from the menu. Channel and role settings "
                "use Discord's native pickers, so you do not need to copy IDs."
            )
        )

        select_row = discord.ui.ActionRow()
        select_row.add_item(SetupOptionSelect(self))
        container.add_item(select_row)

        container.add_item(discord.ui.Separator())

        button_row = discord.ui.ActionRow()

        view_config = discord.ui.Button(
            label="View Config",
            emoji="📋",
            style=discord.ButtonStyle.primary,
        )
        refresh = discord.ui.Button(
            label="Refresh",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
        )
        reset = discord.ui.Button(
            label="Reset",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
        )
        close = discord.ui.Button(
            label="Close",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
        )

        view_config.callback = self.view_config
        refresh.callback = self.refresh
        reset.callback = self.reset
        close.callback = self.close

        button_row.add_item(view_config)
        button_row.add_item(refresh)
        button_row.add_item(reset)
        button_row.add_item(close)

        container.add_item(button_row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await send_ephemeral_result(
                interaction,
                "This panel is not yours",
                "Run the setup command to open your own panel.",
                success=False,
            )
            return False

        if not has_admin_permission(interaction):
            await send_ephemeral_result(
                interaction,
                "Permission denied",
                "You need the **Administrator** permission.",
                success=False,
            )
            return False

        return True

    async def view_config(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=SimpleView(
                "Current Server Configuration",
                format_config(self.guild),
            ),
            ephemeral=True,
        )

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def reset(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=ResetConfirmationView(interaction.user.id),
            ephemeral=True,
        )

    async def close(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# SETUP COG
# =========================================================

class Setup(commands.Cog):
    """Interactive server configuration for Monk."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="setup",
        aliases=["config", "configuration"],
        help="Open Monk's interactive server setup panel.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup_command(self, ctx: commands.Context):
        await ctx.send(
            view=SetupPanel(ctx.guild, ctx.author.id)
        )

    @commands.command(
        name="viewconfig",
        aliases=["showconfig"],
        help="Display the current Monk configuration.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def view_config_command(self, ctx: commands.Context):
        await ctx.send(
            view=SimpleView(
                "Current Server Configuration",
                format_config(ctx.guild),
            )
        )

    @commands.command(
        name="resetconfig",
        help="Reset every Monk setting for this server.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def reset_config_command(self, ctx: commands.Context):
        await ctx.send(
            view=ResetConfirmationView(ctx.author.id)
        )

    @setup_command.error
    @view_config_command.error
    @reset_config_command.error
    async def setup_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(
                view=SimpleView(
                    "Server only",
                    "This command can only be used inside a server.",
                    success=False,
                )
            )

        if isinstance(error, commands.MissingPermissions):
            return await ctx.send(
                view=SimpleView(
                    "Permission denied",
                    "You need the **Administrator** permission.",
                    success=False,
                )
            )

        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))


# =========================================================
# DYNAMIC PREFIX
# =========================================================
#
# Put this function in main.py, or import it:
#
# from cogs.setup import get_dynamic_prefix
#
# Then use:
#
# bot = commands.Bot(
#     command_prefix=get_dynamic_prefix,
#     intents=intents,
#     help_command=None,
#     case_insensitive=True
# )
#
# Mentioning the bot will also work as a prefix.
# =========================================================

async def get_dynamic_prefix(
    bot: commands.Bot,
    message: discord.Message,
):
    if not message.guild:
        return commands.when_mentioned_or("m")(bot, message)

    prefix = get_config_value(message.guild.id, "prefix", "m")
    return commands.when_mentioned_or(prefix)(bot, message)