import discord
from discord.ext import tasks, commands
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import aiohttp
import random

# Load environment variables
load_dotenv()

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration for multiple collections
COLLECTIONS = {
    "dopedoges": {
        "api_url": "https://api.doggy.market/listings/nfts/dopedoges/orders",
        "channel_id": yourchannelidhere,
        "color": 0xFF4500,  # Brighter orange for vibrancy
        "hashtag": "#DopeDogeVibes",
        "last_sale_timestamp_file": "last_dope_sale_timestamp.txt"
    },
    # "minidoges": {
    #     "api_url": "https://api.doggy.market/listings/nfts/minidoges/orders",
    #     "channel_id": yourschannelidhere,  # Update this to the correct Mini Doges channel ID
    #     "color": 0x00CED1,  # Brighter cyan for vibrancy
    #     "hashtag": "#MiniDogeMagic",
    #     "last_sale_timestamp_file": "last_mini_sale_timestamp.txt"
    # }
}

def load_last_sale_timestamp(collection):
    file_path = COLLECTIONS[collection]["last_sale_timestamp_file"]
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            timestamp_str = f.read().strip()
            if timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    return datetime.min.replace(tzinfo=timezone.utc)

def save_last_sale_timestamp(collection, timestamp):
    with open(COLLECTIONS[collection]["last_sale_timestamp_file"], "w") as f:
        f.write(timestamp.isoformat())

async def fetch_sales(collection):
    api_url = COLLECTIONS[collection]["api_url"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}?type=sell&offset=0&limit=20", headers={}) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Fetched {collection} sales data successfully")
                    return data.get("data", [])
                else:
                    print(f"Error fetching {collection} sales: HTTP {response.status}, Response: {await response.text()}")
                    return []
    except Exception as e:
        print(f"Error fetching {collection} sales: {e}")
        return []

def create_sale_message(collection):
    # List of varied emojis for sale announcements
    emojis = ["🔥", "🚀", "💥", "🌟", "⚡"]
    emoji = random.choice(emojis)
    return f"🐶 **{collection.upper()} ALERT! Fresh Sale on Doginals! {emoji}**"

async def post_sale_to_discord(channel, collection, sale):
    raw_price = sale.get("price", 0)
    price_doge = raw_price / 100000000
    sale_id = sale.get("inscriptionId", "")
    sale_timestamp_str = sale.get("date", "1970-01-01T00:00:00.000Z")
    sale_timestamp = datetime.fromisoformat(sale_timestamp_str.replace("Z", "+00:00"))

    # Shorten addresses for privacy (first 4 + last 4 chars)
    seller = sale.get("sellerAddress", "Myst")[:4] + "..." + sale.get("sellerAddress", "Myst")[-4:]
    buyer = sale.get("buyerAddress", "NewP")[:4] + "..." + sale.get("buyerAddress", "NewP")[-4:]

    message = create_sale_message(collection)

    # Construct URLs
    image_url = f"https://cdn.doggy.market/content/{sale_id}"
    sale_url = f"https://doggy.market/inscription/{sale_id}"

    # Create embed
    embed = discord.Embed(
        title=f"{collection.capitalize()} #{sale.get('itemId', '???')}",
        url=sale_url,
        description=message,
        color=COLLECTIONS[collection]["color"]
    )
    embed.add_field(name="💰 Sold for", value=f"{price_doge:.2f} Doge", inline=True)
    embed.add_field(name="Inscription Number", value=str(sale.get("inscriptionNumber", "N/A")), inline=True)
    embed.add_field(name="Buyer", value=buyer, inline=True)  # Same row
    embed.add_field(name="Seller", value=seller, inline=True)  # Same row

    embed.set_thumbnail(url=image_url)
    embed.set_footer(text=f"Sold on {sale_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')} | {COLLECTIONS[collection]['hashtag']} ✅")

    await channel.send(embed=embed)
    print(f"Posted sale for {collection}: itemId={sale.get('itemId')}, price={price_doge:.2f} DOGE")
    return sale_timestamp

@tasks.loop(seconds=60)
async def check_sales():
    for collection in COLLECTIONS:
        channel = bot.get_channel(COLLECTIONS[collection]["channel_id"])
        if not channel:
            print(f"Error: Channel with ID {COLLECTIONS[collection]['channel_id']} not found or bot lacks permission for {collection}.")
            continue

        last_sale_timestamp = load_last_sale_timestamp(collection)
        print(f"Current time: {datetime.now(timezone.utc)}, Last sale timestamp for {collection}: {last_sale_timestamp}")

        sales = await fetch_sales(collection)
        sales = sorted(sales, key=lambda x: datetime.fromisoformat(x.get("date", "1970-01-01T00:00:00.000Z").replace("Z", "+00:00")))

        new_last_sale_timestamp = last_sale_timestamp
        current_time = datetime.now(timezone.utc)

        # Count skipped sales for summary
        skipped_older = 0
        skipped_processed = 0

        for sale in sales:
            if sale.get("status") != "bought" or not sale.get("buyerAddress"):
                continue

            sale_timestamp_str = sale.get("date", "1970-01-01T00:00:00.000Z")
            sale_timestamp = datetime.fromisoformat(sale_timestamp_str.replace("Z", "+00:00"))

            if current_time - sale_timestamp > timedelta(hours=24):
                skipped_older += 1
                continue

            if sale_timestamp <= last_sale_timestamp:
                skipped_processed += 1
                continue

            new_sale_timestamp = await post_sale_to_discord(channel, collection, sale)
            if new_sale_timestamp > new_last_sale_timestamp:
                new_last_sale_timestamp = new_sale_timestamp

        # Log summary of skipped sales
        if skipped_older > 0:
            print(f"Skipped {skipped_older} sales for {collection}: older than 24 hours")
        if skipped_processed > 0:
            print(f"Skipped {skipped_processed} sales for {collection}: already processed")

        if new_last_sale_timestamp != last_sale_timestamp:
            save_last_sale_timestamp(collection, new_last_sale_timestamp)
            print(f"Updated last_sale_timestamp for {collection} to: {new_last_sale_timestamp}")
        else:
            print(f"No new sales to process for {collection}.")

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    check_sales.start()

@bot.command()
async def post_last_sale(ctx, collection: str = "dopedoges"):
    if collection not in COLLECTIONS:
        await ctx.send("Invalid collection. Use 'dopedoges' or 'minidoges'.")
        return

    channel = bot.get_channel(COLLECTIONS[collection]["channel_id"])
    if not channel:
        await ctx.send(f"Error: Channel not found or bot lacks permission for {collection}.")
        return

    sales = await fetch_sales(collection)
    if not sales:
        await ctx.send(f"No sales data available to post for {collection}.")
        return

    sales = sorted(sales, key=lambda x: datetime.fromisoformat(x.get("date", "1970-01-01T00:00:00.000Z").replace("Z", "+00:00")), reverse=True)
    last_sale = sales[0]
    await post_sale_to_discord(channel, collection, last_sale)
    await ctx.send(f"Last sale for {collection} posted to the sales channel!")

@bot.command()
async def test_sale(ctx, collection: str = "dopedoges"):
    if collection not in COLLECTIONS:
        await ctx.send("Invalid collection. Use 'dopedoges' or 'minidoges'.")
        return

    channel = bot.get_channel(COLLECTIONS[collection]["channel_id"])
    if not channel:
        await ctx.send(f"Error: Channel not found or bot lacks permission for {collection}.")
        return

    test_sale = {
        "inscriptionId": f"test_image_id_{collection}",
        "status": "bought",
        "price": 70000000000 if collection == "dopedoges" else 50000000000,
        "sellerAddress": "TESTSELLER123456789",
        "buyerAddress": "TESTBUYER456789123",
        "itemId": "999" if collection == "dopedoges" else "888",
        "date": "2025-03-11T21:00:00.000Z",
        "inscriptionNumber": 12345 if collection == "dopedoges" else 54321
    }
    message = create_sale_message(collection)
    print(f"Test sale message for {collection}: {message}")

    await post_sale_to_discord(channel, collection, test_sale)
    await ctx.send(f"Test sale posted to the {collection} sales channel!")

if __name__ == "__main__":
    bot_token = os.getenv("DISCORD_BOT_TOKEN", "yourbottokenid")
    if not bot_token:
        raise ValueError("DISCORD_BOT_TOKEN not found in .env file")
    bot.run(bot_token)
