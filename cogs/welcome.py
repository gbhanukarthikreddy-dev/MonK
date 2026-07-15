import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord.ext import commands


# =========================================================
# COMPLETE WELCOME CONFIGURATION
# =========================================================

DATABASE_PATH = "database/welcome.json"

ACCENT_COLOR = discord.Color.from_rgb(198, 145, 73)
SUCCESS_COLOR = discord.Color.from_rgb(70, 190, 120)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 75)
WARNING_COLOR = discord.Color.from_rgb(235, 175, 65)

DEFAULT_TITLE = "Welcome to {server}!"
DEFAULT_DESCRIPTION = (
    "Hey {mention}, welcome to **{server}**!\n"
    "You are member **#{member_count}**.\n\n"
    "Please read the rules, introduce yourself, and enjoy your stay."
)

DEFAULT_GOODBYE_TITLE = "A member has left"
DEFAULT_GOODBYE_DESCRIPTION = (
    "**{user}** has left **{server}**.\n"
    "The server now has **{member_count}** members."
)

DEFAULT_DM_TITLE = "Welcome to {server}!"
DEFAULT_DM_DESCRIPTION = (
    "Thanks for joining **{server}**!\n\n"
    "Please make sure to read the rules and follow the server guidelines."
)

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "welcome_channel_id": None,
    "goodbye_enabled": False,
    "goodbye_channel_id": None,

    "title": DEFAULT_TITLE,
    "description": DEFAULT_DESCRIPTION,

    "goodbye_title": DEFAULT_GOODBYE_TITLE,
    "goodbye_description": DEFAULT_GOODBYE_DESCRIPTION,

    "dm_enabled": False,
    "dm_title": DEFAULT_DM_TITLE,
    "dm_description": DEFAULT_DM_DESCRIPTION,

    "autorole_id": None,
    "ping_member": False,
    "show_account_age": True,
    "minimum_account_age_days": 7,

    "rules_channel_id": None,
    "introduction_channel_id": None,
    "support_channel_id": None,

    "welcome_count": 0,
    "leave_count": 0,
}


# =========================================================
# CUSTOM EMOJIS
# =========================================================
# Accepted formats:
#
# 123456789012345678
# "123456789012345678"
# "<:name:123456789012345678>"
# "<a:name:123456789012345678>"
#
# Leave as None to use the Unicode fallback.

CUSTOM_EMOJI_IDS = {
    "welcome": '<a:752588ononono:1527052268493476033>',
    "goodbye": None,
    "member": '<a:8712arrowright:1527056579487334400>',
    "server": '<a:8712arrowright:1527056579487334400>',
    "calendar": '<a:8712arrowright:1527056579487334400>',
    "rules": '<a:8712arrowright:1527056579487334400>',
    "introduce": '<a:8712arrowright:1527056579487334400>',
    "support": '<a:8712arrowright:1527056579487334400>',
    "success": None,
    "error": None,
    "warning": None,
    "settings": None,
    "test": None,
    "role": None,
    "dm": None,
}

EMOJI_FALLBACKS = {
    "welcome": "👋",
    "goodbye": "📤",
    "member": "👤",
    "server": "🌐",
    "calendar": "📅",
    "rules": "📜",
    "introduce": "💬",
    "support": "🛟",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "settings": "⚙️",
    "test": "🧪",
    "role": "⭐",
    "dm": "✉️",
}


# =========================================================
# EMOJI HELPERS
# =========================================================

def get_emoji(
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
    return str(get_emoji(bot, key))


# =========================================================
# DATABASE
# =========================================================

class WelcomeDatabase:
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
    def _merge_defaults(config: dict[str, Any]) -> bool:
        changed = False

        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = copy.deepcopy(value)
                changed = True

        return changed

    def get_guild(self, guild_id: int) -> dict[str, Any]:
        data = self._load()
        key = str(guild_id)

        config = data["guilds"].setdefault(
            key,
            copy.deepcopy(DEFAULT_CONFIG),
        )

        if self._merge_defaults(config):
            self._save(data)

        return copy.deepcopy(config)

    def save_guild(
        self,
        guild_id: int,
        config: dict[str, Any],
    ) -> None:
        data = self._load()
        self._merge_defaults(config)
        data["guilds"][str(guild_id)] = config
        self._save(data)


welcome_db = WelcomeDatabase(DATABASE_PATH)


# =========================================================
# PLACEHOLDER HELPERS
# =========================================================

def account_age_days(member: discord.Member) -> int:
    now = datetime.now(timezone.utc)
    return max(0, (now - member.created_at).days)


def replace_placeholders(
    text: str,
    member: discord.Member,
) -> str:
    replacements = {
        "{mention}": member.mention,
        "{user}": str(member),
        "{username}": member.name,
        "{display_name}": member.display_name,
        "{user_id}": str(member.id),
        "{server}": member.guild.name,
        "{server_id}": str(member.guild.id),
        "{member_count}": str(member.guild.member_count or 0),
        "{account_age}": str(account_age_days(member)),
        "{created_at}": discord.utils.format_dt(
            member.created_at,
            style="F",
        ),
    }

    result = text

    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


# =========================================================
# RESPONSE VIEW
# =========================================================

class WelcomeResponse(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        title: str,
        description: str,
        *,
        emoji_key: str = "settings",
        success: bool = True,
        warning: bool = False,
    ):
        super().__init__(timeout=60)

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


# =========================================================
# WELCOME VIEW
# =========================================================

class MemberWelcomeView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        member: discord.Member,
        config: dict[str, Any],
        *,
        test_mode: bool = False,
    ):
        super().__init__(timeout=None)

        self.bot = bot
        self.member = member
        self.config = config
        self.test_mode = test_mode

        self.build()

    def build(self) -> None:
        guild = self.member.guild
        age_days = account_age_days(self.member)

        title = replace_placeholders(
            self.config["title"],
            self.member,
        )
        description = replace_placeholders(
            self.config["description"],
            self.member,
        )

        container = discord.ui.Container(
            accent_colour=ACCENT_COLOR
        )

        container.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"## {emoji_text(self.bot, 'welcome')} {title}"
                ),
                discord.ui.TextDisplay(description),
                accessory=discord.ui.Thumbnail(
                    self.member.display_avatar.url
                ),
            )
        )

        container.add_item(discord.ui.Separator())

        details = (
            f"{emoji_text(self.bot, 'member')} "
            f"**Member:** {self.member.mention}\n"
            f"{emoji_text(self.bot, 'server')} "
            f"**Server:** {guild.name}\n"
            f"{emoji_text(self.bot, 'calendar')} "
            f"**Account created:** "
            f"{discord.utils.format_dt(self.member.created_at, style='R')}"
        )

        if self.config["show_account_age"]:
            details += (
                f"\n{emoji_text(self.bot, 'calendar')} "
                f"**Account age:** `{age_days}` days"
            )

        if self.test_mode:
            details += "\n\n`This is a welcome-message preview.`"

        container.add_item(
            discord.ui.TextDisplay(details)
        )

        minimum_age = int(
            self.config.get("minimum_account_age_days", 0)
        )

        if minimum_age > 0 and age_days < minimum_age:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(
                    f"{emoji_text(self.bot, 'warning')} "
                    f"**New Account Warning**\n"
                    f"This account is only `{age_days}` day"
                    f"{'s' if age_days != 1 else ''} old. "
                    f"The configured minimum is `{minimum_age}` days."
                )
            )

        buttons = []

        rules_channel = guild.get_channel(
            self.config.get("rules_channel_id")
        )
        introduction_channel = guild.get_channel(
            self.config.get("introduction_channel_id")
        )
        support_channel = guild.get_channel(
            self.config.get("support_channel_id")
        )

        if rules_channel:
            buttons.append(
                discord.ui.Button(
                    label="Rules",
                    emoji=get_emoji(self.bot, "rules"),
                    style=discord.ButtonStyle.link,
                    url=rules_channel.jump_url,
                )
            )

        if introduction_channel:
            buttons.append(
                discord.ui.Button(
                    label="Introduce Yourself",
                    emoji=get_emoji(self.bot, "introduce"),
                    style=discord.ButtonStyle.link,
                    url=introduction_channel.jump_url,
                )
            )

        if support_channel:
            buttons.append(
                discord.ui.Button(
                    label="Support",
                    emoji=get_emoji(self.bot, "support"),
                    style=discord.ButtonStyle.link,
                    url=support_channel.jump_url,
                )
            )

        if buttons:
            container.add_item(discord.ui.Separator())
            row = discord.ui.ActionRow()

            for button in buttons[:5]:
                row.add_item(button)

            container.add_item(row)

        self.add_item(container)


# =========================================================
# GOODBYE VIEW
# =========================================================

class MemberGoodbyeView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        member: discord.Member,
        config: dict[str, Any],
    ):
        super().__init__(timeout=None)

        title = replace_placeholders(
            config["goodbye_title"],
            member,
        )
        description = replace_placeholders(
            config["goodbye_description"],
            member,
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"## {emoji_text(bot, 'goodbye')} {title}"
                    ),
                    discord.ui.TextDisplay(description),
                    accessory=discord.ui.Thumbnail(
                        member.display_avatar.url
                    ),
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"{emoji_text(bot, 'member')} "
                    f"**User ID:** `{member.id}`\n"
                    f"{emoji_text(bot, 'calendar')} "
                    f"**Joined Discord:** "
                    f"{discord.utils.format_dt(member.created_at, style='R')}"
                ),
                accent_colour=ERROR_COLOR,
            )
        )


# =========================================================
# CONFIGURATION MODALS
# =========================================================

class WelcomeMessageModal(
    discord.ui.Modal,
    title="Customize Welcome Message",
):
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="Welcome to {server}!",
        required=True,
        max_length=200,
    )

    description_input = discord.ui.TextInput(
        label="Description",
        placeholder="Hey {mention}, welcome to {server}!",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1800,
    )

    def __init__(
        self,
        current_title: str,
        current_description: str,
    ):
        super().__init__()

        self.title_input.default = current_title
        self.description_input.default = current_description

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        config = welcome_db.get_guild(interaction.guild.id)
        config["title"] = self.title_input.value.strip()
        config["description"] = (
            self.description_input.value.strip()
        )
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Welcome Message Updated",
                "The welcome title and description were saved.",
                emoji_key="success",
            ),
            ephemeral=True,
        )


class GoodbyeMessageModal(
    discord.ui.Modal,
    title="Customize Goodbye Message",
):
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="A member has left",
        required=True,
        max_length=200,
    )

    description_input = discord.ui.TextInput(
        label="Description",
        placeholder="{user} has left {server}.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1800,
    )

    def __init__(
        self,
        current_title: str,
        current_description: str,
    ):
        super().__init__()

        self.title_input.default = current_title
        self.description_input.default = current_description

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        config = welcome_db.get_guild(interaction.guild.id)
        config["goodbye_title"] = self.title_input.value.strip()
        config["goodbye_description"] = (
            self.description_input.value.strip()
        )
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Goodbye Message Updated",
                "The goodbye title and description were saved.",
                emoji_key="success",
            ),
            ephemeral=True,
        )


class DMMessageModal(
    discord.ui.Modal,
    title="Customize Welcome DM",
):
    title_input = discord.ui.TextInput(
        label="DM title",
        placeholder="Welcome to {server}!",
        required=True,
        max_length=200,
    )

    description_input = discord.ui.TextInput(
        label="DM description",
        placeholder="Thanks for joining {server}!",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1800,
    )

    def __init__(
        self,
        current_title: str,
        current_description: str,
    ):
        super().__init__()

        self.title_input.default = current_title
        self.description_input.default = current_description

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        config = welcome_db.get_guild(interaction.guild.id)
        config["dm_title"] = self.title_input.value.strip()
        config["dm_description"] = (
            self.description_input.value.strip()
        )
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Welcome DM Updated",
                "The private welcome message was saved.",
                emoji_key="dm",
            ),
            ephemeral=True,
        )


# =========================================================
# CHANNEL AND ROLE PICKERS
# =========================================================

class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, setting: str):
        self.setting = setting

        labels = {
            "welcome_channel_id": "welcome channel",
            "goodbye_channel_id": "goodbye channel",
            "rules_channel_id": "rules channel",
            "introduction_channel_id": "introduction channel",
            "support_channel_id": "support channel",
        }

        super().__init__(
            placeholder=f"Select the {labels[setting]}",
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        channel = self.values[0]
        config = welcome_db.get_guild(interaction.guild.id)
        config[self.setting] = channel.id
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Channel Updated",
                f"Saved {channel.mention}.",
                emoji_key="success",
            ),
            ephemeral=True,
        )


class ChannelPickerView(discord.ui.LayoutView):
    def __init__(self, setting: str):
        super().__init__(timeout=120)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"## {EMOJI_FALLBACKS['settings']} Select Channel"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "Choose the channel from the menu below."
            ),
            accent_colour=ACCENT_COLOR,
        )

        row = discord.ui.ActionRow()
        row.add_item(WelcomeChannelSelect(setting))

        container.add_item(row)
        self.add_item(container)


class AutoRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select the automatic role",
            min_values=1,
            max_values=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        role = self.values[0]

        if role.is_default() or role.managed:
            return await interaction.response.send_message(
                view=WelcomeResponse(
                    interaction.client,
                    "Invalid Role",
                    "Choose a normal role other than `@everyone`.",
                    emoji_key="error",
                    success=False,
                ),
                ephemeral=True,
            )

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                view=WelcomeResponse(
                    interaction.client,
                    "Role Hierarchy Error",
                    "My highest role must be above the autorole.",
                    emoji_key="error",
                    success=False,
                ),
                ephemeral=True,
            )

        config = welcome_db.get_guild(interaction.guild.id)
        config["autorole_id"] = role.id
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Autorole Updated",
                f"New members will receive {role.mention}.",
                emoji_key="role",
            ),
            ephemeral=True,
        )


class AutoRolePickerView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=120)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"## {EMOJI_FALLBACKS['role']} Select Autorole"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "Choose the role automatically assigned to new members."
            ),
            accent_colour=ACCENT_COLOR,
        )

        row = discord.ui.ActionRow()
        row.add_item(AutoRoleSelect())

        container.add_item(row)
        self.add_item(container)


# =========================================================
# SETUP PANEL
# =========================================================

class WelcomeConfigView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "Welcome",
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
            await interaction.response.send_message(
                view=WelcomeResponse(
                    interaction.client,
                    "This Panel Is Not Yours",
                    "Run the configuration command yourself.",
                    emoji_key="error",
                    success=False,
                ),
                ephemeral=True,
            )
            return False

        if not isinstance(interaction.user, discord.Member):
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                view=WelcomeResponse(
                    interaction.client,
                    "Permission Denied",
                    "You need **Administrator** permission.",
                    emoji_key="error",
                    success=False,
                ),
                ephemeral=True,
            )
            return False

        return True

    def build(self) -> None:
        self.clear_items()

        container = discord.ui.Container(
            accent_colour=ACCENT_COLOR
        )

        if self.guild.icon:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        "## 👋 Monk Welcome Configuration"
                    ),
                    discord.ui.TextDisplay(
                        f"Configure welcomes for **{self.guild.name}**."
                    ),
                    accessory=discord.ui.Thumbnail(
                        self.guild.icon.url
                    ),
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    "## 👋 Monk Welcome Configuration"
                )
            )

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Configure welcome and goodbye channels, message text, "
                "autorole, private DMs, useful channel buttons, and previews."
            )
        )

        row_one = discord.ui.ActionRow()

        welcome_channel = discord.ui.Button(
            label="Welcome Channel",
            emoji="👋",
            style=discord.ButtonStyle.primary,
        )
        welcome_message = discord.ui.Button(
            label="Welcome Message",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
        )
        autorole = discord.ui.Button(
            label="Autorole",
            emoji="⭐",
            style=discord.ButtonStyle.secondary,
        )
        welcome_toggle = discord.ui.Button(
            label="Enable/Disable",
            emoji="🔁",
            style=discord.ButtonStyle.success,
        )

        welcome_channel.callback = self.welcome_channel
        welcome_message.callback = self.welcome_message
        autorole.callback = self.autorole
        welcome_toggle.callback = self.toggle_welcome

        row_one.add_item(welcome_channel)
        row_one.add_item(welcome_message)
        row_one.add_item(autorole)
        row_one.add_item(welcome_toggle)

        row_two = discord.ui.ActionRow()

        goodbye_channel = discord.ui.Button(
            label="Goodbye Channel",
            emoji="📤",
            style=discord.ButtonStyle.primary,
        )
        goodbye_message = discord.ui.Button(
            label="Goodbye Message",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
        )
        goodbye_toggle = discord.ui.Button(
            label="Goodbye Toggle",
            emoji="🔁",
            style=discord.ButtonStyle.secondary,
        )
        dm_settings = discord.ui.Button(
            label="Welcome DM",
            emoji="✉️",
            style=discord.ButtonStyle.secondary,
        )

        goodbye_channel.callback = self.goodbye_channel
        goodbye_message.callback = self.goodbye_message
        goodbye_toggle.callback = self.toggle_goodbye
        dm_settings.callback = self.dm_settings

        row_two.add_item(goodbye_channel)
        row_two.add_item(goodbye_message)
        row_two.add_item(goodbye_toggle)
        row_two.add_item(dm_settings)

        row_three = discord.ui.ActionRow()

        rules = discord.ui.Button(
            label="Rules Channel",
            emoji="📜",
            style=discord.ButtonStyle.secondary,
        )
        introduction = discord.ui.Button(
            label="Intro Channel",
            emoji="💬",
            style=discord.ButtonStyle.secondary,
        )
        support = discord.ui.Button(
            label="Support Channel",
            emoji="🛟",
            style=discord.ButtonStyle.secondary,
        )
        preview = discord.ui.Button(
            label="Preview",
            emoji="🧪",
            style=discord.ButtonStyle.success,
        )

        rules.callback = self.rules_channel
        introduction.callback = self.introduction_channel
        support.callback = self.support_channel
        preview.callback = self.preview

        row_three.add_item(rules)
        row_three.add_item(introduction)
        row_three.add_item(support)
        row_three.add_item(preview)

        row_four = discord.ui.ActionRow()

        status = discord.ui.Button(
            label="View Config",
            emoji="📋",
            style=discord.ButtonStyle.primary,
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

        status.callback = self.status
        reset.callback = self.reset
        close.callback = self.close

        row_four.add_item(status)
        row_four.add_item(reset)
        row_four.add_item(close)

        container.add_item(row_one)
        container.add_item(row_two)
        container.add_item(row_three)
        container.add_item(row_four)

        self.add_item(container)

    async def welcome_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ChannelPickerView("welcome_channel_id"),
            ephemeral=True,
        )

    async def welcome_message(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)

        await interaction.response.send_modal(
            WelcomeMessageModal(
                config["title"],
                config["description"],
            )
        )

    async def autorole(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=AutoRolePickerView(),
            ephemeral=True,
        )

    async def toggle_welcome(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)
        config["enabled"] = not config["enabled"]
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Welcome System Updated",
                f"Welcome messages are now `{config['enabled']}`.",
                emoji_key="welcome",
            ),
            ephemeral=True,
        )

    async def goodbye_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ChannelPickerView("goodbye_channel_id"),
            ephemeral=True,
        )

    async def goodbye_message(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)

        await interaction.response.send_modal(
            GoodbyeMessageModal(
                config["goodbye_title"],
                config["goodbye_description"],
            )
        )

    async def toggle_goodbye(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)
        config["goodbye_enabled"] = not config["goodbye_enabled"]
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Goodbye System Updated",
                f"Goodbye messages are now `{config['goodbye_enabled']}`.",
                emoji_key="goodbye",
            ),
            ephemeral=True,
        )

    async def dm_settings(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)
        config["dm_enabled"] = not config["dm_enabled"]
        welcome_db.save_guild(interaction.guild.id, config)

        await interaction.response.send_modal(
            DMMessageModal(
                config["dm_title"],
                config["dm_description"],
            )
        )

    async def rules_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ChannelPickerView("rules_channel_id"),
            ephemeral=True,
        )

    async def introduction_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ChannelPickerView("introduction_channel_id"),
            ephemeral=True,
        )

    async def support_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ChannelPickerView("support_channel_id"),
            ephemeral=True,
        )

    async def preview(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)

        await interaction.response.send_message(
            view=MemberWelcomeView(
                interaction.client,
                interaction.user,
                config,
                test_mode=True,
            ),
            ephemeral=True,
        )

    async def status(
        self,
        interaction: discord.Interaction,
    ):
        config = welcome_db.get_guild(interaction.guild.id)

        welcome_channel = interaction.guild.get_channel(
            config["welcome_channel_id"]
        )
        goodbye_channel = interaction.guild.get_channel(
            config["goodbye_channel_id"]
        )
        autorole = interaction.guild.get_role(
            config["autorole_id"]
        )

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Welcome Configuration",
                f"**Welcome enabled:** `{config['enabled']}`\n"
                f"**Welcome channel:** "
                f"{welcome_channel.mention if welcome_channel else '`Not set`'}\n"
                f"**Goodbye enabled:** `{config['goodbye_enabled']}`\n"
                f"**Goodbye channel:** "
                f"{goodbye_channel.mention if goodbye_channel else '`Not set`'}\n"
                f"**Autorole:** "
                f"{autorole.mention if autorole else '`Not set`'}\n"
                f"**DM enabled:** `{config['dm_enabled']}`\n"
                f"**Account-age warning:** "
                f"`{config['minimum_account_age_days']} days`\n"
                f"**Welcomes sent:** `{config['welcome_count']}`\n"
                f"**Goodbyes sent:** `{config['leave_count']}`",
                emoji_key="settings",
            ),
            ephemeral=True,
        )

    async def reset(
        self,
        interaction: discord.Interaction,
    ):
        welcome_db.save_guild(
            interaction.guild.id,
            copy.deepcopy(DEFAULT_CONFIG),
        )

        await interaction.response.send_message(
            view=WelcomeResponse(
                interaction.client,
                "Welcome Configuration Reset",
                "All welcome settings were restored to defaults.",
                emoji_key="warning",
                warning=True,
            ),
            ephemeral=True,
        )

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# WELCOME COG
# =========================================================

class Welcome(commands.Cog):
    """
    Premium welcome system.

    Commands are hidden so this cog does not appear in the help menu.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ):
        config = welcome_db.get_guild(member.guild.id)

        # Autorole
        role_id = config.get("autorole_id")

        if role_id:
            role = member.guild.get_role(role_id)

            if (
                role
                and not role.managed
                and role < member.guild.me.top_role
            ):
                try:
                    await member.add_roles(
                        role,
                        reason="Monk welcome autorole",
                    )
                except discord.HTTPException:
                    pass

        # Welcome channel message
        if config["enabled"]:
            channel = member.guild.get_channel(
                config["welcome_channel_id"]
            )

            if isinstance(channel, discord.TextChannel):
                try:
                    content = (
                        member.mention
                        if config["ping_member"]
                        else None
                    )

                    await channel.send(
                        content=content,
                        view=MemberWelcomeView(
                            self.bot,
                            member,
                            config,
                        ),
                        allowed_mentions=discord.AllowedMentions(
                            users=True,
                            roles=False,
                            everyone=False,
                        ),
                    )

                    config["welcome_count"] += 1

                except discord.HTTPException:
                    pass

        # Welcome DM
        if config["dm_enabled"]:
            try:
                title = replace_placeholders(
                    config["dm_title"],
                    member,
                )
                description = replace_placeholders(
                    config["dm_description"],
                    member,
                )

                await member.send(
                    view=WelcomeResponse(
                        self.bot,
                        title,
                        description,
                        emoji_key="dm",
                    )
                )

            except discord.HTTPException:
                pass

        welcome_db.save_guild(member.guild.id, config)

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member: discord.Member,
    ):
        config = welcome_db.get_guild(member.guild.id)

        if not config["goodbye_enabled"]:
            return

        channel = member.guild.get_channel(
            config["goodbye_channel_id"]
        )

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(
                view=MemberGoodbyeView(
                    self.bot,
                    member,
                    config,
                )
            )

            config["leave_count"] += 1
            welcome_db.save_guild(member.guild.id, config)

        except discord.HTTPException:
            pass

    # Hidden commands keep this cog out of the dynamic help menu.

    @commands.command(
        name="welcomeconfig",
        aliases=["wconfig"],
        hidden=True,
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def welcome_config(
        self,
        ctx: commands.Context,
    ):
        await ctx.send(
            view=WelcomeConfigView(
                self,
                ctx.guild,
                ctx.author.id,
            )
        )

    @commands.command(
        name="welcometest",
        aliases=["testwelcome"],
        hidden=True,
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def welcome_test(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        member = member or ctx.author
        config = welcome_db.get_guild(ctx.guild.id)

        await ctx.send(
            view=MemberWelcomeView(
                self.bot,
                member,
                config,
                test_mode=True,
            )
        )

    @commands.command(
        name="goodbyetest",
        aliases=["testgoodbye"],
        hidden=True,
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def goodbye_test(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        member = member or ctx.author
        config = welcome_db.get_guild(ctx.guild.id)

        await ctx.send(
            view=MemberGoodbyeView(
                self.bot,
                member,
                config,
            )
        )

    @commands.command(
        name="welcomeage",
        hidden=True,
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def welcome_age(
        self,
        ctx: commands.Context,
        days: commands.Range[int, 0, 3650],
    ):
        config = welcome_db.get_guild(ctx.guild.id)
        config["minimum_account_age_days"] = days
        welcome_db.save_guild(ctx.guild.id, config)

        await ctx.send(
            view=WelcomeResponse(
                self.bot,
                "Account Age Updated",
                f"Accounts newer than `{days}` days will show a warning.",
                emoji_key="warning",
                warning=True,
            )
        )

    @commands.command(
        name="welcomeping",
        hidden=True,
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def welcome_ping(
        self,
        ctx: commands.Context,
        state: str,
    ):
        state = state.lower()

        if state not in {"on", "off"}:
            return await ctx.send(
                view=WelcomeResponse(
                    self.bot,
                    "Invalid State",
                    "Use `on` or `off`.",
                    emoji_key="error",
                    success=False,
                )
            )

        config = welcome_db.get_guild(ctx.guild.id)
        config["ping_member"] = state == "on"
        welcome_db.save_guild(ctx.guild.id, config)

        await ctx.send(
            view=WelcomeResponse(
                self.bot,
                "Welcome Ping Updated",
                f"Member pings are now `{config['ping_member']}`.",
                emoji_key="success",
            )
        )

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.MissingPermissions):
            return await ctx.send(
                view=WelcomeResponse(
                    self.bot,
                    "Permission Denied",
                    "You need **Administrator** permission.",
                    emoji_key="error",
                    success=False,
                )
            )

        if isinstance(error, commands.MemberNotFound):
            return await ctx.send(
                view=WelcomeResponse(
                    self.bot,
                    "Member Not Found",
                    "Mention a valid server member.",
                    emoji_key="error",
                    success=False,
                )
            )

        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                view=WelcomeResponse(
                    self.bot,
                    "Invalid Argument",
                    "One or more supplied arguments are invalid.",
                    emoji_key="error",
                    success=False,
                )
            )

        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))