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
from collections import deque

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

# ULTRA FAST Trackers (YTS + Best)
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://9.rarbg.com:2810/announce",
    "udp://tracker.cyberia.is:6969/announce",
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
    logger.warning(f"⚠️ MongoDB: {e}")

# Bot
app = Client(
    f"yts_{int(time.time())}",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/srv",
    workers=16  # More workers for parallel processing
)

# ULTRA FAST Libtorrent
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881',
    'alert_mask': lt.alert.category_t.all_categories,
})

settings = {
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'connections_limit': 10000,
    'upload_rate_limit': 0,
    'download_rate_limit': 0,
    'active_downloads': -1,
    'active_seeds': -1,
    'active_limit': -1,
    'max_out_request_queue': 10000,
    'unchoke_slots_limit': 500,
    'cache_size': 4096,
}
lt_session.apply_settings(settings)

# DHT routers
lt_session.add_dht_router("router.bittorrent.com", 6881)
lt_session.add_dht_router("dht.transmissionbt.com", 6881)
lt_session.add_dht_router("router.utorrent.com", 6881)

active_torrents = {}
processing_queue = deque()
active_tasks = {}

logger.info("🚀 Multi-file YTS bot initialized")


def create_torrent(file_path: Path):
    """Create torrent - YTS optimized"""
    fs = lt.file_storage()
    lt.add_files(fs, str(file_path))
    
    file_size = file_path.stat().st_size
    
    # YTS-style small pieces for FAST start
    if file_size < 100 * 1024 * 1024:  # < 100MB
        piece_size = 128 * 1024  # 128KB
    elif file_size < 500 * 1024 * 1024:  # < 500MB
        piece_size = 256 * 1024  # 256KB
    elif file_size < 1024 * 1024 * 1024:  # < 1GB
        piece_size = 512 * 1024  # 512KB
    else:
        piece_size = 1024 * 1024  # 1MB
    
    t = lt.create_torrent(fs, piece_size=piece_size)
    t.set_priv(False)
    
    for tracker in TRACKERS:
        t.add_tracker(tracker, 0)
    
    t.set_creator("YTS Ultra Bot")
    t.set_comment(f"⚡ FAST | {file_path.name}")
    
    lt.set_piece_hashes(t, str(file_path.parent))
    
    torrent_data = lt.bencode(t.generate())
    torrent_file = TORRENT_DIR / f"{file_path.stem}.torrent"
    
    with open(torrent_file, "wb") as f:
        f.write(torrent_data)
    
    info = lt.torrent_info(str(torrent_file))
    magnet = lt.make_magnet_uri(info)
    
    logger.info(f"⚡ Torrent: {piece_size/1024}KB pieces")
    return torrent_file, magnet


def start_seeding(file_path: Path, torrent_file: Path):
    """Start YTS-style seeding"""
    info = lt.torrent_info(str(torrent_file))
    
    atp = lt.add_torrent_params()
    atp.ti = info
    atp.save_path = str(file_path.parent)
    atp.flags |= lt.torrent_flags.seed_mode
    atp.flags |= lt.torrent_flags.upload_mode
    atp.flags |= lt.torrent_flags.super_seeding
    
    handle = lt_session.add_torrent(atp)
    handle.set_max_uploads(-1)
    handle.set_max_connections(-1)
    handle.set_upload_limit(-1)
    handle.force_reannounce(0, -1)
    
    info_hash = str(info.info_hash())
    active_torrents[info_hash] = {
        'handle': handle,
        'name': file_path.name,
        'started': time.time()
    }
    
    return info_hash


async def process_file(client, message: Message, media, name: str):
    """Process a single file (runs in parallel)"""
    user_id = message.from_user.id
    task_id = f"{user_id}_{int(time.time() * 1000)}"
    
    try:
        size_mb = media.file_size / (1024**2)
        start_time = time.time()
        
        logger.info(f"🔄 [{task_id}] Processing: {name}")
        
        # Status
        status = await message.reply_text(
            f"⚡ **Processing {len(active_tasks) + 1}/{len(active_tasks) + len(processing_queue) + 1}**\n\n"
            f"📄 `{name[:40]}`\n"
            f"📦 {size_mb:.1f} MB\n\n"
            f"⏳ Downloading..."
        )
        
        # Forward to channel
        if BIN_CHANNEL != 0:
            try:
                if message.document:
                    await client.send_document(BIN_CHANNEL, media.file_id, caption=f"📁 {name}")
                elif message.video:
                    await client.send_video(BIN_CHANNEL, media.file_id, caption=f"🎬 {name}")
                else:
                    await client.send_audio(BIN_CHANNEL, media.file_id, caption=f"🎵 {name}")
            except Exception as e:
                logger.warning(f"[{task_id}] Channel: {e}")
        
        # Download with progress
        file_path = SEED_DIR / name
        
        last_update = [0]  # Use list to modify in nested function
        
        async def progress(current, total):
            if time.time() - last_update[0] > 3:  # Update every 3 sec
                percent = (current / total) * 100
                try:
                    await status.edit_text(
                        f"⚡ **Processing {len(active_tasks)}/{len(active_tasks) + len(processing_queue)}**\n\n"
                        f"📄 `{name[:40]}`\n"
                        f"📦 {size_mb:.1f} MB\n\n"
                        f"⏳ Downloading: {percent:.0f}%"
                    )
                except:
                    pass
                last_update[0] = time.time()
        
        await message.download(file_name=str(file_path), progress=progress)
        download_time = time.time() - start_time
        logger.info(f"✅ [{task_id}] Downloaded in {download_time:.1f}s")
        
        # Create torrent
        await status.edit_text(
            f"⚡ **Processing {len(active_tasks)}/{len(active_tasks) + len(processing_queue)}**\n\n"
            f"📄 `{name[:40]}`\n"
            f"📦 {size_mb:.1f} MB\n\n"
            f"🔧 Creating torrent..."
        )
        
        torrent_file, magnet = await asyncio.to_thread(create_torrent, file_path)
        
        # Start seeding
        info_hash = start_seeding(file_path, torrent_file)
        
        total_time = time.time() - start_time
        
        # Save to DB
        if mongo_client:
            try:
                torrents_collection.insert_one({
                    'info_hash': info_hash,
                    'file_name': name,
                    'file_size': media.file_size,
                    'magnet_link': magnet,
                    'created_at': datetime.utcnow(),
                    'user_id': user_id,
                    'processing_time': total_time
                })
            except:
                pass
        
        # Reply
        await status.delete()
        
        await message.reply_document(
            document=str(torrent_file),
            caption=(
                f"⚡ **YTS ULTRA FAST**\n\n"
                f"📄 `{name[:45]}`\n"
                f"📦 {size_mb:.1f} MB\n"
                f"⚡ {total_time:.1f}s\n"
                f"🔑 `{info_hash[:16]}...`\n\n"
                f"🚀 **SEEDING NOW!**"
            )
        )
        
        await message.reply_text(
            f"🧲 **Magnet Link:**\n`{magnet}`",
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ [{task_id}] DONE in {total_time:.1f}s")
        
    except Exception as e:
        logger.error(f"❌ [{task_id}] ERROR: {e}", exc_info=True)
        try:
            await message.reply_text(f"❌ Error: {str(e)[:100]}")
        except:
            pass
    finally:
        if task_id in active_tasks:
            del active_tasks[task_id]


# Handlers
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "🤖 **YTS Multi-File Torrent Bot**\n\n"
        "✅ Send **multiple files** at once!\n"
        "✅ Ultra-fast parallel processing\n"
        "✅ YTS-optimized seeding\n"
        "✅ Small pieces = Fast downloads\n\n"
        "**Commands:**\n"
        "/start - This message\n"
        "/stats - Active torrents\n"
        "/queue - Processing queue\n\n"
        "**Just send files!** 📁"
    )


@app.on_message(filters.command("queue"))
async def queue_cmd(client, message):
    text = f"**Queue Status:**\n\n"
    text += f"⚡ Active: {len(active_tasks)}\n"
    text += f"⏳ Waiting: {len(processing_queue)}\n"
    text += f"🌱 Seeding: {len(active_torrents)}\n"
    await message.reply_text(text)


@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    if not active_torrents:
        await message.reply_text("No active torrents")
        return
    
    text = "**🌱 Active Torrents:**\n\n"
    total_gb = 0
    
    for ih, data in list(active_torrents.items())[:10]:
        h = data['handle']
        s = h.status()
        up_gb = s.total_upload / (1024**3)
        total_gb += up_gb
        
        text += (
            f"📄 `{data['name'][:30]}`\n"
            f"⬆️ {up_gb:.2f}GB | 🌱{s.num_seeds} 👥{s.num_peers}\n\n"
        )
    
    text += f"**Total Upload:** {total_gb:.2f} GB"
    await message.reply_text(text)


@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client, message):
    """Handle files - with parallel processing"""
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
        
        if media.file_size > 4 * 1024**3:
            await message.reply_text("❌ Max 4GB per file!")
            return
        
        user_id = message.from_user.id
        
        # Add to queue
        processing_queue.append((client, message, media, name))
        
        # Show queue position
        position = len(processing_queue)
        await message.reply_text(
            f"✅ **Added to queue!**\n\n"
            f"📄 `{name[:40]}`\n"
            f"📊 Position: {position}\n"
            f"⚡ Active: {len(active_tasks)}"
        )
        
        # Process queue (max 3 simultaneous)
        while processing_queue and len(active_tasks) < 3:
            client, msg, media, fname = processing_queue.popleft()
            task_id = f"{msg.from_user.id}_{int(time.time() * 1000)}"
            
            task = asyncio.create_task(process_file(client, msg, media, fname))
            active_tasks[task_id] = task
        
    except Exception as e:
        logger.error(f"❌ Handle error: {e}")


@app.on_message(filters.text & ~filters.command(["start", "stats", "queue"]))
async def echo(client, message):
    await message.reply_text(
        "✅ **Bot Online!**\n\n"
        "Send me files (even multiple at once) and I'll create torrents!\n\n"
        f"📊 Active: {len(active_tasks)}\n"
        f"⏳ Queue: {len(processing_queue)}\n"
        f"🌱 Seeding: {len(active_torrents)}"
    )


async def monitor_loop():
    """Monitor torrents and process queue"""
    while True:
        try:
            lt_session.pop_alerts()
            
            # Maintain seeding performance
            for ih, data in list(active_torrents.items()):
                handle = data['handle']
                if handle.is_valid():
                    status = handle.status()
                    if status.state == lt.torrent_status.seeding:
                        handle.set_max_uploads(-1)
                        handle.set_max_connections(-1)
                        handle.force_reannounce(0, -1)
            
            # Process pending queue
            while processing_queue and len(active_tasks) < 3:
                client, msg, media, fname = processing_queue.popleft()
                task_id = f"{msg.from_user.id}_{int(time.time() * 1000)}"
                
                task = asyncio.create_task(process_file(client, msg, media, fname))
                active_tasks[task_id] = task
            
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            await asyncio.sleep(30)


async def main():
    """Main"""
    await app.start()
    me = await app.get_me()
    
    logger.info("=" * 60)
    logger.info(f"✅ YTS MULTI-FILE BOT STARTED")
    logger.info(f"📛 Username: @{me.username}")
    logger.info(f"🆔 Bot ID: {me.id}")
    logger.info(f"⚡ Max parallel: 3 files")
    logger.info("=" * 60)
    
    if OWNER_ID != 0:
        try:
            await app.send_message(
                OWNER_ID, 
                f"✅ **YTS Multi-File Bot Started!**\n\n"
                f"Username: @{me.username}\n"
                f"ID: {me.id}\n\n"
                f"⚡ Can process **3 files simultaneously**\n"
                f"📁 Send multiple files at once!"
            )
        except Exception as e:
            logger.warning(f"⚠️ Owner notify: {e}")
    
    # Start monitor
    monitor_task = asyncio.create_task(monitor_loop())
    
    logger.info("🎧 Listening for files...")
    
    # Keep alive
    try:
        from pyrogram import idle
        await idle()
    except ImportError:
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Stopped")
