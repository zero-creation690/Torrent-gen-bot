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
import hashlib

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_NAME = os.getenv("SESSION_NAME", "torrent_userbot")
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL"))  # Supports both -100 and -1003 format
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")

# Directories
SEED_DIR = Path("/srv/seeds")
TORRENT_DIR = Path("/srv/torrents")

# Create directories
SEED_DIR.mkdir(parents=True, exist_ok=True)
TORRENT_DIR.mkdir(parents=True, exist_ok=True)

# Trackers list (optimized for fast peer discovery)
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "https://tracker.openbittorrent.com:443/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce"
]

# Initialize MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['torrent_bot']
torrents_collection = db['torrents']
stats_collection = db['stats']

logger.info("MongoDB connected successfully")

# Initialize Bot (using bot token for better reliability)
app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/srv",
    workers=8  # Increase workers for faster processing
)

# Libtorrent session with optimized settings
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881,[::]:6881',
    'alert_mask': lt.alert.category_t.status_notification | lt.alert.category_t.error_notification,
    'outgoing_interfaces': '',
    'announce_to_all_tiers': True,
    'announce_to_all_trackers': True,
    'aio_threads': 8,
    'checking_mem_usage': 1024
})

# Optimized settings for fast seeding
settings = {
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'enable_natpmp': True,
    'connections_limit': 500,
    'upload_rate_limit': 0,
    'download_rate_limit': 0,
    'active_downloads': -1,
    'active_seeds': -1,
    'active_limit': -1,
    'max_out_request_queue': 1000,
    'max_allowed_in_request_queue': 2000,
}
lt_session.apply_settings(settings)

# Add DHT routers for better peer discovery
lt_session.add_dht_router("router.bittorrent.com", 6881)
lt_session.add_dht_router("dht.transmissionbt.com", 6881)
lt_session.add_dht_router("router.utorrent.com", 6881)
lt_session.add_dht_router("dht.libtorrent.org", 25401)

# Store active torrents
active_torrents = {}

logger.info("Bot initialized with optimized settings")


def save_to_mongodb(torrent_data: dict):
    """Save torrent data to MongoDB"""
    try:
        torrents_collection.insert_one(torrent_data)
        logger.info(f"Saved to MongoDB: {torrent_data['file_name']}")
    except Exception as e:
        logger.error(f"MongoDB save error: {e}")


def create_torrent_file(file_path: Path) -> tuple[Path, str]:
    """Create .torrent file and magnet link - OPTIMIZED"""
    try:
        fs = lt.file_storage()
        lt.add_files(fs, str(file_path))
        
        t = lt.create_torrent(fs)
        t.set_priv(False)
        
        # Add all trackers
        tier = 0
        for tracker in TRACKERS:
            t.add_tracker(tracker, tier)
        
        t.set_creator("TG Torrent Bot")
        t.set_comment(f"File: {file_path.name}")
        
        # Generate piece hashes (optimized with parallel processing)
        lt.set_piece_hashes(t, str(file_path.parent))
        
        # Generate torrent
        torrent_data = lt.bencode(t.generate())
        torrent_file_path = TORRENT_DIR / f"{file_path.stem}.torrent"
        
        with open(torrent_file_path, "wb") as f:
            f.write(torrent_data)
        
        # Generate magnet link
        info = lt.torrent_info(str(torrent_file_path))
        magnet_link = lt.make_magnet_uri(info)
        
        logger.info(f"Torrent created: {torrent_file_path.name}")
        return torrent_file_path, magnet_link
        
    except Exception as e:
        logger.error(f"Error creating torrent: {e}")
        raise


def start_seeding(file_path: Path, torrent_file: Path) -> str:
    """Start seeding with optimized settings"""
    try:
        info = lt.torrent_info(str(torrent_file))
        
        # Create add_torrent_params (compatible with all libtorrent versions)
        atp = lt.add_torrent_params()
        atp.ti = info
        atp.save_path = str(file_path.parent)
        
        # Set flags for seeding
        atp.flags |= lt.torrent_flags.seed_mode
        atp.flags |= lt.torrent_flags.auto_managed
        
        handle = lt_session.add_torrent(atp)
        
        # Force announce to all trackers immediately
        handle.force_reannounce()
        handle.force_dht_announce()
        
        info_hash = str(info.info_hash())
        
        active_torrents[info_hash] = {
            'handle': handle,
            'file_path': file_path,
            'torrent_file': torrent_file,
            'started': time.time(),
            'name': file_path.name
        }
        
        logger.info(f"Seeding: {file_path.name} | Hash: {info_hash[:16]}")
        return info_hash
        
    except Exception as e:
        logger.error(f"Error starting seeder: {e}")
        raise


@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client: Client, message: Message):
    """Handle incoming files - ULTRA OPTIMIZED"""
    try:
        start_time = time.time()
        
        # Get file info
        if message.document:
            media = message.document
            file_name = media.file_name or f"document_{media.file_unique_id}"
        elif message.video:
            media = message.video
            file_name = media.file_name or f"video_{media.file_unique_id}.mp4"
        elif message.audio:
            media = message.audio
            file_name = media.file_name or f"audio_{media.file_unique_id}.mp3"
        else:
            return
        
        file_size = media.file_size
        file_size_gb = file_size / (1024**3)
        file_size_mb = file_size / (1024**2)
        
        logger.info(f"📥 Received: {file_name} ({file_size_gb:.2f} GB)")
        
        # Size check
        if file_size > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File exceeds 4GB limit!")
            return
        
        # Quick status
        status = await message.reply_text(
            f"⚡ **Processing...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 **{file_size_mb:.1f} MB**"
        )
        
        # STEP 1: Forward to BIN_CHANNEL (permanent storage)
        # Skip forward for now - just save locally and create torrent
        forwarded_id = None
        try:
            # Try sending file directly to channel
            if message.document:
                forwarded = await client.send_document(
                    BIN_CHANNEL,
                    message.document.file_id,
                    caption=f"📁 {file_name}\n👤 From: {message.from_user.id}"
                )
                forwarded_id = forwarded.id
            elif message.video:
                forwarded = await client.send_video(
                    BIN_CHANNEL,
                    message.video.file_id,
                    caption=f"🎬 {file_name}\n👤 From: {message.from_user.id}"
                )
                forwarded_id = forwarded.id
            elif message.audio:
                forwarded = await client.send_audio(
                    BIN_CHANNEL,
                    message.audio.file_id,
                    caption=f"🎵 {file_name}\n👤 From: {message.from_user.id}"
                )
                forwarded_id = forwarded.id
            logger.info(f"✅ Sent to BIN_CHANNEL")
        except Exception as e:
            logger.warning(f"⚠️ Channel forward skipped: {e}")
            # Continue anyway - we'll still create torrent
        
        # STEP 2: Download locally (with progress)
        file_path = SEED_DIR / file_name
        download_start = time.time()
        
        async def progress(current, total):
            pass  # No updates during download for speed
        
        try:
            await message.download(file_name=str(file_path), progress=progress)
            download_time = time.time() - download_start
            logger.info(f"✅ Downloaded in {download_time:.1f}s")
        except Exception as e:
            await status.edit_text(f"❌ Download failed: {e}")
            return
        
        # STEP 3: Create torrent (async)
        await status.edit_text(
            f"⚡ **Processing...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 **{file_size_mb:.1f} MB**\n\n"
            f"🔧 Creating torrent..."
        )
        
        try:
            torrent_file, magnet_link = await asyncio.get_event_loop().run_in_executor(
                None, create_torrent_file, file_path
            )
        except Exception as e:
            await status.edit_text(f"❌ Torrent creation failed: {e}")
            return
        
        # STEP 4: Start seeding
        try:
            info_hash = start_seeding(file_path, torrent_file)
        except Exception as e:
            await status.edit_text(f"❌ Seeding failed: {e}")
            return
        
        # Calculate total time
        total_time = time.time() - start_time
        
        # Save to MongoDB
        torrent_data = {
            'info_hash': info_hash,
            'file_name': file_name,
            'file_size': file_size,
            'magnet_link': magnet_link,
            'torrent_file': str(torrent_file),
            'bin_channel_msg_id': forwarded_id,
            'created_at': datetime.utcnow(),
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'processing_time': total_time,
            'channel_forwarded': forwarded_id is not None
        }
        
        await asyncio.get_event_loop().run_in_executor(
            None, save_to_mongodb, torrent_data
        )
        
        # Delete status message
        await status.delete()
        
        # Send final result
        caption = (
            f"✅ **Torrent Ready!**\n\n"
            f"📄 **File:** `{file_name}`\n"
            f"📦 **Size:** {file_size_mb:.1f} MB ({file_size_gb:.2f} GB)\n"
            f"🔑 **Hash:** `{info_hash[:32]}`\n"
            f"⚡ **Time:** {total_time:.1f}s\n"
            f"💾 **Stored:** {'✅ Yes' if forwarded_id else '⚠️ Local only'}\n\n"
            f"🧲 **Magnet:**\n"
            f"`{magnet_link}`\n\n"
            f"🌱 **Seeding now - keep bot online!**"
        )
        
        # Send .torrent file
        await message.reply_document(
            document=str(torrent_file),
            caption=caption,
            file_name=torrent_file.name
        )
        
        logger.info(f"✅ Complete in {total_time:.1f}s: {file_name}")
        
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        try:
            await message.reply_text(f"❌ Error: {e}")
        except:
            pass


@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    """Show seeding stats"""
    if not active_torrents:
        await message.reply_text("📊 **No active torrents**")
        return
    
    stats = "📊 **Active Torrents**\n\n"
    total_upload = 0
    
    for info_hash, data in active_torrents.items():
        handle = data['handle']
        status = handle.status()
        
        uptime = time.time() - data['started']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        upload_gb = status.total_upload / (1024**3)
        total_upload += upload_gb
        
        stats += (
            f"📄 **{data['name'][:30]}**\n"
            f"🔑 `{info_hash[:20]}...`\n"
            f"⬆️ {upload_gb:.2f} GB\n"
            f"🌱 Seeds: {status.num_seeds} | Peers: {status.num_peers}\n"
            f"⏱ {hours}h {minutes}m\n\n"
        )
    
    stats += f"📊 **Total Upload:** {total_upload:.2f} GB"
    await message.reply_text(stats)


@app.on_message(filters.command("list"))
async def list_command(client: Client, message: Message):
    """List all torrents from MongoDB"""
    try:
        torrents = list(torrents_collection.find().sort("created_at", -1).limit(10))
        
        if not torrents:
            await message.reply_text("📂 **No torrents in database**")
            return
        
        text = "📂 **Recent Torrents**\n\n"
        
        for t in torrents:
            size_mb = t['file_size'] / (1024**2)
            text += (
                f"📄 `{t['file_name'][:40]}`\n"
                f"📦 {size_mb:.1f} MB\n"
                f"🔑 `{t['info_hash'][:20]}...`\n\n"
            )
        
        await message.reply_text(text)
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Welcome message"""
    await message.reply_text(
        "🤖 **Telegram Torrent Bot**\n\n"
        "Send me any file up to **4GB**!\n\n"
        "**Features:**\n"
        "✅ Permanent storage in bin channel\n"
        "✅ Ultra-fast torrent creation\n"
        "✅ Instant magnet links\n"
        "✅ MongoDB tracking\n"
        "✅ 24/7 seeding\n\n"
        "**Commands:**\n"
        "/stats - Active torrents\n"
        "/list - Recent torrents\n"
        "/start - This message"
    )


@app.on_message(filters.command("db"))
async def db_stats(client: Client, message: Message):
    """Database statistics"""
    try:
        total = torrents_collection.count_documents({})
        total_size = sum([t['file_size'] for t in torrents_collection.find()])
        total_gb = total_size / (1024**3)
        
        await message.reply_text(
            f"💾 **Database Stats**\n\n"
            f"📊 Total Torrents: **{total}**\n"
            f"📦 Total Size: **{total_gb:.2f} GB**"
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 TELEGRAM TORRENT BOT")
    logger.info("=" * 50)
    logger.info(f"📁 Seeds: {SEED_DIR}")
    logger.info(f"📁 Torrents: {TORRENT_DIR}")
    logger.info(f"📢 Bin Channel: {BIN_CHANNEL}")
    logger.info(f"💾 MongoDB: Connected")
    logger.info(f"🌱 Libtorrent: Optimized")
    logger.info("=" * 50)
    
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        lt_session.pause()
        mongo_client.close()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
