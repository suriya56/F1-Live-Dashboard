"""
Cache Manager Module

Implements Redis caching with Cache-Aside pattern for F1 Dashboard.
Uses aioredis for async compatibility with Textual's async nature.
"""

import json
import logging
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import asyncio

# Use aioredis for async Redis operations
try:
    import aioredis
    from aioredis import Redis as AsyncRedis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    AsyncRedis = None

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
DEFAULT_TTL = int(os.environ.get('REDIS_TTL', 3600))  # 1 hour default


class CacheManager:
    """
    Manages Redis caching with Cache-Aside pattern for F1 data.
    
    Pattern:
    1. Check Redis for cached data
    2. If missing, check SQLite database
    3. If missing, fetch from FastF1 API
    4. Store fetched data in both SQLite and Redis for future requests
    """
    
    def __init__(self, redis_url: Optional[str] = None, ttl: int = DEFAULT_TTL):
        self.redis_url = redis_url or DEFAULT_REDIS_URL
        self.ttl = ttl
        self._redis: Optional[AsyncRedis] = None
        self._connected = False
        self._fallback_to_memory = True
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self) -> bool:
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            logger.warning("aioredis not available, using memory cache fallback")
            return False
        
        try:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using memory cache fallback.")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close Redis connection."""
        if self._redis and self._connected:
            await self._redis.close()
            self._connected = False
    
    def _generate_session_key(self, year: int, round_number: int, session_type: str) -> str:
        """Generate a unique cache key for a session."""
        return f"f1dash:session:{year}:{round_number}:{session_type}"
    
    def _generate_event_key(self, year: int, round_number: int) -> str:
        """Generate a unique cache key for an event's sessions list."""
        return f"f1dash:event:{year}:{round_number}"
    
    def _generate_schedule_key(self, year: int) -> str:
        """Generate a cache key for a season's schedule."""
        return f"f1dash:schedule:{year}"
    
    async def get_session_data(
        self, 
        year: int, 
        round_number: int, 
        session_type: str,
        db_manager: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get session data using Cache-Aside pattern.
        
        Order: Redis -> SQLite -> None
        If not in cache, check database. Database misses return None.
        
        Args:
            year: Season year
            round_number: Event round number
            session_type: Session key (FP1, FP2, Q, R, etc.)
            db_manager: Optional DatabaseManager instance for SQLite lookup
        
        Returns:
            Session data dict with 'data', 'drivers', 'columns' keys, or None
        """
        cache_key = self._generate_session_key(year, round_number, session_type)
        session_id = f"{year}_{round_number}_{session_type}"
        
        # 1. Check Redis cache first
        try:
            if self._connected and self._redis:
                cached_data = await self._redis.get(cache_key)
                if cached_data:
                    logger.debug(f"Redis cache hit for {cache_key}")
                    return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
        
        # Check memory fallback
        if not self._connected and self._fallback_to_memory:
            if cache_key in self._memory_cache:
                logger.debug(f"Memory cache hit for {cache_key}")
                return self._memory_cache[cache_key]['data']
        
        # 2. Check SQLite database if db_manager provided
        if db_manager:
            try:
                db_data = db_manager.get_session_results(session_id)
                if db_data:
                    logger.debug(f"Database hit for {session_id}")
                    # Cache in Redis for future requests
                    await self.set_session_data(year, round_number, session_type, db_data)
                    return db_data
            except Exception as e:
                logger.warning(f"Database lookup error: {e}")
        
        logger.debug(f"Cache miss for {cache_key}")
        return None
    
    async def set_session_data(
        self, 
        year: int, 
        round_number: int, 
        session_type: str, 
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store session data in Redis cache.
        
        Args:
            year: Season year
            round_number: Event round number
            session_type: Session key
            data: Session data to cache
            ttl: Optional custom TTL in seconds
        
        Returns:
            True if stored successfully, False otherwise
        """
        cache_key = self._generate_session_key(year, round_number, session_type)
        effective_ttl = ttl or self.ttl
        
        # Add cache metadata
        data_with_meta = {
            **data,
            '_cached_at': datetime.now().isoformat(),
            '_cache_ttl': effective_ttl
        }
        
        try:
            if self._connected and self._redis:
                json_data = json.dumps(data_with_meta)
                await self._redis.setex(cache_key, effective_ttl, json_data)
                logger.debug(f"Cached session data in Redis: {cache_key}")
                return True
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
        
        # Fallback to memory cache
        if self._fallback_to_memory:
            self._memory_cache[cache_key] = {
                'data': data_with_meta,
                'timestamp': datetime.now().timestamp()
            }
            return True
        
        return False
    
    async def get_schedule(self, year: int, db_manager: Optional[Any] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get season schedule from cache.
        
        Args:
            year: Season year
            db_manager: Optional DatabaseManager for SQLite fallback
        
        Returns:
            List of event dictionaries or None
        """
        cache_key = self._generate_schedule_key(year)
        
        # Check Redis
        try:
            if self._connected and self._redis:
                cached_data = await self._redis.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
        
        # Check memory fallback
        if not self._connected and self._fallback_to_memory:
            if cache_key in self._memory_cache:
                return self._memory_cache[cache_key]['data']
        
        # Check database
        if db_manager:
            try:
                db_events = db_manager.get_events_by_year(year)
                if db_events:
                    await self.set_schedule(year, db_events)
                    return db_events
            except Exception as e:
                logger.warning(f"Database lookup error: {e}")
        
        return None
    
    async def set_schedule(
        self, 
        year: int, 
        events: List[Dict[str, Any]], 
        ttl: Optional[int] = None
    ) -> bool:
        """Store season schedule in cache."""
        cache_key = self._generate_schedule_key(year)
        effective_ttl = ttl or (self.ttl * 24)  # Cache schedules longer (24 hours)
        
        try:
            if self._connected and self._redis:
                json_data = json.dumps(events)
                await self._redis.setex(cache_key, effective_ttl, json_data)
                return True
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
        
        # Fallback to memory cache
        if self._fallback_to_memory:
            self._memory_cache[cache_key] = {
                'data': events,
                'timestamp': datetime.now().timestamp()
            }
            return True
        
        return False
    
    async def invalidate_session(self, year: int, round_number: int, session_type: str) -> bool:
        """Remove a specific session from cache."""
        cache_key = self._generate_session_key(year, round_number, session_type)
        
        try:
            if self._connected and self._redis:
                await self._redis.delete(cache_key)
                return True
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")
        
        # Remove from memory cache
        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]
        
        return True
    
    async def invalidate_event(self, year: int, round_number: int) -> bool:
        """Remove all sessions for an event from cache."""
        pattern = f"f1dash:session:{year}:{round_number}:*"
        
        try:
            if self._connected and self._redis:
                # Find and delete matching keys
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
                # Also delete the event sessions list
                event_key = self._generate_event_key(year, round_number)
                await self._redis.delete(event_key)
                return True
        except Exception as e:
            logger.warning(f"Redis pattern delete error: {e}")
        
        # Clear from memory cache
        keys_to_remove = [k for k in self._memory_cache.keys() if k.startswith(f"f1dash:session:{year}:{round_number}:")]
        for key in keys_to_remove:
            del self._memory_cache[key]
        
        event_key = self._generate_event_key(year, round_number)
        if event_key in self._memory_cache:
            del self._memory_cache[event_key]
        
        return True
    
    async def clear_all_cache(self) -> bool:
        """Clear all F1 dashboard related cache entries."""
        pattern = "f1dash:*"
        
        try:
            if self._connected and self._redis:
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
                logger.info("Cleared all F1 dashboard cache entries")
                return True
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")
        
        # Clear memory cache
        self._memory_cache.clear()
        return True
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'connected': self._connected,
            'redis_url': self.redis_url if not self._connected else '***',
            'default_ttl': self.ttl,
            'memory_cache_entries': len(self._memory_cache)
        }
        
        try:
            if self._connected and self._redis:
                # Count F1 dashboard keys
                keys = await self._redis.keys("f1dash:*")
                stats['redis_keys_count'] = len(keys)
                
                # Get Redis info
                info = await self._redis.info()
                stats['redis_version'] = info.get('redis_version', 'unknown')
                stats['used_memory_human'] = info.get('used_memory_human', 'unknown')
        except Exception as e:
            stats['error'] = str(e)
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Check cache health and connectivity."""
        result = {
            'status': 'unknown',
            'redis_connected': False,
            'fallback_active': False
        }
        
        try:
            if REDIS_AVAILABLE:
                if not self._connected:
                    await self.connect()
                
                if self._connected and self._redis:
                    await self._redis.ping()
                    result['status'] = 'healthy'
                    result['redis_connected'] = True
                else:
                    result['status'] = 'fallback'
                    result['fallback_active'] = True
            else:
                result['status'] = 'fallback'
                result['fallback_active'] = True
                result['reason'] = 'aioredis not installed'
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['fallback_active'] = True
        
        return result


# Global instance for singleton access
cache_manager = CacheManager()


async def get_cache_manager(redis_url: Optional[str] = None, ttl: int = DEFAULT_TTL) -> CacheManager:
    """Get or create a cache manager instance."""
    if redis_url or ttl != DEFAULT_TTL:
        cm = CacheManager(redis_url, ttl)
        await cm.connect()
        return cm
    
    if not cache_manager._connected:
        await cache_manager.connect()
    return cache_manager


# Synchronous wrapper for non-async contexts
def get_cache_manager_sync(redis_url: Optional[str] = None, ttl: int = DEFAULT_TTL) -> CacheManager:
    """Synchronous wrapper to get cache manager."""
    cm = CacheManager(redis_url, ttl)
    # Don't connect here - let the async lifecycle handle it
    return cm
