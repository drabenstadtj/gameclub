import discord
from discord.ext import commands
from dotenv import load_dotenv
import config
import db
import igdb_helpers
import sales_helpers
import re
from datetime import datetime, timezone
import random

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)
bot.remove_command("help")

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    db.init_db()

# --- Commands ---

@bot.command(name="help")
async def help_command(ctx):
    """Show available commands."""
    embed = discord.Embed(
        title="Commands",
        description="",
        color=discord.Color.teal()
    )
    embed.add_field(
        name="🎮 Game Suggestions",
        value=(
            "`!suggest <name or IGDB link>` - Suggest a game\n"
            "`!unsuggest` - Remove your suggestion(s)"
        ),
        inline=False
    )
    embed.add_field(
        name="📋 Lists",
        value=(
            "`!listgames` - View all suggested games\n"
            "`!listsuggestions` - View your suggestions\n"
            "`!listorder` - See the picking order"
        ),
        inline=False
    )
    embed.add_field(
        name="🎯 Game Picking",
        value=(
            "`!pick` - Pick a random suggestion (your turn only)\n"
        ),
        inline=False
    )
    embed.add_field(
        name="💸 Sales",    
        value="`!sales` - Check current sales",
        inline=False
    )
    embed.set_footer(text="Made by Jack")

    await ctx.send(embed=embed)

@bot.command(name="suggest")
async def suggest(ctx, *, game_or_link: str):
    """Suggest a game by name or IGDB link."""
    match = re.match(r'https?://www\.igdb\.com/games/([\w\-]+)', game_or_link.strip())
    query_type = "slug" if match else "search"
    query_value = match.group(1) if match else game_or_link.strip()

    await ctx.send(f"🔍 Searching for **{query_value}**...")

    try:
        results = await fetch_igdb_results(query_value)

        if not results:
            class ConfirmAdd(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.value = None

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("❌ You can't respond for someone else.", ephemeral=True)
                        return
                    db.add_suggestion(ctx.author.name, query_value, "Unknown", "Unknown", "No summary available.", "https://www.igdb.com")
                    await interaction.response.edit_message(content=f"✅ **{query_value}** has been added to your suggestions (manual entry).", view=None)
                    self.value = True

                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("❌ You can't respond for someone else.", ephemeral=True)
                        return
                    await interaction.response.edit_message(content="❌ Cancelled manual addition.", view=None)
                    self.value = False

            view = ConfirmAdd()
            await ctx.send(
                f"❓ Couldn't find **{query_value}** on IGDB. Would you like to add it manually?",
                view=view
            )
            return

        else:
            # Direct link
            game = results[0]
            name = game.get("name", "Unknown")
            summary = game.get("summary", "No summary available.")
            genres = ", ".join(g["name"] for g in game.get("genres", [])) if "genres" in game else "Unknown"
            release_date = game.get("first_release_date")
            url = game.get("url", "https://www.igdb.com")

            if release_date and isinstance(release_date, int):
                release_date = datetime.fromtimestamp(release_date, tz=timezone.utc).strftime('%Y-%m-%d')
            else:
                release_date = "Unknown"

            db.add_suggestion(ctx.author.name, name, genres, release_date, summary, url)
            await ctx.send(f"✅ **{name}** has been added to your suggestions!")

    except ValueError as ve:
        await ctx.send(f"⚠️ {ve}")
    except Exception as e:
        await ctx.send(f"⚠️ Error suggesting game: {str(e)}")


async def fetch_igdb_results(query_value, limit=10):
    return await igdb_helpers.search_igdb(query_value, limit) or []

def build_game_options(results):
    used_labels = set()
    options = []

    for game in results[:5]:
        name = game.get("name", "Unknown")
        release_date = game.get("first_release_date")
        year = datetime.fromtimestamp(release_date, tz=timezone.utc).year if release_date else "Unknown"

        label = name
        if label in used_labels:
            label += f" ({year})"
        used_labels.add(label)

        options.append(discord.SelectOption(label=label, description=f"Release: {year}"))

    return options

async def handle_game_selection(interaction, selected_name, results, ctx):
    selected_game = next((
        g for g in results
        if g.get("name") == selected_name
        or (
            g.get("name") and selected_name == f"{g.get('name')} ({datetime.fromtimestamp(g['first_release_date'], tz=timezone.utc).year})"
            if g.get("first_release_date") else False
        )
    ), None)
    if not selected_game:
        await interaction.response.send_message("⚠️ Game not found in results.", ephemeral=True)
        return

    genres = ", ".join(g["name"] for g in selected_game.get("genres", [])) if "genres" in selected_game else "Unknown"
    release_date = selected_game.get("first_release_date")
    url = selected_game.get("url", "https://www.igdb.com")

    if release_date and isinstance(release_date, int):
        release_date = datetime.fromtimestamp(release_date, tz=timezone.utc).strftime('%Y-%m-%d')
    else:
        release_date = "Unknown"

    try:
        db.add_suggestion(ctx.author.name, selected_game["name"], genres, release_date, selected_game.get("summary", "No summary"), url)
        await interaction.response.edit_message(content=f"✅ **{selected_game['name']}** has been added to your suggestions!", view=None)
    except ValueError as ve:
        await interaction.response.edit_message(content=f"⚠️ {ve}", view=None)
    except Exception as e:
        await interaction.response.edit_message(content=f"⚠️ Error: {str(e)}", view=None)

@bot.command(name="unsuggest")
async def unsuggest(ctx):
    """Remove one or more of your suggestions."""
    suggestions = db.list_user_active_suggestions(ctx.author.name)

    if not suggestions:
        await ctx.send("📭 You have no active suggestions to remove.")
        return

    # Build the options
    options = [discord.SelectOption(label=game, value=game) for game in suggestions]

    class UnsuggestSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Select the games you want to unsuggest",
                min_values=1,
                max_values=len(options),
                options=options
            )

        async def callback(self, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("❌ You can't unsuggest for someone else.", ephemeral=True)
                return

            removed_games = []
            for game_name in self.values:
                try:
                    db.remove_suggestion(ctx.author.name, game_name)
                    removed_games.append(game_name)
                except Exception as e:
                    logger.exception(f"Failed to remove {game_name}: {e}")

            if removed_games:
                await interaction.response.edit_message(
                    content=f"🗑️ Removed your suggestions:\n" + "\n".join(f"- {game}" for game in removed_games),
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="⚠️ No games were removed.",
                    view=None
                )

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("❌ You can't cancel someone else's action.", ephemeral=True)
                return
            await interaction.response.edit_message(content="❌ Cancelled unsuggesting.", view=None)

    view = discord.ui.View()
    view.add_item(UnsuggestSelect())
    view.add_item(CancelButton())

    await ctx.send(f"📝 Select the games you want to **unsuggest**, {ctx.author.mention}:", view=view)


@bot.command(name="listgames")
async def listgames(ctx):
    """List all games suggested by anyone."""
    suggestions = db.get_all_suggestions_with_users()  # NEW helper function you need

    if not suggestions:
        await ctx.send("📭 No games have been suggested yet.")
        return

    msg_lines = []
    for username, game_name, url in suggestions:
        link = url if url else "https://www.igdb.com"  # fallback if url is missing
        msg_lines.append(f"- **{username}** suggested: [{game_name}]({link})")

    await ctx.send("🎮 **All Suggested Games:**\n" + "\n".join(msg_lines))

@bot.command(name="listsuggestions")
async def listsuggestions(ctx):
    """List all your suggestions."""
    games = db.list_user_suggestions(ctx.author.name)
    if not games:
        await ctx.send("📭 You haven't suggested any games yet.")
        return

    msg = "\n".join(f"- {game}" for game in games)
    await ctx.send(f"📝 **Your Suggestions:**\n{msg}")

@bot.command(name="sales")
async def sales(ctx):
    """Check current sales manually."""
    await sales_helpers.run_sale_check(bot, config.SALES_CHANNEL_ID)
    
@bot.command(name="pick")
async def pick(ctx):
    """Randomly pick one of your suggestions when it's your turn."""
    next_user = db.get_next_user_to_pick()

    if ctx.author.name != next_user:
        await ctx.send(f"❌ It's not your turn! It is currently **{next_user}'s** turn.")
        return

    # Get this user's active suggestions
    suggestions = db.list_user_active_suggestions(ctx.author.name)

    if not suggestions:
        await ctx.send("⚠️ You have no available suggestions to pick from!")
        return

    selected_game = random.choice(suggestions)

    # Mark the selected game as picked
    db.pick_game_for_user(ctx.author.name, selected_game)

    await ctx.send(f"🎯 **{ctx.author.name}** has picked **{selected_game}**!")

    # Now fetch full game info
    game_info = db.get_game_info(selected_game)

    if not game_info:
        await ctx.send("⚠️ Could not fetch game info for announcement.")
        return

    # Format announcement
    name, genres, release_date, summary, url = game_info
    link = url if url else "https://www.igdb.com"

    if release_date and release_date != "Unknown":
        try:
            parsed_date = datetime.strptime(release_date, "%Y-%m-%d")
            formatted_date = parsed_date.strftime("%B %d, %Y")  # Example: April 27, 2025
        except Exception:
            formatted_date = release_date  # fallback if somehow broken
    else:
        formatted_date = "Unknown"

    announcement = (
        f"🎮 **New Game Picked!**\n"
        f"**Selected By:** {ctx.author.name}\n"
        f"**Game:** [{name}]({link})\n"
        f"**Genres:** {genres or 'Unknown'}\n"
        f"**Release Date:** {formatted_date or 'Unknown'}\n"
        f"**Summary:** {summary[:300]}{'...' if summary and len(summary) > 300 else ''}"
    )

    announcement_channel = bot.get_channel(config.ANNOUNCEMENT_CHANNEL_ID)
    if announcement_channel:
        await announcement_channel.send(announcement)
    else:
        await ctx.send("⚠️ Announcement channel not found.")

@bot.command(name="setuporder")
@commands.is_owner()
async def setuporder(ctx):
    """Owner-only: Randomly set up initial user order based on current server members."""
    guild = ctx.guild
    members = [member for member in guild.members if not member.bot]

    if not members:
        await ctx.send("❌ No members found to setup.")
        return

    # Randomize the member list
    random.shuffle(members)

    for index, member in enumerate(members, start=1):
        db.add_user(member.name)

    await ctx.send(f"✅ Randomized setup complete. {len(members)} users added to the game club!")
    
@bot.command(name="resetorder")
@commands.is_owner()
async def resetorder(ctx):
    """Owner-only: Reset the picking order."""
    db.clear_user_order()
    await ctx.send("🧹 Picking order has been reset. Run `!setuporder` to create a new one.")
    
@bot.command(name="listorder")
async def listorder(ctx):
    """Show the current picking order, highlighting who is next."""
    order = db.get_user_order()

    if not order:
        await ctx.send("Picking order has not been configured yet.")
        return

    next_user = db.get_next_user_to_pick()

    msg_lines = []
    for i, username in enumerate(order):
        if username == next_user:
            msg_lines.append(f"{i+1}. {username} (Next)")
        else:
            msg_lines.append(f"{i+1}. {username}")

    message = (
        "🔢 **Picking Order:**\n"
        + "\n".join(msg_lines)
    )

    await ctx.send(message)


# --- Run the bot ---

if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)
