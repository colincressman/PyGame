import pygame

import config


def handle_chat_keydown(event) -> bool:
    if not config.chat_open:
        return False
    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
        text = config.chat_input.strip()
        if text:
            config.state_outbox.put({"type": "chat", "text": text})
        config.chat_input = ""
        config.chat_open = False
    elif event.key == pygame.K_ESCAPE:
        config.chat_input = ""
        config.chat_open = False
    elif event.key == pygame.K_BACKSPACE:
        config.chat_input = config.chat_input[:-1]
    else:
        if event.unicode and ord(event.unicode) >= 32:
            config.chat_input += event.unicode
    return True


def try_open_chat(event) -> bool:
    if event.key != pygame.K_t:
        return False
    if (
        not config.show_inventory
        and not config.show_menu
        and not config.show_stats
        and config.show_station_popup is None
        and config.open_chest_uid is None
    ):
        config.chat_open = True
        config.chat_input = ""
    return True


def handle_keybind_listen(event) -> bool:
    if config.controls_listen is None:
        return False
    if event.key != pygame.K_ESCAPE:
        config.keybinds[config.controls_listen] = event.key
        config.save_keybinds()
    config.controls_listen = None
    return True
