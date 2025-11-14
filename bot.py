import os
import asyncio
import libtorrent as lt
from pathlib import Path
from pyrogram import Client, filters, idle
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
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")

# Directories
SEED_DIR = Path("/srv/seeds")
TORRENT_DIR = Path("/srv/torrents")

# Create directories
SEED_DIR.mkdir(parents=True, exist_ok=True)
TORRENT_DIR.mkdir(parents=True, exist_ok=True)

# Delete old session files
import glob
session_files = glob.glob("/srv/*.session*")
for f in session_files:
    try:
        os.remove(f)
        logger.info(f"🗑️ Deleted old session: {f}")
    except:
        pass

# YTS-style ULTRA FAST trackers
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://9.rarbg.com:2810/announce",
    "udp://tracker.cyberia.is:6969/announce",
    "udp://retracker.lanta-net.ru:2710/announce",
    "udp://tracker.zer0day.to:1337/announce",
    "wss://tracker.btorrent.xyz",
    "wss://tracker.openwebtorrent.com",
]

# Initialize MongoDB
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo_client['torrent_bot']
    torrents_collection = db['torrents']
    mongo_client.admin.command('ping')
    logger.info("✅ MongoDB connected")
except Exception as e:
    logger.warning(f"⚠️ MongoDB unavailable: {e}")
    mongo_client = None

# Initialize Bot
app = Client(
    f"yts_bot_{int(time.time())}",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/srv",
    workers=8,
    parse_mode="markdown"
)

# YTS-STYLE ULTRA FAST Libtorrent Settings
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881,[::]:6881',
    'alert_mask': lt.alert.category_t.all_categories,
    'outgoing_interfaces': '',
    'announce_to_all_tiers': True,
    'announce_to_all_trackers': True,
    'aio_threads': 32,
    'checking_mem_usage': 4096
})

# MAXIMUM PERFORMANCE SETTINGS (YTS-style)
settings = {
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'enable_natpmp': True,
    'connections_limit': 10000,
    'upload_rate_limit': 0,
    'download_rate_limit': 0,
    'active_downloads': -1,
    'active_seeds': -1,
    'active_limit': -1,
    'max_out_request_queue': 10000,
    'max_allowed_in_request_queue': 10000,
    'unchoke_slots_limit': 500,
    'max_peerlist_size': 16000,
    'max_paused_peerlist_size': 16000,
    'min_reconnect_time': 1,
    'peer_connect_timeout': 3,
    'request_timeout': 10,
    'inactivity_timeout': 20,
    'torrent_connect_boost': 100,
    'seeding_outgoing_connections': True,
    'no_connect_privileged_ports': False,
    'seed_choking_algorithm': 1,
    'cache_size': 4096,
    'use_read_cache': True,
    'cache_buffer_chunk_size': 256,
    'read_cache_line_size': 256,
    'write_cache_line_size': 256,
    'file_pool_size': 1000,
    'max_retry_port_bind': 100,
    'alert_queue_size': 5000,
    'allow_multiple_connections_per_ip': True,
    'send_buffer_watermark': 10 * 1024 * 1024,
    'send_buffer_low_watermark': 2 * 1024 * 1024,
    'send_buffer_watermark_factor': 200,
}
lt_session.apply_settings(settings)

# Add DHT routers
lt_session.add_dht_router("router.bittorrent.com", 6881)
lt_session.add_dht_router("dht.transmissionbt.com", 6881)
lt_session.add_dht_router("router.utorrent.com", 6881)
lt_session.add_dht_router("dht.libtorrent.org", 25401)

active_torrents = {}

logger.info("✅ YTS-style bot initialized")


def save_to_mongodb(torrent_data: dict):
    """Save torrent data to MongoDB"""
    if not mongo_client:
        return
    try:
        torrents_collection.insert_one(torrent_data)
        logger.info(f"💾 Saved: {torrent_data['file_name']}")
    except Exception as e:
        logger.error(f"❌ MongoDB error: {e}")


def create_torrent_file(file_path: Path) -> tuple[Path, str]:
    """Create .torrent file - YTS OPTIMIZED"""
    try:
        fs = lt.file_storage()
        lt.add_files(fs, str(file_path))
        
        file_size = file_path.stat().st_size
        
        # YTS-style piece size (smaller = faster start)
        if file_size < 50 * 1024 * 1024:  # < 50MB
            piece_size = 128 * 1024  # 128KB
        elif file_size < 200 * 1024 * 1024:  # < 200MB
            piece_size = 256 * 1024  # 256KB
        elif file_size < 700 * 1024 * 1024:  # < 700MB
            piece_size = 512 * 1024  # 512KB
        else:
            piece_size = 1024 * 1024  # 1MB
        
        t = lt.create_torrent(fs, piece_size=piece_size)
        t.set_priv(False)
        
        # Add all trackers
        for tracker in TRACKERS:
            t.add_tracker(tracker, 0)
        
        t.set_creator("YTS-Style Ultra Bot")
        t.set_comment(f"⚡ ULTRA FAST | {file_path.name}")
        
        lt.set_piece_hashes(t, str(file_path.parent))
        
        torrent_data = lt.bencode(t.generate())
        torrent_file_path = TORRENT_DIR / f"{file_path.stem}.torrent"
        
        with open(torrent_file_path, "wb") as f:
            f.write(torrent_data)
        
        info = lt.torrent_info(str(torrent_file_path))
        magnet_link = lt.make_magnet_uri(info)
        
        logger.info(f"⚡ Torrent: {piece_size/1024}KB pieces")
        return torrent_file_path, magnet_link
        
    except Exception as e:
        logger.error(f"❌ Torrent creation failed: {e}")
        raise


def apply_yts_settings(handle: lt.torrent_handle):
    """Apply YTS-style aggressive settings"""
    if handle.is_valid():
        handle.set_max_uploads(-1)
        handle.set_max_connections(-1)
        handle.set_upload_limit(-1)
        handle.force_reannounce(0, -1)
        handle.force_dht_announce()


def start_seeding(file_path: Path, torrent_file: Path) -> str:
    """Start YTS-style seeding"""
    try:
        info = lt.torrent_info(str(torrent_file))
        
        atp = lt.add_torrent_params()
        atp.ti = info
        atp.save_path = str(file_path.parent)
        
        atp.flags |= lt.torrent_flags.seed_mode
        atp.flags |= lt.torrent_flags.auto_managed
        atp.flags |= lt.torrent_flags.upload_mode
        atp.flags |= lt.torrent_flags.super_seeding
        
        handle = lt_session.add_torrent(atp)
        apply_yts_settings(handle)
        
        info_hash = str(info.info_hash())
        
        active_torrents[info_hash] = {
            'handle': handle,
            'file_path': file_path,
            'torrent_file': torrent_file,
            'started': time.time(),
            'name': file_path.name
        }
        
        logger.info(f"🚀 YTS SEEDING: {file_path.name}")
        return info_hash
        
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        raise


async def lt_monitor_loop():
    """YTS-style performance monitor"""
    logger.info("🔄 Monitor loop started")
    while True:
        try:
            alerts = lt_session.pop_alerts()
            
            for info_hash, data in list(active_torrents.items()):
                handle = data['handle']
                if handle.is_valid():
                    status = handle.status()
                    if status.state == lt.torrent_status.seeding:
                        apply_yts_settings(handle)
                        
                        # Log performance every 5 minutes
                        uptime = time.time() - data['started']
                        if int(uptime) % 300 == 0:
                            upload_mb = status.total_upload / (1024**2)
                            logger.info(f"📊 {data['name'][:30]} | ⬆️ {upload_mb:.1f}MB | 🌱 {status.num_seeds}s {status.num_peers}p")
                    
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"❌ Monitor error: {e}")
            await asyncio.sleep(30)


# --- Pyrogram Handlers ---

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client: Client, message: Message):
    """Handle file uploads - YTS optimized"""
    try:
        start_time = time.time()
        
        if message.document:
            media = message.document
            file_name = media.file_name or f"doc_{media.file_unique_id}"
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
        
        if file_size > 4 * 1024**3:
            await message.reply_text("❌ Max 4GB!")
            return
        
        status = await message.reply_text(
            f"⚡ **YTS Processing**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 **{file_size_mb:.1f} MB**"
        )
        
        # Forward to channel
        forwarded_id = None
        try:
            if message.document:
                fwd = await client.send_document(BIN_CHANNEL, media.file_id, caption=f"📁 {file_name}")
            elif message.video:
                fwd = await client.send_video(BIN_CHANNEL, media.file_id, caption=f"🎬 {file_name}")
            elif message.audio:
                fwd = await client.send_audio(BIN_CHANNEL, media.file_id, caption=f"🎵 {file_name}")
            forwarded_id = fwd.id
            logger.info(f"✅ Forwarded to channel")
        except Exception as e:
            logger.warning(f"⚠️ Channel forward failed: {e}")
        
        # Download
        file_path = SEED_DIR / file_name
        
        try:
            await message.download(file_name=str(file_path))
            logger.info(f"✅ Downloaded")
        except Exception as e:
            await status.edit_text(f"❌ Download failed: {e}")
            return
        
        # Create torrent
        await status.edit_text(
            f"⚡ **YTS Processing**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 **{file_size_mb:.1f} MB**\n\n"
            f"🔧 Creating torrent..."
        )
        
        try:
            torrent_file, magnet_link = await asyncio.to_thread(create_torrent_file, file_path)
        except Exception as e:
            await status.edit_text(f"❌ Torrent failed: {e}")
            return
        
        # Start seeding
        try:
            info_hash = start_seeding(file_path, torrent_file)
        except Exception as e:
            await status.edit_text(f"❌ Seeding failed: {e}")
            return
        
        total_time = time.time() - start_time
        
        # Save to MongoDB
        if mongo_client:
            torrent_data = {
                'info_hash': info_hash,
                'file_name': file_name,
                'file_size': file_size,
                'magnet_link': magnet_link,
                'torrent_file': str(torrent_file),
                'bin_channel_msg_id': forwarded_id,
                'created_at': datetime.utcnow(),
                'user_id': message.from_user.id,
                'processing_time': total_time
            }
            await asyncio.to_thread(save_to_mongodb, torrent_data)
        
        await status.delete()
        
        # Send results
        caption = (
            f"⚡ **YTS ULTRA FAST**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 {file_size_mb:.1f} MB\n"
            f"⚡ {total_time:.1f}s\n"
            f"🔑 `{info_hash[:20]}...`\n\n"
            f"🚀 **SEEDING LIKE YTS** 🚀"
        )
        
        torrent_msg = await message.reply_document(
            document=str(torrent_file),
            caption=caption,
            file_name=torrent_file.name
        )
        
        await client.send_message(
            chat_id=message.chat.id,
            text=f"🧲 **Magnet:**\n`{magnet_link}`",
            reply_to_message_id=torrent_msg.id
        )
        
        logger.info(f"✅ YTS Complete: {file_name} in {total_time:.1f}s")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)


@app.on_message(filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        "🤖 **YTS-Style Torrent Bot**\n\n"
        "Send files up to **4GB**!\n\n"
        "✅ YTS-optimized seeding\n"
        "✅ Ultra-fast torrents\n"
        "✅ Instant magnets\n\n"
        "**Commands:**\n"
        "/stats - Seeding stats\n"
        "/list - Recent torrents"
    )


@app.on_message(filters.command("stats"))
async def stats_cmd(_, message: Message):
    if not active_torrents:
        await message.reply_text("📊 No active seeds")
        return
    
    text = "📊 **YTS Seeding**\n\n"
    total = 0
    
    for ih, data in list(active_torrents.items())[:10]:
        h = data['handle']
        s = h.status()
        up_gb = s.total_upload / (1024**3)
        total += up_gb
        
        text += (
            f"📄 `{data['name'][:25]}`\n"
            f"⬆️ {up_gb:.2f}GB | 🌱{s.num_seeds} 👥{s.num_peers}\n\n"
        )
    
    text += f"**Total:** {total:.2f} GB uploaded"
    await message.reply_text(text)


@app.on_message(filters.command("list"))
async def list_cmd(_, message: Message):
    if not mongo_client:
        await message.reply_text("❌ Database unavailable")
        return
    
    try:
        docs = list(torrents_collection.find().sort("created_at", -1).limit(10))
        if not docs:
            await message.reply_text("📂 No torrents yet")
            return
        
        text = "📂 **Recent Torrents**\n\n"
        for d in docs:
            mb = d['file_size'] / (1024**2)
            text += f"📄 `{d['file_name'][:35]}`\n📦 {mb:.1f}MB\n\n"
        
        await message.reply_text(text)
    except Exception as e:
        await message.reply_text(f"❌ {e}")


async def main():
    """Main function"""
    await app.start()
    logger.info("✅ YTS Bot Online!")
    
    if OWNER_ID != 0:
        try:
            await app.send_message(OWNER_ID, "✅ YTS Bot started!")
        except:
            pass
    
    # Start monitor
    monitor_task = asyncio.create_task(lt_monitor_loop())
    
    # Keep running
    await idle()
    
    # Cleanup
    monitor_task.cancel()
    await app.stop()
    lt_session.pause()
    if mongo_client:
        mongo_client.close()


if __name__ == "__main__":
    logger.info("🚀 YTS-STYLE TORRENT BOT")
    logger.info("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
