import asyncio
import copy
import html
import io
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord.ext import commands


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_PATH = "database/tickets.json"

ACCENT = discord.Color.from_rgb(198, 145, 73)
SUCCESS = discord.Color.from_rgb(72, 190, 120)
ERROR = discord.Color.from_rgb(220, 75, 75)
WARNING = discord.Color.from_rgb(235, 175, 65)

DEFAULT_DESCRIPTION = (
    "Need help? Choose the option that best matches your issue. "
    "A member of staff will assist you shortly."
)

DEFAULT_GUILD_DATA: dict[str, Any] = {
    "description": DEFAULT_DESCRIPTION,
    "moderator_role_id": None,
    "logs_channel_id": None,
    "panel_channel_id": None,
    "panel_message_id": None,
    "ticket_counter": 0,
    "options": [],
    "open_tickets": {},
}


# =========================================================
# DATABASE
# =========================================================

class TicketDatabase:
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
                raise ValueError("Database root must be an object.")

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
    def _merge_defaults(target: dict[str, Any]) -> bool:
        changed = False

        for key, value in DEFAULT_GUILD_DATA.items():
            if key not in target:
                target[key] = copy.deepcopy(value)
                changed = True

        return changed

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )

            if self._merge_defaults(guild_data):
                self._save(data)

            return copy.deepcopy(guild_data)

    async def save_guild(
        self,
        guild_id: int,
        guild_data: dict[str, Any],
    ) -> None:
        async with self.lock:
            data = self._load()
            self._merge_defaults(guild_data)
            data["guilds"][str(guild_id)] = guild_data
            self._save(data)

    async def next_ticket_number(self, guild_id: int) -> int:
        async with self.lock:
            data = self._load()
            guild_data = data["guilds"].setdefault(
                str(guild_id),
                copy.deepcopy(DEFAULT_GUILD_DATA),
            )
            self._merge_defaults(guild_data)

            guild_data["ticket_counter"] += 1
            self._save(data)

            return guild_data["ticket_counter"]


ticket_db = TicketDatabase(DATABASE_PATH)


# =========================================================
# HELPERS
# =========================================================

def safe_channel_name(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "user"


def is_ticket_moderator(
    member: discord.Member,
    moderator_role_id: Optional[int],
) -> bool:
    if member.guild_permissions.administrator:
        return True

    if not moderator_role_id:
        return False

    return any(
        role.id == moderator_role_id
        for role in member.roles
    )


def find_option(
    options: list[dict[str, Any]],
    key: str,
) -> Optional[dict[str, Any]]:
    for option in options:
        if option["key"] == key:
            return option

    return None


def ticket_channel_data(
    guild_data: dict[str, Any],
    channel_id: int,
) -> Optional[dict[str, Any]]:
    return guild_data["open_tickets"].get(str(channel_id))


def format_option(
    guild: discord.Guild,
    option: dict[str, Any],
) -> str:
    category = guild.get_channel(option.get("category_id"))

    category_text = (
        f"`{category.name}`"
        if isinstance(category, discord.CategoryChannel)
        else "`Missing category`"
    )

    return (
        f"{option.get('emoji') or '🎫'} **{option['name']}**\n"
        f"{option.get('description') or 'No description'}\n"
        f"Category: {category_text}"
    )


def format_time(value: str) -> str:
    try:
        created = datetime.fromisoformat(value)

        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return discord.utils.format_dt(created, style="R")

    except (TypeError, ValueError):
        return "Unknown"


# =========================================================
# COMPONENTS V2 RESPONSE
# =========================================================

class TicketResponse(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        success: bool = True,
        warning: bool = False,
    ):
        super().__init__(timeout=60)

        colour = WARNING if warning else (SUCCESS if success else ERROR)

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(description),
                accent_colour=colour,
            )
        )


async def interaction_response(
    interaction: discord.Interaction,
    title: str,
    description: str,
    *,
    success: bool = True,
    warning: bool = False,
    ephemeral: bool = True,
) -> None:
    view = TicketResponse(
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
# CONFIGURATION MODALS
# =========================================================

class DescriptionModal(discord.ui.Modal, title="Ticket Panel Description"):
    description_input = discord.ui.TextInput(
        label="Description",
        placeholder="Explain what users should choose and what happens next...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1800,
    )

    def __init__(self, current: str):
        super().__init__()
        self.description_input.default = current

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        guild_data["description"] = self.description_input.value.strip()
        await ticket_db.save_guild(interaction.guild.id, guild_data)

        await interaction_response(
            interaction,
            "Description Updated",
            "The ticket panel description was saved.",
        )


class AddOptionModal(discord.ui.Modal, title="Add Ticket Option"):
    name_input = discord.ui.TextInput(
        label="Option name",
        placeholder="Support",
        required=True,
        min_length=1,
        max_length=40,
    )

    description_input = discord.ui.TextInput(
        label="Option description",
        placeholder="Get help from our support team.",
        required=True,
        max_length=100,
    )

    emoji_input = discord.ui.TextInput(
        label="Emoji",
        placeholder="🎫",
        required=False,
        max_length=50,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        guild_data = await ticket_db.get_guild(interaction.guild.id)

        if len(guild_data["options"]) >= 20:
            return await interaction_response(
                interaction,
                "Option Limit Reached",
                "A maximum of 20 ticket options is supported.",
                success=False,
            )

        name = self.name_input.value.strip()
        key = safe_channel_name(name)
        description = self.description_input.value.strip()
        emoji = self.emoji_input.value.strip() or "🎫"

        if find_option(guild_data["options"], key):
            return await interaction_response(
                interaction,
                "Option Already Exists",
                "An option with that name already exists.",
                success=False,
            )

        moderator_role = interaction.guild.get_role(
            guild_data["moderator_role_id"]
        )

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                manage_channels=True,
                manage_permissions=True,
            ),
        }

        if moderator_role:
            overwrites[moderator_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

        try:
            category = await interaction.guild.create_category(
                name=name[:100],
                overwrites=overwrites,
                reason=f"Ticket option created by {interaction.user}",
            )

        except discord.Forbidden:
            return await interaction_response(
                interaction,
                "Missing Permission",
                "I need **Manage Channels** to create the category.",
                success=False,
            )

        guild_data["options"].append(
            {
                "key": key,
                "name": name,
                "description": description,
                "emoji": emoji,
                "category_id": category.id,
            }
        )

        await ticket_db.save_guild(interaction.guild.id, guild_data)

        await interaction_response(
            interaction,
            "Ticket Option Added",
            f"Created **{name}** and category `{category.name}`.",
        )


class RemoveOptionModal(discord.ui.Modal, title="Remove Ticket Option"):
    name_input = discord.ui.TextInput(
        label="Option name",
        placeholder="Support",
        required=True,
        max_length=40,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        key = safe_channel_name(self.name_input.value)
        option = find_option(guild_data["options"], key)

        if not option:
            return await interaction_response(
                interaction,
                "Option Not Found",
                "No configured option matches that name.",
                success=False,
            )

        guild_data["options"] = [
            existing
            for existing in guild_data["options"]
            if existing["key"] != key
        ]

        await ticket_db.save_guild(interaction.guild.id, guild_data)

        category = interaction.guild.get_channel(
            option.get("category_id")
        )

        await interaction_response(
            interaction,
            "Ticket Option Removed",
            (
                f"Removed **{option['name']}**.\n\n"
                f"The category `{category.name}` was kept."
                if isinstance(category, discord.CategoryChannel)
                else f"Removed **{option['name']}**."
            ),
        )


class RenameTicketModal(discord.ui.Modal, title="Rename Ticket"):
    name_input = discord.ui.TextInput(
        label="New channel name",
        placeholder="payment-help",
        required=True,
        max_length=80,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        ticket = ticket_channel_data(
            guild_data,
            interaction.channel.id,
        )

        if not ticket:
            return await interaction_response(
                interaction,
                "Not a Ticket",
                "This channel is not registered as an open ticket.",
                success=False,
            )

        if not isinstance(interaction.user, discord.Member):
            return

        if not is_ticket_moderator(
            interaction.user,
            guild_data["moderator_role_id"],
        ):
            return await interaction_response(
                interaction,
                "Moderator Only",
                "Only ticket moderators can rename tickets.",
                success=False,
            )

        new_name = safe_channel_name(self.name_input.value)

        await interaction.channel.edit(
            name=new_name,
            reason=f"Ticket renamed by {interaction.user}",
        )

        await interaction_response(
            interaction,
            "Ticket Renamed",
            f"The channel was renamed to `#{new_name}`.",
        )


# =========================================================
# ROLE AND LOG CHANNEL PICKERS
# =========================================================

class ModeratorRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select the ticket moderator role",
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

        if role.is_default():
            return await interaction_response(
                interaction,
                "Invalid Role",
                "`@everyone` cannot be the moderator role.",
                success=False,
            )

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        guild_data["moderator_role_id"] = role.id
        await ticket_db.save_guild(interaction.guild.id, guild_data)

        await interaction_response(
            interaction,
            "Moderator Role Updated",
            f"{role.mention} can now claim, rename, add members, "
            "remove members, and close tickets.",
        )


class ModeratorRolePicker(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=120)

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(
            discord.ui.TextDisplay("## 🛡️ Ticket Moderator Role")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose the staff role that will manage tickets."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(ModeratorRoleSelect())

        container.add_item(row)
        self.add_item(container)


class LogsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select the ticket logs channel",
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
        guild_data = await ticket_db.get_guild(interaction.guild.id)
        guild_data["logs_channel_id"] = channel.id
        await ticket_db.save_guild(interaction.guild.id, guild_data)

        await interaction_response(
            interaction,
            "Ticket Logs Updated",
            f"Ticket transcripts and close logs will be sent to {channel.mention}.",
        )


class LogsChannelPicker(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=120)

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(
            discord.ui.TextDisplay("## 🧾 Ticket Logs Channel")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose where ticket transcripts and close logs should be sent."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(LogsChannelSelect())

        container.add_item(row)
        self.add_item(container)


# =========================================================
# CONFIG PANEL
# =========================================================

class TicketConfigView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "TicketSystem",
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
            await interaction_response(
                interaction,
                "This Panel Is Not Yours",
                "Run `mticketconfig` to open your own setup panel.",
                success=False,
            )
            return False

        if not isinstance(interaction.user, discord.Member):
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction_response(
                interaction,
                "Permission Denied",
                "You need **Administrator** permission.",
                success=False,
            )
            return False

        return True

    def build(self) -> None:
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT)

        if self.guild.icon:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        "## 🎫 Monk Ticket Configuration"
                    ),
                    discord.ui.TextDisplay(
                        f"Configure tickets for **{self.guild.name}**."
                    ),
                    accessory=discord.ui.Thumbnail(
                        self.guild.icon.url
                    ),
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    "## 🎫 Monk Ticket Configuration"
                )
            )

        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Customize the panel, create option categories, select staff, "
                "configure logs, and send the finished ticket panel."
            )
        )

        row_one = discord.ui.ActionRow()

        description = discord.ui.Button(
            label="Description",
            emoji="📝",
            style=discord.ButtonStyle.primary,
        )
        add_option = discord.ui.Button(
            label="Add Option",
            emoji="➕",
            style=discord.ButtonStyle.success,
        )
        remove_option = discord.ui.Button(
            label="Remove Option",
            emoji="➖",
            style=discord.ButtonStyle.danger,
        )
        moderator_role = discord.ui.Button(
            label="Moderator Role",
            emoji="🛡️",
            style=discord.ButtonStyle.secondary,
        )

        description.callback = self.edit_description
        add_option.callback = self.add_option
        remove_option.callback = self.remove_option
        moderator_role.callback = self.set_moderator_role

        row_one.add_item(description)
        row_one.add_item(add_option)
        row_one.add_item(remove_option)
        row_one.add_item(moderator_role)

        row_two = discord.ui.ActionRow()

        logs = discord.ui.Button(
            label="Logs Channel",
            emoji="🧾",
            style=discord.ButtonStyle.secondary,
        )
        view_config = discord.ui.Button(
            label="View Config",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
        )
        send_panel = discord.ui.Button(
            label="Send Panel",
            emoji="📨",
            style=discord.ButtonStyle.success,
        )
        close = discord.ui.Button(
            label="Close",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
        )

        logs.callback = self.set_logs_channel
        view_config.callback = self.view_config
        send_panel.callback = self.send_panel
        close.callback = self.close_panel

        row_two.add_item(logs)
        row_two.add_item(view_config)
        row_two.add_item(send_panel)
        row_two.add_item(close)

        container.add_item(row_one)
        container.add_item(row_two)

        self.add_item(container)

    async def edit_description(
        self,
        interaction: discord.Interaction,
    ):
        guild_data = await ticket_db.get_guild(interaction.guild.id)

        await interaction.response.send_modal(
            DescriptionModal(guild_data["description"])
        )

    async def add_option(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(AddOptionModal())

    async def remove_option(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(RemoveOptionModal())

    async def set_moderator_role(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=ModeratorRolePicker(),
            ephemeral=True,
        )

    async def set_logs_channel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            view=LogsChannelPicker(),
            ephemeral=True,
        )

    async def view_config(
        self,
        interaction: discord.Interaction,
    ):
        guild_data = await ticket_db.get_guild(interaction.guild.id)

        moderator_role = interaction.guild.get_role(
            guild_data["moderator_role_id"]
        )
        logs_channel = interaction.guild.get_channel(
            guild_data["logs_channel_id"]
        )

        options = (
            "\n\n".join(
                format_option(interaction.guild, option)
                for option in guild_data["options"]
            )
            or "`No ticket options configured`"
        )

        await interaction_response(
            interaction,
            "Current Ticket Configuration",
            f"### Description\n{guild_data['description']}\n\n"
            f"### Moderator Role\n"
            f"{moderator_role.mention if moderator_role else '`Not configured`'}\n\n"
            f"### Logs Channel\n"
            f"{logs_channel.mention if logs_channel else '`Not configured`'}\n\n"
            f"### Ticket Options\n{options}",
        )

    async def send_panel(
        self,
        interaction: discord.Interaction,
    ):
        guild_data = await ticket_db.get_guild(interaction.guild.id)

        if not guild_data["moderator_role_id"]:
            return await interaction_response(
                interaction,
                "Moderator Role Missing",
                "Set the moderator role before sending the panel.",
                success=False,
            )

        if not guild_data["options"]:
            return await interaction_response(
                interaction,
                "No Ticket Options",
                "Add at least one ticket option before sending the panel.",
                success=False,
            )

        panel = TicketPanelView(
            self.cog,
            interaction.guild.id,
        )
        await panel.build()

        message = await interaction.channel.send(view=panel)

        guild_data["panel_channel_id"] = interaction.channel.id
        guild_data["panel_message_id"] = message.id
        await ticket_db.save_guild(interaction.guild.id, guild_data)

        self.cog.bot.add_view(
            panel,
            message_id=message.id,
        )

        await interaction_response(
            interaction,
            "Ticket Panel Sent",
            f"The ticket panel was sent to {interaction.channel.mention}.",
        )

    async def close_panel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(view=None)
        self.stop()


# =========================================================
# PUBLIC TICKET PANEL
# =========================================================

class TicketOptionSelect(discord.ui.Select):
    def __init__(
        self,
        cog: "TicketSystem",
        guild_id: int,
        options: list[dict[str, Any]],
    ):
        self.cog = cog
        self.guild_id = guild_id

        select_options = [
            discord.SelectOption(
                label=option["name"][:100],
                value=option["key"],
                description=option["description"][:100],
                emoji=option.get("emoji") or "🎫",
            )
            for option in options[:25]
        ]

        super().__init__(
            custom_id=f"monk_ticket_create:{guild_id}",
            placeholder="Choose a ticket option",
            min_values=1,
            max_values=1,
            options=select_options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.cog.create_ticket(
            interaction,
            self.values[0],
        )


class TicketPanelView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "TicketSystem",
        guild_id: int,
    ):
        super().__init__(timeout=None)

        self.cog = cog
        self.guild_id = guild_id

    async def build(self) -> None:
        guild_data = await ticket_db.get_guild(self.guild_id)
        self.clear_items()

        container = discord.ui.Container(accent_colour=ACCENT)
        container.add_item(
            discord.ui.TextDisplay("## 🎫 Create a Ticket")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(guild_data["description"])
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Choose the most suitable option below. "
                "Only one open ticket is allowed per user."
            )
        )

        row = discord.ui.ActionRow()
        row.add_item(
            TicketOptionSelect(
                self.cog,
                self.guild_id,
                guild_data["options"],
            )
        )

        container.add_item(row)
        self.add_item(container)


# =========================================================
# TICKET CONTROL PANEL
# =========================================================

class TicketControls(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "TicketSystem",
        guild_id: int,
        ticket_number: int,
        creator_id: int,
        option_name: str,
        *,
        claimed_by: Optional[int] = None,
    ):
        super().__init__(timeout=None)

        self.cog = cog
        self.guild_id = guild_id
        self.ticket_number = ticket_number
        self.creator_id = creator_id
        self.option_name = option_name
        self.claimed_by = claimed_by

        self.build()

    def build(self) -> None:
        self.clear_items()

        colour = SUCCESS if self.claimed_by else ACCENT
        container = discord.ui.Container(accent_colour=colour)

        title = (
            f"## ✅ Ticket #{self.ticket_number:04d} Claimed"
            if self.claimed_by
            else f"## 🎫 Ticket #{self.ticket_number:04d}"
        )

        status = (
            f"**Claimed by:** <@{self.claimed_by}>\n"
            f"**Status:** `Claimed`"
            if self.claimed_by
            else "**Status:** `Waiting for staff`"
        )

        container.add_item(discord.ui.TextDisplay(title))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"**Created by:** <@{self.creator_id}>\n"
                f"**Ticket type:** {self.option_name}\n"
                f"{status}\n\n"
                "Please explain your issue clearly and include any useful "
                "screenshots or details."
            )
        )

        container.add_item(discord.ui.Separator())

        row_one = discord.ui.ActionRow()

        claim = discord.ui.Button(
            label="Claimed" if self.claimed_by else "Claim",
            emoji="✅" if self.claimed_by else "🙋",
            style=(
                discord.ButtonStyle.success
                if self.claimed_by
                else discord.ButtonStyle.primary
            ),
            disabled=bool(self.claimed_by),
            custom_id=(
                f"monk_ticket_claim:{self.guild_id}:{self.ticket_number}"
            ),
        )

        close = discord.ui.Button(
            label="Close",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id=(
                f"monk_ticket_close:{self.guild_id}:{self.ticket_number}"
            ),
        )

        rename = discord.ui.Button(
            label="Rename",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            custom_id=(
                f"monk_ticket_rename:{self.guild_id}:{self.ticket_number}"
            ),
        )

        claim.callback = self.claim
        close.callback = self.close
        rename.callback = self.rename

        row_one.add_item(claim)
        row_one.add_item(rename)
        row_one.add_item(close)

        container.add_item(row_one)
        self.add_item(container)

    async def ensure_moderator(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if not interaction.guild:
            return False

        if not isinstance(interaction.user, discord.Member):
            return False

        guild_data = await ticket_db.get_guild(interaction.guild.id)

        if not is_ticket_moderator(
            interaction.user,
            guild_data["moderator_role_id"],
        ):
            await interaction_response(
                interaction,
                "Moderator Only",
                "Only the configured moderator role or an administrator "
                "can use this control.",
                success=False,
            )
            return False

        return True

    async def claim(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.ensure_moderator(interaction):
            return

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        ticket = ticket_channel_data(
            guild_data,
            interaction.channel.id,
        )

        if not ticket:
            return await interaction_response(
                interaction,
                "Ticket Data Missing",
                "This channel is not registered as an open ticket.",
                success=False,
            )

        if ticket.get("claimed_by"):
            return await interaction_response(
                interaction,
                "Already Claimed",
                f"This ticket is already claimed by "
                f"<@{ticket['claimed_by']}>.",
                success=False,
            )

        ticket["claimed_by"] = interaction.user.id
        guild_data["open_tickets"][str(interaction.channel.id)] = ticket
        await ticket_db.save_guild(interaction.guild.id, guild_data)

        self.claimed_by = interaction.user.id
        self.build()

        await interaction.response.edit_message(view=self)

        await interaction.channel.send(
            view=TicketResponse(
                "Ticket Claimed",
                f"{interaction.user.mention} is now handling this ticket.",
            )
        )

    async def rename(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.ensure_moderator(interaction):
            return

        await interaction.response.send_modal(
            RenameTicketModal()
        )

    async def close(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.ensure_moderator(interaction):
            return

        await interaction.response.send_message(
            view=CloseTicketConfirmation(
                self.cog,
                interaction.guild.id,
                self.ticket_number,
                interaction.user.id,
            ),
            ephemeral=True,
        )


# =========================================================
# CLOSE CONFIRMATION
# =========================================================

class CloseTicketConfirmation(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "TicketSystem",
        guild_id: int,
        ticket_number: int,
        moderator_id: int,
    ):
        super().__init__(timeout=30)

        self.cog = cog
        self.guild_id = guild_id
        self.ticket_number = ticket_number
        self.moderator_id = moderator_id

        container = discord.ui.Container(accent_colour=WARNING)
        container.add_item(
            discord.ui.TextDisplay("## ⚠️ Close This Ticket?")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "A transcript will be generated and the channel will then "
                "be deleted."
            )
        )

        row = discord.ui.ActionRow()

        confirm = discord.ui.Button(
            label="Close Ticket",
            emoji="🔒",
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

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.moderator_id:
            await interaction_response(
                interaction,
                "This Confirmation Is Not Yours",
                "Only the moderator who opened it can use these buttons.",
                success=False,
            )
            return False

        return True

    async def confirm(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            return

        await interaction.response.edit_message(
            view=TicketResponse(
                "Closing Ticket",
                "Generating the transcript and closing this ticket...",
                warning=True,
            )
        )

        await self.cog.close_ticket(
            interaction.channel,
            interaction.user,
        )

    async def cancel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.edit_message(
            view=TicketResponse(
                "Close Cancelled",
                "The ticket remains open.",
                success=False,
            )
        )


# =========================================================
# TICKET COG
# =========================================================

class TicketSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.restore_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        self.restore_task = asyncio.create_task(
            self.restore_persistent_views()
        )

    def cog_unload(self):
        if self.restore_task and not self.restore_task.done():
            self.restore_task.cancel()

    async def restore_persistent_views(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            guild_data = await ticket_db.get_guild(guild.id)

            panel_message_id = guild_data.get("panel_message_id")

            if panel_message_id and guild_data["options"]:
                panel = TicketPanelView(self, guild.id)
                await panel.build()

                self.bot.add_view(
                    panel,
                    message_id=panel_message_id,
                )

            for ticket in guild_data["open_tickets"].values():
                control_message_id = ticket.get("control_message_id")

                if not control_message_id:
                    continue

                controls = TicketControls(
                    self,
                    guild.id,
                    ticket["ticket_number"],
                    ticket["creator_id"],
                    ticket["option_name"],
                    claimed_by=ticket.get("claimed_by"),
                )

                self.bot.add_view(
                    controls,
                    message_id=control_message_id,
                )

    async def create_ticket(
        self,
        interaction: discord.Interaction,
        option_key: str,
    ):
        if not interaction.guild:
            return

        await interaction.response.defer(ephemeral=True)

        guild_data = await ticket_db.get_guild(interaction.guild.id)
        option = find_option(
            guild_data["options"],
            option_key,
        )

        if not option:
            return await interaction.followup.send(
                view=TicketResponse(
                    "Option Missing",
                    "This ticket option no longer exists.",
                    success=False,
                ),
                ephemeral=True,
            )

        stale_channels = []

        for channel_id, ticket in guild_data["open_tickets"].items():
            channel = interaction.guild.get_channel(int(channel_id))

            if not channel:
                stale_channels.append(channel_id)
                continue

            if ticket["creator_id"] == interaction.user.id:
                return await interaction.followup.send(
                    view=TicketResponse(
                        "Ticket Already Open",
                        f"You already have an open ticket: {channel.mention}",
                        success=False,
                    ),
                    ephemeral=True,
                )

        for channel_id in stale_channels:
            guild_data["open_tickets"].pop(channel_id, None)

        if stale_channels:
            await ticket_db.save_guild(
                interaction.guild.id,
                guild_data,
            )

        category = interaction.guild.get_channel(
            option["category_id"]
        )

        if not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send(
                view=TicketResponse(
                    "Category Missing",
                    f"The category for **{option['name']}** no longer exists.",
                    success=False,
                ),
                ephemeral=True,
            )

        moderator_role = interaction.guild.get_role(
            guild_data["moderator_role_id"]
        )

        if not moderator_role:
            return await interaction.followup.send(
                view=TicketResponse(
                    "Moderator Role Missing",
                    "The configured moderator role no longer exists.",
                    success=False,
                ),
                ephemeral=True,
            )

        ticket_number = await ticket_db.next_ticket_number(
            interaction.guild.id
        )

        username = safe_channel_name(
            interaction.user.display_name
        )
        channel_name = (
            f"{username}-{ticket_number:04d}"
        )[:100]

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            moderator_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True,
            ),
        }

        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Ticket #{ticket_number:04d} | "
                    f"Creator: {interaction.user.id} | "
                    f"Option: {option['name']}"
                ),
                reason=f"Ticket created by {interaction.user}",
            )

        except discord.Forbidden:
            return await interaction.followup.send(
                view=TicketResponse(
                    "Ticket Creation Failed",
                    "I need **Manage Channels** permission.",
                    success=False,
                ),
                ephemeral=True,
            )

        controls = TicketControls(
            self,
            interaction.guild.id,
            ticket_number,
            interaction.user.id,
            option["name"],
        )

        try:
            control_message = await channel.send(
                view=controls,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=True,
                    everyone=False,
                ),
            )

        except Exception as error:
            try:
                await channel.delete(
                    reason="Ticket control panel failed to send"
                )
            except discord.HTTPException:
                pass

            return await interaction.followup.send(
                view=TicketResponse(
                    "Ticket Panel Failed",
                    f"The ticket channel was removed because the control "
                    f"panel could not be sent.\n\n"
                    f"```py\n{type(error).__name__}: {error}\n```",
                    success=False,
                ),
                ephemeral=True,
            )

        guild_data = await ticket_db.get_guild(
            interaction.guild.id
        )

        guild_data["open_tickets"][str(channel.id)] = {
            "channel_id": channel.id,
            "creator_id": interaction.user.id,
            "ticket_number": ticket_number,
            "option_key": option_key,
            "option_name": option["name"],
            "claimed_by": None,
            "control_message_id": control_message.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await ticket_db.save_guild(
            interaction.guild.id,
            guild_data,
        )

        self.bot.add_view(
            controls,
            message_id=control_message.id,
        )

        await interaction.followup.send(
            view=TicketResponse(
                "Ticket Created",
                f"Your ticket is ready: {channel.mention}",
            ),
            ephemeral=True,
        )

    async def create_transcript(
        self,
        channel: discord.TextChannel,
    ) -> discord.File:
        messages = []

        async for message in channel.history(
            limit=None,
            oldest_first=True,
        ):
            created = message.created_at.strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            content = html.escape(
                message.clean_content or ""
            ).replace("\n", "<br>")

            attachments = "<br>".join(
                f'<a href="{html.escape(attachment.url)}">'
                f'{html.escape(attachment.filename)}</a>'
                for attachment in message.attachments
            )

            if attachments:
                content += (
                    "<br><strong>Attachments:</strong><br>"
                    + attachments
                )

            messages.append(
                "<div class='message'>"
                f"<div class='meta'>{html.escape(str(message.author))} "
                f"• {created}</div>"
                f"<div class='content'>{content or '<em>No text content</em>'}</div>"
                "</div>"
            )

        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Transcript - {html.escape(channel.name)}</title>
<style>
body {{
    background: #111318;
    color: #e7e9ee;
    font-family: Arial, sans-serif;
    padding: 24px;
}}
h1 {{
    color: #d6a354;
}}
.message {{
    background: #1b1e25;
    border-left: 4px solid #c69149;
    padding: 12px;
    margin-bottom: 12px;
    border-radius: 8px;
}}
.meta {{
    color: #aeb4c0;
    font-size: 13px;
    margin-bottom: 8px;
}}
.content {{
    line-height: 1.5;
}}
a {{
    color: #7ab7ff;
}}
</style>
</head>
<body>
<h1>Ticket Transcript: #{html.escape(channel.name)}</h1>
<p>Generated by Monk at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
{''.join(messages)}
</body>
</html>"""

        buffer = io.BytesIO(page.encode("utf-8"))

        return discord.File(
            buffer,
            filename=f"{channel.name}-transcript.html",
        )

    async def close_ticket(
        self,
        channel: discord.TextChannel,
        moderator: discord.Member,
    ):
        guild_data = await ticket_db.get_guild(channel.guild.id)
        ticket = ticket_channel_data(
            guild_data,
            channel.id,
        )

        if not ticket:
            try:
                await channel.send(
                    view=TicketResponse(
                        "Ticket Data Missing",
                        "This channel is not registered as an open ticket.",
                        success=False,
                    )
                )
            except discord.HTTPException:
                pass
            return

        transcript = await self.create_transcript(channel)

        logs_channel = channel.guild.get_channel(
            guild_data["logs_channel_id"]
        )

        if isinstance(logs_channel, discord.TextChannel):
            try:
                await logs_channel.send(
                    view=TicketResponse(
                        f"Ticket #{ticket['ticket_number']:04d} Closed",
                        f"**Channel:** `#{channel.name}`\n"
                        f"**Creator:** <@{ticket['creator_id']}>\n"
                        f"**Type:** {ticket['option_name']}\n"
                        f"**Claimed by:** "
                        f"{f'<@{ticket['claimed_by']}>' if ticket.get('claimed_by') else '`Nobody`'}\n"
                        f"**Closed by:** {moderator.mention}\n"
                        f"**Opened:** {format_time(ticket['created_at'])}",
                    ),
                    file=transcript,
                )

            except discord.HTTPException:
                pass

        guild_data["open_tickets"].pop(
            str(channel.id),
            None,
        )

        await ticket_db.save_guild(
            channel.guild.id,
            guild_data,
        )

        await asyncio.sleep(2)

        try:
            await channel.delete(
                reason=f"Ticket closed by {moderator}",
            )
        except discord.Forbidden:
            try:
                await channel.send(
                    view=TicketResponse(
                        "Close Failed",
                        "I need **Manage Channels** to delete this ticket.",
                        success=False,
                    )
                )
            except discord.HTTPException:
                pass

    # -----------------------------------------------------
    # COMMANDS
    # -----------------------------------------------------

    @commands.command(
        name="ticketconfig",
        aliases=["tconfig"],
        help="Open the interactive ticket configuration panel.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ticket_config(
        self,
        ctx: commands.Context,
    ):
        await ctx.send(
            view=TicketConfigView(
                self,
                ctx.guild,
                ctx.author.id,
            )
        )

    @commands.command(
        name="ticketpanel",
        aliases=["sendticketpanel"],
        help="Send the configured ticket panel.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ticket_panel(
        self,
        ctx: commands.Context,
    ):
        guild_data = await ticket_db.get_guild(ctx.guild.id)

        if not guild_data["moderator_role_id"]:
            return await ctx.send(
                view=TicketResponse(
                    "Moderator Role Missing",
                    "Set it using `mticketconfig`.",
                    success=False,
                )
            )

        if not guild_data["options"]:
            return await ctx.send(
                view=TicketResponse(
                    "No Ticket Options",
                    "Add at least one option using `mticketconfig`.",
                    success=False,
                )
            )

        panel = TicketPanelView(
            self,
            ctx.guild.id,
        )
        await panel.build()

        message = await ctx.send(view=panel)

        guild_data["panel_channel_id"] = ctx.channel.id
        guild_data["panel_message_id"] = message.id
        await ticket_db.save_guild(ctx.guild.id, guild_data)

        self.bot.add_view(
            panel,
            message_id=message.id,
        )

    @commands.command(
        name="ticketadd",
        help="Add a member to the current ticket.",
    )
    @commands.guild_only()
    async def ticket_add(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ):
        guild_data = await ticket_db.get_guild(ctx.guild.id)

        if not is_ticket_moderator(
            ctx.author,
            guild_data["moderator_role_id"],
        ):
            return await ctx.send(
                view=TicketResponse(
                    "Moderator Only",
                    "Only ticket moderators can add members.",
                    success=False,
                )
            )

        if not ticket_channel_data(guild_data, ctx.channel.id):
            return await ctx.send(
                view=TicketResponse(
                    "Not a Ticket",
                    "This command only works inside an open ticket.",
                    success=False,
                )
            )

        await ctx.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            reason=f"Added to ticket by {ctx.author}",
        )

        await ctx.send(
            view=TicketResponse(
                "Member Added",
                f"{member.mention} can now access this ticket.",
            )
        )

    @commands.command(
        name="ticketremove",
        help="Remove a member from the current ticket.",
    )
    @commands.guild_only()
    async def ticket_remove(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ):
        guild_data = await ticket_db.get_guild(ctx.guild.id)

        if not is_ticket_moderator(
            ctx.author,
            guild_data["moderator_role_id"],
        ):
            return await ctx.send(
                view=TicketResponse(
                    "Moderator Only",
                    "Only ticket moderators can remove members.",
                    success=False,
                )
            )

        ticket = ticket_channel_data(
            guild_data,
            ctx.channel.id,
        )

        if not ticket:
            return await ctx.send(
                view=TicketResponse(
                    "Not a Ticket",
                    "This command only works inside an open ticket.",
                    success=False,
                )
            )

        if member.id == ticket["creator_id"]:
            return await ctx.send(
                view=TicketResponse(
                    "Cannot Remove Creator",
                    "The ticket creator cannot be removed.",
                    success=False,
                )
            )

        await ctx.channel.set_permissions(
            member,
            overwrite=None,
            reason=f"Removed from ticket by {ctx.author}",
        )

        await ctx.send(
            view=TicketResponse(
                "Member Removed",
                f"{member.mention} can no longer access this ticket.",
            )
        )

    @commands.command(
        name="ticketrename",
        help="Rename the current ticket.",
    )
    @commands.guild_only()
    async def ticket_rename(
        self,
        ctx: commands.Context,
        *,
        name: str,
    ):
        guild_data = await ticket_db.get_guild(ctx.guild.id)

        if not is_ticket_moderator(
            ctx.author,
            guild_data["moderator_role_id"],
        ):
            return await ctx.send(
                view=TicketResponse(
                    "Moderator Only",
                    "Only ticket moderators can rename tickets.",
                    success=False,
                )
            )

        if not ticket_channel_data(guild_data, ctx.channel.id):
            return await ctx.send(
                view=TicketResponse(
                    "Not a Ticket",
                    "This command only works inside an open ticket.",
                    success=False,
                )
            )

        new_name = safe_channel_name(name)

        await ctx.channel.edit(
            name=new_name,
            reason=f"Ticket renamed by {ctx.author}",
        )

        await ctx.send(
            view=TicketResponse(
                "Ticket Renamed",
                f"The ticket was renamed to `#{new_name}`.",
            )
        )

    @commands.command(
        name="ticketclose",
        help="Close the current ticket.",
    )
    @commands.guild_only()
    async def ticket_close(
        self,
        ctx: commands.Context,
    ):
        guild_data = await ticket_db.get_guild(ctx.guild.id)

        if not is_ticket_moderator(
            ctx.author,
            guild_data["moderator_role_id"],
        ):
            return await ctx.send(
                view=TicketResponse(
                    "Moderator Only",
                    "Only ticket moderators can close tickets.",
                    success=False,
                )
            )

        if not ticket_channel_data(guild_data, ctx.channel.id):
            return await ctx.send(
                view=TicketResponse(
                    "Not a Ticket",
                    "This command only works inside an open ticket.",
                    success=False,
                )
            )

        await ctx.send(
            view=CloseTicketConfirmation(
                self,
                ctx.guild.id,
                ticket_channel_data(
                    guild_data,
                    ctx.channel.id,
                )["ticket_number"],
                ctx.author.id,
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
                view=TicketResponse(
                    "Permission Denied",
                    "You need **Administrator** permission.",
                    success=False,
                )
            )

        if isinstance(error, commands.MemberNotFound):
            return await ctx.send(
                view=TicketResponse(
                    "Member Not Found",
                    "Mention a valid server member.",
                    success=False,
                )
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(
                view=TicketResponse(
                    "Missing Argument",
                    f"You did not provide `{error.param.name}`.",
                    success=False,
                )
            )

        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystem(bot))