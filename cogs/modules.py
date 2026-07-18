from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from cogs.Help import get_command_category
from cogs.setup import config_db, get_config_value


AVAILABLE_MODULES = (
    "moderation",
    "advanced_moderation",
    "automod",
    "security",
    "logging",
    "tickets",
    "utility",
    "economy",
    "leveling",
    "voice",
    "setup",
    "welcome",
    "music",
    "information",
    "fun",
)

MODULE_ALIASES = {
    "advancedmod": "advanced_moderation",
    "advancedmoderation": "advanced_moderation",
    "advanced_mod": "advanced_moderation",
    "automoderation": "automod",
    "economy": "economy",
    "level": "leveling",
    "levels": "leveling",
    "levelling": "leveling",
    "mod": "moderation",
    "mods": "moderation",
    "ticket": "tickets",
    "utilities": "utility",
    "vc": "voice",
}

CATEGORY_MODULES = {
    "advanced moderation": "advanced_moderation",
    "automod": "automod",
    "economy": "economy",
    "fun": "fun",
    "information": "information",
    "leveling": "leveling",
    "logging": "logging",
    "moderation": "moderation",
    "music": "music",
    "security": "security",
    "setup": "setup",
    "tickets": "tickets",
    "utility": "utility",
    "voice": "voice",
}

COG_MODULES = {
    "Welcome": "welcome",
}

EXEMPT_COGS = {"Help", "Modules", "Owner"}


def normalize_module(value: str) -> Optional[str]:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = MODULE_ALIASES.get(normalized, normalized)
    return normalized if normalized in AVAILABLE_MODULES else None


def get_disabled_modules(guild_id: int) -> set[str]:
    stored = get_config_value(guild_id, "disabled_modules", [])
    if not isinstance(stored, list):
        return set()
    return {module for value in stored if (module := normalize_module(str(value)))}


def is_module_disabled(guild_id: int, module: str) -> bool:
    normalized = normalize_module(module)
    return bool(normalized and normalized in get_disabled_modules(guild_id))


def set_module_disabled(guild_id: int, module: str, disabled: bool) -> None:
    modules = get_disabled_modules(guild_id)
    if disabled:
        modules.add(module)
    else:
        modules.discard(module)
    config_db.set(guild_id, "disabled_modules", sorted(modules))


def command_module(command: commands.Command) -> Optional[str]:
    if command.cog_name in EXEMPT_COGS:
        return None
    if command.cog_name in COG_MODULES:
        return COG_MODULES[command.cog_name]
    return CATEGORY_MODULES.get(get_command_category(command).lower())


class Modules(commands.Cog):
    """Per-server feature module controls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="disable", aliases=["moduleoff"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def disable_module(self, ctx: commands.Context, *, module: str):
        normalized = normalize_module(module)
        if not normalized:
            return await ctx.send(
                "Unknown module. Use `mmodules` to see the available modules."
            )

        if is_module_disabled(ctx.guild.id, normalized):
            return await ctx.send(
                f"**{normalized.replace('_', ' ').title()}** is already disabled."
            )

        set_module_disabled(ctx.guild.id, normalized, True)

        if normalized == "music" and ctx.guild.voice_client:
            await ctx.guild.voice_client.disconnect()

        await ctx.send(
            f"Disabled the **{normalized.replace('_', ' ').title()}** module."
        )

    @commands.command(name="enable", aliases=["moduleon"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def enable_module(self, ctx: commands.Context, *, module: str):
        normalized = normalize_module(module)
        if not normalized:
            return await ctx.send(
                "Unknown module. Use `mmodules` to see the available modules."
            )

        if not is_module_disabled(ctx.guild.id, normalized):
            return await ctx.send(
                f"**{normalized.replace('_', ' ').title()}** is already enabled."
            )

        set_module_disabled(ctx.guild.id, normalized, False)
        await ctx.send(
            f"Enabled the **{normalized.replace('_', ' ').title()}** module."
        )

    @commands.command(name="modules", aliases=["modulelist"])
    @commands.guild_only()
    async def modules_status(self, ctx: commands.Context):
        disabled = get_disabled_modules(ctx.guild.id)
        lines = [
            f"{'❌' if module in disabled else '✅'} "
            f"`{module}`"
            for module in AVAILABLE_MODULES
        ]
        await ctx.send(
            "## Server Modules\n" + "\n".join(lines)
            + "\n\nManagers can use `mdisable <module>` or `menable <module>`."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Modules(bot))
