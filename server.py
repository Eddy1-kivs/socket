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
connected_clients = {}  # Dictionary to track connections by userId

async def notify_clients(message: str):
    """Notify all connected WebSocket clients with a given message."""
    if connected_clients:
        await asyncio.gather(*[client.send(message) for client in connected_clients.values()])

async def broadcast_user_status(user_id: str, status: str):
    """Broadcast online/offline status of a user to all clients."""
    status_message = json.dumps({"userId": user_id, "status": status})
    await notify_clients(status_message)

async def handle_connection(websocket, path):
    """Handle new WebSocket connections for real-time messaging."""
    user_id = None
    try:
        # First, receive the userId and status (online/offline) from the client
        initial_message = await websocket.recv()
        initial_data = json.loads(initial_message)
        user_id = initial_data.get("userId")
        status = initial_data.get("status")

        if not user_id:
            print(f"User without ID tried to connect from {websocket.remote_address}")
            await websocket.close()
            return

        # Mark the user as online and broadcast the status
        print(f"User {user_id} connected from {websocket.remote_address} and is now {status}")
        connected_clients[user_id] = websocket
        await broadcast_user_status(user_id, "online")

        # Handle incoming messages
        async for message in websocket:
            print(f"Received message from user {user_id}: {message}")
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
 
            # Publish the message to Redis
            await redis_client.publish(REDIS_CHANNEL, json.dumps(data))

            # Notify clients about the message
            await notify_clients(message)

    except websockets.ConnectionClosed:
        print(f"User {user_id} disconnected from {websocket.remote_address}")
    finally:
        # Remove client from connected_clients and mark them as offline
        if user_id in connected_clients:
            del connected_clients[user_id]
            await broadcast_user_status(user_id, "offline")  # Broadcast offline status

async def redis_listener():
    """Listen for Redis messages and broadcast them to WebSocket clients."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe('chat_messages', 'notifications')  # Subscribing to both channels
    print(f"Subscribed to Redis channels: chat_messages, notifications")

    async for message in pubsub.listen():
        if message["type"] == "message":
            decoded_message = message["data"].decode("utf-8")

            # Check which channel the message came from
            if message["channel"].decode("utf-8") == "notifications":
                notification_data = json.loads(decoded_message)
                # Notify clients about the new notification
                await notify_clients(json.dumps({
                    "type": "notification",
                    "freelancer_notification": notification_data.get("freelancer"),
                    "client_notification": notification_data.get("client")
                }))
            else:
                # Handle chat messages as before
                await notify_clients(decoded_message)

async def main():
    websocket_server = await websockets.serve(handle_connection, "0.0.0.0", 8002)
    print("WebSocket server started on ws://0.0.0.0:8002")
    asyncio.create_task(redis_listener())
    await websocket_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
