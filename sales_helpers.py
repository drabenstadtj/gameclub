import aiohttp
import db
import logging

logger = logging.getLogger("sales")

async def query_cheapshark_deal(deal_id):
    url = f"https://www.cheapshark.com/api/1.0/deals?id={deal_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def run_sale_check(bot, channel_id):
    channel = bot.get_channel(channel_id)
    if not channel:
        logger.warning("Sales channel not found.")
        return

    games = db.get_all_game_names()
    found_sales = []

    async with aiohttp.ClientSession() as session:
        for game_name in games:
            search_url = f"https://www.cheapshark.com/api/1.0/games?title={game_name}&limit=1"
            async with session.get(search_url) as resp:
                data = await resp.json()
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
                                    f"💸 **{title}** is on sale! **${sale}** (was ${retail}, {discount}% off)"
                                    f"\n👉 [Buy here](https://www.cheapshark.com/redirect?dealID={deal_id})"
                                )

    if found_sales:
        await channel.send("🛍️ **Today's Game Sales:**\n" + "\n".join(found_sales))
    else:
        await channel.send("🔍 No sales found today.")
