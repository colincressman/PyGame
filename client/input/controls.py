import pygame
from rendering.display import toggle_fullscreen
from config import TILE_SIZE
from networking.interpolation import player_interpolator
from networking.lag_compensation import lag_compensator

def handle_movement(state, keys, dt):
    base_speed = 6
    sprint_speed = 9
    speed = sprint_speed if keys[pygame.K_LSHIFT] else base_speed

    dx = keys[pygame.K_d] - keys[pygame.K_a]
    dy = keys[pygame.K_s] - keys[pygame.K_w]

    if dx != 0 or dy != 0:
        length = (dx**2 + dy**2) ** 0.5
        dx /= length
        dy /= length
        
        # Apply movement with potential prediction for high-latency connections
        movement_x = dx * speed * dt
        movement_y = dy * speed * dt
        
        # If we have high ping, apply some client-side prediction
        if lag_compensator.should_predict_movement():
            prediction_factor = min(lag_compensator.get_network_delay() * 2, 0.1)
            movement_x *= (1 + prediction_factor)
            movement_y *= (1 + prediction_factor)
        
        state["player_data"]["pos"][0] += movement_x
        state["player_data"]["pos"][1] += movement_y

def handle_events(state):
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            state["running"] = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                state["show_map"] = not state["show_map"]
                state["map_needs_redraw"] = state["show_map"]
            elif event.key == pygame.K_F11:
                toggle_fullscreen(state)
            elif event.key == pygame.K_ESCAPE:
                state["running"] = False
        elif event.type == pygame.VIDEORESIZE:
            state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"] = event.w, event.h
            state["screen"] = pygame.display.set_mode((state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]), pygame.RESIZABLE | pygame.DOUBLEBUF)
            state["camera_x"] = state["player_data"]["pos"][0] * TILE_SIZE
            state["camera_y"] = state["player_data"]["pos"][1] * TILE_SIZE