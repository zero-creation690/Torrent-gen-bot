import os
import asyncio
import libtorrent as lt
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
from datetime import datetime
import time
import logging

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")

# Directories
SEED_DIR = Path("/srv/seeds")
TORRENT_DIR = Path("/srv/torrents")
SEED_DIR.mkdir(parents=True, exist_ok=True)
TORRENT_DIR.mkdir(parents=True, exist_ok=True)

# Clean old sessions
import glob
for f in glob.glob("/srv/*.session*"):
    try:
        os.remove(f)
    except:
        pass

# Trackers
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
]

# MongoDB
mongo_client = None
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    db = mongo_client['torrent_bot']
    torrents_collection = db['torrents']
    mongo_client.admin.command('ping')
    logger.info("✅ MongoDB OK")
except Exception as e:
    logger.warning(f"⚠️ MongoDB failed: {e}")

# Bot
app = Client(
    f"bot_{int(time.time())}",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/srv"
)

# Libtorrent
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881',
    'alert_mask': lt.alert.category_t.all_categories,
})

settings = {
    'enable_dht': True,
    'enable_lsd': True,
    'connections_limit': 5000,
    'upload_rate_limit': 0,
}
lt_session.apply_settings(settings)

active_torrents = {}

logger.info("🚀 Bot initialized")


def create_torrent(file_path: Path):
    """Create torrent"""
    fs = lt.file_storage()
    lt.add_files(fs, str(file_path))
    
    file_size = file_path.stat().st_size
    piece_size = 256 * 1024 if file_size < 500 * 1024 * 1024 else 1024 * 1024
    
    t = lt.create_torrent(fs, piece_size=piece_size)
    t.set_priv(False)
    
    for tracker in TRACKERS:
        t.add_tracker(tracker, 0)
    
    lt.set_piece_hashes(t, str(file_path.parent))
    
    torrent_data = lt.bencode(t.generate())
    torrent_file = TORRENT_DIR / f"{file_path.stem}.torrent"
    
    with open(torrent_file, "wb") as f:
        f.write(torrent_data)
    
    info = lt.torrent_info(str(torrent_file))
    magnet = lt.make_magnet_uri(info)
    
    return torrent_file, magnet


def start_seeding(file_path: Path, torrent_file: Path):
    """Start seeding"""
    info = lt.torrent_info(str(torrent_file))
    
    atp = lt.add_torrent_params()
    atp.ti = info
    atp.save_path = str(file_path.parent)
    atp.flags |= lt.torrent_flags.seed_mode
    atp.flags |= lt.torrent_flags.upload_mode
    
    handle = lt_session.add_torrent(atp)
    handle.set_max_uploads(-1)
    handle.set_max_connections(-1)
    
    info_hash = str(info.info_hash())
    active_torrents[info_hash] = {
        'handle': handle,
        'name': file_path.name,
        'started': time.time()
    }
    
    return info_hash


# Handlers
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    logger.info(f"✅ /start from user {message.from_user.id}")
    await message.reply_text(
        "🤖 **Torrent Bot**\n\n"
        "Send me a file and I'll create a torrent!\n\n"
        "Commands:\n"
        "/start - This message\n"
        "/stats - Active torrents"
    )


@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    if not active_torrents:
        await message.reply_text("No active torrents")
        return
    
    text = "**Active Torrents:**\n\n"
    for ih, data in list(active_torrents.items())[:5]:
        text += f"📄 {data['name'][:30]}\n"
    
    await message.reply_text(text)


@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client, message):
    logger.info(f"📥 FILE from user {message.from_user.id}")
    
    try:
        # Get media
        if message.document:
            media = message.document
            name = media.file_name or f"file_{media.file_unique_id}"
        elif message.video:
            media = message.video
            name = media.file_name or f"video_{media.file_unique_id}.mp4"
        else:
            media = message.audio
            name = media.file_name or f"audio_{media.file_unique_id}.mp3"
        
        size_mb = media.file_size / (1024**2)
        
        if media.file_size > 4 * 1024**3:
            await message.reply_text("❌ Max 4GB!")
            return
        
        # Status
        status = await message.reply_text(f"⚡ Processing {name[:30]}...")
        
        # Forward to channel
        if BIN_CHANNEL != 0:
            try:
                if message.document:
                    await client.send_document(BIN_CHANNEL, media.file_id)
                elif message.video:
                    await client.send_video(BIN_CHANNEL, media.file_id)
                else:
                    await client.send_audio(BIN_CHANNEL, media.file_id)
                logger.info("✅ Forwarded to channel")
            except Exception as e:
                logger.warning(f"Channel forward failed: {e}")
        
        # Download
        file_path = SEED_DIR / name
        await message.download(file_name=str(file_path))
        logger.info(f"✅ Downloaded")
        
        # Create torrent
        await status.edit_text(f"⚡ Creating torrent...")
        torrent_file, magnet = await asyncio.to_thread(create_torrent, file_path)
        logger.info(f"✅ Torrent created")
        
        # Start seeding
        info_hash = start_seeding(file_path, torrent_file)
        logger.info(f"✅ Seeding started")
        
        # Save to DB
        if mongo_client:
            try:
                torrents_collection.insert_one({
                    'info_hash': info_hash,
                    'file_name': name,
                    'file_size': media.file_size,
                    'magnet_link': magnet,
                    'created_at': datetime.utcnow(),
                    'user_id': message.from_user.id
                })
            except:
                pass
        
        # Reply
        await status.delete()
        
        await message.reply_document(
            document=str(torrent_file),
            caption=(
                f"⚡ **Torrent Ready**\n\n"
                f"📄 `{name}`\n"
                f"📦 {size_mb:.1f} MB\n"
                f"🔑 `{info_hash[:16]}...`\n\n"
                f"🚀 Seeding now!"
            )
        )
        
        await message.reply_text(
            f"🧲 **Magnet:**\n`{magnet}`",
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ DONE: {name}")
        
    except Exception as e:
        logger.error(f"❌ ERROR: {e}", exc_info=True)
        try:
            await message.reply_text(f"❌ Error: {str(e)[:100]}")
        except:
            pass


@app.on_message(filters.text & ~filters.command(["start", "stats"]))
async def echo(client, message):
    logger.info(f"💬 Text from {message.from_user.id}: {message.text}")
    await message.reply_text("✅ I'm alive! Send me a file to create a torrent.")


async def monitor_loop():
    """Monitor torrents"""
    while True:
        try:
            lt_session.pop_alerts()
            
            for ih, data in list(active_torrents.items()):
                handle = data['handle']
                if handle.is_valid():
                    status = handle.status()
                    if status.state == lt.torrent_status.seeding:
                        handle.set_max_uploads(-1)
                        handle.set_max_connections(-1)
            
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            await asyncio.sleep(60)


async def main():
    """Main"""
    await app.start()
    me = await app.get_me()
    
    logger.info("=" * 50)
    logger.info(f"✅ BOT STARTED: @{me.username}")
    logger.info(f"✅ Bot ID: {me.id}")
    logger.info("=" * 50)
    
    if OWNER_ID != 0:
        try:
            await app.send_message(
                OWNER_ID, 
                f"✅ Bot started!\n\n"
                f"Username: @{me.username}\n"
                f"ID: {me.id}\n\n"
                f"Send me a file to test!"
            )
            logger.info(f"✅ Notified owner {OWNER_ID}")
        except Exception as e:
            logger.warning(f"⚠️ Could not notify owner: {e}")
    
    # Start monitor
    monitor_task = asyncio.create_task(monitor_loop())
    
    logger.info("🎧 Listening for updates...")
    
    # Keep alive
    try:
        from pyrogram import idle
        await idle()
    except ImportError:
        # Fallback if idle() not available
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Stopped")
