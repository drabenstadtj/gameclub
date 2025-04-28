import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
access_token = None

async def get_igdb_token():
    global access_token
    if access_token:
        return access_token

    url = "https://id.twitch.tv/oauth2/token"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }) as resp:
            data = await resp.json()
            access_token = data["access_token"]
            return access_token

async def search_igdb(game_name, num_results):
    token = await get_igdb_token()
    headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}
    query = f'fields name, genres.name, summary, url, first_release_date; search "{game_name}"; limit {num_results};'

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.igdb.com/v4/games", headers=headers, data=query) as resp:
            return await resp.json()
