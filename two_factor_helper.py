import pyotp
import pyqrcode
import discord
import sqlite3
import db_handler
import random


def setup_and_get_path(ctx, connection):
    """
    Takes the context and connection data and creates a random secret.
    Returns a qr code with the uri generated.
    Finally, adds the client to the database preliminarily
    """
    secret = pyotp.random_base32()
    filesys = pyotp.random_base32()
    user_for_path = f'{str(filesys)}'
    user_id = int(f'{ctx.user.id}')
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name="Discord Announcement", issuer_name="HQ Announcements")
    qr_code = pyqrcode.create(uri, error='L')
    png_path = f'./qr_codes/QR-{user_for_path}.png'
    qr_code.png(png_path, scale=6)
    db_handler.insert_user(conn=connection, info=(user_id, secret, 0))
    print("User added!")
    return png_path

def verify_code(connection, user_id: int, code : str):
    """
    Get client's secret, compares it to the current totp based on secret and verifies
    """
    code = "{0:06d}".format(code)
    secret = db_handler.get_secret(conn=connection, user_id=user_id)
    totp = pyotp.TOTP(secret)
    if totp.verify(code):
        return True
    else:
        return False

def get_log_channel(bot, guild):
    # Get log channel or None
    log_channel = None
    log_id = db_handler.get_log_channel(bot.CONN, guild.id)
    try:
        log_channel = bot.get_channel(log_id)
    finally:
        return log_channel

    

def correct_permissions(permission_list):
    """
    Take in a set of permissions, iterate through them and return the new permissions
    """
    permissions = [
        "kick_members",
        "ban_members",
        "administrator",
        "manage_channels",
        "manage_guild",
        "mention_everyone",
        "manage_nicknames",
        "manage_roles",
        "manage_webhooks",
        "manage_events",
        "view_channel"
        ]
    key_list = [k for (k,v) in permission_list]
    for permission in permissions:
        if permission in key_list:
            setattr(permission_list, permission, False)
    return permission_list
