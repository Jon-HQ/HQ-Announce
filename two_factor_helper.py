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
    user = f'{ctx.user.name}#{ctx.user.discriminator}'
    user_for_path = f'{ctx.user.name}{str(random.randint(0,9999))}'
    user_id = int(f'{ctx.user.id}')
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user, issuer_name="2fA Discord Bot")
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
    print(type(totp))
    if totp.verify(code):
        return True
    else:
        return False

