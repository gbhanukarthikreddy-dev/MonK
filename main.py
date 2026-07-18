from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
COGS_DIR = ROOT_DIR / "cogs"

# Keep JSON database paths working when a process manager launches elsewhere.
os.chdir(ROOT_DIR)
load_dotenv(ROOT_DIR / ".env")

from cogs.owner import get_prefix  # noqa: E402


log = logging.getLogger("monk")


def required_token() -> str:
    token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
    if not token:
        raise RuntimeError(
            "Missing DISCORD_TOKEN. Copy .env.example to .env and add your token."
        )
    return token


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    return intents


class MonkBot(commands.Bot):
    async def setup_hook(self) -> None:
        for path in sorted(COGS_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue

            extension = f"cogs.{path.stem}"
            try:
                await self.load_extension(extension)
            except Exception:
                log.exception("Failed to load %s", extension)
                raise
            else:
                log.info("Loaded %s", extension)

    async def on_ready(self) -> None:
        user_id = self.user.id if self.user else "unknown"
        log.info("Logged in as %s (%s)", self.user, user_id)

    async def process_commands(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        ctx = await self.get_context(message)
        if ctx.command and ctx.guild:
            from cogs.modules import command_module, is_module_disabled

            module = command_module(ctx.command)
            if (
                module
                and is_module_disabled(ctx.guild.id, module)
                and not await self.is_owner(ctx.author)
            ):
                await ctx.send(
                    f"The **{module.replace('_', ' ').title()}** module is disabled "
                    "in this server."
                )
                return

        await self.invoke(ctx)


async def main() -> None:
    discord.utils.setup_logging(level=logging.INFO, root=False)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    bot = MonkBot(
        command_prefix=get_prefix,
        intents=build_intents(),
        help_command=None,
        case_insensitive=True,
    )

    async with bot:
        await bot.start(required_token())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
