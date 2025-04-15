import discord
from discord.ext import commands, tasks
import sqlite3
import aiohttp
import re
import os
from dotenv import load_dotenv
import datetime
import logging
from discord import Embed, ButtonStyle, ui, Interaction

# --- Logging Setup ---
logging.basicConfig(level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO)
logger = logging.getLogger("gameclub")

# Load environment variables
load_dotenv()

# Debug flag
DEBUG_MODE = False

# IGDB / Twitch API credentials
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Channel IDs and Owner ID
SALES_CHANNEL_ID = 1361774693576868063
SUGGESTIONS_CHANNEL_ID = 1361756574963728738
ANNOUNCEMENT_CHANNEL_ID = 1361756466666803471
OWNER_ID = 174970986934960128

# DB 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../db/gameclub.db")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")


# SQLite setup
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS game_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT,
    game_name TEXT,
    genres TEXT,
    release_date TEXT,
    summary TEXT,
    url TEXT
)
''')
c.execute(
'''CREATE TABLE IF NOT EXISTS current_game (
    id INTEGER PRIMARY KEY,
    game_id INTEGER,
    FOREIGN KEY (game_id) REFERENCES game_picks(id)
);
''')
c.execute('''CREATE TABLE IF NOT EXISTS archived_games AS
SELECT * FROM game_picks WHERE 0;
''')
c.execute('''
CREATE TABLE IF NOT EXISTS picked_users (
    user TEXT PRIMARY KEY
)
''')
conn.commit()

# Global token cache
access_token = None

# --- Utility Functions ---
def is_in_suggestions_channel():
    return commands.check(lambda ctx: ctx.channel.id == SUGGESTIONS_CHANNEL_ID)

def is_owner():
    return commands.check(lambda ctx: ctx.author.id == OWNER_ID)

async def get_igdb_token():
    global access_token
    if access_token:
        return access_token
    url = "https://id.twitch.tv/oauth2/token"
    logger.debug("Requesting new IGDB token")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }) as resp:
            data = await resp.json()
            access_token = data["access_token"]
            logger.info("Received new IGDB token")
            return access_token

async def query_igdb(game_name):
    logger.debug(f"Querying IGDB for: {game_name}")
    token = await get_igdb_token()
    headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}
    query = f'''fields name, platforms.name, genres.name, summary, url, first_release_date; search "{game_name}"; limit 1;'''
    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.igdb.com/v4/games", headers=headers, data=query) as resp:
            result = await resp.json()
            logger.debug(f"IGDB response: {result}")
            return result

async def query_cheapshark_deal(deal_id):
    logger.debug(f"Querying CheapShark deal ID: {deal_id}")
    url = f"https://www.cheapshark.com/api/1.0/deals?id={deal_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            result = await resp.json()
            logger.debug(f"CheapShark deal response: {result}")
            return result

async def run_sale_check():
    logger.info("Running manual sale check")
    channel = bot.get_channel(SALES_CHANNEL_ID)
    if not channel:
        logger.warning("Sales channel not found")
        return

    c.execute("SELECT game_name FROM game_picks")
    games = c.fetchall()
    found_sales = []

    async with aiohttp.ClientSession() as session:
        for (game_name,) in games:
            logger.debug(f"Checking deals for: {game_name}")
            search_url = f"https://www.cheapshark.com/api/1.0/games?title={game_name}&limit=1"
            async with session.get(search_url) as resp:
                data = await resp.json()
                logger.debug(f"CheapShark search result: {data}")
                if data:
                    deal_id = data[0].get("cheapestDealID")
                    if deal_id:
                        deal_data = await query_cheapshark_deal(deal_id)
                        if "gameInfo" in deal_data:
                            info = deal_data["gameInfo"]
                            sale = float(info.get("salePrice", 0))
                            retail = float(info.get("retailPrice", 0))
                            title = info.get("name", game_name)
                            if sale < retail:
                                discount = round((1 - sale / retail) * 100)
                                found_sales.append(
                                    f"💸 **{title}** is on sale! **${sale}** (was ${retail}, {discount}% off)\n"
                                    f"👉 [Buy here](https://www.cheapshark.com/redirect?dealID={deal_id})"
                                )

    if found_sales:
        await channel.send("🛍️ **Today's Game Sales:**\n" + "\n".join(found_sales))
    else:
        await channel.send("🔍 No sales found for saved games today.")


# # --- Commands --- 
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Bot Help",
        description="List of commands:",
        color=discord.Color.teal()
    )

    embed.add_field(
        name="🎮 Game Suggestions",
        value=(
            "`!suggest <game name or IGDB URL>` – Suggest a game for the club.\n"
            "You'll get a preview to confirm or cancel before it's added."
        ),
        inline=False
    )

    embed.add_field(
        name="🗃️ Viewing Suggestions",
        value=(
            "`!listgames` – View all currently suggested games.\n"
            "`!listpastgames` – View games that have been picked in the past."
        ),
        inline=False
    )

    embed.add_field(
        name="🎲 Game Selection",
        value=(
            "`!pick_next` – (Owner only) Picks the next game from the queue using round-robin.\n"
            "Automatically announces it and updates the site."
        ),
        inline=False
    )

    embed.add_field(
        name="💸 Game Sales",
        value=(
            "`!sales` – Manually check for sales on currently suggested games.\n"
            "This also runs daily at noon automatically."
        ),
        inline=False
    )

    embed.set_footer(text="Made by Jack.")

    await ctx.send(embed=embed)


class SuggestionView(ui.View):
    def __init__(self, author_id, timeout=5):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.result = None
        self.interaction_message = None

    async def disable_buttons(self):
        for item in self.children:
            item.disabled = True
        if self.interaction_message:
            await self.interaction_message.edit(view=self)

    @ui.button(label="✅ Accept", style=ButtonStyle.success)
    async def accept_button(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You can't accept someone else's suggestion.", ephemeral=True)
            return
        self.result = "accept"
        await interaction.response.defer()
        await self.disable_buttons()

    @ui.button(label="❌ Cancel", style=ButtonStyle.danger)
    async def cancel_button(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You can't cancel someone else's suggestion.", ephemeral=True)
            return
        self.result = "cancel"
        await interaction.message.delete()
        await interaction.channel.send("❌ Suggestion cancelled.")


@bot.command(name="suggest")
# @is_in_suggestions_channel()
async def suggest_game(ctx, *, input_name: str):
    logger.info(f"{ctx.author} suggested: {input_name}")

    match = re.match(r'https?://www\.igdb\.com/games/([\w\-]+)', input_name.strip())
    query_type = "slug" if match else "search"
    query_value = match.group(1) if match else input_name.strip()

    await ctx.send(f"🔍 Looking up **{query_value}**...")

    try:
        token = await get_igdb_token()
        headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}

        if query_type == "slug":
            igdb_query = f'''
                fields name, genres.name, summary, url, first_release_date, cover.image_id;
                where slug = "{query_value}";
                limit 1;
            '''
        else:
            igdb_query = f'''
                fields name, genres.name, summary, url, first_release_date, cover.image_id;
                search "{query_value}";
                limit 1;
            '''

        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.igdb.com/v4/games", headers=headers, data=igdb_query) as resp:
                results = await resp.json()

        if not results:
            await ctx.send("❌ Game not found on IGDB.")
            return

        game = results[0]
        name = game.get("name", "Unknown")
        summary = game.get("summary") or "No summary provided."
        genres = ", ".join([g["name"] for g in game.get("genres", [])]) if "genres" in game else "N/A"

        release_date = game.get("first_release_date")
        if isinstance(release_date, int):
            release_date = datetime.datetime.utcfromtimestamp(release_date).strftime("%Y-%m-%d")
        else:
            release_date = "Unknown"

        url = game.get("url", "https://www.igdb.com")
        url = f"https://www.igdb.com{url}" if url.startswith("/") else url

        cover_url = None
        if "cover" in game and game["cover"].get("image_id"):
            cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{game['cover']['image_id']}.jpg"

        c.execute("SELECT id FROM game_picks WHERE game_name = ?", (name,))
        if c.fetchone():
            await ctx.send(f"⚠️ **{name}** has already been suggested.")
            return

        embed = discord.Embed(
            title=name,
            url=url,
            description=summary[:300] + ("..." if len(summary) > 300 else ""),
            color=discord.Color.blurple()
        )
        embed.add_field(name="Genres", value=genres, inline=False)
        embed.add_field(name="Release Date", value=release_date, inline=False)
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        view = SuggestionView(ctx.author.id)
        preview = await ctx.send(
            f"📝 {ctx.author.mention} suggested a game — confirm below:",
            embed=embed,
            view=view
        )
        view.interaction_message = preview

        await view.wait()

        if view.result == "cancel":
            return

        # If accepted or timeout
        c.execute('''
            INSERT INTO game_picks (user, game_name, genres, release_date, summary, url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ctx.author.name, name, genres, release_date, summary, url))
        conn.commit()

        await preview.edit(
            content=f"✅ **[{name}]({url})** successfully added by {ctx.author.mention}!",
            embed=embed,
            view=None
        )

    except Exception as e:
        logger.exception("Error in suggest_game")
        await ctx.send(f"⚠️ Error: {str(e)}")


        
@bot.command(name="pick_next")
@commands.is_owner()
async def pick_next_game(ctx):
    logger.info(f"{ctx.author} triggered pick_next_game")
    try:
        # Find the next game whose user hasn't had a pick yet
        c.execute("""
            SELECT id, user, game_name, genres, release_date, summary, url
            FROM game_picks
            WHERE user NOT IN (SELECT user FROM picked_users)
            ORDER BY id
            LIMIT 1
        """)
        row = c.fetchone()

        # If all users have had a pick, reset and try again
        if not row:
            c.execute("DELETE FROM picked_users")
            conn.commit()
            c.execute("""
                SELECT id, user, game_name, genres, release_date, summary, url
                FROM game_picks
                ORDER BY id
                LIMIT 1
            """)
            row = c.fetchone()

        if not row:
            await ctx.send("No games left to pick from.")
            return

        game_id, user, name, genres, release_date, summary, url = row

        # Archive the selected game BEFORE deleting it
        c.execute('''
            INSERT INTO archived_games (id, user, game_name, genres, release_date, summary, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, user, name, genres, release_date, summary, url))

        # Set it as the current game
        c.execute("DELETE FROM current_game")
        c.execute("INSERT INTO current_game (game_id) VALUES (?)", (game_id,))

        # Mark user as picked
        c.execute("INSERT OR IGNORE INTO picked_users (user) VALUES (?)", (user,))

        # Remove from suggestions
        c.execute("DELETE FROM game_picks WHERE id = ?", (game_id,))
        conn.commit()

        # IGDB + CheapShark queries
        token = await get_igdb_token()
        headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}
        search_query = f'fields id,name; search "{name}"; limit 1;'

        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.igdb.com/v4/games", headers=headers, data=search_query) as search_resp:
                search_data = await search_resp.json()
                game_igdb_id = search_data[0]["id"] if search_data else None

            estimated_hours = "Unknown"
            if game_igdb_id:
                ttb_query = f"fields normally; where game_id = {game_igdb_id};"
                async with session.post("https://api.igdb.com/v4/game_time_to_beats", headers=headers, data=ttb_query) as ttb_resp:
                    ttb_data = await ttb_resp.json()
                    if ttb_data and "normally" in ttb_data[0]:
                        normally_seconds = ttb_data[0]["normally"]
                        estimated_hours = f"~{round(normally_seconds / 3600)} hours"

            price_str = "Unknown — Check link"
            price_api = f"https://www.cheapshark.com/api/1.0/games?title={name}&limit=1"
            async with session.get(price_api) as price_resp:
                price_data = await price_resp.json()
                if price_data:
                    game_price = price_data[0].get("cheapest")
                    deal_id = price_data[0].get("cheapestDealID")
                    if game_price and deal_id:
                        price_str = f"[${game_price} here](https://www.cheapshark.com/redirect?dealID={deal_id})"

        today = datetime.date.today()
        discussion_date = today + datetime.timedelta(days=7)
        message = (
            f"🎮 **Game Pick:**\n"
            f"**Selected By:** {user}\n"
            f"**Game:** [{name}]({url})\n"
            f"**Price:** {price_str}\n"
            f"**Estimated Time to Finish:** {estimated_hours}\n\n"
            f"**Play Period:** {today.strftime('%B %d')} → {discussion_date.strftime('%B %d')}\n"
            f"We'll meet for discussion on **{discussion_date.strftime('%B %d')}** — time TBA."
        )

        announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if announcement_channel:
            await announcement_channel.send(message)
        else:
            logger.warning("Announcement channel not found.")
            await ctx.send(message)

    except Exception as e:
        logger.exception("Error in pick_next_game")
        await ctx.send(f"⚠️ Error: {str(e)}")

# --- Sales Task ---
@tasks.loop(minutes=1)
async def daily_sale_check():
    now = datetime.datetime.now()
    if DEBUG_MODE or (now.hour == 12 and now.minute == 0):
        await run_sale_check()

@bot.command(name="listgames")
async def list_games(ctx):
    logger.info(f"{ctx.author} requested list of suggested games")
    try:
        c.execute("SELECT user, game_name FROM game_picks ORDER BY id")
        rows = c.fetchall()
        if not rows:
            await ctx.send("📭 No games have been suggested yet.")
            return

        msg_lines = [f"**{user}**: {game}" for user, game in rows]
        chunks = [msg_lines[i:i + 20] for i in range(0, len(msg_lines), 20)]

        for chunk in chunks:
            await ctx.send("\n".join(chunk))
    except Exception as e:
        logger.exception("Error in list_games")
        await ctx.send(f"⚠️ Error retrieving game list: {str(e)}")
        
        
@bot.command(name="listpastgames")
async def list_archived_games(ctx):
    logger.info(f"{ctx.author} requested list of archived games")
    try:
        c.execute("SELECT user, game_name FROM archived_games ORDER BY id DESC")
        rows = c.fetchall()

        if not rows:
            await ctx.send("📦 No archived games yet.")
            return

        msg_lines = [f"**{user}**: {game}" for user, game in rows]
        chunks = [msg_lines[i:i + 20] for i in range(0, len(msg_lines), 20)]

        for chunk in chunks:
            await ctx.send("\n".join(chunk))
    except Exception as e:
        logger.exception("Error in list_archived_games")
        await ctx.send(f"⚠️ Error retrieving archived games: {str(e)}")


@bot.command(name="sales")
async def checksales(ctx):
    logger.info(f"{ctx.author} manually triggered sales check")
    await run_sale_check()


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    if not daily_sale_check.is_running():
        daily_sale_check.start()

bot.run(DISCORD_TOKEN)
