from doctest import master
from http.client import FORBIDDEN, HTTPException
from re import L
import discord
from discord import commands
from discord.commands import Option
from discord.ext import commands
import json
import two_factor_helper
import db_handler
import asyncio
import os
from discord.ext import tasks
from typing import Union
with open('./data/config.json', 'r') as f:
    config = json.load(f)

token = config['token']
master_user = config['master_user_id']
announcement_wait = config['announcement_role_lifetime']
class DiscordBot(discord.Bot):
    async def on_ready(self):
        print(f'Logged in as {self.user.name}')
        print("----------------------------")
        self.CONN = db_handler.startup_db()
        if self.CONN is None:
            print("Error retrieving database connection.")
        else:
            print("DB Connected")
        delete_pngs.start()
        permissions_check.start()
        self.master_user = config['master_user_id']

    async def build_log_embed(self, color, user, channel, action_str):
        embed = discord.Embed(
            color=color,
            title='Webhook Creation')
        if user is not None:
            embed.add_field(name='Created By', value=f'**{user.name}**#{user.discriminator} (ID {user.id})', inline=False)
        else:
            embed.add_field(name='Created By', value='Unknown', inline=False)
        embed.add_field(name='Channel', value=f'{channel.mention}', inline=False)
        embed.add_field(name='Action', value=action_str, inline=False)
        embed.set_footer(text='Protected by Server Supervisor', icon_url='https://i.imgur.com/xCTOwPj.png')
        return embed


bot = DiscordBot()
bot.load_extension("cogs.webhooks")

@bot.command(description="Command used to start the 2fA pairing setup. Requires Authy/Google Authenticator.")
async def setup(ctx):
    """
    The initial setup command.
    """
    m_user = True if bot.master_user == ctx.author.id else False
    # Check if the user exists and do so accordingly
    if not db_handler.check_authorised(bot.CONN,info=(ctx.guild.id, ctx.author.id)) and not m_user:
        await ctx.respond("You are not authorised to perform this command.", ephemeral = True)
        return
    if db_handler.check_user(bot.CONN, int(ctx.user.id)):
        await ctx.respond("You are already registered in the 2fA system.", ephemeral=True)
    else:
        delete_pngs.cancel()
        pngpath = two_factor_helper.setup_and_get_path(ctx, bot.CONN)
        pngfile = discord.File(pngpath)

        await ctx.respond("""
Your information has been input.
Scan the QR Code as shown below with Authy/Google Authenticator and type /verify [code] with the code currently shown via the authentication application used.
Without using the /verify command, you will not be able to use the 2fA system fully.
        """,file=pngfile, ephemeral=True)
        delete_pngs.start()

@commands.cooldown(1, 5, commands.BucketType.user)
@bot.command(description="Command used to verify a 2fA pairing setup.")
async def verify(ctx, code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    if not db_handler.check_user(bot.CONN, ctx.author.id):
        await ctx.respond("You are not in the database for pending verification. Please use /setup to start.", ephemeral=True)
    else:
        verification = db_handler.check_verified(bot.CONN, ctx.author.id)
        if verification == 0:
            if two_factor_helper.verify_code(bot.CONN, user_id=ctx.user.id, code=code):
                db_handler.verify(bot.CONN, ctx.author.id)
                # Test clause
                assert db_handler.check_verified(bot.CONN, ctx.author.id) == 1
                await ctx.respond("You are now verified.", ephemeral=True)
            else:
                await ctx.respond("Incorrect code given.", ephemeral=True)
        elif verification == 1:
            await ctx.respond("You are already verified.", ephemeral=True)

@commands.cooldown(1, 5, commands.BucketType.user)
@commands.guild_only()
@bot.command(description="Command used to gain the trusted role for a single announcements")
async def announcement(ctx,
    announcement_channel : Option(
        discord.TextChannel,
        'Enter the channel to authorise for.', required=True),
    code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    """
    Input:
    Context : discord.InteractionContext
    Code : int.

    Checks:
    1. Is user 2fA activated?
    2. is user authorised?
    3. is the verification code correct?
    4. is the guild set up?
    """
    guild_id = ctx.guild.id
    member_id = ctx.author.id
    # Check 1: Is guild registered

    # Is user authorised for this command?

    if not (db_handler.check_user(bot.CONN,int(member_id)) and db_handler.check_verified(bot.CONN,int(member_id)) == 1):
        await ctx.respond("You are not authorised to perform this command.", ephemeral=True)
        return
    if not db_handler.check_authorised(bot.CONN,info=(guild_id,member_id)):
        await ctx.respond("You are not authorised to perform this command.", ephemeral=True)
        return
    # Is verification code correct?
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect verification code given.", ephemeral=True)
        return
    if not db_handler.check_guild(bot.CONN, guild_id):
        await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
        return
    # All is good!
    if announcement_channel.id not in [channel_id for channel_id in db_handler.get_channels(bot.CONN, ctx.guild.id)]:
        print(announcement_channel)
        await ctx.respond("Channel is not a valid announcements channel. Set it up with /insert_channel.",ephemeral=True)
        return
    voice_channel_id = db_handler.get_event_channel(bot.CONN,guild_id)
    log_channel_id = db_handler.get_log_channel(bot.CONN, guild_id)
    if (announcement_channel.id and voice_channel_id) is not None:
        # Get text and vc channel
        channel = bot.get_channel(announcement_channel.id)
        vc_channel = bot.get_channel(voice_channel_id)
        log_channel = bot.get_channel(log_channel_id)
        await log_channel.send(f"{ctx.author.mention} has invoked the announcements command for channel: {channel}.")
        print(channel.overwrites)
        #Set the overwrites
        permissions_check.cancel()
        overwrite = discord.PermissionOverwrite()
        overwrite.send_messages = overwrite.mention_everyone = True
        try: # Try set permissions
            await channel.set_permissions(ctx.author, overwrite=overwrite)
        except discord.Forbidden:
            await ctx.respond("I do not have the correct permissions. Please ensure I have Administrator permissions.", ephemeral=True)
            return
        except HTTPException as e:
            await ctx.respond("There was an error when executing the command. HTTP Error Code: {}".format(str(e.code)))
            return
        try: # Try set permissions
            vc_overwrite = discord.PermissionOverwrite()
            vc_overwrite.manage_events = True
            await vc_channel.set_permissions(ctx.author, overwrite=vc_overwrite)
            await ctx.respond("Permissions granted.", ephemeral=True)
        except discord.Forbidden:
            await ctx.respond("I do not have the correct permissions. Please ensure I have Administrator permissions.", ephemeral=True)
            return
        except HTTPException as e:
            await ctx.respond("There was an error when setting the manage_events permission. HTTP Error Code: {}".format(str(e.code)))
            return
        await log_channel.send(f"{ctx.author.mention} has elevated permissions (Manage events, send messages in the announcements channel, mention everyone) for {str(announcement_wait)} seconds.")
        # Wait x seconds
        await asyncio.sleep(int(announcement_wait))
        # Rewrite the overwrites
        try:
            await channel.set_permissions(ctx.author, overwrite=None)
        except discord.Forbidden:
            await ctx.respond("I do not have the correct permissions. Please ensure I have Administrator permissions.", ephemeral=True)
            return
        except HTTPException as e:
            await ctx.respond("There was an error when executing the command. HTTP Error Code: {}".format(str(e.code)))
            return
        try:
            await vc_channel.set_permissions(ctx.author, overwrite=None)
        except discord.Forbidden:
                await ctx.respond("I do not have the correct permissions. Please ensure I have Administrator permissions.", ephemeral=True)
                return
        except HTTPException as e:
            await ctx.respond("There was an error when executing the command. HTTP Error Code: {}".format(str(e.code)))
            return
        permissions_check.start()
        await log_channel.send(f"{ctx.author.mention}'s permissions are now revoked.")

# MASTER USER
@commands.cooldown(1, 5, commands.BucketType.user)
@commands.guild_only()
@bot.command(description="Command used to gain the trusted role for a single announcements")
async def authorise(ctx, member : Option(discord.Member, "User to authorise"), code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    """
    Takes a member option to authorise for /lockdown and /announcements.
    """
    if ctx.author.id != master_user:
        await ctx.respond("You are not authorised to use this command.", ephemeral=True)
        return
    # If user is not in the database and verified
    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action. Have you used /setup and /verify yet?", ephemeral=True)
        return

    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect verification code given.", ephemeral=True)
        return

    # If guild is not in database
    elif not db_handler.check_guild(bot.CONN, ctx.guild.id):
        await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
        return
    # If user is not authorised
    elif db_handler.check_authorised(bot.CONN, (ctx.guild.id, member.id)):
        await ctx.respond("The user is already authorised.", ephemeral=True)
    else:
        try:
            # Authorise Member
            db_handler.authorise_member(conn=bot.CONN,info=(ctx.guild.id, member.id))
            log = db_handler.get_log_channel(bot.CONN, ctx.guild.id)
            lg = bot.get_channel(log)
            try:
                await lg.send(f'{member.mention} authorised for the server: {str(ctx.guild.id)}')
            except HTTPException:
                await ctx.author.send("The bot has been set up accordingly, however I was unable to send a message to {} due to a connection issue.".format(lg))
            except discord.Forbidden:
                await ctx.author.send("The bot has been set up, however I do not have permissions to post in log channel:{}. Please let me read/write messages there.".format(lg))
            await ctx.respond(f'{member.name} authorised for guild: {str(ctx.guild.id)}', ephemeral=True)
        except Exception as e:
            # Catch exceptions
            print(e)
            await ctx.respond(f"Error occured whilst authorising. Check console for details. {e}", ephemeral=True)

#MASTER USER CHECK
@commands.cooldown(1, 5, commands.BucketType.user)
@commands.guild_only()
@bot.command(description="Command used to gain the trusted role for a single announcements")
async def setup_guild(ctx, 
            event_channel : Option(Union[discord.VoiceChannel, discord.StageChannel], "Voice used as a proxy for the 'manage events' permission."), 
            announcement_channel : Option(discord.TextChannel, "Channel to listen in on for announcements"),
            log_channel : Option(discord.TextChannel, "Channel for the bot to post logs in."),
            code : Option(int,'Enter the 6-digit code on your authentication application',required=True),
            ):
    """
    Takes a role, log, event and announcement channel and a verification code.
    Failure:
        Guild is already setup
        Code doesn't verify
    Success:
        Guild is not set up
        Verification is successful
    """
    guild_id = ctx.guild.id
    voice_id = event_channel.id
    channel_id = announcement_channel.id
    log_channel_id = log_channel.id

    if ctx.author.id != master_user:
        await ctx.respond("You do not have permission to use this command.", ephemeral=True)
        return

    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action.", ephemeral=True)
        return
    else:
        # Check if 2fA is correct
        if two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
            # Check if guild is already setup
            if db_handler.check_guild(bot.CONN, guild_id):
                await ctx.respond("The guild is already setup.", ephemeral=True)
                return
            try:
                if log_channel_id == channel_id:
                    await ctx.respond("Log channel and announcement channel cannot be the same", ephemeral=True)
                    return
            # Try insert the guild into the guilds database
                db_handler.insert_guild(bot.CONN, (guild_id,voice_id,channel_id, log_channel_id))
                ## Automatically authorise master member
                db_handler.authorise_member(bot.CONN,(guild_id, master_user))
                # Automatically insert channel
                db_handler.insert_channel(bot.CONN, (channel_id,guild_id))
                await ctx.respond("The guild has been added to the database.", ephemeral=True)
                lg = bot.get_channel(db_handler.get_log_channel(bot.CONN, guild_id))
                # LOG SEND
                try:
                    await lg.send(f"This server is now set up in {bot.user.name}'s database by {ctx.author.mention}.")
                except HTTPException:
                    await ctx.author.send("The bot has been set up accordingly, however I was unable to send a message to {} due to a connection issue.".format(lg))
                except discord.Forbidden:
                    await ctx.author.send("The bot has been set up, however I do not have permissions to post in log channel:{}. Please let me read/write messages there.".format(lg))
            except Exception as e:
                print(e)
                await ctx.respond("Unable to setup the guild.", ephemeral=True)
        else:
            # Incorrect 2fA code
            await ctx.respond("You have supplied an incorrect 2fA code.", ephemeral=True)

@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
@commands.bot_has_permissions(manage_roles = True, manage_webhooks = True, manage_guild = True, administrator = True)
@bot.command(description="Lockdown the server (requires 2fA).")
async def lockdown(ctx, code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    """
        Phase 1: Remove list of dangerous perms from ALL roles:
    Phase 2:
    Remove all webhooks (just in case)
    Phase 3:
    Each channel, go through each override, and set EVERY override to deny view
    this will make it so no one can manage channels to make it so people can see channels again
    without damanging the server way too much
    """
    guild_id = ctx.guild.id
    member_id = ctx.author.id
    guild_name = ctx.guild.name
    new_name = f'LOCKDOWN {guild_name}'
    try:
        await ctx.guild.edit(name=new_name)
    except Exception as e:
        print(e)
    # Check 1: Is guild registered
    # Is user authorised for this command?
    if not (db_handler.check_user(bot.CONN,int(member_id)) and db_handler.check_verified(bot.CONN,int(member_id)) == 1):
        await ctx.respond("You are not authorised to perform this command.", ephemeral=True)
        return
    if not db_handler.check_authorised(bot.CONN,info=(guild_id,member_id)):
        await ctx.respond("You are not authorised to perform this command.", ephemeral=True)
        return
    # Is verification code correct?
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect verification code given.", ephemeral=True)
        return
    if not db_handler.check_guild(bot.CONN, guild_id):
        await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
        return
    log_channel = two_factor_helper.get_log_channel(bot, ctx.guild)
    if log_channel is None:
        await ctx.respond("I do not have permissions to write to the log channel, please fix this.", ephemeral = True)
    roles = ctx.guild.roles
    audit_reason = f"Lockdown via {ctx.author} (ID: {ctx.author.id})"
    bot_user = ctx.guild.get_member(bot.user.id)
    bot_role = bot_user.top_role
    webhooks = [webhook for webhook in await ctx.guild.webhooks()]
    text_channels = ctx.guild.text_channels
    num_wh = len(webhooks)
    wh_status = role_status = override_status = 0
    # Go through the roles and adjust the permissions. Step 1.
    #
    """
    Go through the roles and update the permissions to have the dangerous permissions removed.
    It will ignore the bot's role and any roles that are above the bot's role.
    """
    await log_channel.send(f"Lockdown activated by {ctx.author} (ID: {ctx.author.id})")
    for role in roles:
        if role is not bot_role:
            if role < bot_role:
                perms = role.permissions
                new_perms = two_factor_helper.correct_permissions(perms)
                try:
                    # Replace permissions with new permissions
                    await role.edit(permissions=new_perms,
                                    reason=audit_reason)
                except HTTPException as e:
                    role_status += 1
                    await log_channel.send(f'HTTP Error encountered when attempting to overwrite {role}. Status code: {str(e.staus)}. Reason: {e.text}')
                    ctx.respond(f'HTTP Error encountered when attempting to overwrite {role}. Status code: {str(e.staus)}. Reason: {e.text}', ephemeral=True)
                except discord.Forbidden:
                    role_status += 1
                    await log_channel.send(f'I do not have permissions to overwrite {role}. Please ensure I have "Administrator" privileges and that I can manage roles.')
                    ctx.respond(f'I do not have permissions to overwrite {role}. Please ensure I have "Administrator" privileges and that I can manage roles.', ephemeral = True)
    """
    Go through and delete each webhook.
    """
    for webhook in webhooks:
        try:
            # Delete the webhook
            await webhook.delete(reason=audit_reason)
        except HTTPException as e:
            wh_status += 1
            await log_channel.send(f'HTTP Error encountered when attempting to delete {webhook}. Status code: {str(e.staus)}. Reason: {e.text}')
            ctx.respond(f'HTTP Error encountered when attempting to delete {webhook}. Status code: {str(e.staus)}. Reason: {e.text}', ephemeral=True)
        except discord.Forbidden:
            wh_status += 1
            await log_channel.send(f'I do not have permissions to delete {webhook}. Please ensure I have "Administrator" privileges and that I can manage roles.')
            ctx.respond(f'I do not have permissions to delete {webhook}. Please ensure I have "Administrator" privileges and that I can manage roles.', ephemeral = True)
    """
    Finally go through each text channel and change any overrides to view as False.
    """
    default_role = ctx.guild.default_role
    perms = {'view_channel': False, 'send_messages': False}
    new_overwrites = {default_role: discord.PermissionOverwrite(**perms)}
    for channel in text_channels:
        try:
            await channel.edit(overwrites=new_overwrites, reason=audit_reason)
        except HTTPException as e:
            override_status += 1
            await log_channel.send(f'HTTP Error encountered when attempting to edit {channel}. Status code: {str(e.staus)}. Reason: {e.text}')
            ctx.respond(f'HTTP Error encountered when attempting to edit {channel}. Status code: {str(e.staus)}. Reason: {e.text}', ephemeral=True)
        except discord.Forbidden:
            override_status += 1
            await log_channel.send(f'I do not have permissions to edit {channel}. Please ensure I have "Administrator" privileges and that I can manage roles.')
            ctx.respond(f'I do not have permissions to edit {channel}. Please ensure I have "Administrator" privileges and that I can manage roles.', ephemeral = True)
    await log_channel.send(f"Server is now locked down. Edited {len(roles)} roles ({role_status} errors), {str(num_wh)} webhooks ({wh_status} errors) and {len(text_channels)} channels ({override_status} errors)")
    await ctx.respond(f'Server is now locked down.Edited {len(roles)} roles ({role_status} errors), {str(num_wh)} webhooks ({wh_status} errors) and {len(text_channels)} channels ({override_status} errors)',
    ephemeral = True)

@tasks.loop(minutes=1)
async def delete_pngs():
    """
    Get rid of all QR codes every minute.
    """
    path_dir = f'./qr_codes/'
    for images in os.listdir(path_dir):
        if images.endswith(".png"):
            os.remove(os.path.join(path_dir, images))

@tasks.loop(minutes=1)
async def permissions_check():
    for guild in bot.guilds:
        if db_handler.check_guild(bot.CONN, guild.id):
            channels = [bot.get_channel(channel_id) for channel_id in db_handler.get_channels(bot.CONN, guild.id)]
            log_id = db_handler.get_log_channel(bot.CONN, guild.id)
            log_channel = bot.get_channel(log_id)
            for channel in channels:
                for permissions in channel.overwrites:
                    if type(permissions) == discord.member.Member:
                        try:
                            await channel.set_permissions(permissions, overwrite=None)
                            print(f"{permissions} had permissions. Removed.")
                        except discord.Forbidden:
                            await log_channel.send(f"Error occured when attempting to clear permissions from channel: {channel}. Please check permissions.")


#MASTER USER CHECK
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
@bot.command(description="Reset a user's 2fA")
async def reset(ctx, code : Option(int,'Enter the 6-digit code on your authentication application',required=True), member : Option(discord.Member,'The member to reset (or yourself).', required=False, default=None)):
    if ctx.author.id != master_user:
        await ctx.respond("You are not authorised to use this command.", ephemeral=True)
        return
    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action.", ephemeral=True)
        return
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect code given.",ephemeral=True)
        return
    if member is None:
        user_id = ctx.author.id
    else:
        user_id = member.id
    if db_handler.check_user(bot.CONN,user_id):
        db_handler.delete_user(bot.CONN, user_id)
        await ctx.respond(f"{user_id} deleted from the database.", ephemeral=True)
    else:
        await ctx.respond("User not found in the database.", ephemeral=True)

@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
@bot.command(description="Insert a channel into the database")
async def insert_channel(ctx, announcement_channel : Option(discord.TextChannel,'Text channel to add to the announcement'),code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    if ctx.author.id != master_user:
        await ctx.respond("You are not authorised to use this command.", ephemeral=True)
        return
    guild_id = ctx.guild.id
    if not db_handler.check_guild(bot.CONN, guild_id):
        await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
        return
    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action.", ephemeral=True)
        return
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect code given.", ephemeral=True)
        return
    log = db_handler.get_log_channel(bot.CONN, guild_id)
    lg = bot.get_channel(log)

    if announcement_channel.id not in [channel_id for channel_id in db_handler.get_channels(bot.CONN, ctx.guild.id)]:
        db_handler.insert_channel(bot.CONN, (announcement_channel.id, guild_id))
        await lg.send(f'Channel "{announcement_channel}" added to the database for guild by {ctx.author.mention}')
        await ctx.respond(f'Channel "{announcement_channel}" added to the database for guild', ephemeral=True)
    else:
        await ctx.respond(f'Channel "{announcement_channel}" is already in the database.', ephemeral=True)

@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
@bot.command(description="Delete a channel from the database")
async def delete_channel(ctx, 
    channel : Option(
    discord.TextChannel,
    'Channel to remove (Or channel ID if the channel no longer exists).'
    ),
    code : Option(int,'Enter the 6-digit code on your authentication application', required=True)):

    if ctx.author.id != master_user:
        await ctx.respond("You are not authorised to use this command.", ephemeral=True)
        return
    guild_id = ctx.guild.id
    if not db_handler.check_guild(bot.CONN, guild_id):
        await ctx.respond("The guild is not set up yet. Run /setup_guild.", ephemeral=True)
        return
    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action.", ephemeral=True)
        return
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect code given.", ephemeral=True)
        return
    
    log = db_handler.get_log_channel(bot.CONN, guild_id)
    lg = bot.get_channel(log)
    if channel.id in [channel_id for channel_id in db_handler.get_channels(bot.CONN, ctx.guild.id)]:
        db_handler.delete_channel(bot.CONN, channel.id)
        await ctx.respond(f'{channel} successfully removed from the database', ephemeral=True)
        await lg.send(f'{channel} was removed from the database by {ctx.author.mention}')
    else:
        await ctx.respond(f'{channel} was not found in the database.', ephemeral=True)

@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
@bot.command(description="Remove the guild from the database.")
async def remove_guild(ctx, code : Option(int,'Enter the 6-digit code on your authentication application',required=True)):
    if ctx.author.id != master_user:
        await ctx.respond("You are not authorised to use this command.", ephemeral=True)
        return
    if not db_handler.check_user(bot.CONN, ctx.author.id) or not db_handler.check_verified(bot.CONN, ctx.author.id) == 1:
        await ctx.respond("You do not have permission for this action.", ephemeral=True)
        return
    if not two_factor_helper.verify_code(bot.CONN, ctx.author.id, code):
        await ctx.respond("Incorrect code given.", ephemeral=True)
        return
    guild_id = ctx.guild.id
    if not db_handler.check_guild(bot.CONN, guild_id):
        await ctx.respond("The guild is not set up yet.", ephemeral=True)
        return
    else:
        log = db_handler.get_log_channel(bot.CONN, guild_id)
        lg = bot.get_channel(log)
        db_handler.delete_guild(bot.CONN, guild_id)
        await lg.send(f'{ctx.guild} was removed from the database by {ctx.author.mention}')
        await ctx.respond("Guild successfully reset.", ephemeral=True)

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.respond("This command has a 5 second cooldown.", ephemeral=True)
    if isinstance(error, commands.BotMissingPermissions):
        await ctx.respond("I am missing permissions. I require administrator for my commands to work.", ephemeral=True)

if __name__ == '__main__':
    bot.run(token)