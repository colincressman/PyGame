import time
import math
from typing import Dict, List, Tuple, Optional

class PlayerInterpolator:
    """Handles smooth interpolation and extrapolation of player positions"""
    
    def __init__(self, buffer_time: float = 0.1, extrapolation_limit: float = 0.2):
        self.buffer_time = buffer_time  # How far back in time to interpolate
        self.extrapolation_limit = extrapolation_limit  # Max time to extrapolate forward
        self.position_history: Dict[str, List[Tuple[float, float, float]]] = {}  # player_id -> [(timestamp, x, y), ...]
        self.velocities: Dict[str, Tuple[float, float]] = {}  # player_id -> (vx, vy)
        self.last_update_time: Dict[str, float] = {}
        
    def add_position_update(self, player_id: str, x: float, y: float, timestamp: Optional[float] = None):
        """Add a new position update for a player"""
        if timestamp is None:
            timestamp = time.time()
            
        if player_id not in self.position_history:
            self.position_history[player_id] = []
            self.velocities[player_id] = (0.0, 0.0)
            
        history = self.position_history[player_id]
        history.append((timestamp, x, y))
        
        # Keep only recent history (last 1 second)
        cutoff_time = timestamp - 1.0
        self.position_history[player_id] = [
            (t, px, py) for t, px, py in history if t > cutoff_time
        ]
        
        # Calculate velocity from recent positions
        self._update_velocity(player_id)
        self.last_update_time[player_id] = timestamp
        
    def _update_velocity(self, player_id: str):
        """Calculate velocity based on recent position history"""
        history = self.position_history[player_id]
        if len(history) < 2:
            return
            
        # Use last two positions to calculate velocity
        (t1, x1, y1) = history[-2]
        (t2, x2, y2) = history[-1]
        
        dt = t2 - t1
        if dt > 0:
            vx = (x2 - x1) / dt
            vy = (y2 - y1) / dt
            
            # Smooth velocity changes to avoid jitter
            old_vx, old_vy = self.velocities[player_id]
            smoothing = 0.7  # Higher = more smoothing
            self.velocities[player_id] = (
                old_vx * smoothing + vx * (1 - smoothing),
                old_vy * smoothing + vy * (1 - smoothing)
            )
    
    def get_interpolated_position(self, player_id: str, current_time: Optional[float] = None) -> Tuple[float, float]:
        """Get the interpolated/extrapolated position for a player at the current time"""
        if current_time is None:
            current_time = time.time()
            
        if player_id not in self.position_history:
            return (0.0, 0.0)
            
        history = self.position_history[player_id]
        if not history:
            return (0.0, 0.0)
            
        # Target time for interpolation (slightly in the past)
        target_time = current_time - self.buffer_time
        
        # Find the two positions to interpolate between
        before_pos = None
        after_pos = None
        
        for i, (timestamp, x, y) in enumerate(history):
            if timestamp <= target_time:
                before_pos = (timestamp, x, y)
            else:
                after_pos = (timestamp, x, y)
                break
                
        # If we have positions on both sides of target time, interpolate
        if before_pos and after_pos:
            return self._interpolate_between_positions(before_pos, after_pos, target_time)
            
        # If we only have past positions, extrapolate forward
        elif before_pos and not after_pos:
            return self._extrapolate_from_position(player_id, before_pos, target_time)
            
        # If we only have future positions, use the earliest one
        elif after_pos and not before_pos:
            return (after_pos[1], after_pos[2])
            
        # Fallback to last known position
        last_timestamp, last_x, last_y = history[-1]
        return (last_x, last_y)
    
    def _interpolate_between_positions(self, pos1: Tuple[float, float, float], 
                                     pos2: Tuple[float, float, float], 
                                     target_time: float) -> Tuple[float, float]:
        """Interpolate between two positions"""
        t1, x1, y1 = pos1
        t2, x2, y2 = pos2
        
        # Calculate interpolation factor
        dt = t2 - t1
        if dt == 0:
            return (x1, y1)
            
        factor = (target_time - t1) / dt
        factor = max(0.0, min(1.0, factor))  # Clamp to [0, 1]
        
        # Linear interpolation
        x = x1 + (x2 - x1) * factor
        y = y1 + (y2 - y1) * factor
        
        return (x, y)
    
    def _extrapolate_from_position(self, player_id: str, pos: Tuple[float, float, float], 
                                 target_time: float) -> Tuple[float, float]:
        """Extrapolate position based on velocity"""
        timestamp, x, y = pos
        dt = target_time - timestamp
        
        # Limit extrapolation time to prevent wild predictions
        dt = min(dt, self.extrapolation_limit)
        
        vx, vy = self.velocities[player_id]
        
        # Apply some damping to extrapolation to make it more conservative
        damping = max(0.1, 1.0 - (dt / self.extrapolation_limit) * 0.5)
        
        extrapolated_x = x + vx * dt * damping
        extrapolated_y = y + vy * dt * damping
        
        return (extrapolated_x, extrapolated_y)
    
    def remove_player(self, player_id: str):
        """Remove a player from interpolation tracking"""
        self.position_history.pop(player_id, None)
        self.velocities.pop(player_id, None)
        self.last_update_time.pop(player_id, None)
    
    def get_player_velocity(self, player_id: str) -> Tuple[float, float]:
        """Get the current velocity of a player"""
        return self.velocities.get(player_id, (0.0, 0.0))
    
    def is_player_moving(self, player_id: str, threshold: float = 0.1) -> bool:
        """Check if a player is currently moving"""
        vx, vy = self.get_player_velocity(player_id)
        speed = math.sqrt(vx * vx + vy * vy)
        return speed > threshold

# Global interpolator instance
player_interpolator = PlayerInterpolator()