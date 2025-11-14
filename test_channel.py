#!/usr/bin/env python3
"""Test if bot can access and send to BIN_CHANNEL"""

import os
import asyncio
from pyrogram import Client

# Load from environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL"))

print(f"Testing channel: {BIN_CHANNEL}")

app = Client(
    "test_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def test_channel():
    async with app:
        print("\n" + "="*50)
        print("🧪 TESTING CHANNEL ACCESS")
        print("="*50)
        
        # Get bot info
        me = await app.get_me()
        print(f"\n✅ Bot: @{me.username} (ID: {me.id})")
        
        # Test 1: Get channel info
        print(f"\n📋 Test 1: Getting channel info...")
        try:
            chat = await app.get_chat(BIN_CHANNEL)
            print(f"✅ Channel found: {chat.title}")
            print(f"   Type: {chat.type}")
            print(f"   Username: @{chat.username if chat.username else 'Private'}")
        except Exception as e:
            print(f"❌ Failed: {e}")
            return
        
        # Test 2: Check admin status
        print(f"\n👤 Test 2: Checking admin status...")
        try:
            member = await app.get_chat_member(BIN_CHANNEL, me.id)
            print(f"✅ Status: {member.status}")
            if member.status not in ["administrator", "creator"]:
                print(f"❌ Bot is not admin!")
                return
        except Exception as e:
            print(f"❌ Failed: {e}")
            return
        
        # Test 3: Send text message
        print(f"\n💬 Test 3: Sending text message...")
        try:
            msg = await app.send_message(
                BIN_CHANNEL,
                "✅ **Test Message**\n\nBot can send messages!"
            )
            print(f"✅ Message sent! ID: {msg.id}")
            await asyncio.sleep(2)
            await msg.delete()
            print(f"✅ Message deleted")
        except Exception as e:
            print(f"❌ Failed: {e}")
            print(f"   Make sure bot has 'Post Messages' permission")
            return
        
        # Test 4: Send document (if exists)
        print(f"\n📄 Test 4: Testing document send...")
        test_file = "/tmp/test.txt"
        try:
            # Create test file
            with open(test_file, "w") as f:
                f.write("This is a test file for Telegram Torrent Bot")
            
            msg = await app.send_document(
                BIN_CHANNEL,
                test_file,
                caption="✅ Test document upload"
            )
            print(f"✅ Document sent! ID: {msg.id}")
            await asyncio.sleep(2)
            await msg.delete()
            print(f"✅ Document deleted")
            os.remove(test_file)
        except Exception as e:
            print(f"❌ Failed: {e}")
            return
        
        print("\n" + "="*50)
        print("✅ ALL TESTS PASSED!")
        print("="*50)
        print("\n🎉 Your bot is ready to use!")
        print(f"📢 Channel ID: {BIN_CHANNEL}")
        print(f"🤖 Bot: @{me.username}")

if __name__ == "__main__":
    asyncio.run(test_channel())
