import discord
from discord.ext import commands
from discord import app_commands
import json
import os


DATA_FILE = "data/reactionroles.json"


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()

    def load_data(self):
        if not os.path.exists("data"):
            os.makedirs("data")

        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, "w") as f:
                json.dump({}, f)

        with open(DATA_FILE, "r") as f:
            self.data = json.load(f)


    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=4)


    @app_commands.command(
        name="reactionrole",
        description="Setup a reaction role message"
    )
    @app_commands.describe(
        channel="Channel where message will be sent",
        role="Role users will receive",
        emoji="Emoji for reaction",
        title="Embed title"
    )
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        emoji: str,
        title: str = "Reaction Roles"
    ):

        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "❌ You need Manage Roles permission",
                ephemeral=True
            )


        embed = discord.Embed(
            title=title,
            description=(
                f"React with {emoji} to get {role.mention}\n\n"
                "React again to remove the role."
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Reaction Roles System"
        )


        msg = await channel.send(embed=embed)

        await msg.add_reaction(emoji)


        self.data[str(msg.id)] = {
            "guild": interaction.guild.id,
            "channel": channel.id,
            "emoji": emoji,
            "role": role.id
        }

        self.save_data()


        await interaction.response.send_message(
            f"✅ Reaction role created in {channel.mention}",
            ephemeral=True
        )



    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):

        if payload.message_id not in map(int, self.data.keys()):
            return


        info = self.data[str(payload.message_id)]


        if str(payload.emoji) != info["emoji"]:
            return


        guild = self.bot.get_guild(info["guild"])

        if not guild:
            return


        role = guild.get_role(info["role"])

        if not role:
            return


        member = guild.get_member(payload.user_id)

        if not member or member.bot:
            return


        await member.add_roles(
            role,
            reason="Reaction Role"
        )


    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):

        if payload.message_id not in map(int, self.data.keys()):
            return


        info = self.data[str(payload.message_id)]


        if str(payload.emoji) != info["emoji"]:
            return


        guild = self.bot.get_guild(info["guild"])

        if not guild:
            return


        role = guild.get_role(info["role"])

        if not role:
            return


        member = guild.get_member(payload.user_id)

        if not member:
            return


        await member.remove_roles(
            role,
            reason="Reaction Role Removed"
        )



async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))