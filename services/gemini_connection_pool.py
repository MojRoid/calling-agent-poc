"""
Gemini Connection Pool Manager
Maintains pre-established Gemini connections to reduce call setup latency
"""
import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from services.gemini_client import GeminiLiveClient
from config import DEFAULT_SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)

class GeminiConnectionPool:
    """Manages a pool of pre-warmed Gemini connections"""
    
    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.available_connections: asyncio.Queue = asyncio.Queue()
        self.in_use_connections: Dict[str, GeminiLiveClient] = {}
        self._running = False
        self._maintenance_task = None
        
    async def start(self):
        """Start the connection pool"""
        logger.info(f"Starting Gemini connection pool with size {self.pool_size}")
        self._running = True
        
        # Create initial connections
        await self._refill_pool()
        
        # Start maintenance task
        self._maintenance_task = asyncio.create_task(self._maintain_pool())
        logger.info("✅ Gemini connection pool started")
        
    async def stop(self):
        """Stop the connection pool and close all connections"""
        logger.info("Stopping Gemini connection pool")
        self._running = False
        
        # Cancel maintenance task
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
                
        # Close all connections
        while not self.available_connections.empty():
            try:
                client = self.available_connections.get_nowait()
                await self._close_connection(client)
            except asyncio.QueueEmpty:
                break
                
        for client in list(self.in_use_connections.values()):
            await self._close_connection(client)
            
        logger.info("✅ Gemini connection pool stopped")
        
    async def acquire(self, call_sid: str) -> Optional[GeminiLiveClient]:
        """
        Acquire a pre-warmed connection from the pool
        
        Args:
            call_sid: The Twilio call SID to associate with this connection
            
        Returns:
            A connected GeminiLiveClient or None if unavailable
        """
        try:
            # Try to get a connection immediately (non-blocking)
            try:
                client = self.available_connections.get_nowait()
                logger.info(f"🚀 Acquired pre-warmed Gemini connection for call {call_sid}")
            except asyncio.QueueEmpty:
                logger.warning("No pre-warmed connections available, creating new one")
                client = None
                
            # Validate existing connection or create new one
            if client and client._connected:
                self.in_use_connections[call_sid] = client
                # Trigger refill in background
                asyncio.create_task(self._refill_pool())
                return client
            else:
                if client:
                    await self._close_connection(client)
                    
                # Create a new connection
                client = await self._create_connection()
                if client:
                    self.in_use_connections[call_sid] = client
                    logger.info(f"Created new Gemini connection for call {call_sid}")
                    
                return client
                
        except Exception as e:
            logger.error(f"Error acquiring connection: {e}")
            return None
        
    async def release(self, call_sid: str):
        """
        Release a connection after use
        
        Args:
            call_sid: The Twilio call SID to release
        """
        client = self.in_use_connections.pop(call_sid, None)
        if client:
            # Always close connections after use (don't reuse for different calls)
            await self._close_connection(client)
            logger.info(f"Released and closed connection for call {call_sid}")
            # Trigger refill
            asyncio.create_task(self._refill_pool())
            
    async def _create_connection(self) -> Optional[GeminiLiveClient]:
        """Create a new Gemini connection"""
        try:
            logger.info("Creating new Gemini connection...")
            client = GeminiLiveClient()
            success = await client.connect(system_instruction=DEFAULT_SYSTEM_INSTRUCTIONS)
            
            if success:
                logger.info("✅ Successfully created new Gemini connection")
                return client
            else:
                logger.error("❌ Failed to create Gemini connection")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Gemini connection: {e}")
            return None
            
    async def _close_connection(self, client: GeminiLiveClient):
        """Close a Gemini connection safely"""
        try:
            await asyncio.wait_for(client.close(), timeout=5.0)
            logger.debug("Closed Gemini connection")
        except asyncio.TimeoutError:
            logger.warning("Timeout closing Gemini connection")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            
    async def _refill_pool(self):
        """Refill the pool to the desired size"""
        if not self._running:
            return
            
        current_size = self.available_connections.qsize()
        in_use = len(self.in_use_connections)
        needed = self.pool_size - current_size - in_use
        
        if needed > 0:
            logger.info(f"Refilling pool: current={current_size}, in_use={in_use}, needed={needed}")
            
            # Create connections one by one to avoid overwhelming the API
            for i in range(needed):
                if not self._running:
                    break
                    
                client = await self._create_connection()
                if client:
                    try:
                        self.available_connections.put_nowait(client)
                        logger.info(f"Added connection to pool ({i+1}/{needed})")
                    except asyncio.QueueFull:
                        await self._close_connection(client)
                        
                # Small delay between connections
                if i < needed - 1:
                    await asyncio.sleep(0.5)
                    
    async def _maintain_pool(self):
        """Maintain the connection pool"""
        while self._running:
            try:
                # Refill pool if needed
                await self._refill_pool()
                
                # Log pool status
                available = self.available_connections.qsize()
                in_use = len(self.in_use_connections)
                logger.info(f"Pool status: {available} available, {in_use} in use")
                
                # Wait before next maintenance cycle
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                logger.info("Pool maintenance task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pool maintenance: {e}")
                await asyncio.sleep(30)

# Global connection pool instance
connection_pool = GeminiConnectionPool(pool_size=2)  # Start with 2 pre-warmed connections 