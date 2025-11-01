import pygame
import math
import random
import noise
import hashlib
import sys
import os
import time
import pygame
import ctypes
from ctypes import wintypes

pygame.init()

# Get screen and work area sizes
user32 = ctypes.windll.user32
SPI_GETWORKAREA = 0x0030
rect = wintypes.RECT()
ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)

work_x = rect.left
work_y = rect.top
work_width = rect.right - rect.left
work_height = rect.bottom - rect.top

# Set window position before creating it
os.environ['SDL_VIDEO_WINDOW_POS'] = f"{work_x},{work_y}"

# Create borderless window that fits the work area (taskbar visible)
WIN = pygame.display.set_mode((work_width, work_height), pygame.NOFRAME)
WIDTH, HEIGHT = WIN.get_size()
pygame.display.set_caption("Sciencervival")

# === LIGHT EFFECTS  ===
LIGHT_SURFACE = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
LIGHT_COLOR = (0, 0, 0, 180)  # Dark overlay with alpha

# === FONT ===
font = pygame.font.Font("font.ttf", 20)

# === COLORS ===
WHITE = (255, 255, 255)
BLUE = (50, 100, 255)
BLACK = (0, 0, 0)
LIGHT_GRAY = (220, 220, 220)
DARK_GRAY = (150, 150, 150)

# === CLOCK ===
clock = pygame.time.Clock()

# === QUADTREE ===
class Quadtree:
    def __init__(self, x, y, w, h, capacity=8, depth=0, max_depth=12):
        self.rect = pygame.Rect(x, y, w, h)
        self.capacity = capacity
        self.points = []  # list of tuples (x, y, obj)
        self.divided = False
        self.children = None
        self.depth = depth
        self.max_depth = max_depth

    def subdivide(self):
        x, y, w, h = self.rect
        hw, hh = w // 2, h // 2
        self.children = [
            Quadtree(x, y, hw, hh, self.capacity, self.depth+1, self.max_depth),
            Quadtree(x+hw, y, hw, hh, self.capacity, self.depth+1, self.max_depth),
            Quadtree(x, y+hh, hw, hh, self.capacity, self.depth+1, self.max_depth),
            Quadtree(x+hw, y+hh, hw, hh, self.capacity, self.depth+1, self.max_depth),
        ]
        self.divided = True

    def insert(self, x, y, obj):
        if not self.rect.collidepoint(x, y):
            return False
        if len(self.points) < self.capacity or self.depth >= self.max_depth:
            self.points.append((x, y, obj))
            return True
        if not self.divided:
            self.subdivide()
        for child in self.children:
            if child.insert(x, y, obj):
                return True
        # fallback
        self.points.append((x, y, obj))
        return True

    def query_range(self, rect, found=None):
        if found is None:
            found = []
        if not self.rect.colliderect(rect):
            return found
        for (px, py, obj) in self.points:
            if rect.collidepoint(px, py):
                found.append(obj)
        if self.divided:
            for child in self.children:
                child.query_range(rect, found)
        return found

    def clear(self):
        self.points.clear()
        self.divided = False
        self.children = None

# global quadtree instance (cover a very large range for an effectively infinite world)
QT_ROOT = None
QT_WORLD_BOUNDS = (-2000000, -2000000, 4000000, 4000000)

last_unload_time = 0
UNLOAD_INTERVAL = 5  # seconds

# New: throttle quadtree rebuilds and chunk unloads
last_qt_rebuild_time = 0
QT_REBUILD_INTERVAL = 0.5  # seconds (tweak as needed)
last_items_count = 0
last_structures_count = 0

last_unload_chunks_time = 0
UNLOAD_CHUNK_INTERVAL = 0.5  # seconds
last_player_chunk = (None, None)


def rebuild_quadtree():
    """Rebuild quadtree from current items and structures. Call occasionally."""
    global QT_ROOT
    QT_ROOT = Quadtree(*QT_WORLD_BOUNDS, capacity=10)
    for it in items:
        # ensure items have x,y
        if "x" in it and "y" in it:
            QT_ROOT.insert(int(it["x"]), int(it["y"]), it)
    for s in structures:
        if "x" in s and "y" in s:
            QT_ROOT.insert(int(s["x"]), int(s["y"]), s)

# === PLAYER ===
player_size = 80
player_x = WIDTH // 2
player_y = HEIGHT // 2
player_speed = 5
player_texture = pygame.transform.scale(pygame.image.load(os.path.join("other", "character.png")), (player_size, player_size))

# === PLAYER STATS ===
MAX_HEALTH = 100
MAX_HUNGER = 100
MAX_THIRST = 100
MAX_STAMINA = 100

health = MAX_HEALTH
hunger = MAX_HUNGER
thirst = MAX_THIRST
stamina = MAX_STAMINA

# how fast stats decay
HUNGER_DECAY = 1      # per 10 seconds
THIRST_DECAY = 2      # per 10 seconds
STAMINA_RECOVER = 1   # per second (when not moving)
STAMINA_DRAIN = 1    # per second (when moving)

# === TILE SETTINGS ===
TILE_SIZE = 100
ITEMED_TILE = {}
PLANTED_TILE = {}

# === LOAD TILE TEXTURES ===
TILE_PATH = "tiles"
TILE_IMAGES = {
    "grass": pygame.image.load(os.path.join(TILE_PATH, "grass.png")),
    "sand": pygame.image.load(os.path.join(TILE_PATH, "sand.png")),
    "dirt": pygame.image.load(os.path.join(TILE_PATH, "dirt.png")),
    "stone": pygame.image.load(os.path.join(TILE_PATH, "stone.png")),
    "sedimentary_stone": pygame.image.load(os.path.join(TILE_PATH, "sedimentary_stone.png")),
    "water": pygame.image.load(os.path.join(TILE_PATH, "water.png")),
    "sedimentary_iron": pygame.image.load(os.path.join(TILE_PATH, "sedimentary_iron.png")),
    "laterite_soil": pygame.image.load(os.path.join(TILE_PATH, "laterite_soil.png")),
}
ORE_TYPES = [
    {"name": "sedimentary_iron", "rarity": 0.4},
    {"name": "laterite_soil", "rarity": 0.5}
]
PLANT_STATS = {
    "mung_bean": {
        "pollination": "self",
        "fruit_time": 2,
        "lastlast_drop": ["mung_beans"],
        "last_drop": None,
        "prelast_drop": ["mung_beans"],
        "stages": [
            {"name": "ve", "timer_mins": 1},
            {"name": "v1", "timer_mins": 1},
            {"name": "v2", "timer_mins": 1},
            {"name": "v3", "timer_mins": 3},
            {"name": "v6", "timer_mins": 3},
        ],
        "last_stage": "flowering",
        "last_stage_last": "fruited",
        "only_tiles": ["grass", "dirt"]
    }
}

# Scale tiles to match TILE_SIZE
for key in TILE_IMAGES:
    TILE_IMAGES[key] = pygame.transform.scale(TILE_IMAGES[key], (TILE_SIZE, TILE_SIZE))

CHUNK_SIZE = 16
WORLD_SEED = 9
NOISE = noise.combine_noise_smooth(noise.make_fractal_mask(WORLD_SEED, ),noise.make_perlin(WORLD_SEED))
ORE_NOISE = noise.make_ore_patches(WORLD_SEED+1, [0.05, 0.1], [0.4, 0.5])
world_chunks = {}
items = []
plants = []
WORLD_TILE_ITEMS = {}  # {(tile_x, tile_y): item_dict} — deferred/generated items not yet in `items`

def spawn_plant(plant_type, x, y, growth_stage="ve", growth_timer=0):
    plant = {
        "type": plant_type,
        "x": x,
        "y": y,
        "growth_stage": growth_stage,
        "growth_timer": growth_timer
    }
    return plant

def generate_item(tile_type, _x, _y):
    """Generate a deterministic item for a given tile (x,y) and tile type."""
    h = float(int(hashlib.md5(f"{_x},{_y},{WORLD_SEED}".encode()).hexdigest(), 16) % 100) / 100.0
    lh = float(int(hashlib.md5(f"{_x},{_y},{WORLD_SEED}_".encode()).hexdigest(), 16) % 100) / 100.0
    x, y = float(_x) + random.uniform(-1, 1), float(_y) + random.uniform(-1, 1)
    
    if tile_type == "grass":
        if h < 0.04:
            return {"type": "rattan", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.05:
            return {"type": "carrot", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "cotton_plant", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.1:
            return {"type": "stick", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    elif tile_type == "dirt":
        if h < 0.02:
            return {"type": "limestone", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.05:
            return {"type": "clay", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "magnesite", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    elif tile_type == "sand":
        if h < 0.04:
            return {"type": "rock", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "clam", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    return None

def generate_plant(tile, world_x, world_y):
    h = float(int(hashlib.md5(f"{world_x},{world_y},{WORLD_SEED}__".encode()).hexdigest(), 16) % 100) / 100.0
    sh = float(int(hashlib.md5(f"{world_x},{world_y},{WORLD_SEED}____".encode()).hexdigest(), 16) % 100) / 100.0
    th = float(int(hashlib.md5(f"__{world_x},{world_y},{WORLD_SEED}__".encode()).hexdigest(), 16) % 100) / 100.0

    px = (world_x * TILE_SIZE + TILE_SIZE // 2) + random.uniform(-TILE_SIZE, TILE_SIZE)
    py = (world_y * TILE_SIZE + TILE_SIZE // 2) + random.uniform(-TILE_SIZE, TILE_SIZE)
    if tile == "grass":
        if h < 0.02:
            stages = PLANT_STATS["mung_bean"]["stages"]
            stage = stages[int(sh*(len(stages)-1))]
            return spawn_plant("mung_bean", px, py, stage["name"], stage["timer_mins"]*th)

def generate_chunk(cx, cy):
    """Generate a single chunk of terrain and spawn items into global items list."""
    chunk_tiles = []

    for ty in range(CHUNK_SIZE):
        row = []
        for tx in range(CHUNK_SIZE):
            world_x = cx * CHUNK_SIZE + tx
            world_y = cy * CHUNK_SIZE + ty
            r = NOISE(world_x / 100, world_y / 100)

            if r < 0.3:
                tile = "water"
            elif r < 0.4:
                tile = "sand"
            elif r < 0.41:
                tile = "dirt"
            elif r < 0.6:
                tile = "grass"
            elif r < 0.62:
                tile = "dirt"
            elif r < 0.8:
                tile = "stone"
                ore = ORE_NOISE(world_x, world_y)
                if ore != 0:
                    ore_name = ORE_TYPES[ore - 1]["name"]
                    tile = ore_name
            else:
                tile = "sedimentary_stone"

            row.append(tile)

            # === Generate item directly into global items list ===
            item = generate_item(tile, world_x, world_y)
            if item and (world_x, world_y) not in ITEMED_TILE:
                # store by tile coordinates so it's not active until picked up
                WORLD_TILE_ITEMS[(world_x, world_y)] = item
            plant = generate_plant(tile, world_x, world_y)
            if plant and (world_x, world_y) not in PLANTED_TILE:
                plants.append(plant)
            ITEMED_TILE[(world_x, world_y)] = True
            PLANTED_TILE[(world_x, world_y)] = True

        chunk_tiles.append(row)

    return chunk_tiles

def get_chunk(cx, cy):
    if (cx, cy) not in world_chunks:
        world_chunks[(cx, cy)] = generate_chunk(cx, cy)
    return world_chunks[(cx, cy)]

def draw_world(camera_x, camera_y):
    start_tile_x = camera_x // TILE_SIZE
    start_tile_y = camera_y // TILE_SIZE
    end_tile_x = (camera_x + WIDTH) // TILE_SIZE + 1
    end_tile_y = (camera_y + HEIGHT) // TILE_SIZE + 1

    for tile_y in range(start_tile_y, end_tile_y):
        for tile_x in range(start_tile_x, end_tile_x):
            chunk_x = tile_x // CHUNK_SIZE
            chunk_y = tile_y // CHUNK_SIZE
            local_x = tile_x % CHUNK_SIZE
            local_y = tile_y % CHUNK_SIZE

            chunk = get_chunk(chunk_x, chunk_y)
            tile_type = chunk[local_y][local_x]
            tile_img = TILE_IMAGES[tile_type]

            screen_x = tile_x * TILE_SIZE - camera_x
            screen_y = tile_y * TILE_SIZE - camera_y
            WIN.blit(tile_img, (screen_x, screen_y))

def unload_far_chunks(player_chunk_x, player_chunk_y, max_distance=3):
    for cx, cy in tuple(world_chunks):
        if abs(cx - player_chunk_x) > max_distance or abs(cy - player_chunk_y) > max_distance:
            del world_chunks[(cx, cy)]

# === LOAD PLANT TEXTURES ===
PLANT_SIZE = 80
PLANT_PATH = "plants"
PLANT_IMAGES = {
    "mung_bean": {
        "ve": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "ve.png"))),
        "v1": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "v1.png"))),
        "v2": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "v2.png"))),
        "v3": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "v3.png"))),
        "v6": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "v6.png"))),
        "flowering": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "flowering.png"))),
        "fruited": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("mung_bean", "fruited.png"))),
    }
}
for plant_type in PLANT_IMAGES:
    for stage in PLANT_IMAGES[plant_type]:
        PLANT_IMAGES[plant_type][stage] = pygame.transform.scale(PLANT_IMAGES[plant_type][stage], (PLANT_SIZE, PLANT_SIZE))

# === LOAD ITEM TEXTURES ===
RESOURCE_PATH = "resources"
ITEM_IMAGES = {
    "rock": pygame.image.load(os.path.join(RESOURCE_PATH, "rock.png")),
    "stick": pygame.image.load(os.path.join(RESOURCE_PATH, "stick.png")),
    "rattan": pygame.image.load(os.path.join(RESOURCE_PATH, "rattan.png")),
    "cracked_rock": pygame.image.load(os.path.join(RESOURCE_PATH, "cracked_rock.png")),
    "sharp_rock": pygame.image.load(os.path.join(RESOURCE_PATH, "sharp_rock.png")),
    "hard_fiber": pygame.image.load(os.path.join(RESOURCE_PATH, "hard_fiber.png")),
    "raw_rope": pygame.image.load(os.path.join(RESOURCE_PATH, "raw_rope.png")),
    "pointy_stick": pygame.image.load(os.path.join(RESOURCE_PATH, "pointy_stick.png")),
    "clam": pygame.image.load(os.path.join(RESOURCE_PATH, "clam.png")),
    "limestone": pygame.image.load(os.path.join(RESOURCE_PATH, "limestone.png")),
    "magnesite": pygame.image.load(os.path.join(RESOURCE_PATH, "magnesite.png")),
    "stone_chisel": pygame.image.load(os.path.join(RESOURCE_PATH, "stone_chisel.png")),
    "carved_stick": pygame.image.load(os.path.join(RESOURCE_PATH, "carved_stick.png")),
    "holed_stick": pygame.image.load(os.path.join(RESOURCE_PATH, "holed_stick.png")),
    "cotton_boll": pygame.image.load(os.path.join(RESOURCE_PATH, "cotton_boll.png")),
    "cotton_plant": pygame.image.load(os.path.join(RESOURCE_PATH, "cotton_plant.png")),
    "cotton_seed": pygame.image.load(os.path.join(RESOURCE_PATH, "cotton_seed.png")),
    "mung_beans": pygame.image.load(os.path.join(RESOURCE_PATH, "mung_beans.png")),
    "fire_plough": pygame.image.load(os.path.join(RESOURCE_PATH, "fire_plough.png")),
    "ashed_holed_stick": pygame.image.load(os.path.join(RESOURCE_PATH, "ashed_holed_stick.png")),
    "nonfunctional_stone_axe": pygame.image.load(os.path.join(RESOURCE_PATH, "nonfunctional_stone_axe.png")),
    "stone_axe": pygame.image.load(os.path.join(RESOURCE_PATH, "stone_axe.png")),
    "burning_cotton_boll": pygame.image.load(os.path.join(RESOURCE_PATH, "burning_cotton_boll.png")),
    "ashes": pygame.image.load(os.path.join(RESOURCE_PATH, "ashes.png")),
    "wood_dust": pygame.image.load(os.path.join(RESOURCE_PATH, "wood_dust.png")),
    "burning_wood_dust": pygame.image.load(os.path.join(RESOURCE_PATH, "burning_wood_dust.png")),
    "clay": pygame.image.load(os.path.join(RESOURCE_PATH, "clay.png")),
    "clay_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "clay_cup.png")),
    "rolled_clay": pygame.image.load(os.path.join(RESOURCE_PATH, "rolled_clay.png")),
    "clay_mold": pygame.image.load(os.path.join(RESOURCE_PATH, "clay_mold.png")),
    "ingot_mold": pygame.image.load(os.path.join(RESOURCE_PATH, "ingot_mold.png")),
    "rod_mold": pygame.image.load(os.path.join(RESOURCE_PATH, "rod_mold.png")),
    "axehead_mold": pygame.image.load(os.path.join(RESOURCE_PATH, "axehead_mold.png")),
    "pickaxehead_mold": pygame.image.load(os.path.join(RESOURCE_PATH, "pickaxehead_mold.png")),
    "carrot": pygame.image.load(os.path.join(RESOURCE_PATH, "carrot.png")),
    "dried_clay_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "dried_clay_cup.png")),
    "ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "ceramic_cup.png")),
    "saltwater_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "saltwater_ceramic_cup.png")),
    "freshwater_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "freshwater_ceramic_cup.png")),
    "drinkable_water_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "drinkable_water_ceramic_cup.png")),
    "iob_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "iob_ceramic_cup.png")),
    "anoxic_iob_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "iob_ceramic_cup.png")),
}

MAX_ITEM_DUR = {
    "sharp_rock": 15,
    "stone_chisel": 5,
    "pointy_stick": 10,
    "fire_plough": 20,
    "stone_axe": 50,
}

ITEM_CONVERT = {
    "burning_cotton_boll": [5, None],
    "burning_wood_dust": [10, "ashes"],
    "clay_cup": [60, "dried_clay_cup"],
}

ITEM_CONVERT_LABELS = {
    "burning_cotton_boll": "Burns in: ",
    "burning_wood_dust": "Burns in: ",
    "cocoa_beans_bamboo_bottle": "Ferments in: ",
    "clay_cup": "Dries in: "
}

FOOD_STATS = {
    "carrot": {"hunger": 10, "thirst": -10, "stamina": 0},
    "drinkable_water_ceramic_cup": {"hunger": 0, "thirst": 35, "stamina": 10},
    "saltwater_ceramic_cup": {"hunger": 1, "thirst": -15, "stamina": -5}
}

FOOD_CONVERTS = {
    "carrot": None,
    "drinkable_water_ceramic_cup": "ceramic_cup",
    "saltwater_ceramic_cup": "ceramic_cup"
}

CONSUME_TYPES = {
    "carrot": "Eat",
    "drinkable_water_ceramic_cup": "Drink",
    "saltwater_ceramic_cup": "Drink"
}

ITEM_TILE_INTERACTION = {
    "ceramic_cup": {
        "water": { "item_converts": "saltwater_ceramic_cup"}
    }
}

ITEM_SIZE = 40
for key in ITEM_IMAGES:
    ITEM_IMAGES[key] = pygame.transform.scale(ITEM_IMAGES[key], (ITEM_SIZE, ITEM_SIZE))

# === ITEM SPAWNING ===
def spawn_items(num=30):
    items = []
    for _ in range(num):
        item_type = random.choice(["rock", "rattan", "stick", "cotton_plant"])
        x = random.randint(0, WIDTH - ITEM_SIZE)
        y = random.randint(0, HEIGHT - ITEM_SIZE)
        item = {"type": item_type, "x": x, "y": y}
        if item_type in MAX_ITEM_DUR:
            item["dur"] = MAX_ITEM_DUR[item_type]
        items.append(item)
    return items

#items.extend(spawn_items())

# === INVENTORY ===
inventory = [None, None]
slot_size = 60
slot_margin = 10

def get_inventory_slot_rects():
    total_width = (slot_size * 2) + slot_margin
    start_x = (WIDTH - total_width) // 2
    y = HEIGHT - slot_size - 20
    return [
        pygame.Rect(start_x + i * (slot_size + slot_margin), y, slot_size, slot_size)
        for i in range(2)
    ]

# === CRAFTING GUI ===
crafting_visible = False
craft_slots = [None, None]
CRAFT_SLOT_SIZE = slot_size
craft_output_slots = []

# Base crafting frame
craft_gui_rect = pygame.Rect(WIDTH//2 - 150, HEIGHT//2 - 80, 300, 160)
craft_slot_rects = [
    pygame.Rect(craft_gui_rect.x + 20, craft_gui_rect.y + 50, CRAFT_SLOT_SIZE, CRAFT_SLOT_SIZE),
    pygame.Rect(craft_gui_rect.x + 90, craft_gui_rect.y + 50, CRAFT_SLOT_SIZE, CRAFT_SLOT_SIZE),
]
right_arrow_rect = pygame.Rect(craft_gui_rect.x + 180, craft_gui_rect.y + 65, 30, 30)

# === DRAG-DROP STATE ===
drag_item = None
drag_origin = None
drag_offset = (0, 0)

# === HELPER: Crafting Logic ===
def get_craft_result(inputs):
    """Return result items based on crafting input."""
    # Convert dicts to their type strings
    input_types = [i["type"] if isinstance(i, dict) else i for i in inputs]
    
    if sorted(input_types) == sorted(["rock", "rock"]):
        return ["cracked_rock", "rock"]
    elif sorted(input_types) == sorted(["cracked_rock", "rock"]):
        return ["sharp_rock", "rock"]
    elif sorted(input_types) == sorted(["sharp_rock", "stick"]):
        return ["pointy_stick"]
    elif sorted(input_types) == sorted(["sharp_rock", "rattan"]):
        return ["hard_fiber", "hard_fiber"]
    elif sorted(input_types) == sorted(["hard_fiber", "hard_fiber"]):
        return ["raw_rope"]
    elif sorted(input_types) == sorted(["cotton_plant"]):
        return ["cotton_seed", "cotton_boll"]
    elif sorted(input_types) == sorted(["cracked_rock", "cracked_rock"]):
        return ["cracked_rock", "stone_chisel"]
    elif sorted(input_types) == sorted(["stone_chisel", "stick"]):
        return ["carved_stick", "wood_dust"]
    elif sorted(input_types) == sorted(["carved_stick", "stone_chisel"]):
        return ["holed_stick", "wood_dust"]
    elif sorted(input_types) == sorted(["pointy_stick", "carved_stick"]):
        return ["fire_plough"]
    elif sorted(input_types) == sorted(["holed_stick", "ashes"]):
        return ["ashed_holed_stick"]
    elif sorted(input_types) == sorted(["ashed_holed_stick", "sharp_rock"]):
        return ["nonfunctional_stone_axe"]
    elif sorted(input_types) == sorted(["nonfunctional_stone_axe", "hard_fiber"]):
        return ["stone_axe"]
    elif sorted(input_types) == sorted(["cotton_boll", "fire_plough"]):
        return ["burning_cotton_boll"]
    elif sorted(input_types) == sorted(["wood_dust", "fire_plough"]):
        return ["burning_wood_dust"]
    elif sorted(input_types) == sorted(["wood_dust", "burning_cotton_boll"]):
        return ["burning_wood_dust"]
    elif sorted(input_types) == sorted(["clay"]):
        return ["rolled_clay"]
    elif sorted(input_types) == sorted(["rolled_clay", "clay"]):
        return ["clay_cup"]
    elif sorted(input_types) == sorted(["clay", "clay"]):
        return ["clay_mold"]
    else:
        return []

def get_craft_result_durs(inputs):
    """Return durability effects for tools used in crafting."""
    input_types = [i["type"] if isinstance(i, dict) else i for i in inputs]
    
    if sorted(input_types) == sorted(["sharp_rock", "stick"]):
        return [["sharp_rock", -1]]
    elif sorted(input_types) == sorted(["sharp_rock", "rattan"]):
        return [["sharp_rock", -1]]
    elif sorted(input_types) == sorted(["stone_chisel", "stick"]):
        return [["stone_chisel", -1]]
    elif sorted(input_types) == sorted(["carved_stick", "stone_chisel"]):
        return [["stone_chisel", -1]]
    elif sorted(input_types) == sorted(["pointy_stick", "carved_stick"]):
        return [["pointy_stick", "gone"]]
    elif sorted(input_types) == sorted(["ashed_holed_stick", "sharp_rock"]):
        return [["sharp_rock", "gone"]]
    elif sorted(input_types) == sorted(["cotton_boll", "fire_plough"]):
        return [["fire_plough", -1]]
    elif sorted(input_types) == sorted(["wood_dust", "fire_plough"]):
        return [["fire_plough", -3]]
    else:
        return []

def update_craft_output():
    """Update output slots and expand GUI if necessary."""
    global craft_output_slots, craft_gui_rect, right_arrow_rect
    current_inputs = [slot for slot in craft_slots if slot]
    result_items = get_craft_result(current_inputs)

    # Compute width based on number of results
    extra_width = len(result_items) * (CRAFT_SLOT_SIZE + 10)
    new_width = 240 + extra_width
    craft_gui_rect.width = new_width
    craft_gui_rect.x = WIDTH//2 - new_width//2

    # Reposition input slots and arrow
    craft_slot_rects[0].x = craft_gui_rect.x + 20
    craft_slot_rects[1].x = craft_gui_rect.x + 100
    right_arrow_rect.x = craft_gui_rect.x + 180

    # Create output slot rects
    craft_output_slots = []
    x_start = right_arrow_rect.right + 20
    for i, item in enumerate(result_items):
        rect = pygame.Rect(x_start + i * (CRAFT_SLOT_SIZE + 10), craft_gui_rect.y + 50,
                           CRAFT_SLOT_SIZE, CRAFT_SLOT_SIZE)
        craft_output_slots.append({"item": item, "rect": rect})

def perform_craft():
    """Craft items: remove inputs, spawn outputs near player."""
    global craft_slots

    # Capture current inputs (dicts)
    current_inputs = [slot for slot in craft_slots if slot]

    # Compute result
    result_items = get_craft_result(current_inputs)
    if not result_items:
        return

    # Apply durability changes BEFORE clearing slots
    dur_updates = get_craft_result_durs(current_inputs)
    for tool_type, delta in dur_updates:
        for slot in craft_slots:
            if slot and slot["type"] == tool_type and "dur" in slot:
                slot["dur"] += delta if isinstance(delta, int) else 0  # negative = lose durability
                if slot["dur"] <= 0 or delta == "gone":
                    craft_slots[craft_slots.index(slot)] = None  # break the tool

    # Clear only non-tool items after crafting
    for i, slot in enumerate(craft_slots):
        if slot and (slot["type"] not in MAX_ITEM_DUR or slot["dur"] <= 0):
            craft_slots[i] = None

    # Spawn crafted items near player
    for result in result_items:
        drop_x = player_x + random.randint(-50, 50)
        drop_y = player_y + random.randint(-50, 50)
        new_item = {"type": result, "x": drop_x, "y": drop_y}
        if result in MAX_ITEM_DUR:
            new_item["dur"] = MAX_ITEM_DUR[result]
        items.append(new_item)

    update_craft_output()

# === LOAD STRUCTURES IMAGE ===
STRUCTURE_SIZE = 80
STRUCTURE_PATH = "structures"
STRUCTURE_IMAGES = {
    "cross_sticks": pygame.image.load(os.path.join(STRUCTURE_PATH, "cross_sticks.png")),
    "sticks_pile": pygame.image.load(os.path.join(STRUCTURE_PATH, "sticks_pile.png")),
    "fire_place": pygame.image.load(os.path.join(STRUCTURE_PATH, "fire_place.png")),
    "burning_sticks_pile": pygame.image.load(os.path.join(STRUCTURE_PATH, "burning_sticks_pile.png")),
    "stick_stake": pygame.image.load(os.path.join(STRUCTURE_PATH, "stick_stake.png")),
    "roped_stick_stake": pygame.image.load(os.path.join(STRUCTURE_PATH, "roped_stick_stake.png")),
}
for img in STRUCTURE_IMAGES.keys():
    STRUCTURE_IMAGES[img] = pygame.transform.scale(STRUCTURE_IMAGES[img], (STRUCTURE_SIZE, STRUCTURE_SIZE))

STRUCTURE_ITEM_INTERACTIONS = {
    "cross_sticks": {
        "stick": {
            "structure_convert": "sticks_pile",
            "item_convert": None
        }
    },
    "sticks_pile": {
        "burning_wood_dust": {
            "structure_convert": "burning_sticks_pile",
            "item_convert": None
        }
    },
    "burning_sticks_pile": {
        "stick": {
            "structure_convert": "fire_place",
            "item_convert": None
        }
    }
}
STRUCTURE_SPECIALS = {
    "burning_sticks_pile": {
        "light_radius": 3, # Tiles
        "light_intensity": 1, # starting intensity; max intensity = light_radius
        "light_flickering": [0.5, 1, 2], # [timer_secs, min_intensity, max_intensity]
        "timer_convertion": [20, ["ashes", "ashes", "ashes"], []] # [timer_secs, items_convert, structures_convert]
    },
    "fire_place": {
        "light_radius": 10, 
        "light_intensity": 5,
        "light_flickering": [0.2, 1, 6],
        "timer_convertion": [120, ["ashes", "ashes", "ashes", "ashes", "ashes"], []],
        "fuelers": { # restarts timer
            "stick": {"timer_add": 30, "return_item": None},
            "wood_dust": {"timer_add": 10, "return_item": None},
            "cotton_boll": {"timer_add": 5, "return_item": None}
        },
        "cooks": {
            "dried_clay_cup": {"timer": 60, "cooks_into": "ceramic_cup"},
            "saltwater_ceramic_cup": {"timer": 20, "cooks_into": "drinkable_water_ceramic_cup"}
        }
    }
}

# === STRUCTURES ===
structures = []

# === STRUCTURES GUI ===
crafting_structures_visible = False

# background frame for structure crafting
structure_frame_rect = pygame.Rect(10, HEIGHT - 320 - slot_size, slot_size + 20, 320)
structure_crafting_slots = [None, None]
output_structure = None
held_structure = None
structure_crafting_slot_rects = [
    pygame.Rect(20, HEIGHT - 300 - slot_size, slot_size, slot_size),
    pygame.Rect(20, HEIGHT - 290, slot_size, slot_size)
]
output_structure_slot_rect = pygame.Rect(20, HEIGHT - 240 + slot_size, slot_size, slot_size)
down_arrow_rect = pygame.Rect(0, HEIGHT - 220, 30, 30)
down_arrow_rect.centerx = structure_frame_rect.centerx

# === HELPER: Structure Crafting Logic ===
def get_structure(type, x, y):
    return {"type": type, "x": x, "y": y}

def get_structure_result(inputs):
    input_types = [i["type"] if isinstance(i, dict) else i for i in inputs]
    
    if sorted(input_types) == sorted(["stick", "stick"]):
        return "cross_sticks"
    elif sorted(input_types) == sorted(["pointy_stick", "raw_rope"]):
        return "roped_stick_stake"
    elif sorted(input_types) == sorted(["pointy_stick"]):
        return "stick_stake"
    else:
        return None
    
def update_structure_gui():
    """Update output slot based on current inputs."""
    global output_structure
    inputs = [slot for slot in structure_crafting_slots if slot]
    output_structure = get_structure_result(inputs)

def perform_structure_craft():
    global structure_crafting_slots, output_structure, held_structure

    if not output_structure:
        return  # Nothing to craft

    # Consume materials
    for i in range(len(structure_crafting_slots)):
        structure_crafting_slots[i] = None

    # Hold the crafted structure
    held_structure = output_structure
    output_structure = None  # clear GUI output after crafting

    update_structure_gui()

def handle_structure_interaction(structure, item):
    """Handle interaction between a structure and an item."""
    if structure["type"] in STRUCTURE_ITEM_INTERACTIONS:
        interactions = STRUCTURE_ITEM_INTERACTIONS[structure["type"]]
        if item["type"] in interactions:
            result = interactions[item["type"]]
            
            # Convert structure if specified
            if "structure_convert" in result:
                before_type = structure["type"]
                structure["type"] = result["structure_convert"]
                if before_type in STRUCTURE_SPECIALS:
                    specs = STRUCTURE_SPECIALS[before_type]
                    if "time_convertion" in specs:
                        structure["timer"] = specs["time_convertion"][0]
            
            # Convert item if specified
            if "item_convert" in result and result["item_convert"] is not None:
                item["type"] = result["item_convert"]
                return True  # Keep item
            return False  # Remove item
    return True  # Keep item by default

def update_structures(dt):
    for structure in structures[:]:  # Use slice to allow removal during iteration
        if structure["type"] in STRUCTURE_SPECIALS:
            specs = STRUCTURE_SPECIALS[structure["type"]]
            
            # Handle timer conversion
            if "timer_convertion" in specs:
                timer, items_convert, structs_convert = specs["timer_convertion"]
                
                # Initialize timer if not exists
                if "timer" not in structure:
                    structure["timer"] = timer
                    
                structure["timer"] -= dt
                
                # Convert when timer expires
                if structure["timer"] <= 0:
                    # Spawn converted items
                    for item_type in items_convert:
                        items.append({
                            "type": item_type,
                            "x": structure["x"] + random.randint(-20, 20),
                            "y": structure["y"] + random.randint(-20, 20)
                        })
                    
                    # Convert or remove structure
                    if structs_convert:
                        structure["type"] = random.choice(structs_convert)
                        structure["timer"] = timer  # Reset timer
                    else:
                        structures.remove(structure)
                        
            # Handle fueling
            if "fuelers" in specs and structure.get("timer"):
                structure_rect = pygame.Rect(structure["x"], structure["y"], 
                                          STRUCTURE_SIZE, STRUCTURE_SIZE)
                
                for item in items[:]:  # Use slice to allow removal
                    if item["type"] in specs["fuelers"]:
                        item_rect = pygame.Rect(item["x"], item["y"], 
                                              ITEM_SIZE, ITEM_SIZE)
                        
                        if structure_rect.colliderect(item_rect):
                            fuel_data = specs["fuelers"][item["type"]]
                            structure["timer"] += fuel_data["timer_add"]
                            
                            if fuel_data["return_item"]:
                                item["type"] = fuel_data["return_item"]
                            else:
                                items.remove(item)

def handle_cooking(structure, item):
    """Handle cooking items in structures that support it."""
    if structure["type"] in STRUCTURE_SPECIALS:
        specs = STRUCTURE_SPECIALS[structure["type"]]
        
        if "cooks" in specs and item["type"] in specs["cooks"]:
            cook_data = specs["cooks"][item["type"]]
            
            # Initialize cooking timer
            if "cook_timer" not in item:
                item["cook_timer"] = cook_data["timer"]
            
            item["cook_timer"] -= 1
            
            # Convert item when done cooking
            if item["cook_timer"] <= 0:
                item["type"] = cook_data["cooks_into"]
                del item["cook_timer"]
                return True
    
    return False

# === PERFORMANCE FUNCTIONS ===
def unload_far_entities(player_x, player_y, max_distance=CHUNK_SIZE*TILE_SIZE*3):
    global items, plants
    items = [i for i in items if abs(i["x"] - player_x) < max_distance and abs(i["y"] - player_y) < max_distance]
    plants = [p for p in plants if abs(p["x"] - player_x) < max_distance and abs(p["y"] - player_y) < max_distance]

# Before the main loop
last_unload_time = 0
UNLOAD_INTERVAL = 5  # seconds

# === HELPER FUNCTIONS ===
def find_spawn_location(search_radius=10):
    """Finds the nearest non-water tile near (0,0) and returns its world position."""
    for radius in range(search_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                world_x = dx
                world_y = dy
                r = NOISE(world_x / 100, world_y / 100)
                
                # Match your tile thresholds from generate_chunk()
                if r >= 0.3:  # 0.3+ means not water
                    # Found land!
                    return (world_x * TILE_SIZE + TILE_SIZE // 2,
                            world_y * TILE_SIZE + TILE_SIZE // 2)
    # fallback if somehow all water
    return (0, 0)

def get_tile_at(x, y):
    """Return the tile type at world coordinate (x, y) in pixels."""
    # Convert from pixel coordinates to tile coordinates
    tile_x = int(x // TILE_SIZE)
    tile_y = int(y // TILE_SIZE)

    # Determine which chunk that tile belongs to
    chunk_x = tile_x // CHUNK_SIZE
    chunk_y = tile_y // CHUNK_SIZE

    # Determine the tile’s local position within the chunk
    local_x = tile_x % CHUNK_SIZE
    local_y = tile_y % CHUNK_SIZE

    # Handle negative coordinates properly (Python’s % works differently for negatives)
    if local_x < 0:
        local_x += CHUNK_SIZE
        chunk_x -= 1
    if local_y < 0:
        local_y += CHUNK_SIZE
        chunk_y -= 1

    # Load or retrieve the chunk
    chunk = get_chunk(chunk_x, chunk_y)

    # Return the tile type
    return chunk[local_y][local_x]

# === DRAW FUNCTIONS ===
def draw_inventory():
    slot_rects = get_inventory_slot_rects()
    for i, rect in enumerate(slot_rects):
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        if inventory[i]:
            img = ITEM_IMAGES[inventory[i]["type"]]
            img_rect = img.get_rect(center=rect.center)
            WIN.blit(img, img_rect)
            
            # Draw durability bars
            if "dur" in inventory[i]:
                max_dur = MAX_ITEM_DUR[inventory[i]["type"]]
                dur_ratio = inventory[i]["dur"] / max_dur
                bar_width = int(rect.width * dur_ratio)
                pygame.draw.rect(WIN, (0, 200, 0), (rect.x, rect.bottom - 6, bar_width, 5))

def draw_right_arrow():
    pygame.draw.polygon(WIN, BLACK, [
        (right_arrow_rect.x, right_arrow_rect.y),
        (right_arrow_rect.x, right_arrow_rect.y + right_arrow_rect.height),
        (right_arrow_rect.x + right_arrow_rect.width, right_arrow_rect.y + right_arrow_rect.height // 2)
    ])

def draw_down_arrow(): # draw a down arrow for structure crafting
    pygame.draw.polygon(WIN, BLACK, [
        (down_arrow_rect.x, down_arrow_rect.y),
        (down_arrow_rect.x + down_arrow_rect.width, down_arrow_rect.y),
        (down_arrow_rect.x + down_arrow_rect.width // 2, down_arrow_rect.y + down_arrow_rect.height)
    ])

def draw_crafting_gui():
    pygame.draw.rect(WIN, DARK_GRAY, craft_gui_rect)
    pygame.draw.rect(WIN, BLACK, craft_gui_rect, 3)

    # Draw input slots
    for i, rect in enumerate(craft_slot_rects):
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        if craft_slots[i]:
            item = craft_slots[i]
            img = ITEM_IMAGES[item["type"]]
            img_rect = img.get_rect(center=rect.center)
            WIN.blit(img, img_rect)

            # === Durability bar (for tools) ===
            if "dur" in item:
                max_dur = MAX_ITEM_DUR[item["type"]]
                dur_ratio = item["dur"] / max_dur
                bar_width = int(rect.width * dur_ratio)
                pygame.draw.rect(WIN, (0, 200, 0), (rect.x, rect.bottom - 6, bar_width, 5))
                pygame.draw.rect(WIN, BLACK, (rect.x, rect.bottom - 6, rect.width, 5), 1)

    # Draw arrow
    draw_right_arrow()

    # Draw output slots
    for out in craft_output_slots:
        rect = out["rect"]
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        img = ITEM_IMAGES[out["item"]]
        img_rect = img.get_rect(center=rect.center)
        WIN.blit(img, img_rect)

        # === Durability bar for crafted items (if any) ===
        if out["item"] in MAX_ITEM_DUR:
            max_dur = MAX_ITEM_DUR[out["item"]]
            dur_ratio = 1.0  # crafted items start full
            bar_width = int(rect.width * dur_ratio)
            pygame.draw.rect(WIN, (0, 200, 0), (rect.x, rect.bottom - 6, bar_width, 5))
            pygame.draw.rect(WIN, BLACK, (rect.x, rect.bottom - 6, rect.width, 5), 1)

def draw_structure_crafting_gui():
    pygame.draw.rect(WIN, DARK_GRAY, structure_frame_rect)
    pygame.draw.rect(WIN, BLACK, structure_frame_rect, 3)

    # draw slots
    for i, rect in enumerate(structure_crafting_slot_rects):
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        if structure_crafting_slots[i]:
            item = structure_crafting_slots[i]
            img = ITEM_IMAGES[item["type"]]
            img_rect = img.get_rect(center=rect.center)
            WIN.blit(img, img_rect)

    # draw output slot
    pygame.draw.rect(WIN, LIGHT_GRAY, output_structure_slot_rect)
    pygame.draw.rect(WIN, BLACK, output_structure_slot_rect, 2)

    # draw output structure
    if output_structure is not None:
        img = STRUCTURE_IMAGES[output_structure]
        img_rect = img.get_rect(center=output_structure_slot_rect.center)
        WIN.blit(img, img_rect.topleft)

    # draw arrow
    draw_down_arrow()

active_lights = []  # Track structures that emit light

def update_structure_lighting():
    global active_lights
    active_lights.clear()
    
    for structure in structures:
        if structure["type"] in STRUCTURE_SPECIALS:
            specs = STRUCTURE_SPECIALS[structure["type"]]
            if "light_radius" in specs:
                # Add light flickering if specified
                intensity = specs["light_intensity"]
                if "light_flickering" in specs:
                    timer, min_int, max_int = specs["light_flickering"]
                    flicker = math.sin(time.time() / timer) * (max_int - min_int) / 2
                    intensity = min_int + (max_int - min_int) / 2 + flicker
                
                active_lights.append({
                    "x": structure["x"],
                    "y": structure["y"],
                    "radius": specs["light_radius"] * TILE_SIZE,
                    "intensity": intensity
                })

def draw_status_bars():
    bar_width = 200
    bar_height = 30
    x = 20
    y = 20

    def draw_bar(label, value, max_value, color, offset):
        pygame.draw.rect(WIN, (50, 50, 50), (x, y + offset, bar_width, bar_height))
        fill_width = int((value / max_value) * bar_width)
        pygame.draw.rect(WIN, color, (x, y + offset, fill_width, bar_height))
        label_text = font.render(f"{label}: {int(value)}", True, (255, 255, 255))
        WIN.blit(label_text, (x + 5, y + offset))

    draw_bar("Health", health, MAX_HEALTH, (200, 50, 50), 0)
    draw_bar("Hunger", hunger, MAX_HUNGER, (200, 150, 50), 40)
    draw_bar("Thirst", thirst, MAX_THIRST, (50, 100, 255), 80)
    draw_bar("Stamina", stamina, MAX_STAMINA, (100, 255, 100), 120)

def draw_lighting(camera_x, camera_y):
    """Draw dynamic lighting effects."""
    # Fill with dark overlay
    LIGHT_SURFACE.fill(LIGHT_COLOR)
    
    # Draw light circles for each light source
    for light in active_lights:
        # Convert world position to screen position
        screen_x = int(light["x"] - camera_x)
        screen_y = int(light["y"] - camera_y)
        
        # Create light gradient
        radius = int(light["radius"])
        intensity = light["intensity"]
        
        # Draw multiple circles with decreasing alpha for smooth gradient
        steps = 10
        for i in range(steps):
            current_radius = radius * (1 - i/steps)
            alpha = int(255 * (intensity/steps) * (1 - i/steps))
            pygame.draw.circle(LIGHT_SURFACE, (255, 200, 100, alpha),
                             (screen_x + STRUCTURE_SIZE//2, screen_y + STRUCTURE_SIZE//2), 
                             int(current_radius))
    
    # Blit the light surface using alpha blending
    WIN.blit(LIGHT_SURFACE, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

# === MAIN LOOP ===
player_x, player_y = find_spawn_location()
paused = False
dead = False

items.append({"type": "ceramic_cup", "x": player_x, "y": player_y})

shown_info = None
shown_button = pygame.Rect(0,0,0,0)

running = True
while running:
    dt = clock.tick(60) / 1000
    mouse_pos = pygame.mouse.get_pos()
    world_mouse_x = mouse_pos[0] + (player_x - WIDTH // 2)
    world_mouse_y = mouse_pos[1] + (player_y - HEIGHT // 2)
    world_mouse = (world_mouse_x, world_mouse_y)

    now = time.time()
    total_items = len(items)
    total_structs = len(structures)
    if (total_items != last_items_count or total_structs != last_structures_count
            or now - last_qt_rebuild_time > QT_REBUILD_INTERVAL):
        rebuild_quadtree()
        last_qt_rebuild_time = now
        last_items_count = total_items
        last_structures_count = total_structs

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if not paused:
            # === Toggle Crafting GUI ===
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_e: # Open crafting GUI
                    crafting_visible = not crafting_visible
                    if crafting_structures_visible:
                        crafting_structures_visible = False
                    if crafting_visible:
                        update_craft_output()
                    else:
                        # Return items in craft slots to inventory
                        for i in range(2):
                            if craft_slots[i]:
                                for j in range(2):
                                    if inventory[j] is None:
                                        inventory[j] = craft_slots[i]
                                        craft_slots[i] = None
                                        break
                elif event.key == pygame.K_h: # Harvest a plant
                    for plant in plants[:]:
                        plant_rect = pygame.Rect(plant["x"], plant["y"], PLANT_SIZE, PLANT_SIZE)
                        distance = ((player_x - plant_rect.centerx) ** 2 +
                                    (player_y - plant_rect.centery) ** 2) ** 0.5
                        if distance < player_size*2 and plant_rect.collidepoint(world_mouse):
                            plant_stats = PLANT_STATS["mung_bean"]
                            if plant["growth_stage"] == plant_stats["last_stage_last"]:
                                stage_drop = "lastlast_drop"
                            elif plant["growth_stage"] == plant_stats["last_stage"]:
                                stage_drop = "last_drop"
                            else:
                                stage_drop = "prelast_drop"
                            drops = plant_stats[stage_drop]
                            if drops is not None:
                                for drop in drops:
                                    items.append({"type": drop, "x": plant["x"]+random.randint(-TILE_SIZE//2, TILE_SIZE//2), "y": plant["y"]+random.randint(-TILE_SIZE//2, TILE_SIZE//2)})
                            plants.remove(plant)
                elif event.key == pygame.K_p: # Open crafting structures GUI
                    crafting_structures_visible = not crafting_structures_visible
                    if crafting_visible:
                        crafting_visible = False
                if event.key == pygame.K_RETURN and output_structure:
                    place_x = world_mouse_x
                    place_y = world_mouse_y

                    structures.append(get_structure(output_structure, place_x, place_y))
                    structure_crafting_slots = [None, None]
                    update_structure_gui()

            # === Mouse down ===
            if event.type == pygame.MOUSEBUTTONDOWN:
                # GUI closed → pick/drop
                if not (crafting_visible or crafting_structures_visible):
                    if event.button == 1 and shown_info and shown_info[3].collidepoint(mouse_pos):
                        name = shown_info[0]
                        if name in FOOD_STATS:
                            food = FOOD_STATS[name]
                            hunger = min(MAX_HUNGER, hunger + food["hunger"])
                            thirst = max(0, min(MAX_THIRST, thirst + food["thirst"]))
                            stamina = min(MAX_STAMINA, stamina + food["stamina"])
                            # remove eaten item
                            for i in range(2):
                                if inventory[i] and inventory[i]["type"] == name:
                                    food_converts = FOOD_CONVERTS[inventory[i]["type"]]
                                    if food_converts is not None:
                                        inventory[i]["type"] = food_converts
                                        shown_info = None
                                    else:
                                        inventory[i] = None
                                    break
                    player_rect = pygame.Rect(player_x, player_y, player_size, player_size)
                    # Drop item
                    for i, rect in enumerate(get_inventory_slot_rects()):
                        if event.button == 1 and rect.collidepoint(mouse_pos) and inventory[i] is not None:
                            dropped = inventory[i]
                            drop_x = player_x
                            drop_y = player_y
                            dropped["x"] = drop_x
                            dropped["y"] = drop_y
                            
                            # Check for nearby structures
                            structure_range = STRUCTURE_SIZE  # Define this constant if not already defined
                            interacted = False
                            
                            for structure in structures:
                                structure_rect = pygame.Rect(structure["x"], structure["y"], STRUCTURE_SIZE, STRUCTURE_SIZE)
                                if ((structure_rect.centerx - drop_x) ** 2 + 
                                    (structure_rect.centery - drop_y) ** 2) <= structure_range ** 2:
                                    # Found nearby structure, handle interaction
                                    keep_item = handle_structure_interaction(structure, dropped)
                                    if not keep_item:
                                        inventory[i] = None
                                        interacted = True
                                        break
                                    
                            if not interacted:
                                # No interaction occurred, drop item normally
                                items.append(dropped)
                                inventory[i] = None
                    else:
                        # First: check deferred/generated items on this tile (not yet in `items`)
                        tile_x = int(world_mouse_x // TILE_SIZE)
                        tile_y = int(world_mouse_y // TILE_SIZE)
                        if (tile_x, tile_y) in WORLD_TILE_ITEMS and event.button == 1:
                            # promote generated item into world or inventory
                            gen_item = WORLD_TILE_ITEMS.pop((tile_x, tile_y))
                            # place item at tile center
                            gen_item["x"] = tile_x * TILE_SIZE + TILE_SIZE // 2
                            gen_item["y"] = tile_y * TILE_SIZE + TILE_SIZE // 2

                            # if player is close enough, try to put directly into inventory
                            tile_center_x = gen_item["x"]
                            tile_center_y = gen_item["y"]
                            distance = ((player_rect.centerx - tile_center_x) ** 2 + (player_rect.centery - tile_center_y) ** 2) ** 0.5
                            if distance < player_size * 2:
                                placed_to_inventory = False
                                for i in range(2):
                                    if inventory[i] is None:
                                        inventory[i] = gen_item
                                        placed_to_inventory = True
                                        break
                                if not placed_to_inventory:
                                    items.append(gen_item)
                                    if QT_ROOT:
                                        QT_ROOT.insert(int(gen_item["x"]), int(gen_item["y"]), gen_item)
                            else:
                                # too far, just spawn into world items so it can be picked later
                                items.append(gen_item)
                                if QT_ROOT:
                                    QT_ROOT.insert(int(gen_item["x"]), int(gen_item["y"]), gen_item)
                        else:
                            # fallback: pick up already-active items via quadtree as before
                            if QT_ROOT:
                                query_rect = pygame.Rect(world_mouse_x - 100, world_mouse_y - 100, 200, 200)
                                nearby_items = QT_ROOT.query_range(query_rect)
                                for item in nearby_items:
                                    item_rect = pygame.Rect(item["x"], item["y"], ITEM_SIZE, ITEM_SIZE)
                                    distance = ((player_rect.centerx - item_rect.centerx)**2 + (player_rect.centery - item_rect.centery)**2)**0.5
                                    if event.button == 1 and item_rect.collidepoint(world_mouse) and distance < player_size*2:
                                        for i in range(2):
                                            if item in items and inventory[i] is None:
                                                inventory[i] = item  # directly store the whole item dict
                                                items.remove(item)
                                                break
                                        break
                # GUI open → drag or craft
                elif crafting_visible:
                    if event.button == 1:
                        # Click arrow to craft
                        if right_arrow_rect.collidepoint(mouse_pos):
                            perform_craft()
                            break

                    # Check crafting slots for drag
                    for i, rect in enumerate(craft_slot_rects):
                        if rect.collidepoint(mouse_pos) and craft_slots[i]:
                            if event.button == 1:
                                drag_item = craft_slots[i]
                                craft_slots[i] = None
                                drag_origin = ("craft", i)
                                drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                                break
                            elif event.button == 3:
                                # Right-click to remove item back to inventory
                                if craft_slots[i]:
                                    for j in range(2):
                                        if inventory[j] is None:
                                            inventory[j] = craft_slots[i]
                                            craft_slots[i] = None
                                            update_craft_output()
                                            break
                                break

                    # Check inventory slots for drag
                    for i, rect in enumerate(get_inventory_slot_rects()):
                        if rect.collidepoint(mouse_pos) and inventory[i]:
                            if event.button == 1:
                                drag_item = inventory[i]
                                inventory[i] = None
                                drag_origin = ("inventory", i)
                                drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                                break
                            elif event.button == 3:
                                # Right-click to move item to crafting slot
                                if inventory[i]:
                                    for j, craft_rect in enumerate(craft_slot_rects):
                                        if not craft_slots[j]:
                                            craft_slots[j] = inventory[i]
                                            inventory[i] = None
                                            update_craft_output()
                                            break
                                break
                elif crafting_structures_visible:
                    # Check crafting slots for drag
                    for i, rect in enumerate(structure_crafting_slot_rects):
                        if rect.collidepoint(mouse_pos) and structure_crafting_slots[i]:
                            if event.button == 1:
                                drag_item = structure_crafting_slots[i]
                                structure_crafting_slots[i] = None
                                drag_origin = ("structure", i)
                                drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                                break
                            elif event.button == 3:
                                # Right-click to remove item back to inventory
                                if structure_crafting_slots[i]:
                                    for j in range(2):
                                        if inventory[j] is None:
                                            inventory[j] = structure_crafting_slots[i]
                                            structure_crafting_slots[i] = None
                                            update_structure_gui()
                                            break
                                break

                    # Check inventory slots for drag
                    for i, rect in enumerate(get_inventory_slot_rects()):
                        if rect.collidepoint(mouse_pos) and inventory[i]:
                            if event.button == 1:
                                drag_item = inventory[i]
                                inventory[i] = None
                                drag_origin = ("inventory", i)
                                drag_offset = (mouse_pos[0] - rect.x, mouse_pos[1] - rect.y)
                                break
                            elif event.button == 3:
                                # Right-click to move item to crafting slot
                                if inventory[i]:
                                    for j, craft_rect in enumerate(structure_crafting_slot_rects):
                                        if not structure_crafting_slots[j]:
                                            structure_crafting_slots[j] = inventory[i]
                                            inventory[i] = None
                                            update_structure_gui()
                                            break
                                break

            # === Mouse up ===
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drag_item:
                placed = False

                if crafting_visible:
                    for i, rect in enumerate(craft_slot_rects):
                        if rect.collidepoint(mouse_pos) and not craft_slots[i]:
                            craft_slots[i] = drag_item
                            placed = True
                            break
                    for i, rect in enumerate(get_inventory_slot_rects()):
                        if rect.collidepoint(mouse_pos) and not inventory[i]:
                            inventory[i] = drag_item
                            placed = True
                            break
                    update_craft_output()

                if crafting_structures_visible:
                    for i, rect in enumerate(structure_crafting_slot_rects):
                        if rect.collidepoint(mouse_pos) and not structure_crafting_slots[i]:
                            structure_crafting_slots[i] = drag_item
                            placed = True
                            break
                    for i, rect in enumerate(get_inventory_slot_rects()):
                        if rect.collidepoint(mouse_pos) and not inventory[i]:
                            inventory[i] = drag_item
                            placed = True
                            break
                    update_structure_gui()

                if not placed and drag_origin:
                    origin_type, idx = drag_origin
                    if origin_type == "inventory":
                        inventory[idx] = drag_item
                    elif origin_type == "craft":
                        craft_slots[idx] = drag_item
                    elif origin_type == "structure":
                        structure_crafting_slots[idx] = drag_item

                drag_item = None
                drag_origin = None

    if not paused:
        # === Movement ===
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            player_x -= player_speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            player_x += player_speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            player_y -= player_speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_y += player_speed

        # === UPDATE PLAYER STATS ===
        # Gradual hunger/thirst decay
        hunger -= HUNGER_DECAY * dt / 10
        thirst -= THIRST_DECAY * dt / 10

        # Clamp to 0–MAX
        hunger = max(0, min(MAX_HUNGER, hunger))
        thirst = max(0, min(MAX_THIRST, thirst))

        # === STAMINA ===
        moving = keys[pygame.K_w] or keys[pygame.K_a] or keys[pygame.K_s] or keys[pygame.K_d]
        if moving:
            stamina -= STAMINA_DRAIN * dt
        else:
            stamina += STAMINA_RECOVER * dt
        stamina = max(0, min(MAX_STAMINA, stamina))

        # === HEALTH ===
        # Lose health if starving/dehydrated
        if hunger <= 0 or thirst <= 0:
            health -= 5 * dt  # slow damage
        else:
            # Small passive regen if full
            if hunger > 80 and thirst > 80:
                health += 1 * dt
        health = max(0, min(MAX_HEALTH, health))

        # === DEATH CHECK ===
        if health <= 0:
            dead = True
            paused = True

        # Update structure effects
        update_structure_lighting()
        update_structures(dt)
        
        # Check for items being cooked
        for item in items[:]:
            for structure in structures:
                if abs(item["x"] - structure["x"]) < STRUCTURE_SIZE and \
                abs(item["y"] - structure["y"]) < STRUCTURE_SIZE:
                    handle_cooking(structure, item)

    """player_x = max(0, min(WIDTH - player_size, player_x))
    player_y = max(0, min(HEIGHT - player_size, player_y))"""

    # === UPDATE PLANTS ===
    for plant in plants:
        tile = get_tile_at(plant["x"], plant["y"])
        if tile in PLANT_STATS[plant["type"]]["only_tiles"]:
            plant["growth_timer"] += dt / 60  # convert seconds to minutes
            stats = PLANT_STATS[plant["type"]]
            stages = stats["stages"]

            # Find the current stage index
            current_stage_index = next((i for i, s in enumerate(stages) if s["name"] == plant["growth_stage"]), -1)

            # Only update if we're in the stage list (not already in flowering/fruited)
            if current_stage_index != -1:
                current_stage = stages[current_stage_index]
                # Check if enough time has passed to move to next stage
                if plant["growth_timer"] >= current_stage["timer_mins"]:
                    plant["growth_timer"] = 0  # reset timer for next stage
                    next_index = current_stage_index + 1

                    if next_index < len(stages):
                        plant["growth_stage"] = stages[next_index]["name"]
                    else:
                        plant["growth_stage"] = stats["last_stage"]

            # If already flowering and enough time passes, go to fruited
            elif plant["growth_stage"] == stats["last_stage"]:
                if plant["growth_timer"] > stats["fruit_time"]:
                    plant["growth_stage"] = stats["last_stage_last"]

    # === UPDATE ITEMS ===
    for item in items:
        if item["type"] in ITEM_CONVERT:
            item["timer"] = item.get("timer", ITEM_CONVERT[item["type"]][0])
            item["timer"] -= dt
            if item["timer"] <= 0 and ITEM_CONVERT[item["type"]][1] is not None:
                item["type"] = ITEM_CONVERT[item["type"]][1]
                if item["type"] in MAX_ITEM_DUR:
                    item["dur"] = MAX_ITEM_DUR[item["type"]]
                del item["timer"]
            elif item["timer"] <= 0 and ITEM_CONVERT[item["type"]][1] is None:
                items.remove(item)
                break
        tile = get_tile_at(item["x"]//TILE_SIZE, item["y"]//TILE_SIZE)
        if item["type"] in ITEM_TILE_INTERACTION:
            interaction = ITEM_TILE_INTERACTION[item["type"]]
            if tile in interaction:
                tile_interaction = interaction[tile]
                item_converts = tile_interaction["item_converts"]
                if item_converts is not None:
                    item["type"] = item_converts
                    if item["type"] in MAX_ITEM_DUR:
                        item["dur"] = MAX_ITEM_DUR[item["type"]]

    # === HOTBAR ITEMS INFO ===
    slot_rects = get_inventory_slot_rects()
    new_info = None
    for i in range(2):
        if slot_rects[i].collidepoint(mouse_pos) and inventory[i] is not None:
            new_info = [inventory[i]["type"], slot_rects[i], inventory[i]["type"] in FOOD_STATS, pygame.Rect(0,0,0,0)]
            break

    # Only clear shown_info if not hovering hotbar or info box
    info_hovered = False
    if shown_info is not None and shown_info[3].width > 0 and shown_info[3].height > 0:
        if shown_info[3].collidepoint(mouse_pos):
            info_hovered = True

    if new_info is not None:
        shown_info = new_info
    elif not info_hovered:
        shown_info = None

    i = get_inventory_slot_rects().index(shown_info[1]) if shown_info else -1
    if i != -1 and inventory[i] is None:
        shown_info = None

    # === DRAW EVERYTHING ===
    WIN.fill(WHITE)
    # === CAMERA ===
    camera_x = player_x - WIDTH // 2
    camera_y = player_y - HEIGHT // 2

    current_time = time.time()
    if current_time - last_unload_time > UNLOAD_INTERVAL:
        unload_far_entities(player_x, player_y, CHUNK_SIZE*TILE_SIZE*4)
        last_unload_time = current_time

    # === WORLD DRAW ===
    player_chunk_x = (player_x // TILE_SIZE) // CHUNK_SIZE
    player_chunk_y = (player_y // TILE_SIZE) // CHUNK_SIZE
    # Unload far chunks only occasionally or when the player changes chunk to reduce hitches
    if (player_chunk_x, player_chunk_y) != last_player_chunk or (time.time() - last_unload_chunks_time) > UNLOAD_CHUNK_INTERVAL:
        unload_far_chunks(player_chunk_x, player_chunk_y)
        last_unload_chunks_time = time.time()
        last_player_chunk = (player_chunk_x, player_chunk_y)
    draw_world(camera_x, camera_y)

    # === DRAW INACTIVE / GENERATED (DIRTY) TILE ITEMS ===
    # These are items generated for tiles but not yet promoted into `items`.
    # Draw them faded so player can see they exist but they are "inactive".
    visible_rect = pygame.Rect(camera_x, camera_y, WIDTH, HEIGHT)
    for (tx, ty), gen_item in WORLD_TILE_ITEMS.items():
        # tile center in world pixels
        wx = tx * TILE_SIZE + TILE_SIZE // 2
        wy = ty * TILE_SIZE + TILE_SIZE // 2
        item_type = gen_item.get("type")
        if not item_type or item_type not in ITEM_IMAGES:
            continue
        # quick visibility check
        if not visible_rect.collidepoint(wx, wy):
            continue
        screen_x = wx - camera_x - ITEM_SIZE // 2
        screen_y = wy - camera_y - ITEM_SIZE // 2
        # draw a faded copy so it's visually distinct from active items
        img = ITEM_IMAGES[item_type]
        faded = img.copy()
        # alpha 140 makes it look "inactive" — tweak as needed
        faded.set_alpha(140)
        WIN.blit(faded, (screen_x, screen_y))

    # === ITEMS ===
    chunk_range = 3 * CHUNK_SIZE * TILE_SIZE
    for item in items:
        if abs(item["x"] - player_x) <= chunk_range and abs(item["y"] - player_y) <= chunk_range:
            screen_x = item["x"] - camera_x
            screen_y = item["y"] - camera_y
            WIN.blit(ITEM_IMAGES[item["type"]], (screen_x, screen_y))

    # === PLANTS ===
    for plant in plants:
        screen_x = plant["x"] - camera_x
        screen_y = plant["y"] - camera_y
        stage = plant["growth_stage"]
        img = PLANT_IMAGES[plant["type"]][stage]
        WIN.blit(img, (screen_x, screen_y))

    # === PLAYER ===
    player_screen_x = WIDTH // 2 - player_size // 2
    player_screen_y = HEIGHT // 2 - player_size // 2
    mouse_player_atan2 = math.atan2((mouse_pos[1] - player_screen_y) - player_size//2, (mouse_pos[0] - player_screen_x) - player_size//2)
    player_texture_rotated = pygame.transform.rotate(player_texture, -math.degrees(mouse_player_atan2) - 90)
    player_rect = player_texture_rotated.get_rect(center=(WIDTH//2, HEIGHT//2))
    WIN.blit(player_texture_rotated, player_rect.topleft)

    # === STRUCTURES ===
    for structure in structures:
        screen_x = structure["x"] - camera_x
        screen_y = structure["y"] - camera_y
        img = STRUCTURE_IMAGES[structure["type"]]
        WIN.blit(img, (screen_x, screen_y))

    # === LIGHTING === (add this)
    #draw_lighting(camera_x, camera_y)

    # === GUI (no camera offset) ===
    draw_inventory()
    draw_status_bars()

    for item in items:
        screen_x = item["x"] - camera_x
        screen_y = item["y"] - camera_y
        screen_rect = pygame.Rect(screen_x, screen_y, ITEM_SIZE, ITEM_SIZE)
        if screen_rect.collidepoint(mouse_pos):
            info_text = font.render(item["type"], True, BLACK)
            WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] + 15))
            if "dur" in item:
                dur_text = font.render(f"Durability: {(item['dur'] / MAX_ITEM_DUR[item['type']])*100:.2f}%", True, BLACK)
                WIN.blit(dur_text, (mouse_pos[0] + 15, mouse_pos[1] + 35))
            if "timer" in item:
                timer_text = font.render(f"{ITEM_CONVERT_LABELS[item['type']]}{item['timer']:.1f}s", True, BLACK)
                WIN.blit(timer_text, (mouse_pos[0] + 15, mouse_pos[1] + 55))
            break

    for structure in structures:
        screen_x = structure["x"] - camera_x
        screen_y = structure["y"] - camera_y
        screen_rect = pygame.Rect(screen_x, screen_y, STRUCTURE_SIZE, STRUCTURE_SIZE)
        if screen_rect.collidepoint(mouse_pos):
            info_text = font.render(structure["type"], True, BLACK)
            WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 15))
            if "timer" in structure:
                info_text = font.render(f"Burns in: {structure['timer']}", True, BLACK)
                WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 35))
            break

    if crafting_structures_visible:
        draw_structure_crafting_gui()
    elif crafting_visible:
        draw_crafting_gui()
    elif shown_info is not None:
        name, rect, is_edible, name_rect = shown_info
        if not is_edible:
            name_text = font.render(name, True, (0, 0, 0))
            text_rect = name_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-12
            shown_info[3] = WIN.blit(name_text, text_rect.topleft)
        else:
            eat_text = font.render("> "+CONSUME_TYPES[name], True, (100, 230, 100) if shown_button.collidepoint(mouse_pos) else (0, 0, 0))
            text_rect = eat_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-12
            shown_button = WIN.blit(eat_text, text_rect.topleft)
            shown_info[3] = shown_button
            name_text = font.render(name, True, (0, 0, 0))
            text_rect = name_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-32
            WIN.blit(name_text, text_rect.topleft)

    # === DRAGGED ITEM (GUI layer) ===
    if drag_item:
        WIN.blit(ITEM_IMAGES[drag_item["type"]],
                (mouse_pos[0] - drag_offset[0] + 10, mouse_pos[1] - drag_offset[1] + 10))
        
    pygame.display.update()

pygame.quit()
sys.exit()
