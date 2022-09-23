import sqlite3
from sqlite3 import Error


def create_connection(db_file):
    """
    create a database connection to the SQLite database
    specified by db_file
    :param db_file: database file url
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(e)
    return conn


def create_table(conn, create_table_sql):
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return:
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except Error as e:
        print(e)


def startup_db():
    database = r"database.db"

    sql_create_user_table = """ CREATE TABLE IF NOT EXISTS users (
                                    user_id integer PRIMARY KEY,
                                    secret text NOT NULL,
                                    verified BOOLEAN NOT NULL CHECK (verified IN (0, 1))
                                    ); """
    sql_create_guild_table = """ CREATE TABLE IF NOT EXISTS guilds (
                                    guild_id integer PRIMARY KEY,
                                    event_channel integer,
                                    announcement_channel integer,
                                    log_channel integer,
                                    webhook_protection BOOLEAN NOT NULL CHECK (webhook_protection IN (0, 1)),
                                    verified_bots BOOLEAN NOT NULL CHECK (verified_bots IN (0, 1))
                                    ); """
    sql_create_trusted_table = """ CREATE TABLE IF NOT EXISTS trusted_members (
                                    trusted_id integer PRIMARY KEY,
                                    guild_id integer,
                                    member_id integer,
                                    foreign key (guild_id) references guilds(guild_id) ON DELETE CASCADE,
                                    foreign key (member_id) references users (user_id) ON DELETE CASCADE
                                    );"""
    sql_create_announcement_channel_table = """ CREATE TABLE IF NOT EXISTS channel_table (
                                    channel_id integer PRIMARY KEY,
                                    guild_id integer,
                                    foreign key (guild_id) references guilds(guild_id) ON DELETE CASCADE
                                    );"""
    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create projects table
        print()
        create_table(conn, sql_create_user_table)
        create_table(conn, sql_create_guild_table)
        create_table(conn, sql_create_trusted_table)
        create_table(conn, sql_create_announcement_channel_table)
        return conn

    else:
        print("Error! cannot create the database connection.")
        return None


# create a database connection
def insert_user(conn, info):
    """
    Create a new user
    :param conn: database connection
    :param info: (user_id, secret, verified = 0/1)
    :return:
    """

    sql = ''' 
    INSERT INTO users(user_id, secret, verified) VALUES(?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, info)
    conn.commit()
    print(f'{info} added to database.')

def get_channels(conn, guild_id):
    """
    Return the channels
    :param conn: database connection
    :param guild_id: guild ID
    :return:
    """
    sql = '''SELECT channel_id from channel_table where guild_id = ?'''
    cur = conn.cursor()
    cur.execute(sql, (guild_id,))
    channels = [channel[0] for channel in cur.fetchall()]
    return channels

def get_all_channels():
    """
    Return the channels
    :param conn: database connection
    :param guild_id: guild ID
    :return:
    """
    database = r"database.db"
    conn = create_connection(database)
    sql = '''SELECT channel_id from channel_table'''
    cur = conn.cursor()
    cur.execute(sql)
    channels = [channel[0] for channel in cur.fetchall()]
    print(channels)
    return channels

def insert_channel(conn, info):
    """
    Create a new announcement_channel
    :param conn: database connection
    :param info: (channel_id, guild_id)
    :return:
    """

    sql = '''INSERT INTO channel_table(channel_id, guild_id) VALUES(?,?) '''
    cur = conn.cursor()
    cur.execute(sql, info)
    conn.commit()
    print(f'Channel {info[0]} added to database.')

def delete_channel(conn, channel_id : int):
    """
    Create a new announcement_channel
    :param conn: database connection
    :param info: (channel_id)
    :return:
    """

    sql = '''DELETE FROM channel_table WHERE channel_id = ?'''
    cur = conn.cursor()
    cur.execute(sql, (channel_id,))
    conn.commit()
    print(f'Channel {channel_id} deleted from database.')


def delete_user(conn, user_id):
    # Test function
    sql = 'DELETE FROM users WHERE user_id=?'
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    conn.commit()

def delete_guild(conn, guild_id):
    """
    Create a new guild entry
    :param conn: database connection
    :param info: (guild_id, event_chanel, announcement_channel)
    :return:
    """

    delete_guild_sql = ''' DELETE FROM guilds where guild_id = ?;'''
    delete_trusted_users = '''DELETE FROM trusted_members where guild_id = ?'''
    delete_channels_users = '''DELETE FROM channel_table where guild_id = ?'''
    cur = conn.cursor()
    cur.execute(delete_guild_sql, (guild_id,))
    cur.execute(delete_trusted_users, (guild_id,))
    cur.execute(delete_channels_users, (guild_id,))
    conn.commit()
    print(f'{guild_id} removed from database.')


def check_user(conn, user_id : int):
    # If user is in DB, return true
    sql = 'SELECT EXISTS (SELECT 1 FROM users where user_id = ?)'
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    if cur.fetchone()[0]:
        return True
    else:
        return False

def check_guild(conn, guild_id):
    # If user is in DB, return true
    sql = 'SELECT EXISTS (SELECT 1 FROM guilds where guild_id = ?)'
    cur = conn.cursor()
    cur.execute(sql, (guild_id,))
    if cur.fetchone()[0]:
        return True
    else:
        return False

def insert_guild(conn, info):
    """
    Create a new guild entry
    :param conn: database connection
    :param info: (guild_id, event_chanel, announcement_channel, webhook protection, verified_bots) 
    :return:
    """

    sql = '''
    INSERT INTO guilds(guild_id, event_channel, announcement_channel, log_channel,webhook_protection, verified_bots) VALUES(?,?,?,?,0,0) '''
    cur = conn.cursor()
    cur.execute(sql, info)
    conn.commit()
    print(f'{info} added to database.')

def check_webhook(conn, guild_id : int):
    sql = 'SELECT webhook_protection FROM guilds where guild_id = ?'
    cur = conn.cursor()
    cur.execute(sql, (guild_id,))
    result = cur.fetchone()[0]
    return result

def check_verified_bots(conn, guild_id : int):
    sql = 'SELECT verified_bots FROM guilds where guild_id = ?'
    cur = conn.cursor()
    cur.execute(sql, (guild_id,))
    result = cur.fetchone()[0]
    return result

def set_webhook_parameters(conn, info):
    """
    :param conn: database connection
    :param info: (webhook_protection, verified_bots, guild_id)
    """
    sql = ''' UPDATE guilds
              SET 
                webhook_protection = ?,
                verified_bots = ?
              WHERE guild_id = ?'''
    cur = conn.cursor()
    cur.execute(sql, info)
    conn.commit()

def authorise_member(conn, info):
    """
    Create a new guild entry
    :param conn: database connection
    :param info: (guild_id, user_id)
    :return:
    """

    sql = '''
    INSERT INTO trusted_members(guild_id, member_id) VALUES(?,?) '''
    cur = conn.cursor()
    cur.execute(sql, info)
    conn.commit()
    print(f'{info} added to database.')



def check_authorised(conn,info):
    sql = 'SELECT EXISTS (SELECT 1 FROM trusted_members where guild_id = ? AND member_id = ?)'
    cur = conn.cursor()
    cur.execute(sql,info)
    if cur.fetchone()[0]:
        return True
    else:
        return False

def get_channel(conn, guild_id):
    sql = 'SELECT announcement_channel FROM guilds where guild_id = ?'
    cur = conn.cursor()
    cur.execute(sql,(guild_id,))
    channel_id = cur.fetchone()
    return channel_id[0] if  len(channel_id) > 0 else None


def get_event_channel(conn, guild_id):
    sql = 'SELECT event_channel FROM guilds where guild_id = ?'
    cur = conn.cursor()
    cur.execute(sql,(guild_id,))
    channel_id = cur.fetchone()
    return channel_id[0] if  len(channel_id) > 0 else None


def get_log_channel(conn, guild_id):
    sql = 'SELECT log_channel FROM guilds where guild_id = ?'
    cur = conn.cursor()
    cur.execute(sql,(guild_id,))
    channel_id = cur.fetchone()
    return channel_id[0] if  len(channel_id) > 0 else None



def check_verified(conn, user_id : int):
    sql = 'SELECT verified FROM users where user_id = ?'
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    result = cur.fetchone()[0]
    return result

def get_secret(conn, user_id : int):
    result = 3
    sql = 'SELECT secret FROM users where user_id = ?'
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    result = cur.fetchone()[0]
    return result

def verify(conn, user_id : int):
    sql = ''' UPDATE users
              SET verified = 1
              WHERE user_id = ?'''
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    conn.commit()

    