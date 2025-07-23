# 🧙 PyGame Multiplayer RPG

A modular, tile-based multiplayer RPG built with Python, Pygame, and socket networking. This project includes both a real-time game client and a threaded, chunk-based server.

---

## 📦 Project Structure

```
PyGame_M/
├── client/                 # Modular game client logic
├── server/                 # Threaded game server (TCP/UDP)
├── world_chunks/           # Auto-generated chunk save data
├── tiles/                  # Tile images used for rendering the map
├── requirements.txt        # Python dependencies
├── LICENSE                 # MIT License
├── README.md               # You're reading it
```

---

## 🚀 Features

- 🌍 **Real-time multiplayer** (TCP for world updates, UDP for movement)
- 🧱 **Chunked world loading** with async rendering
- 🎮 **Tkinter-based game menu**
- 🗺️ **Tile-based map** with biomes, elevation, and minimap
- 💡 **Modular codebase**: Networking, rendering, controls, and state separated
- 💬 **Logging and debugging support**

---

## 🛠️ Getting Started

### 1. Clone the Repo

```bash
git clone https://github.com/colincressman/PyGame.git
cd PyGame
```

### 2. Set Up a Virtual Environment (optional but recommended)

```bash
python -m venv .venv
source .venv/Scripts/activate   # On Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Server

```bash
cd server
python -m server.server
```

### 5. Run the Client

```bash
cd ..
python client/client.py
```

> Make sure the server is running first!

---

## 📸 Screenshots

> *(Add some gameplay screenshots here for more appeal)*

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🧠 Future Ideas

- Character classes / leveling
- Inventory and items
- Chat system
- Dynamic world generation
- Combat and health tracking

---

## 👤 Author

Colin Cressman  
[GitHub](https://github.com/colincressman)