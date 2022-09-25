import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
import db_handler
import time
import two_factor_helper

class Webhooks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot # This is so you can access Bot instance in your cog

    webhook_options = SlashCommandGroup("webhook_options", "Toggle webhook protection for this server.", guild_only=True)
    @commands.Cog.listener("on_webhooks_update")
    async def on_webhooks_update(self, channel):
        print(channel)
        print(channel.guild)

        # Guild not set up?
        if not db_handler.check_guild(self.bot.CONN, channel.guild.id):
            print("The guild selected is not in the guild list.")
            return

	    # check webhook protection status in the server
        if not db_handler.check_webhook(self.bot.CONN, channel.guild.id):
            print("No webhook protection.")
            return

	# find the server's log channel
        try:
            log_channel_id = db_handler.get_log_channel(self.bot.CONN, channel.guild.id)
            log_channel = channel.guild.get_channel(log_channel_id)
            if log_channel is None:
                log_channel = await channel.guild.fetch_channel(log_channel_id)
        except:
            print(f'webhook-protection log channel not found for {channel.guild}')
            return

        try:
            # find the most recently created webhook in the channel
            webhooks = await channel.webhooks()
            if len(webhooks) < 1:
                return
            recent_webhook = webhooks[-1]
        except:
            embed = await self.bot.build_log_embed(0xe74c3c, None, channel, '❌ FAILED TO DELETE - MISSING PERMISSIONS.')
            await log_channel.send(embed=embed)
            return

        # only process webhooks created within 120 seconds
        if recent_webhook.created_at.timestamp() < (time.time() - 120):
            return
        # don't process channel follows
        if recent_webhook.type == discord.WebhookType.channel_follower:
            return

	# # check to see if the webhook was created by a verified bot
        if db_handler.check_verified_bots(self.bot.CONN, channel.guild.id):
            if recent_webhook.user.public_flags.verified_bot:
                embed = await self.bot.build_log_embed(0x2ecc71, recent_webhook.user, channel, '✅ Verified Bot - No action taken.')
                await log_channel.send(embed=embed)
                return

        # attempt to delete all webhooks
        try:
            await recent_webhook.delete(reason='Webhook protection')
        except:
            embed = await self.bot.build_log_embed(0xe74c3c, recent_webhook.user, channel, '❌ FAILED TO DELETE - MISSING PERMISSIONS.')
            await log_channel.send(embed=embed)
            return

        # log the webhook deletion
        embed = await self.bot.build_log_embed(0xf1c40f, recent_webhook.user, channel, '✅ Webhook deleted.')
        await log_channel.send(embed=embed)
        return

    @commands.guild_only()
    @webhook_options.command()
    async def enable(self, 
    ctx,
    code : Option(int,'Enter the 6-digit code on your authentication application',required=True),
    verified_bots : Option(
        description="Allow verified bots?",
        choices = ['True','False']
    )):
        if ctx.author.id != self.bot.master_user:
            await ctx.respond("You are not authorised to use this command.", ephemeral=True)
            return
        if not db_handler.check_user(self.bot.CONN, ctx.author.id) or not db_handler.check_verified(self.bot.CONN, ctx.author.id) == 1:
            await ctx.respond("You do not have permission for this action.", ephemeral=True)
            return
        if not two_factor_helper.verify_code(self.bot.CONN, user_id=ctx.user.id, code=code):
            await ctx.respond("Incorrect verification code given.",ephemeral=True)
            return
        if not db_handler.check_guild(self.bot.CONN, ctx.guild.id):
            await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
            return
        bot_bool = 1 if verified_bots == 'True' else 0
        print(bot_bool)
        log = db_handler.get_log_channel(self.bot.CONN, ctx.guild.id)
        lg = self.bot.get_channel(log)
        db_handler.set_webhook_parameters(self.bot.CONN, (1,bot_bool, ctx.guild.id))
        await lg.send(f'Webhook protection was activated on the server by {ctx.author.mention}. Verified Bot Bypass: {True if bot_bool else False}')
        await ctx.respond("Webhook options enabled.", ephemeral=True)

    @commands.guild_only()
    @webhook_options.command()
    async def disable(self, ctx, code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
        # MASTER CHECK
        if ctx.author.id != self.bot.master_user:
            await ctx.respond("You are not authorised to use this command.", ephemeral=True)
            return
        if not db_handler.check_user(self.bot.CONN, ctx.author.id) or not db_handler.check_verified(self.bot.CONN, ctx.author.id) == 1:
            await ctx.respond("You do not have permission for this action.", ephemeral=True)
            return
        if not two_factor_helper.verify_code(self.bot.CONN, user_id=ctx.user.id, code=code):
            await ctx.respond("Incorrect verification code given.",ephemeral=True)
            return
        if not db_handler.check_guild(self.bot.CONN, ctx.guild.id):
            await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
            return
        log = db_handler.get_log_channel(self.bot.CONN, ctx.guild.id)
        lg = self.bot.get_channel(log)
        db_handler.set_webhook_parameters(self.bot.CONN, (0,0,ctx.guild.id))
        await lg.send(f'Webhook protection was removed from the server by {ctx.author}.')
        await ctx.respond("Webhook options disabled.", ephemeral=True)


# You must have this function for `bot.load_extension` to call
def setup(bot):
    bot.add_cog(Webhooks(bot))
