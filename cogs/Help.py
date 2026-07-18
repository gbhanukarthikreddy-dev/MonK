import math
from typing import Optional

import discord
from discord.ext import commands


# =========================================================
# COMPLETE HELP CONFIGURATION
# =========================================================

ACCENT_COLOR = discord.Color.from_rgb(198, 145, 73)
SUCCESS_COLOR = discord.Color.from_rgb(70, 190, 120)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 75)
INFO_COLOR = discord.Color.from_rgb(80, 150, 230)

HELP_TIMEOUT = 300
COMMANDS_PER_PAGE = 5
MAX_SEARCH_RESULTS = 10

BOT_TAGLINE = "Advanced moderation, tickets, utilities, security and server management."
SUPPORT_SERVER_URL: Optional[str] = None
INVITE_URL: Optional[str] = None
WEBSITE_URL: Optional[str] = None

# Commands that should never appear in the help menu.
HIDDEN_COMMANDS = {
    "eval",
    "shutdown",
    "leaveguild",
}

# Commands visible only to the bot owner.
OWNER_COMMANDS = {
    "np",
    "rnp",
    "nplist",
    "load",
    "unload",
    "reload",
    "reloadall",
    "sync",
    "botstats",
    "guilds",
    "guildinfo",
    "leaveguild",
    "say",
    "dm",
    "eval",
    "shutdown",
}


# =========================================================
# CUSTOM EMOJI IDS
# =========================================================
# Put only numeric custom emoji IDs.
# Leave None to use the Unicode fallback.
#
# Example:
# "home": 123456789012345678

CUSTOM_EMOJI_IDS = {
    "home": '<:house:1527032485488234737>',
    "moderation": '<:shield:1527031903767760916>',
    "advanced_moderation": '<:swords:1527046425861423304>',
    "automod": '<:chevronsleftrightellipsis:1527045955562635314>',
    "security": None,
    "logging": None,
    "tickets": '<:ticket:1527040620760404151>',
    "utility": '<:settings:1527032720327184465>',
    "economy": '<:circleeuro:1527045826105446552>',
    "leveling": '<:trophy:1527040912201486468>',
    "voice": '<:music:1527041142544142426>',
    "setup": '<:gitbranch:1527046276464644328>',
    "owner": '<:crown:1527042562190217346>',
    "information": '<:info:1527032861348204706>',
    "fun": None,
    "music": None,
    "other": '<:folder:1527033394372939798>',

    "search": '<:search:1527044316965372134>',
    "commands": '<:list:1527044575158341732>',
    "categories": '<:folderopen:1527044004020092958>',
    "prefix": None,
    "server": '<:globe:1527043380289470536>',
    "user": '<:user:1527043175191941211>',
    "bot": '<:bot:1527043822104875208>',

    "previous": '<:arrowbigleft:1527044929518571702>',
    "next": '<:arrowbigright:1527044807858454740>',
    "back": None,
    "close": '<:circlex:1527045249598492944>',
    "refresh": None,
    "details": None,

    "success": None,
    "error": None,
    "warning": None,
    "loading": None,
}


EMOJI_FALLBACKS = {
    "home": "🏠",
    "moderation": "🛡️",
    "advanced_moderation": "⚔️",
    "automod": "🤖",
    "security": "🔐",
    "logging": "📜",
    "tickets": "🎫",
    "utility": "📈",
    "economy": "💰",
    "leveling": "🏆",
    "voice": "🔊",
    "setup": "⚙️",
    "owner": "👑",
    "information": "ℹ️",
    "fun": "🎮",
    "music": "🎵",
    "other": "📁",

    "search": "🔎",
    "commands": "⌨️",
    "categories": "🗂️",
    "prefix": "❯",
    "server": "🌐",
    "user": "👤",
    "bot": "🤖",

    "previous": "◀️",
    "next": "▶️",
    "back": "↩️",
    "close": "✖️",
    "refresh": "🔄",
    "details": "📖",

    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "loading": "⏳",
}


# =========================================================
# CATEGORY CONFIGURATION
# =========================================================

CATEGORY_CONFIG = {
    "Home": {
        "emoji": "home",
        "description": "Overview, quick-start instructions and bot statistics.",
    },
    "Moderation": {
        "emoji": "moderation",
        "description": "Warnings, timeouts, bans, roles and channel moderation.",
    },
    "Advanced Moderation": {
        "emoji": "advanced_moderation",
        "description": "Jail, sticky messages, lockdown, cases and moderation history.",
    },
    "AutoMod": {
        "emoji": "automod",
        "description": "Automatic spam, invite, link and mention protection.",
    },
    "Security": {
        "emoji": "security",
        "description": "Server protection, anti-raid and security tools.",
    },
    "Logging": {
        "emoji": "logging",
        "description": "Moderation logs and server-event tracking.",
    },
    "Tickets": {
        "emoji": "tickets",
        "description": "Ticket setup, panels, transcripts and staff controls.",
    },
    "Utility": {
        "emoji": "utility",
        "description": "AFK, reminders, polls, starboard and counting.",
    },
    "Economy": {
        "emoji": "economy",
        "description": "Currency, rewards, banking and leaderboards.",
    },
    "Leveling": {
        "emoji": "leveling",
        "description": "XP, ranks, leaderboards and level rewards.",
    },
    "Voice": {
        "emoji": "voice",
        "description": "Temporary voice channels and voice management.",
    },
    "Setup": {
        "emoji": "setup",
        "description": "Server configuration, channels, roles and prefix settings.",
    },
    "Owner": {
        "emoji": "owner",
        "description": "Private bot-owner administration commands.",
    },
    "Information": {
        "emoji": "information",
        "description": "User, server and bot information.",
    },
    "Fun": {
        "emoji": "fun",
        "description": "Games and entertainment commands.",
    },
    "Music": {
        "emoji": "music",
        "description": "Music playback and player controls.",
    },
    "Other": {
        "emoji": "other",
        "description": "Commands that do not fit another category.",
    },
}


# Maps cog names to help categories.
COG_CATEGORY_MAP = {
    "Moderation": "Moderation",
    "AdvancedModeration": "Advanced Moderation",
    "ModUpgrade": "Advanced Moderation",
    "AutoMod": "AutoMod",
    "Security": "Security",
    "Logging": "Logging",
    "TicketSystem": "Tickets",
    "Tickets": "Tickets",
    "UtilitySuite": "Utility",
    "Utility": "Utility",
    "Economy": "Economy",
    "Leveling": "Leveling",
    "Voice": "Voice",
    "Setup": "Setup",
    "Owner": "Owner",
    "Information": "Information",
    "Fun": "Fun",
    "Music": "Music",
}


# Command-level overrides for commands located in multi-feature cogs.
COMMAND_CATEGORY_OVERRIDES = {
    # Utility
    "afk": "Utility",
    "afklist": "Utility",
    "remind": "Utility",
    "reminders": "Utility",
    "cancelreminder": "Utility",
    "poll": "Utility",
    "starboard": "Utility",
    "counting": "Utility",
    "utilityconfig": "Utility",
    "utilitystatus": "Utility",

    # Leveling
    "leveling": "Leveling",
    "rank": "Leveling",
    "level": "Leveling",
    "levelboard": "Leveling",
    "levelrole": "Leveling",

    # Economy
    "economy": "Economy",
    "balance": "Economy",
    "bal": "Economy",
    "wallet": "Economy",
    "daily": "Economy",
    "work": "Economy",
    "deposit": "Economy",
    "withdraw": "Economy",
    "pay": "Economy",
    "economyboard": "Economy",

    # Voice
    "tempvc": "Voice",
    "vclock": "Voice",
    "vcunlock": "Voice",
    "vclimit": "Voice",
    "vcrename": "Voice",

    # AutoMod
    "automod": "AutoMod",

    # Tickets
    "ticketconfig": "Tickets",
    "ticketpanel": "Tickets",
    "ticketadd": "Tickets",
    "ticketremove": "Tickets",
    "ticketrename": "Tickets",
    "ticketclose": "Tickets",

    # Setup
    "setup": "Setup",
    "config": "Setup",
    "viewconfig": "Setup",
    "resetconfig": "Setup",
}


# =========================================================
# EMOJI HELPERS
# =========================================================

def get_emoji(
    bot: commands.Bot,
    key: str,
) -> str | discord.Emoji | discord.PartialEmoji:
    """
    Accepts any of these custom emoji formats:

    123456789012345678
    "123456789012345678"
    "<:emoji_name:123456789012345678>"
    "<a:animated_name:123456789012345678>"
    """

    configured = CUSTOM_EMOJI_IDS.get(key)

    if configured:
        # Already an Emoji or PartialEmoji object.
        if isinstance(
            configured,
            (discord.Emoji, discord.PartialEmoji),
        ):
            return configured

        # Numeric ID as int or numeric string.
        if isinstance(configured, int) or str(configured).isdigit():
            emoji = bot.get_emoji(int(configured))

            if emoji:
                return emoji

        # Full Discord custom emoji string.
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
# COMMAND HELPERS
# =========================================================

def get_prefix(ctx: commands.Context) -> str:
    prefix = ctx.clean_prefix

    if isinstance(prefix, str):
        return prefix

    return "m"


def get_command_category(command: commands.Command) -> str:
    name = command.qualified_name.lower()
    root_name = command.root_parent.name if command.root_parent else command.name

    if name in COMMAND_CATEGORY_OVERRIDES:
        return COMMAND_CATEGORY_OVERRIDES[name]

    if root_name.lower() in COMMAND_CATEGORY_OVERRIDES:
        return COMMAND_CATEGORY_OVERRIDES[root_name.lower()]

    if command.cog_name in COG_CATEGORY_MAP:
        return COG_CATEGORY_MAP[command.cog_name]

    if command.cog_name and command.cog_name in CATEGORY_CONFIG:
        return command.cog_name

    return "Other"


def get_command_description(command: commands.Command) -> str:
    if command.brief:
        return command.brief.strip()

    if command.help:
        first_line = command.help.strip().splitlines()[0]
        return first_line or "No description provided."

    if command.description:
        return command.description.strip()

    return "No description provided."


def get_command_usage(
    command: commands.Command,
    prefix: str,
) -> str:
    signature = command.signature.strip()

    if signature:
        return f"{prefix}{command.qualified_name} {signature}"

    return f"{prefix}{command.qualified_name}"


def get_cooldown_text(command: commands.Command) -> str:
    buckets = getattr(command, "_buckets", None)

    if not buckets:
        return "None"

    cooldown = getattr(buckets, "_cooldown", None)

    if not cooldown:
        return "None"

    return (
        f"{cooldown.rate} use"
        f"{'s' if cooldown.rate != 1 else ''} every "
        f"{cooldown.per:g} seconds"
    )


def get_required_permissions(command: commands.Command) -> list[str]:
    permissions: list[str] = []

    for check in command.checks:
        required = getattr(check, "required_permissions", None)

        if required:
            for permission, enabled in required.items():
                if enabled:
                    pretty = permission.replace("_", " ").title()

                    if pretty not in permissions:
                        permissions.append(pretty)

    return permissions


async def is_bot_owner(
    ctx: commands.Context,
) -> bool:
    try:
        return await ctx.bot.is_owner(ctx.author)
    except Exception:
        return False


async def can_show_command(
    ctx: commands.Context,
    command: commands.Command,
) -> bool:
    if command.hidden:
        return False

    if command.name in HIDDEN_COMMANDS:
        return False

    owner = await is_bot_owner(ctx)

    if command.name in OWNER_COMMANDS and not owner:
        return False

    try:
        return await command.can_run(ctx)

    except commands.CommandError:
        return False

    except Exception:
        return False


async def get_visible_commands(
    ctx: commands.Context,
) -> list[commands.Command]:
    visible = []

    for command in ctx.bot.walk_commands():
        if command.parent is not None:
            continue

        if ctx.guild:
            from cogs.modules import command_module, is_module_disabled

            module = command_module(command)
            if module and is_module_disabled(ctx.guild.id, module):
                continue

        if await can_show_command(ctx, command):
            visible.append(command)

    return sorted(
        visible,
        key=lambda item: item.qualified_name.lower(),
    )


async def get_category_map(
    ctx: commands.Context,
) -> dict[str, list[commands.Command]]:
    categories: dict[str, list[commands.Command]] = {}

    for command in await get_visible_commands(ctx):
        category = get_command_category(command)
        categories.setdefault(category, []).append(command)

    ordered: dict[str, list[commands.Command]] = {}

    for category in CATEGORY_CONFIG:
        if category == "Home":
            continue

        if category in categories:
            ordered[category] = categories[category]

    for category, commands_list in categories.items():
        if category not in ordered:
            ordered[category] = commands_list

    return ordered


def split_text(
    text: str,
    limit: int = 3800,
) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n\n"):
        candidate = (
            f"{current}\n\n{paragraph}"
            if current
            else paragraph
        )

        if len(candidate) > limit:
            if current:
                chunks.append(current)

            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


# =========================================================
# ERROR VIEW
# =========================================================

class HelpErrorView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        title: str,
        description: str,
    ):
        super().__init__(timeout=60)

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {emoji_text(bot, 'error')} {title}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=ERROR_COLOR,
            )
        )


# =========================================================
# SEARCH MODAL
# =========================================================

class HelpSearchModal(discord.ui.Modal, title="Search Commands"):
    query_input = discord.ui.TextInput(
        label="Command or category",
        placeholder="Example: ban, tickets, rank, setup",
        required=True,
        min_length=1,
        max_length=100,
    )

    def __init__(self, parent_view: "HelpView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        query = self.query_input.value.strip().lower()
        matches: list[commands.Command] = []

        for command in await get_visible_commands(self.parent_view.ctx):
            names = [
                command.name,
                command.qualified_name,
                *command.aliases,
            ]

            description = get_command_description(command)

            if (
                any(query in name.lower() for name in names)
                or query in description.lower()
                or query in get_command_category(command).lower()
            ):
                matches.append(command)

        if not matches:
            return await interaction.response.send_message(
                view=HelpErrorView(
                    self.parent_view.ctx.bot,
                    "Nothing Found",
                    f"No commands matched `{query}`.",
                ),
                ephemeral=True,
            )

        lines = []

        prefix = get_prefix(self.parent_view.ctx)

        for command in matches[:MAX_SEARCH_RESULTS]:
            lines.append(
                f"### `{prefix}{command.qualified_name}`\n"
                f"{get_command_description(command)}\n"
                f"**Category:** {get_command_category(command)}"
            )

        result_view = discord.ui.LayoutView(timeout=90)
        result_view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {emoji_text(self.parent_view.ctx.bot, 'search')} "
                    f"Search Results"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n\n".join(lines)),
                accent_colour=INFO_COLOR,
            )
        )

        await interaction.response.send_message(
            view=result_view,
            ephemeral=True,
        )


# =========================================================
# COMMAND DETAIL VIEW
# =========================================================

class CommandDetailView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        command: commands.Command,
        return_category: str,
    ):
        super().__init__(timeout=HELP_TIMEOUT)

        self.ctx = ctx
        self.command = command
        self.return_category = return_category

        prefix = get_prefix(ctx)
        aliases = (
            ", ".join(f"`{alias}`" for alias in command.aliases)
            if command.aliases
            else "None"
        )
        permissions = get_required_permissions(command)
        permissions_text = (
            ", ".join(permissions)
            if permissions
            else "No special user permissions"
        )

        category = get_command_category(command)

        description = (
            f"{get_command_description(command)}\n\n"
            f"### Usage\n"
            f"```text\n{get_command_usage(command, prefix)}\n```\n"
            f"**Category:** {category}\n"
            f"**Aliases:** {aliases}\n"
            f"**Required permissions:** {permissions_text}\n"
            f"**Cooldown:** {get_cooldown_text(command)}\n"
            f"**Qualified name:** `{command.qualified_name}`"
        )

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)
        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(ctx.bot, 'details')} "
                f"{command.qualified_name}"
            )
        )
        container.add_item(discord.ui.Separator())

        for chunk in split_text(description):
            container.add_item(discord.ui.TextDisplay(chunk))

        container.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()

        back_button = discord.ui.Button(
            label="Back",
            emoji=get_emoji(ctx.bot, "back"),
            style=discord.ButtonStyle.secondary,
        )
        close_button = discord.ui.Button(
            label="Close",
            emoji=get_emoji(ctx.bot, "close"),
            style=discord.ButtonStyle.danger,
        )

        back_button.callback = self.back
        close_button.callback = self.close

        row.add_item(back_button)
        row.add_item(close_button)
        container.add_item(row)

        self.add_item(container)

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                view=HelpErrorView(
                    self.ctx.bot,
                    "This Menu Is Not Yours",
                    "Run the help command to open your own menu.",
                ),
                ephemeral=True,
            )
            return False

        return True

    async def back(
        self,
        interaction: discord.Interaction,
    ):
        view = HelpView(
            self.ctx,
            initial_category=self.return_category,
        )
        await view.prepare()

        await interaction.response.edit_message(view=view)

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# CATEGORY SELECT
# =========================================================

class CategorySelect(discord.ui.Select):
    def __init__(
        self,
        parent_view: "HelpView",
    ):
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label="Home",
                value="Home",
                emoji=get_emoji(parent_view.ctx.bot, "home"),
                description="Return to the main help page.",
                default=parent_view.category == "Home",
            )
        ]

        for category, commands_list in parent_view.categories.items():
            config = CATEGORY_CONFIG.get(
                category,
                CATEGORY_CONFIG["Other"],
            )

            options.append(
                discord.SelectOption(
                    label=category[:100],
                    value=category,
                    emoji=get_emoji(
                        parent_view.ctx.bot,
                        config["emoji"],
                    ),
                    description=(
                        f"{len(commands_list)} command"
                        f"{'s' if len(commands_list) != 1 else ''} • "
                        f"{config['description']}"
                    )[:100],
                    default=parent_view.category == category,
                )
            )

        super().__init__(
            placeholder="Choose a command category",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        self.parent_view.category = self.values[0]
        self.parent_view.page = 0
        self.parent_view.build()

        await interaction.response.edit_message(
            view=self.parent_view
        )


# =========================================================
# MAIN HELP VIEW
# =========================================================
class HelpView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        *,
        initial_category: str = "Home",
    ):
        super().__init__(timeout=HELP_TIMEOUT)

        self.ctx = ctx
        self.category = initial_category
        self.page = 0
        self.categories: dict[str, list[commands.Command]] = {}

    async def prepare(self):
        self.categories = await get_category_map(self.ctx)

        if (
            self.category != "Home"
            and self.category not in self.categories
        ):
            self.category = "Home"

        self.build()

    @property
    def max_page(self) -> int:
        if self.category == "Home":
            return 0

        commands_list = self.categories.get(self.category, [])

        if not commands_list:
            return 0

        return max(
            0,
            math.ceil(len(commands_list) / COMMANDS_PER_PAGE) - 1,
        )

    def build(self):
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT_COLOR)

        if self.category == "Home":
            self.build_home(container)
        else:
            self.build_category(container)

        container.add_item(discord.ui.Separator())

        select_row = discord.ui.ActionRow()
        select_row.add_item(CategorySelect(self))
        container.add_item(select_row)

        container.add_item(discord.ui.Separator())

        controls = discord.ui.ActionRow()

        previous = discord.ui.Button(
            label="Previous",
            emoji=get_emoji(self.ctx.bot, "previous"),
            style=discord.ButtonStyle.secondary,
            disabled=self.category == "Home" or self.page <= 0,
        )
        home = discord.ui.Button(
            label="Home",
            emoji=get_emoji(self.ctx.bot, "home"),
            style=discord.ButtonStyle.secondary,
            disabled=self.category == "Home",
        )
        search = discord.ui.Button(
            label="Search",
            emoji=get_emoji(self.ctx.bot, "search"),
            style=discord.ButtonStyle.secondary,
        )
        next_button = discord.ui.Button(
            label="Next",
            emoji=get_emoji(self.ctx.bot, "next"),
            style=discord.ButtonStyle.secondary,
            disabled=(
                self.category == "Home"
                or self.page >= self.max_page
            ),
        )
        close = discord.ui.Button(
            label="Close",
            emoji=get_emoji(self.ctx.bot, "close"),
            style=discord.ButtonStyle.secondary,
        )

        previous.callback = self.previous
        home.callback = self.home
        search.callback = self.search
        next_button.callback = self.next_page
        close.callback = self.close

        controls.add_item(previous)
        controls.add_item(home)
        controls.add_item(search)
        controls.add_item(next_button)
        controls.add_item(close)

        container.add_item(controls)
        self.add_item(container)

    def build_home(
        self,
        container: discord.ui.Container,
    ):
        bot_user = self.ctx.bot.user
        bot_name = bot_user.name if bot_user else "Monk"
        prefix = get_prefix(self.ctx)
        total_commands = sum(
            len(commands_list)
            for commands_list in self.categories.values()
        )

        intro = (
            f"Welcome {self.ctx.author.mention}! I am **{bot_name}**.\n"
            f"{BOT_TAGLINE}\n\n"
            "Choose a category below, search for a command, or use "
            f"`{prefix}help <command>` for detailed usage."
        )

        if bot_user:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"## {emoji_text(self.ctx.bot, 'home')} "
                        f"{bot_name} Help Centre"
                    ),
                    discord.ui.TextDisplay(intro),
                    accessory=discord.ui.Thumbnail(
                        bot_user.display_avatar.url
                    ),
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    f"## {emoji_text(self.ctx.bot, 'home')} "
                    f"{bot_name} Help Centre"
                )
            )
            container.add_item(discord.ui.TextDisplay(intro))

        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                f"{emoji_text(self.ctx.bot, 'prefix')} "
                f"**Prefix:** `{prefix}`\n"
                f"{emoji_text(self.ctx.bot, 'commands')} "
                f"**Available commands:** `{total_commands}`\n"
                f"{emoji_text(self.ctx.bot, 'categories')} "
                f"**Categories:** `{len(self.categories)}`\n"
                f"{emoji_text(self.ctx.bot, 'server')} "
                f"**Server:** {self.ctx.guild.name if self.ctx.guild else 'Direct Messages'}\n"
                f"{emoji_text(self.ctx.bot, 'user')} "
                f"**Requested by:** {self.ctx.author.mention}\n"
                f"{emoji_text(self.ctx.bot, 'bot')} "
                f"**Latency:** `{round(self.ctx.bot.latency * 1000)}ms`"
            )
        )

        if self.categories:
            container.add_item(discord.ui.Separator())

            category_lines = []

            for category, commands_list in self.categories.items():
                config = CATEGORY_CONFIG.get(
                    category,
                    CATEGORY_CONFIG["Other"],
                )

                category_lines.append(
                    f"{emoji_text(self.ctx.bot, config['emoji'])} "
                    f"**{category}** — `{len(commands_list)}`"
                )

            container.add_item(
                discord.ui.TextDisplay(
                    "### Command Categories\n\n"
                    + "\n".join(category_lines)
                )
            )

        links = []

        if SUPPORT_SERVER_URL:
            links.append(f"[Support Server]({SUPPORT_SERVER_URL})")

        if INVITE_URL:
            links.append(f"[Invite Monk]({INVITE_URL})")

        if WEBSITE_URL:
            links.append(f"[Website]({WEBSITE_URL})")

        if links:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(" • ".join(links))
            )

    def build_category(
        self,
        container: discord.ui.Container,
    ):
        commands_list = self.categories.get(self.category, [])
        config = CATEGORY_CONFIG.get(
            self.category,
            CATEGORY_CONFIG["Other"],
        )

        if self.page > self.max_page:
            self.page = self.max_page

        start = self.page * COMMANDS_PER_PAGE
        page_commands = commands_list[
            start:start + COMMANDS_PER_PAGE
        ]

        container.add_item(
            discord.ui.TextDisplay(
                f"## {emoji_text(self.ctx.bot, config['emoji'])} "
                f"{self.category}"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"{config['description']}\n\n"
                f"**Commands:** `{len(commands_list)}` • "
                f"**Page:** `{self.page + 1}/{self.max_page + 1}`"
            )
        )
        container.add_item(discord.ui.Separator())

        prefix = get_prefix(self.ctx)

        if not page_commands:
            container.add_item(
                discord.ui.TextDisplay(
                    "No commands are available in this category."
                )
            )
            return

        sections = []

        for command in page_commands:
            aliases = (
                "\n**Aliases:** "
                + ", ".join(
                    f"`{alias}`"
                    for alias in command.aliases[:5]
                )
                if command.aliases
                else ""
            )

            sections.append(
                f"### `{prefix}{command.qualified_name}`\n"
                f"{get_command_description(command)}\n"
                f"**Usage:** `{get_command_usage(command, prefix)}`"
                f"{aliases}"
            )

        for chunk in split_text("\n\n".join(sections)):
            container.add_item(discord.ui.TextDisplay(chunk))

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"Use `{prefix}help <command>` for aliases, permissions, "
                "cooldowns and full command details."
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                view=HelpErrorView(
                    self.ctx.bot,
                    "This Menu Is Not Yours",
                    "Run the help command to open your own menu.",
                ),
                ephemeral=True,
            )
            return False

        return True

    async def previous(
        self,
        interaction: discord.Interaction,
    ):
        self.page = max(0, self.page - 1)
        self.build()
        await interaction.response.edit_message(view=self)

    async def next_page(
        self,
        interaction: discord.Interaction,
    ):
        self.page = min(self.max_page, self.page + 1)
        self.build()
        await interaction.response.edit_message(view=self)

    async def home(
        self,
        interaction: discord.Interaction,
    ):
        self.category = "Home"
        self.page = 0
        self.build()
        await interaction.response.edit_message(view=self)

    async def search(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(
            HelpSearchModal(self)
        )

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# HELP COG
# =========================================================

class Help(commands.Cog):
    """Premium Components V2 help system for Monk."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="help",
        aliases=["commands", "cmds", "h"],
        help="Open Monk's interactive command menu.",
    )
    @commands.cooldown(
        1,
        3,
        commands.BucketType.user,
    )
    async def help_command(
        self,
        ctx: commands.Context,
        *,
        query: Optional[str] = None,
    ):
        if not query:
            view = HelpView(ctx)
            await view.prepare()
            return await ctx.send(view=view)

        query = query.strip().lower()

        command = self.bot.get_command(query)

        if command:
            if not await can_show_command(ctx, command):
                return await ctx.send(
                    view=HelpErrorView(
                        self.bot,
                        "Command Unavailable",
                        "You do not have permission to view or use this command.",
                    )
                )

            category = get_command_category(command)

            return await ctx.send(
                view=CommandDetailView(
                    ctx,
                    command,
                    category,
                )
            )

        categories = await get_category_map(ctx)

        category_match = next(
            (
                category
                for category in categories
                if category.lower() == query
            ),
            None,
        )

        if category_match:
            view = HelpView(
                ctx,
                initial_category=category_match,
            )
            await view.prepare()
            return await ctx.send(view=view)

        matches = []

        for visible_command in await get_visible_commands(ctx):
            names = [
                visible_command.name,
                visible_command.qualified_name,
                *visible_command.aliases,
            ]

            if any(
                query in name.lower()
                for name in names
            ):
                matches.append(visible_command)

        if matches:
            prefix = get_prefix(ctx)

            lines = [
                f"`{prefix}{command.qualified_name}` — "
                f"{get_command_description(command)}"
                for command in matches[:MAX_SEARCH_RESULTS]
            ]

            result_view = discord.ui.LayoutView(timeout=90)
            result_view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"## {emoji_text(self.bot, 'search')} "
                        "Possible Matches"
                    ),
                    discord.ui.Separator(),
                    discord.ui.TextDisplay("\n".join(lines)),
                    accent_colour=INFO_COLOR,
                )
            )

            return await ctx.send(view=result_view)

        await ctx.send(
            view=HelpErrorView(
                self.bot,
                "Nothing Found",
                f"No command or category matched `{query}`.\n\n"
                f"Use `{get_prefix(ctx)}help` to view all commands.",
            )
        )

    @help_command.error
    async def help_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                view=HelpErrorView(
                    self.bot,
                    "Slow Down",
                    f"Try again in `{error.retry_after:.1f}` seconds.",
                )
            )

        await ctx.send(
            view=HelpErrorView(
                self.bot,
                "Help Menu Error",
                f"```py\n{type(error).__name__}: {error}\n```",
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
