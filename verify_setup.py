#!/usr/bin/env python3
"""
Verify Telegram Bot Setup
Run this to check if your bot can access the bin channel
"""

import os
from pyrogram import Client
import asyncio

API_ID = int(os.getenv("API_ID", input("Enter API_ID: ")))
API_HASH = os.getenv("API_HASH", input("Enter API_HASH: "))
BOT_TOKEN = os.getenv("BOT_TOKEN", input("Enter BOT_TOKEN: "))
BIN_CHANNEL = int(os.getenv("BIN_CHANNEL", input("Enter BIN_CHANNEL: ")))

app = Client(
    "verify_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def verify():
    print("=" * 50)
    print("🔍 VERIFYING TELEGRAM BOT SETUP")
    print("=" * 50)
    
    async with app:
        print(f"\n✅ Bot logged in successfully!")
        
        # Get bot info
        me = await app.get_me()
        print(f"🤖 Bot Username: @{me.username}")
        print(f"🆔 Bot ID: {me.id}")
        
        # Check bin channel
        print(f"\n🔍 Checking Bin Channel: {BIN_CHANNEL}")
        
        try:
            chat = await app.get_chat(BIN_CHANNEL)
            print(f"✅ Channel found!")
            print(f"📢 Channel Title: {chat.title}")
            print(f"📝 Channel Type: {chat.type}")
            
            # Check if bot is admin
            try:
                member = await app.get_chat_member(BIN_CHANNEL, me.id)
                print(f"👤 Bot Status: {member.status}")
                
                if member.status in ["administrator", "creator"]:
                    print(f"✅ Bot has admin rights!")
                else:
                    print(f"❌ Bot is NOT an admin!")
                    print(f"⚠️ Add bot as admin to the channel!")
            except Exception as e:
                print(f"❌ Cannot check admin status: {e}")
                print(f"⚠️ Make sure bot is added to channel!")
            
            # Try to send a test message
            print(f"\n🧪 Testing message send...")
            try:
                test_msg = await app.send_message(
                    BIN_CHANNEL,
                    "✅ **Test Message**\n\nBot can send messages to this channel!"
                )
                print(f"✅ Test message sent successfully!")
                print(f"🔗 Message ID: {test_msg.id}")
                
                # Delete test message
                await test_msg.delete()
                print(f"🗑️ Test message deleted")
                
            except Exception as e:
                print(f"❌ Cannot send message: {e}")
                print(f"⚠️ Make sure bot is admin with 'Post Messages' permission!")
        
        except Exception as e:
            print(f"❌ Channel not found or not accessible: {e}")
            print(f"\n📋 TROUBLESHOOTING:")
            print(f"1. Create a private channel")
            print(f"2. Add your bot (@{me.username}) to the channel")
            print(f"3. Make bot an ADMIN with 'Post Messages' permission")
            print(f"4. Get channel ID:")
            print(f"   - Forward any message from channel to @userinfobot")
            print(f"   - Copy the channel ID (format: -100XXXXXXXXXX)")
            print(f"5. Update BIN_CHANNEL in .env file")
    
    print("\n" + "=" * 50)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(verify())
