"""One-time interactive login for the optional Telethon source.

    TG_API_ID=12345 TG_API_HASH=abcdef python -m dronemap.telethon_login
"""
import asyncio
import os


async def main() -> None:
    from telethon import TelegramClient  # type: ignore

    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ.get("TG_SESSION", "data/dronemap")
    os.makedirs(os.path.dirname(session) or ".", exist_ok=True)
    client = TelegramClient(session, api_id, api_hash)
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name}. Session saved to {session}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
