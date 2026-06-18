"""Hermes TCP Client — agent bus connection for python daemons.

Links python claws directly to the Node-based Hermes message bus (port 8520).
Provides real-time event publishing and subscription handling with auto-reconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Coroutine

logger = logging.getLogger("arcanea-claw.hermes")

class HermesClient:
    """Client to interact with the Hermes JSONL-over-TCP broker."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8520) -> None:
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.agent_id: str | None = None
        self.subscriptions: set[str] = set()
        self.handlers: dict[str, list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]]] = {}
        self.connected = False
        self._send_queue: asyncio.Queue[str] = asyncio.Queue()
        self._write_task: asyncio.Task | None = None

    async def connect(self, agent_id: str) -> bool:
        """Connect to the Hermes message bus and register this agent."""
        self.agent_id = agent_id
        try:
            logger.info("Connecting to Hermes Message Bus at %s:%d...", self.host, self.port)
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            logger.info("Hermes connected. Registering agent %s...", agent_id)
            
            # Send registration packet
            await self._send_packet({"type": "register", "agentId": agent_id})
            
            # Re-subscribe to any active topics
            for topic in self.subscriptions:
                await self._send_packet({"type": "subscribe", "topic": topic})

            # Start background writer task
            self._write_task = asyncio.create_task(self._write_loop())
            return True
        except Exception as exc:
            logger.warning("Failed to connect to Hermes: %s", exc)
            self.connected = False
            return False

    async def subscribe(
        self, 
        topic: str, 
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Subscribe to a topic with a callback handler."""
        self.subscriptions.add(topic)
        self.handlers.setdefault(topic, []).append(handler)
        if self.connected:
            await self._send_packet({"type": "subscribe", "topic": topic})
        logger.info("Subscribed to topic: %s", topic)

    async def publish(self, topic: str, payload: dict[str, Any], priority: str = "normal") -> None:
        """Publish a message/event to the bus."""
        if not self.agent_id:
            logger.warning("Cannot publish message before registration")
            return
        
        packet = {
            "type": "publish",
            "message": {
                "from": self.agent_id,
                "to": "*",
                "topic": topic,
                "payload": payload,
                "priority": priority,
                "timestamp": int(time.time() * 1000)
            }
        }
        if self.connected:
            await self._send_packet(packet)
            logger.debug("Published event %s to Hermes", topic)
        else:
            logger.warning("Hermes disconnected. Queueing publish for event %s", topic)
            # We queue it for when we reconnect
            self._send_queue.put_nowait(json.dumps(packet) + "\n")

    async def _send_packet(self, packet: dict[str, Any]) -> None:
        """Helper to write packet followed by newline."""
        if self.writer and self.connected:
            try:
                line = json.dumps(packet) + "\n"
                self.writer.write(line.encode("utf-8"))
                await self.writer.drain()
            except Exception as exc:
                logger.warning("Error writing packet to Hermes: %s", exc)
                self.connected = False

    async def _write_loop(self) -> None:
        """Background loop to drain the send queue."""
        while self.connected and self.writer:
            try:
                line = await self._send_queue.get()
                self.writer.write(line.encode("utf-8"))
                await self.writer.drain()
                self._send_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in Hermes write loop: %s", exc)
                self.connected = False
                break

    async def listen_loop(self, shutdown_event: asyncio.Event) -> None:
        """Listen for incoming JSONL messages and execute handlers."""
        backoff = 1
        while not shutdown_event.is_set():
            if not self.connected:
                # Cleanup write task
                if self._write_task:
                    self._write_task.cancel()
                    self._write_task = None
                
                if self.agent_id:
                    success = await self.connect(self.agent_id)
                    if success:
                        backoff = 1
                    else:
                        logger.info("Retrying Hermes connection in %ds...", backoff)
                        try:
                            await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
                        except asyncio.TimeoutError:
                            pass
                        backoff = min(backoff * 2, 60)
                        continue

            try:
                assert self.reader is not None
                line_bytes = await self.reader.readline()
                if not line_bytes:
                    logger.warning("Hermes TCP connection closed by remote peer")
                    self.connected = False
                    continue

                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue

                packet = json.loads(line)
                status = packet.get("status")
                p_type = packet.get("type")

                if status == "error":
                    logger.error("Hermes error response: %s", packet.get("error"))
                    continue

                if p_type == "message":
                    message = packet.get("message", {})
                    topic = message.get("topic")
                    if topic in self.handlers:
                        for handler in self.handlers[topic]:
                            asyncio.create_task(handler(message))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in Hermes listen loop: %s", exc)
                self.connected = False
                await asyncio.sleep(1)

        # Cleanup on shutdown
        if self._write_task:
            self._write_task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
        self.reader = None
        self.connected = False
        logger.info("Hermes client loop terminated.")

# Global client instance
_client: HermesClient | None = None

def get_client(host: str = "127.0.0.1", port: int = 8520) -> HermesClient:
    """Get or create the global Hermes client instance."""
    global _client
    if _client is None:
        _client = HermesClient(host, port)
    return _client
