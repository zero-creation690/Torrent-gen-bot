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
# CRITICAL: BIN_CHANNEL must be a negative integer ID (e.g., -100xxxxxxxxxx)
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")

# Directories
SEED_DIR = Path("/srv/seeds")
TORRENT_DIR = Path("/srv/torrents")

# Create directories
SEED_DIR.mkdir(parents=True, exist_ok=True)
TORRENT_DIR.mkdir(parents=True, exist_ok=True)

# CRITICAL FIX: Delete old session files to prevent auth errors
import glob
session_files = glob.glob("/srv/*.session*")
for f in session_files:
    try:
        os.remove(f)
        logger.info(f"🗑️ Deleted old session: {f}")
    except:
        pass

# ULTRA FAST trackers
TRACKERS = [
    # Tier 1 - FASTEST (Public & Popular)
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    
    # Tier 2 - Fast & Reliable
    "https://tracker.openbittorrent.com:443/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    
    # Tier 3 - High Performance
    "udp://9.rarbg.com:2810/announce",
    "udp://tracker.cyberia.is:6969/announce",
    "udp://retracker.lanta-net.ru:2710/announce",
    "udp://tracker.zer0day.to:1337/announce",
    
    # WebTorrent for browser downloads
    "wss://tracker.btorrent.xyz",
    "wss://tracker.openwebtorrent.com",
    "wss://tracker.fastcast.nz"
]

# Initialize MongoDB
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client['torrent_bot']
    torrents_collection = db['torrents']
    stats_collection = db['stats']
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    mongo_client = None

# Initialize Bot with FIXED session name
app = Client(
    f"bot_{int(time.time())}",  # UNIQUE name with timestamp to avoid old sessions
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/srv",
    workers=8
)

# Libtorrent session with ULTRA FAST settings
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881,[::]:6881',
    'alert_mask': lt.alert.category_t.status_notification | lt.alert.category_t.error_notification | lt.alert.category_t.tracker_notification,
    'outgoing_interfaces': '',
    'announce_to_all_tiers': True,
    'announce_to_all_trackers': True,
    'aio_threads': 16,
    'checking_mem_usage': 2048  # 2GB
})

# ULTRA FAST seeding settings
settings = {
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'enable_natpmp': True,
    'connections_limit': 4000,
    'upload_rate_limit': 0,  # Unlimited upload
    'download_rate_limit': 0,
    'active_downloads': -1,
    'active_seeds': -1,
    'active_limit': -1,
    'max_out_request_queue': 5000,
    'max_allowed_in_request_queue': 5000,
    'unchoke_slots_limit': 200,
    'max_peerlist_size': 8000,
    'max_paused_peerlist_size': 8000,
    'min_reconnect_time': 1,
    'peer_connect_timeout': 5,
    'request_timeout': 15,
    'inactivity_timeout': 30,
    'torrent_connect_boost': 50,
    'seeding_outgoing_connections': True,
    'no_connect_privileged_ports': False,
    'seed_choking_algorithm': 1,  # Fastest upload
    'cache_size': 2048,  # 2GB cache
    'use_read_cache': True,
    'cache_buffer_chunk_size': 128,
    'read_cache_line_size': 128,
    'write_cache_line_size': 128,
    'file_pool_size': 500,
    'max_retry_port_bind': 100,
    'alert_queue_size': 2000,
    'allow_multiple_connections_per_ip': True,
    'send_buffer_watermark': 5 * 1024 * 1024,
    'send_buffer_low_watermark': 1 * 1024 * 1024,
    'send_buffer_watermark_factor': 150,
}
lt_session.apply_settings(settings)

# Add DHT routers for better peer discovery
lt_session.add_dht_router("router.bittorrent.com", 6881)
lt_session.add_dht_router("dht.transmissionbt.com", 6881)
lt_session.add_dht_router("router.utorrent.com", 6881)
lt_session.add_dht_router("dht.libtorrent.org", 25401)

# Store active torrents
active_torrents = {}

logger.info("✅ Bot initialized with optimized settings")


def save_to_mongodb(torrent_data: dict):
    """Save torrent data to MongoDB"""
    if not mongo_client:
        logger.warning("⚠️ MongoDB not available, skipping save")
        return
    
    try:
        torrents_collection.insert_one(torrent_data)
        logger.info(f"✅ Saved to MongoDB: {torrent_data['file_name']}")
    except Exception as e:
        logger.error(f"❌ MongoDB save error: {e}")


def create_torrent_file(file_path: Path) -> tuple[Path, str]:
    """Create .torrent file and magnet link - ULTRA OPTIMIZED"""
    try:
        fs = lt.file_storage()
        lt.add_files(fs, str(file_path))
        
        # Create torrent with OPTIMAL piece size
        file_size = file_path.stat().st_size
        
        # Piece size optimization logic
        if file_size < 100 * 1024 * 1024:  # < 100MB
            piece_size = 256 * 1024  # 256KB
        elif file_size < 500 * 1024 * 1024:  # < 500MB
            piece_size = 512 * 1024  # 512KB
        elif file_size < 1024 * 1024 * 1024:  # < 1GB
            piece_size = 1024 * 1024  # 1MB
        else:  # > 1GB
            piece_size = 2 * 1024 * 1024  # 2MB
        
        t = lt.create_torrent(fs, piece_size=piece_size)
        t.set_priv(False)  # Public for more peers
        
        # Add BEST trackers
        tier = 0
        for tracker in TRACKERS:
            t.add_tracker(tracker, tier)
        
        t.set_creator("TG Ultra Fast Bot")
        t.set_comment(f"Fast Download | {file_path.name}")
        
        # Generate piece hashes
        lt.set_piece_hashes(t, str(file_path.parent))
        
        # Generate torrent
        torrent_data = lt.bencode(t.generate())
        torrent_file_path = TORRENT_DIR / f"{file_path.stem}.torrent"
        
        with open(torrent_file_path, "wb") as f:
            f.write(torrent_data)
        
        # Generate magnet link
        info = lt.torrent_info(str(torrent_file_path))
        magnet_link = lt.make_magnet_uri(info)
        
        logger.info(f"✅ Torrent created: {torrent_file_path.name} | Piece: {piece_size/1024}KB")
        return torrent_file_path, magnet_link
        
    except Exception as e:
        logger.error(f"❌ Error creating torrent: {e}")
        raise


def apply_aggressive_handle_settings(handle: lt.torrent_handle):
    """Apply aggressive settings to a torrent handle"""
    if handle.is_valid():
        handle.set_max_uploads(-1)
        handle.set_max_connections(-1)
        handle.set_upload_limit(-1)
        handle.force_reannounce(0, -1)
        handle.force_dht_announce()


def start_seeding(file_path: Path, torrent_file: Path) -> str:
    """Start seeding with ULTRA FAST settings"""
    try:
        info = lt.torrent_info(str(torrent_file))
        
        # Create add_torrent_params with MAXIMUM performance
        atp = lt.add_torrent_params()
        atp.ti = info
        atp.save_path = str(file_path.parent)
        
        # Set flags for ULTRA FAST seeding
        atp.flags |= lt.torrent_flags.seed_mode
        atp.flags |= lt.torrent_flags.auto_managed
        atp.flags |= lt.torrent_flags.upload_mode
        atp.flags |= lt.torrent_flags.share_mode
        atp.flags |= lt.torrent_flags.super_seeding
        
        handle = lt_session.add_torrent(atp)
        
        # Apply aggressive settings immediately
        apply_aggressive_handle_settings(handle)
        
        info_hash = str(info.info_hash())
        
        active_torrents[info_hash] = {
            'handle': handle,
            'file_path': file_path,
            'torrent_file': torrent_file,
            'started': time.time(),
            'name': file_path.name
        }
        
        logger.info(f"🌱 ULTRA SEEDING: {file_path.name} | Hash: {info_hash[:16]}")
        return info_hash
        
    except Exception as e:
        logger.error(f"❌ Error starting seeder: {e}")
        raise


async def lt_monitor_loop():
    """Monitor libtorrent session and maintain performance"""
    logger.info("🔄 Monitor loop started")
    while True:
        try:
            # Process alerts
            lt_session.pop_alerts()
            
            # Re-apply aggressive settings
            for info_hash, data in list(active_torrents.items()):
                handle = data['handle']
                if handle.is_valid() and handle.status().state == lt.torrent_status.seeding:
                    apply_aggressive_handle_settings(handle)
                    
            await asyncio.sleep(15)
        except Exception as e:
            logger.error(f"❌ Monitor loop error: {e}")
            await asyncio.sleep(30)


# --- Pyrogram Handlers ---

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client: Client, message: Message):
    """Handle incoming files"""
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
        file_size_mb = file_size / (1024**2)
        
        logger.info(f"📥 Received: {file_name} ({file_size_mb:.2f} MB)")
        
        # Size check (4GB limit)
        if file_size > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File exceeds 4GB limit!")
            return
        
        # Status message
        status = await message.reply_text(
            f"⚡ **Processing...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 **{file_size_mb:.1f} MB**"
        )
        
        # STEP 1: Forward to BIN_CHANNEL
        forwarded_id = None
        try:
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
            logger.info(f"✅ Sent to BIN_CHANNEL: {forwarded_id}")
        except Exception as e:
            logger.warning(f"⚠️ Channel forward failed: {e}")
        
        # STEP 2: Download locally
        file_path = SEED_DIR / file_name
        download_start = time.time()
        
        try:
            await message.download(file_name=str(file_path))
            download_time = time.time() - download_start
            logger.info(f"✅ Downloaded in {download_time:.1f}s")
        except Exception as e:
            await status.edit_text(f"❌ Download failed: {e}")
            return
        
        # STEP 3: Create torrent
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
        
        # Send final result
        await status.delete()
        
        # Send .torrent file with caption
        caption = (
            f"⚡ **ULTRA FAST TORRENT**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 {file_size_mb:.1f} MB\n"
            f"⚡ {total_time:.1f}s\n"
            f"🔑 `{info_hash[:24]}...`\n\n"
            f"🚀 **SEEDING AT MAX SPEED** 🚀"
        )
        
        torrent_message = await message.reply_document(
            document=str(torrent_file),
            caption=caption,
            file_name=torrent_file.name
        )
        
        # Send magnet link
        await client.send_message(
            chat_id=message.chat.id,
            text=f"🧲 **Magnet:**\n`{magnet_link}`",
            reply_to_message_id=torrent_message.id,
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ Complete in {total_time:.1f}s: {file_name}")
        
    except Exception as e:
        logger.error(f"❌ Critical error: {e}", exc_info=True)
        try:
            await message.reply_text(f"❌ Error: {e}")
        except:
            pass


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
        "/db - Database statistics\n"
        "/start - This message"
    )


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
    if not mongo_client:
        await message.reply_text("❌ MongoDB not available")
        return
    
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


@app.on_message(filters.command("db"))
async def db_stats(client: Client, message: Message):
    """Database statistics"""
    if not mongo_client:
        await message.reply_text("❌ MongoDB not available")
        return
    
    try:
        total = torrents_collection.count_documents({})
        total_size = sum([t.get('file_size', 0) for t in torrents_collection.find()])
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
    
    loop = asyncio.get_event_loop()
    
    try:
        # Start the Pyrogram client
        app.set_parse_mode("markdown")
        loop.run_until_complete(app.start())
        
        # Notify owner
        if OWNER_ID != 0:
            try:
                loop.run_until_complete(
                    app.send_message(OWNER_ID, "✅ Bot started successfully!")
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not notify owner: {e}")
        
        # Run monitor loop and main bot concurrently
        loop.run_until_complete(asyncio.gather(
            lt_monitor_loop(),
            app.idle()
        ))
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        lt_session.pause()
        if mongo_client:
            mongo_client.close()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        loop.run_until_complete(app.stop())
