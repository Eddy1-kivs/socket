import asyncio
import websockets
import json
import redis.asyncio as aioredis
import os
import base64
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_CHANNEL = 'chat_messages'

# Redis client setup
redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
connected_clients = set()

async def notify_clients(message: str):
    """Notify all connected WebSocket clients with a given message."""
    if connected_clients:
        await asyncio.gather(*[client.send(message) for client in connected_clients])

async def handle_connection(websocket, path):
    """Handle new WebSocket connections for real-time messaging."""
    connected_clients.add(websocket)
    print(f"New client connected: {websocket.remote_address}")

    try:
        async for message in websocket:
            print(f"Received message from {websocket.remote_address}: {message}")
            data = json.loads(message)
            receiver = data.get("receiver")
            sender = data.get("sender")
            text_message = data.get("message", "")
            file_data = data.get("file", None)

            # Handle file data if present
            if file_data:
                file_bytes = base64.b64decode(file_data)
                file_path = f"uploads/{sender}_to_{receiver}_file"
                with open(file_path, "wb") as file:
                    file.write(file_bytes)

            await redis_client.publish(REDIS_CHANNEL, json.dumps(data))
            await notify_clients(message)

    except websockets.ConnectionClosed:
        print(f"Client disconnected: {websocket.remote_address}")
    finally:
        connected_clients.remove(websocket)

async def redis_listener():
    """Listen for Redis messages and broadcast them to WebSocket clients."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    print(f"Subscribed to Redis channel: {REDIS_CHANNEL}")

    async for message in pubsub.listen():
        if message["type"] == "message":
            decoded_message = message["data"].decode("utf-8")
            await notify_clients(decoded_message)

async def main():
    websocket_server = await websockets.serve(handle_connection, "0.0.0.0", 8002)
    print("WebSocket server started on ws://0.0.0.0:8002")
    asyncio.create_task(redis_listener())
    await websocket_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
