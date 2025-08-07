import time
from typing import Dict, Optional

class LagCompensator:
    """Handles client-side lag compensation and prediction"""
    
    def __init__(self):
        self.ping_samples: list = []
        self.max_samples = 10
        self.average_ping = 0.0
        self.last_ping_time = 0.0
        
    def add_ping_sample(self, ping_ms: float):
        """Add a ping sample for calculating average network delay"""
        self.ping_samples.append(ping_ms)
        if len(self.ping_samples) > self.max_samples:
            self.ping_samples.pop(0)
        
        # Calculate rolling average
        self.average_ping = sum(self.ping_samples) / len(self.ping_samples)
    
    def get_network_delay(self) -> float:
        """Get estimated one-way network delay in seconds"""
        return (self.average_ping / 1000.0) / 2.0  # Convert to seconds and halve for one-way
    
    def get_compensation_time(self) -> float:
        """Get the time offset for lag compensation"""
        return self.get_network_delay()
    
    def should_predict_movement(self) -> bool:
        """Determine if we should use movement prediction based on network conditions"""
        return self.average_ping > 50  # Use prediction if ping > 50ms

# Global lag compensator
lag_compensator = LagCompensator()