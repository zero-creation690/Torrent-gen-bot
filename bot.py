import os
import asyncio
import libtorrent as lt
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
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
SESSION_NAME = os.getenv("SESSION_NAME", "torrent_userbot")
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL"))  # Format: -100XXXXXXXXXXXXX

# Directories
SEED_DIR = Path("/srv/seeds")
TORRENT_DIR = Path("/srv/torrents")

# Create directories
SEED_DIR.mkdir(parents=True, exist_ok=True)
TORRENT_DIR.mkdir(parents=True, exist_ok=True)

# Trackers
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "https://tracker.openbittorrent.com:443/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://exodus.desync.com:6969/announce"
]

# Initialize Pyrogram client (MTProto)
app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    workdir="/srv"
)

# Libtorrent session
lt_session = lt.session({
    'listen_interfaces': '0.0.0.0:6881',
    'alert_mask': lt.alert.category_t.status_notification
})

# Configure DHT for better peer discovery
lt_session.apply_settings({
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'enable_natpmp': True,
    'announce_to_all_tiers': True,
    'announce_to_all_trackers': True
})

# Add DHT routers
lt_session.add_dht_router("router.bittorrent.com", 6881)
lt_session.add_dht_router("dht.transmissionbt.com", 6881)

# Store active torrents
active_torrents = {}

logger.info("Bot initialized successfully")


def create_torrent_file(file_path: Path) -> tuple[Path, str]:
    """Create .torrent file and magnet link"""
    try:
        fs = lt.file_storage()
        lt.add_files(fs, str(file_path))
        
        t = lt.create_torrent(fs)
        t.set_priv(False)  # Public torrent
        
        # Add all trackers
        for tracker in TRACKERS:
            t.add_tracker(tracker, 0)
        
        t.set_creator("Telegram Torrent Bot")
        t.set_comment(f"Seeded via Telegram | {file_path.name}")
        
        # Generate piece hashes (this is the time-consuming part)
        lt.set_piece_hashes(t, str(file_path.parent))
        
        # Generate and save torrent
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
    """Start seeding the torrent"""
    try:
        info = lt.torrent_info(str(torrent_file))
        
        params = {
            'ti': info,
            'save_path': str(file_path.parent),
            'seed_mode': True,
            'upload_mode': False,
            'auto_managed': True,
            'duplicate_is_error': True
        }
        
        handle = lt_session.add_torrent(params)
        handle.set_max_uploads(-1)  # Unlimited uploads
        handle.set_max_connections(-1)  # Unlimited connections
        
        info_hash = str(info.info_hash())
        
        active_torrents[info_hash] = {
            'handle': handle,
            'file_path': file_path,
            'torrent_file': torrent_file,
            'started': time.time(),
            'name': file_path.name
        }
        
        logger.info(f"Started seeding: {file_path.name} | Hash: {info_hash[:16]}")
        return info_hash
        
    except Exception as e:
        logger.error(f"Error starting seeder: {e}")
        raise


@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client: Client, message: Message):
    """Handle all incoming files"""
    try:
        # Determine media type and get file info
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
        
        # Log incoming file
        logger.info(f"Received file: {file_name} ({file_size_gb:.2f} GB)")
        
        # Check size limit
        if file_size > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File exceeds 4GB limit!")
            return
        
        # Initial status
        status = await message.reply_text(
            f"⚡ **Processing file...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 Size: **{file_size_gb:.2f} GB**\n\n"
            f"🔄 Forwarding to storage..."
        )
        
        # Step 1: Forward to BIN_CHANNEL for permanent storage
        try:
            await message.forward(BIN_CHANNEL)
            logger.info(f"Forwarded {file_name} to BIN_CHANNEL")
        except Exception as e:
            await status.edit_text(f"❌ Failed to forward to storage: {e}")
            logger.error(f"Forward error: {e}")
            return
        
        # Step 2: Download file locally
        await status.edit_text(
            f"⚡ **Processing file...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 Size: **{file_size_gb:.2f} GB**\n\n"
            f"✅ Stored in channel\n"
            f"📥 Downloading... 0%"
        )
        
        file_path = SEED_DIR / file_name
        last_update = [0]
        
        async def progress(current, total):
            now = time.time()
            if now - last_update[0] >= 3:  # Update every 3 seconds
                last_update[0] = now
                percent = (current / total) * 100
                try:
                    await status.edit_text(
                        f"⚡ **Processing file...**\n\n"
                        f"📄 `{file_name}`\n"
                        f"📦 Size: **{file_size_gb:.2f} GB**\n\n"
                        f"✅ Stored in channel\n"
                        f"📥 Downloading... {percent:.1f}%"
                    )
                except:
                    pass
        
        try:
            await message.download(file_name=str(file_path), progress=progress)
            logger.info(f"Downloaded {file_name} successfully")
        except Exception as e:
            await status.edit_text(f"❌ Download failed: {e}")
            logger.error(f"Download error: {e}")
            return
        
        # Step 3: Create torrent
        await status.edit_text(
            f"⚡ **Processing file...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 Size: **{file_size_gb:.2f} GB**\n\n"
            f"✅ Stored in channel\n"
            f"✅ Downloaded locally\n"
            f"🔧 Creating torrent..."
        )
        
        try:
            torrent_file, magnet_link = await asyncio.get_event_loop().run_in_executor(
                None, create_torrent_file, file_path
            )
        except Exception as e:
            await status.edit_text(f"❌ Torrent creation failed: {e}")
            logger.error(f"Torrent creation error: {e}")
            return
        
        # Step 4: Start seeding
        await status.edit_text(
            f"⚡ **Processing file...**\n\n"
            f"📄 `{file_name}`\n"
            f"📦 Size: **{file_size_gb:.2f} GB**\n\n"
            f"✅ Stored in channel\n"
            f"✅ Downloaded locally\n"
            f"✅ Torrent created\n"
            f"🌱 Starting seeder..."
        )
        
        try:
            info_hash = start_seeding(file_path, torrent_file)
        except Exception as e:
            await status.edit_text(f"❌ Seeding failed: {e}")
            logger.error(f"Seeding error: {e}")
            return
        
        # Final response with magnet link and torrent file
        await status.delete()
        
        caption = (
            f"✅ **Seeding Active**\n\n"
            f"📄 **File:** `{file_name}`\n"
            f"📦 **Size:** {file_size_gb:.2f} GB\n"
            f"🔑 **Hash:** `{info_hash[:32]}`\n\n"
            f"🧲 **Magnet Link:**\n"
            f"`{magnet_link}`\n\n"
            f"⚠️ **Seeding started — keep bot online to keep torrent alive.**"
        )
        
        # Send .torrent file with caption
        await message.reply_document(
            document=str(torrent_file),
            caption=caption,
            file_name=torrent_file.name
        )
        
        logger.info(f"✅ Complete: {file_name} | Hash: {info_hash[:16]}")
        
    except Exception as e:
        logger.error(f"Critical error in handle_file: {e}", exc_info=True)
        await message.reply_text(f"❌ Critical error: {e}")


@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    """Show seeding stats"""
    if not active_torrents:
        await message.reply_text("📊 No torrents currently seeding.")
        return
    
    stats = "📊 **Active Torrents**\n\n"
    
    for info_hash, data in active_torrents.items():
        handle = data['handle']
        status = handle.status()
        
        uptime_sec = time.time() - data['started']
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        
        stats += (
            f"📄 **{data['name']}**\n"
            f"🔑 `{info_hash[:24]}...`\n"
            f"⬆️ Uploaded: {status.total_upload / (1024**3):.2f} GB\n"
            f"🌱 Seeds: {status.num_seeds} | Peers: {status.num_peers}\n"
            f"⏱ Uptime: {hours}h {minutes}m\n\n"
        )
    
    await message.reply_text(stats)


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Welcome message"""
    await message.reply_text(
        "🤖 **Telegram Torrent Userbot**\n\n"
        "Send me any file up to 4GB!\n\n"
        "**I will:**\n"
        "✅ Store it permanently in your bin channel\n"
        "✅ Save it locally for seeding\n"
        "✅ Create a .torrent file\n"
        "✅ Generate magnet link\n"
        "✅ Start seeding immediately\n\n"
        "**Commands:**\n"
        "/stats - View active torrents\n"
        "/start - Show this message"
    )


async def save_torrents_on_shutdown():
    """Save torrent session on shutdown"""
    logger.info("Saving torrent session...")
    lt_session.save_state()
    logger.info("Session saved")


if __name__ == "__main__":
    logger.info("🚀 Starting Telegram Torrent Userbot...")
    logger.info(f"📁 Seed directory: {SEED_DIR}")
    logger.info(f"📁 Torrent directory: {TORRENT_DIR}")
    logger.info(f"📢 Bin channel: {BIN_CHANNEL}")
    
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        asyncio.run(save_torrents_on_shutdown())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
