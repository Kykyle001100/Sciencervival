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
from pygame import mask

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
LIGHT_GRAY = (200, 200, 200)
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
# Add these new variables
player_vel_x = 0
player_vel_y = 0
player_acceleration = player_speed  # Acceleration rate
player_friction = 0.5  # Friction coefficient

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
STAMINA_DRAIN = 0.1     # per second (when moving)

MAX_DELTA_TIME = 0.2  # Maximum allowed delta time (seconds)
MAX_VELOCITY = 5000    # Maximum velocity for player movement

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
    "water": pygame.image.load(os.path.join(TILE_PATH, "saltwater.png")),
    "sedimentary_iron": pygame.image.load(os.path.join(TILE_PATH, "sedimentary_iron.png")),
    "laterite_soil": pygame.image.load(os.path.join(TILE_PATH, "laterite_soil.png")),
    "freshwater": pygame.image.load(os.path.join(TILE_PATH, "freshwater.png")),
    "iob": pygame.image.load(os.path.join(TILE_PATH, "iob.png")),
    "earthworm_dirt": pygame.image.load(os.path.join(TILE_PATH, "earthworm_dirt.png")),
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
            {"name": "ve", "timer_mins": 1, "max_health": 1},
            {"name": "v1", "timer_mins": 1, "max_health": 1},
            {"name": "v2", "timer_mins": 1, "max_health": 1},
            {"name": "v3", "timer_mins": 3, "max_health": 1},
            {"name": "v6", "timer_mins": 3, "max_health": 1},
        ],
        "last_stage": "flowering", # max_health = prelast_max_health averaged
        "last_stage_last": "fruited", # max_health = prelast_max_health averaged
        "only_tiles": ["grass", "dirt"],
        "can_collide": False,
        "harvest": {
            "ve": "harvest",
            "v1": "harvest",
            "v2": "harvest",
            "v3": "harvest",
            "v6": "harvest",
            "flowering": "harvest",
            "fruited": "harvest",
        }
    },
    "bamboo": {
        "pollination": None,
        "fruit_time": None,
        "lastlast_drop": [],
        "last_drop": [],
        "prelast_drop": ["bamboo_shoot"],
        "stages": [
            {"name": "shoot", "timer_mins": 4, "max_health": 5},
            {"name": "grown_shoot", "timer_mins": 4, "max_health": 10},
            {"name": "v1", "timer_mins": 10, "max_health": 20},
            {"name": "v2", "timer_mins": 10, "max_health": 40},
            {"name": "v3", "timer_mins": 10, "max_health": 60},
        ],
        "last_stage": None,
        "last_stage_last": None,
        "only_tiles": ["grass", "dirt"],
        "can_collide": True,
        "harvest": {
            "shoot": "harvest",
            "grown_shoot": "harvest",
            "v1": "chop",
            "v2": "chop",
            "v3": "chop",
        }
    }
}

# Scale tiles to match TILE_SIZE
for key in TILE_IMAGES:
    TILE_IMAGES[key] = pygame.transform.scale(TILE_IMAGES[key], (TILE_SIZE, TILE_SIZE))

CHUNK_SIZE = 16
WORLD_SEED = 9
NOISE = noise.combine_noise_smooth(noise.make_fractal_mask(WORLD_SEED, ),noise.make_perlin(WORLD_SEED))
ORE_NOISE = noise.make_ore_patches(WORLD_SEED+1, [0.05, 0.1], [0.4, 0.5])
LAKE_NOISE = noise.make_ore_patches(WORLD_SEED+2, [0.05], [0.52])
world_chunks = {}
items = []
plants = []
animals = []
WORLD_TILE_ITEMS = {}  # {(tile_x, tile_y): item_dict} — deferred/generated items not yet in `items`

def spawn_plant(plant_type, x, y, growth_stage="ve", growth_timer=0):
    stages = PLANT_STATS[plant_type]["stages"]
    stage = None
    for s in stages:
        if s["name"] == growth_stage:
            stage = s

    plant = {
        "type": plant_type,
        "x": x,
        "y": y,
        "growth_stage": growth_stage,
        "growth_timer": growth_timer,
        "health": 1 if stage is None else stage["max_health"]
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
        elif h < 0.08:
            stages = PLANT_STATS["bamboo"]["stages"]
            stage = stages[int(sh*(len(stages)-1))]
            return spawn_plant("bamboo", px, py, stage["name"], stage["timer_mins"]*th)
        
def get_tile(world_x, world_y):
    r = NOISE(world_x / 100, world_y / 100)

    if r < 0.3:
        tile = "water"
    elif r < 0.4:
        tile = "sand"
    elif r < 0.41:
        tile = "dirt"
    elif r < 0.6:
        tile = "grass"
        lake = LAKE_NOISE(world_x, world_y)
        if lake != 0:
            tile = "freshwater"
            ore = ORE_NOISE(world_x, world_y)
            if ore != 0:
                ore_name = ORE_TYPES[ore - 1]["name"]
                if ore_name == "sedimentary_iron":
                    tile = "iob"
        else:
            h = float(int(hashlib.md5(f"{world_x}___{world_y}___{WORLD_SEED}".encode()).hexdigest(), 16) % 100) / 100.0
            if h < 0.01:
                tile = "earthworm_dirt"
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

    return tile

def generate_chunk(cx, cy):
    """Generate a single chunk of terrain and spawn items into global items list."""
    chunk_tiles = []
    
    for ty in range(CHUNK_SIZE):
        row = []
        for tx in range(CHUNK_SIZE):
            world_x = cx * CHUNK_SIZE + tx
            world_y = cy * CHUNK_SIZE + ty
            tile = get_tile(world_x, world_y)
            
            row.append(tile)
            
            # Spawn animals (with very low probability)
            if random.random() < 0.1:  # Adjust probability as needed
                if tile == "grass":
                    if random.random() < 0.8:
                        animals.append(spawn_animal("earthworm", 
                            world_x * TILE_SIZE + TILE_SIZE//2,
                            world_y * TILE_SIZE + TILE_SIZE//2))
                    else:
                        animals.append(spawn_animal("pigeon",
                            world_x * TILE_SIZE + TILE_SIZE//2,
                            world_y * TILE_SIZE + TILE_SIZE//2))
                        
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

    for tile_y in range(int(start_tile_y), int(end_tile_y)):
        for tile_x in range(int(start_tile_x), int(end_tile_x)):
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
    },
    "bamboo": {
        "shoot": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("bamboo", "shoot.png"))),
        "grown_shoot": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("bamboo", "grown_shoot.png"))),
        "v1": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("bamboo", "v1.png"))),
        "v2": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("bamboo", "v2.png"))),
        "v3": pygame.image.load(os.path.join(PLANT_PATH, os.path.join("bamboo", "v3.png"))),
    }
}
for plant_type in PLANT_IMAGES:
    for stage in PLANT_IMAGES[plant_type]:
        PLANT_IMAGES[plant_type][stage] = pygame.transform.scale(PLANT_IMAGES[plant_type][stage], (PLANT_SIZE, PLANT_SIZE))

# Create masks for player and plant textures
player_mask = pygame.mask.from_surface(player_texture)
player_mask_radius = max(player_mask.get_size()) // 2

def get_tighter_radius(mask):
    """Get radius excluding empty edges."""
    bbox = mask.get_bounding_rects()[0]
    return max(bbox.width, bbox.height) // 2

PLANT_MASKS = {}
for plant_type in PLANT_IMAGES:
    PLANT_MASKS[plant_type] = {}
    for stage in PLANT_IMAGES[plant_type]:
        texture = PLANT_IMAGES[plant_type][stage]
        plant_mask = pygame.mask.from_surface(texture)
        # Get the actual radius from non-transparent pixels
        w, h = plant_mask.get_size()
        PLANT_MASKS[plant_type][stage] = get_tighter_radius(plant_mask)

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
    "nonfunctional_stone_hatchet": pygame.image.load(os.path.join(RESOURCE_PATH, "nonfunctional_stone_hatchet.png")),
    "stone_hatchet": pygame.image.load(os.path.join(RESOURCE_PATH, "stone_hatchet.png")),
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
    "anoxic_iob_ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "anoxic_iob_ceramic_cup.png")),
    "bamboo_bottle": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo_bottle.png")),
    "green_basket": pygame.image.load(os.path.join(RESOURCE_PATH, "green_basket.png")),
    "green_weaved_cone": pygame.image.load(os.path.join(RESOURCE_PATH, "green_weaved_cone.png")),
    "weaved_fiber": pygame.image.load(os.path.join(RESOURCE_PATH, "weaved_fiber.png")),
    "iron_rock": pygame.image.load(os.path.join(RESOURCE_PATH, "iron_rock.png")),
    "bamboo": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo.png")),
    "hollow_bamboo": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo_pipe.png")),
    "bamboo_bottle": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo_bottle.png")),
    "saltwater_bamboo_bottle": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo_bottle.png")),
    "freshwater_bamboo_bottle": pygame.image.load(os.path.join(RESOURCE_PATH, "bamboo_bottle.png")),
    "earthworm": pygame.image.load(os.path.join(RESOURCE_PATH, "earthworm.png")),
    "earthworm_waste": pygame.image.load(os.path.join(RESOURCE_PATH, "earthworm_waste.png")),
    "fertilizer": pygame.image.load(os.path.join(RESOURCE_PATH, "fertilizer.png")),
    "charcoal": pygame.image.load(os.path.join(RESOURCE_PATH, "charcoal.png")),
    "coal": pygame.image.load(os.path.join(RESOURCE_PATH, "coal.png")),
    "quicklime": pygame.image.load(os.path.join(RESOURCE_PATH, "quicklime.png")),
    "slaked_lime_Ceramic_cup": pygame.image.load(os.path.join(RESOURCE_PATH, "drinkable_water_ceramic_cup.png")),
}

MAX_ITEM_DUR = {
    "sharp_rock": 15,
    "stone_chisel": 5,
    "pointy_stick": 10,
    "fire_plough": 20,
    "stone_hatchet": 50,
}

ITEM_CONVERT = {
    "burning_cotton_boll": [5, None],
    "burning_wood_dust": [10, "ashes"],
    "clay_cup": [60, "dried_clay_cup"],
    "iob_ceramic_cup": [70, "anoxic_iob_ceramic_cup"]
}

MINING_TOOLS = {
    "stone_hatchet": {
        "ores": {
            "sedimentary_iron": {"tool_dur": -20, "ore_converts": "stone", "item_drop": ["iron_rock"]},
        },
        "plants": {
            "bamboo": {"tool_dur": -2, "plant_damage": 7, "plant_converts": None, "item_drop": {"v1": ["bamboo", "bamboo"], "v2": ["bamboo", "bamboo", "bamboo"], "v3": ["bamboo", "bamboo", "bamboo", "bamboo"]}}
        }
    }
}

ITEM_CONVERT_LABELS = {
    "burning_cotton_boll": "Burns in: ",
    "burning_wood_dust": "Burns in: ",
    "cocoa_beans_bamboo_bottle": "Ferments in: ",
    "clay_cup": "Dries in: ",
    "iob_ceramic_cup": "Anoxicates in: "
}

FOOD_STATS = {
    "carrot": {"hunger": 10, "thirst": -10, "stamina": 0},
    "drinkable_water_ceramic_cup": {"hunger": 0, "thirst": 35, "stamina": 10},
    "saltwater_ceramic_cup": {"hunger": 1, "thirst": -15, "stamina": -5},
    "freshwater_ceramic_cup": {"hunger": 1, "thirst": 10, "stamina": 2}
}

FOOD_CONVERTS = {
    "carrot": None,
    "drinkable_water_ceramic_cup": "ceramic_cup",
    "saltwater_ceramic_cup": "ceramic_cup",
    "freshwater_ceramic_cup": "ceramic_cup"
}

CONSUME_TYPES = {
    "carrot": "Eat",
    "drinkable_water_ceramic_cup": "Drink",
    "saltwater_ceramic_cup": "Drink",
    "freshwater_ceramic_cup": "Drink"
}

ITEM_TILE_INTERACTION = {
    "ceramic_cup": {
        "water": {"item_converts": "saltwater_ceramic_cup", "tile_converts": "water"},
        "iob": {"item_converts": "iob_ceramic_cup", "tile_converts": "freshwater"},
        "freshwater": {"item_converts": "freshwater_ceramic_cup", "tile_converts": "dirt"}
    },
    "bamboo_bottle": {
        "water": {"item_converts": "saltwater_bamboo_bottle", "tile_converts": "water"},
        "freshwater": {"item_converts": "freshwater_bamboo_bottle", "tile_converts": "dirt"}
    }
}

STORAGE_ITEMS = {
    "green_basket": {
        "slots": 3,
        "slot_rects": [
            pygame.Rect(0, HEIGHT//2-70, 60, 60),
            pygame.Rect(0, HEIGHT//2, 60, 60),
            pygame.Rect(0, HEIGHT//2+70, 60, 60)
        ],
        "gui_frame_rect": pygame.Rect(WIDTH-90, HEIGHT//2-80, 80, 230),
        "slot_rects_custom": [
            {"centerx": "gui_frame_rect_centerx"},
            {"centerx": "gui_frame_rect_centerx"},
            {"centerx": "gui_frame_rect_centerx"}
        ],
        "not_allowed_items": ["green_basket"]
    }
}

def handle_tool_action(tool_item, target_type, target_data, world_x, world_y):
    """Handle mining ores or chopping plants with tools.
    Returns: (keep_target, keep_tool)"""
    
    if tool_item["type"] not in MINING_TOOLS:
        return True, True  # No effect
        
    tool_data = MINING_TOOLS[tool_item["type"]]
    
    # Check if target is an ore
    if "ores" in tool_data and target_type in tool_data["ores"]:
        ore_data = tool_data["ores"][target_type]
        
        # Update tool durability
        tool_item["dur"] += ore_data["tool_dur"]
        
        # Convert tile
        if ore_data["ore_converts"]:
            chunk_x = world_x // CHUNK_SIZE
            chunk_y = world_y // CHUNK_SIZE
            local_x = world_x % CHUNK_SIZE 
            local_y = world_y % CHUNK_SIZE
            chunk = get_chunk(chunk_x, chunk_y)
            chunk[local_y][local_x] = ore_data["ore_converts"]
            
        # Spawn drops
        for drop in ore_data["item_drop"]:
            items.append({
                "type": drop,
                "x": world_x * TILE_SIZE + random.randint(-20, 20),
                "y": world_y * TILE_SIZE + random.randint(-20, 20)
            })
            
        return False, tool_item["dur"] > 0
        
    # Check if target is a plant
    elif "plants" in tool_data and target_data and target_data["type"] in tool_data["plants"]:
        plant_data = tool_data["plants"][target_data["type"]]
        
        # Update tool durability
        tool_item["dur"] += plant_data.get("tool_dur", 0)
        
        # Damage the plant using configured damage value
        damage = plant_data.get("plant_damage", 0)
        # First, check if this tool can perform the required action on this growth stage
        stage = target_data["growth_stage"]
        plant_stats = PLANT_STATS.get(target_data["type"], {})
        harvest_map = plant_stats.get("harvest", {})
        required_action = harvest_map.get(stage)  # e.g. "harvest" or "chop"
        # If there's a required action and it's not appropriate for this tool, do nothing
        # (Assume tools configured in MINING_TOOLS are intended to perform 'chop' actions)
        if required_action and required_action not in ("chop", "harvest"):
            return True, tool_item["dur"] > 0
        
        # Apply damage and check if plant survives
        target_data["health"] = target_data.get("health", 1) - damage
        if target_data["health"] > 0:
            # still standing (hit effect could be added here)
            return True, tool_item["dur"] > 0
        
        # Plant destroyed: determine drops
        if isinstance(plant_data.get("item_drop"), dict):
            drops = plant_data["item_drop"].get(stage, [])
        else:
            drops = plant_data.get("item_drop", []) or []
        
        # Fallback to plant definition drops if tool config provides none
        if not drops:
            if stage == plant_stats.get("last_stage_last"):
                drops = plant_stats.get("lastlast_drop", []) or []
            elif stage == plant_stats.get("last_stage"):
                drops = plant_stats.get("last_drop", []) or []
            else:
                drops = plant_stats.get("prelast_drop", []) or []
        
        # Spawn drops at plant position
        for drop in drops:
            items.append({
                "type": drop,
                "x": int(target_data.get("x", 0)) + random.randint(-20, 20),
                "y": int(target_data.get("y", 0)) + random.randint(-20, 20)
            })
            
        # Caller should remove the plant if keep_target is False
        return False, tool_item["dur"] > 0
        
    return True, True

ITEM_SIZE = 40
for key in ITEM_IMAGES:
    ITEM_IMAGES[key] = pygame.transform.scale(ITEM_IMAGES[key], (ITEM_SIZE, ITEM_SIZE))

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

# === STORAGE GUI STATE ===
storage_open = None  # when not None contains inventory index of the storage item being opened

def open_storage(inv_index):
    """Open storage held in inventory slot inv_index. Ensure it has a 'contents' list."""
    global storage_open
    if inv_index < 0 or inv_index >= len(inventory):
        return
    item = inventory[inv_index]
    if not item:
        return
    st_def = STORAGE_ITEMS.get(item["type"])
    if not st_def:
        return
    if "contents" not in item:
        item["contents"] = [None] * st_def["slots"]
    storage_open = inv_index

def close_storage():
    global storage_open
    storage_open = None

def get_storage_slot_rects(storage_def):
    """Generate slot rects inside storage_def['gui_frame_rect'] (runtime-calculated)."""
    frame = storage_def.get("gui_frame_rect", pygame.Rect(0,0,200,200))
    slots = storage_def["slots"]
    rects = []
    padding_top = 20
    spacing = slot_size + 10
    for i in range(slots):
        cx = frame.centerx
        rx = cx - slot_size // 2
        ry = frame.y + padding_top + i * spacing
        rects.append(pygame.Rect(rx, ry, slot_size, slot_size))
    return rects

def draw_storage_gui():
    """Draw currently-open storage GUI and its contents."""
    if storage_open is None:
        return
    st_item = inventory[storage_open]
    if not st_item:
        close_storage()
        return
    st_def = STORAGE_ITEMS.get(st_item["type"])
    if not st_def:
        close_storage()
        return
    frame = st_def["gui_frame_rect"]
    pygame.draw.rect(WIN, DARK_GRAY, frame)
    pygame.draw.rect(WIN, BLACK, frame, 3)
    slot_rects = get_storage_slot_rects(st_def)
    contents = st_item.get("contents", [None]*st_def["slots"])
    for i, rect in enumerate(slot_rects):
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        content = contents[i] if i < len(contents) else None
        if content:
            img = ITEM_IMAGES.get(content["type"])
            if img:
                img_rect = img.get_rect(center=rect.center)
                WIN.blit(img, img_rect)

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
        return ["nonfunctional_stone_hatchet"]
    elif sorted(input_types) == sorted(["nonfunctional_stone_hatchet", "hard_fiber"]):
        return ["stone_hatchet"]
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
    elif sorted(input_types) == sorted(["rattan", "rattan"]):
        return ["weaved_fiber"]
    elif sorted(input_types) == sorted(["weaved_fiber", "weaved_fiber"]):
        return ["green_basket"]
    elif sorted(input_types) == sorted(["weaved_fiber", "rattan"]):
        return ["green_weaved_cone"]
    elif sorted(input_types) == sorted(["bamboo", "stone_chisel"]):
        return ["hollow_bamboo"]
    elif sorted(input_types) == sorted(["hollow_bamboo", "raw_rope"]):
        return ["bamboo_bottle"]
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
    elif sorted(input_types) == sorted(["bamboo", "stone_chisel"]):
        return [["stone_chisel", -2]]
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

# === LOAD ANIMALS IMAGE ===
ANIMAL_BASE_SIZE = 80
ANIMAL_PATH = "animals"
ANIMAL_IMAGES = {
    "snail": {
        "animated": False,
        "image": pygame.image.load(os.path.join(ANIMAL_PATH, "snail.png"))
    },
    "cone_snail": {
        "animated": False,
        "image": pygame.image.load(os.path.join(ANIMAL_PATH, "cone_snail.png"))
    },
    "earthworm": {
        "animated": True,
        "frames": [
            pygame.image.load(os.path.join(ANIMAL_PATH, os.path.join("earthworm", "shortened.png"))),
            pygame.image.load(os.path.join(ANIMAL_PATH, os.path.join("earthworm", "extended.png")))
        ],
        "animation_spf": 2.0 # seconds per frame
    },
    "pigeon": {
        "animated": False,
        "image": pygame.image.load(os.path.join(ANIMAL_PATH, "pigeon.png"))
    }
}

for animal, data in ANIMAL_IMAGES.items():
    if not data["animated"]:
        data["image"] = pygame.transform.scale(data["image"], (ANIMAL_BASE_SIZE, ANIMAL_BASE_SIZE))
    else:
        for i, frame in enumerate(data["frames"]):
            data["frames"][i] = pygame.transform.scale(frame, (ANIMAL_BASE_SIZE, ANIMAL_BASE_SIZE))

DEFAULT_ANIMAL_IDLE_TIMER = 5 # seconds when an animal that is goes_idle-True arrives at their target
DEFAULT_ANIMAL_WANDER_RADIUS = 10 # the radius in tiles an animal can when picking a random tile to target
DEFAULT_ANIMAL_PATIENCE = 10 # in seconds, if the animal can't reach the tile in time
# animals have patience, if their patience is lost (patience in seconds <= 0) while going to a tile, they pick another tile
# when picking a tile: if (they can't find a thing from their convert_plant, convert_item, or convert_animal) or (they are not hungry) or (can't find a tile from convert_tile), pick a random tile to go to
# same thing happens when they reach their target tile
ANIMAL_PROPS = {
    "snail": {
        "goes_idle": False,
        "max_health": 10,
        "max_hunger": 10,
        "heal_speed": 1, # per 10 secs
        "heal_threshold": 6, # hunger before healing
        "hunger_decay": 1, # per 30 secs
        "move_speed": 3, # pixels per second
        "convert_plant": {
            "mung_bean": {
                "edible_stages": ["v1", "v2", "v3", "v6", "fruited"],
                "plant_damage": 1, # damage to plant
                "item_converts": None,
                "heal": 2,
                "hunger": 2,
                "animal_damage": 0, # damage to animal
                "eating_duration": 5, # seconds before the plant disappears
                "move_stop": True, # stops animal from moving while eating
            }
        },
        "convert_item": {
            "carrot": {
                "item_converts": None,
                "heal": 0,
                "hunger": 4,
                "animal_damage": 0,
                "eating_duration": 6,
                "move_stop": True,
            }
        },
        "convert_tile": {},
        "convert_animal": {}, # interaction with other animals
        "death_drop": [],
        "pickup_item": None
    },
    "earthworm": {
        "goes_idle": False,
        "max_health": 5,
        "max_hunger": 10,
        "heal_speed": 2, 
        "heal_threshold": 4,
        "hunger_decay": 1,
        "move_speed": 30, 
        "sine_movement": { # oscillating speed
            "min_move_speed": 10,
            "sine_speed": 10 # pixel per frame (multiplied by dt)
        },
        "convert_plant": {
            "mung_bean": {
                "edible_stages": ["ve", "v1", "v2", "v3"],
                "plant_damage": 1,
                "item_converts": "earthworm_waste",
                "heal": 0,
                "hunger": 2,
                "animal_damage": 0,
                "eating_duration": 5,
                "move_stop": False,
            }
        },
        "convert_item": {
            "carrot": {
                "item_converts": "earthworm_waste",
                "heal": 0,
                "hunger": 4,
                "animal_damage": 0,
                "eating_duration": 6,
                "move_stop": True,
            }
        },
        "convert_tile": {
            "grass": {
                "tile_into": "earthworm_dirt",
                "when": {
                    "seconds": 0,
                    "after_timer": False,
                    "after_damaged": True,
                    "of_being_alive": False,
                    "of_being_dead": False,
                    "of_eating": False,
                    "of_near_player": {
                        "radius": 0,
                        "does": False
                    }
                },
                "animal_disappears": True
            }
        },
        "convert_animal": {},
        "death_drop": [],
        "pickup_item": "earthworm"
    },
    "cone_snail": {
        "goes_idle": False,
        "max_health": 10,
        "max_hunger": 10,
        "heal_speed": 1,
        "heal_threshold": 5,
        "hunger_decay": 1,
        "move_speed": 5,
        "convert_plant": {},
        "convert_item": {},
        "convert_animal": {},
        "convert_tile": {},
        "death_drop": [],
        "pickup_item": None
    },
    "pigeon": {
        "goes_idle": True,
        "max_health": 30,
        "max_hunger": 30,
        "heal_speed": 1,
        "heal_threshold": 10,
        "hunger_decay": 2,
        "move_speed": 40,
        "convert_plant": {},
        "convert_item": {
            "mung_beans": {
                "item_converts": None,
                "heal": 0,
                "hunger": 4,
                "animal_damage": 0,
                "eating_duration": 1,
                "move_stop": True,
            },
            "cotton_seed": {
                "item_converts": None,
                "heal": 0,
                "hunger": 4,
                "animal_damage": 0,
                "eating_duration": 1,
                "move_stop": True,
            },
        },
        "convert_tile": {},
        "convert_animal": {
            "earthworm": {
                "target_damage": 3, # damage to target
                "target_dead": { # when target dies
                    "heal": 0,
                    "hunger": 7,
                    "animal_damage": 0,
                    "target_drop_cancel": True, # sets if the prey doesn't drop something
                },
            }
        },
        "death_drop": [],
        "pickup_item": None # None means it can't be picked up
    }
}

def spawn_animal(animal_type, x, y):
    """Create a new animal instance."""
    props = ANIMAL_PROPS[animal_type]
    return {
        "type": animal_type,
        "x": x,
        "y": y,
        "health": props["max_health"],
        "hunger": props["max_hunger"],
        "target": None,
        "patience": DEFAULT_ANIMAL_PATIENCE,
        "frame": 0,  # for animated animals
        "frame_timer": 0,  # for animated animals
        "sine_offset": random.random() * math.tau,  # for oscillating movement
        "last_tile_convert_time": 0,  # for tile conversion tracking
        "state_timer": 0,
        "texture_angle": 0
    }

def update_animals(dt):
    """Update all animals' states using full ANIMAL_PROPS capabilities."""
    for animal in animals[:]:  # Use slice to allow removal during iteration
        props = ANIMAL_PROPS[animal["type"]]

        # --- Idle / wander behavior ---
        if animal.get("target") is None:
            if props.get("goes_idle", False):
                # stays idle for a while before picking a new target
                animal["state"] = "idle"
                animal["state_timer"] += dt
                if animal["state_timer"] >= DEFAULT_ANIMAL_IDLE_TIMER:
                    animal["state_timer"] = 0
                    # pick a new random nearby point
                    angle = random.uniform(0, 2*math.pi)
                    dist = random.uniform(20, DEFAULT_ANIMAL_WANDER_RADIUS * TILE_SIZE)
                    animal["target"] = {"type": "position", "ref": (
                        animal["x"] + math.cos(angle)*dist,
                        animal["y"] + math.sin(angle)*dist
                    )}
                    animal["state"] = "moving"
            else:
                # immediately wander again (never idles)
                angle = random.uniform(0, 2*math.pi)
                dist = random.uniform(20, DEFAULT_ANIMAL_WANDER_RADIUS * TILE_SIZE)
                animal["target"] = {"type": "position", "ref": (
                    animal["x"] + math.cos(angle)*dist,
                    animal["y"] + math.sin(angle)*dist
                )}
                animal["state"] = "moving"
        
        # --- Initialize runtime fields ---
        if "state" not in animal:
            animal["state"] = "idle"
            animal["state_timer"] = 0.0
            animal["target"] = None
            animal["patience"] = DEFAULT_ANIMAL_PATIENCE
            
        # --- Update basic stats ---
        # Hunger decay
        animal["hunger"] = max(0, animal["hunger"] - props.get("hunger_decay", 0) * dt / 30.0)
        
        # Healing when above threshold
        if animal["hunger"] >= props.get("heal_threshold", 0):
            animal["health"] = min(props["max_health"], 
                                 animal["health"] + props.get("heal_speed", 0) * dt / 10.0)
        
        # --- Death check ---
        if animal["hunger"] <= 0:
            animal["health"] -= props.get("hunger_decay", 0) * dt / 30.0

        if animal["health"] <= 0 and not animal.get("recently_damaged", False):
            # Spawn death drops
            for item_type in props.get("death_drop", []):
                items.append({
                    "type": item_type,
                    "x": animal["x"] + random.randint(-20, 20),
                    "y": animal["y"] + random.randint(-20, 20)
                })
            animals.remove(animal)
            continue

        # --- Handle idle timers to restart wandering ---
        if animal["state"] == "idle":
            animal["state_timer"] += dt
            if animal["state_timer"] >= DEFAULT_ANIMAL_IDLE_TIMER:
                animal["state_timer"] = 0
                # choose new random wander target
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(20, DEFAULT_ANIMAL_WANDER_RADIUS * TILE_SIZE)
                animal["target"] = {"type": "position", "ref": (
                    animal["x"] + math.cos(angle) * dist,
                    animal["y"] + math.sin(angle) * dist
                )}
                animal["state"] = "moving"
            
        # --- Target selection ---
        animal["patience"] -= dt
        if (animal["state"] == "idle" or 
            animal["patience"] <= 0 or 
            animal["target"] is None):
            
            # Reset state
            animal["target"] = None
            animal["patience"] = DEFAULT_ANIMAL_PATIENCE
            # Give up on old target and wander again
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(20, DEFAULT_ANIMAL_WANDER_RADIUS * TILE_SIZE)
            animal["target"] = {"type": "position", "ref": (
                animal["x"] + math.cos(angle) * dist,
                animal["y"] + math.sin(angle) * dist
            )}
            animal["state"] = "moving"
            
            # Find nearest target based on priorities
            best_target = None
            search_radius = DEFAULT_ANIMAL_WANDER_RADIUS * TILE_SIZE
            
            # 1. Check for plants to eat
            if props.get("convert_plant"):
                for plant in plants:
                    if plant["type"] in props["convert_plant"]:
                        conv = props["convert_plant"][plant["type"]]
                        if plant["growth_stage"] in conv.get("edible_stages", []):
                            dist = math.hypot(plant["x"] - animal["x"], 
                                           plant["y"] - animal["y"])
                            if dist <= search_radius:
                                if not best_target or dist < best_target[0]:
                                    best_target = (dist, "plant", plant)
            
            # 2. Check for items to consume
            if not best_target and props.get("convert_item"):
                for item in items:
                    if item["type"] in props["convert_item"]:
                        dist = math.hypot(item["x"] - animal["x"],
                                        item["y"] - animal["y"])
                        if dist <= search_radius:
                            if not best_target or dist < best_target[0]:
                                best_target = (dist, "item", item)
            
            # 3. Check for prey animals
            if not best_target and props.get("convert_animal"):
                for other in animals:
                    if other is not animal and other["type"] in props["convert_animal"]:
                        dist = math.hypot(other["x"] - animal["x"],
                                        other["y"] - animal["y"])
                        if dist <= search_radius:
                            if not best_target or dist < best_target[0]:
                                best_target = (dist, "animal", other)
            
            # Set target or wander
            if best_target:
                _, ttype, target = best_target
                animal["target"] = {"type": ttype, "ref": target}
                animal["state"] = "moving"
            else:
                # Random wandering
                angle = random.random() * math.tau
                dist = random.uniform(0, search_radius)
                animal["target"] = {
                    "type": "position",
                    "ref": (animal["x"] + math.cos(angle) * dist,
                           animal["y"] + math.sin(angle) * dist)
                }
                animal["state"] = "moving"
        
        # --- Animate frame if applicable ---
        imgdata = ANIMAL_IMAGES[animal["type"]]
        if imgdata.get("animated", False):
            spf = imgdata.get("animation_spf", 1.0)  # seconds per frame
            animal["frame_timer"] += dt
            if animal["frame_timer"] >= spf:
                animal["frame_timer"] = 0
                animal["frame"] = (animal["frame"] + 1) % len(imgdata["frames"])

        # --- Movement ---
        if animal["state"] == "moving":
            # Get target position
            tx, ty = None, None
            if animal["target"]["type"] == "position":
                tx, ty = animal["target"]["ref"]
            else:
                target = animal["target"]["ref"]
                tx, ty = target["x"], target["y"]
            
            if tx is not None and ty is not None:
                # Calculate movement
                dx = tx - animal["x"]
                dy = ty - animal["y"]
                dist = math.hypot(dx, dy)

                if dist < 5:
                    animal["state"] = "arrived"
                    continue  # Prevent jitter/spin

                if dist > 5:  # Distance threshold
                    # Base movement speed
                    speed = props.get("move_speed", 0)
                    
                    # Apply sine movement if configured
                    if "sine_movement" in props:
                        sine = props["sine_movement"]
                        base = sine.get("min_move_speed", speed)
                        amp = sine.get("sine_speed", 0)
                        speed = base + abs(math.sin(time.time() + animal["sine_offset"])) * (amp * 0.3)
                    
                    # Move
                    vx = (dx / dist) * speed * dt
                    vy = (dy / dist) * speed * dt
                    animal["x"] += vx
                    animal["y"] += vy
                    
                    if dist > 1:  # update facing only if actually moving
                        animal["texture_angle"] = math.degrees(math.atan2(dy, dx))
                else:
                    # Reached target
                    animal["state"] = "arrived"
                    
        # --- Handle arrival at target ---
        if animal["state"] == "arrived":
            if animal["target"]["type"] == "plant":
                # Start eating plant
                animal["state"] = "eating"
                conv = props["convert_plant"][animal["target"]["ref"]["type"]]
                animal["state_timer"] = conv.get("eating_duration", 1.0)
            elif animal["target"]["type"] == "item":
                # Start eating item
                animal["state"] = "eating"
                conv = props["convert_item"][animal["target"]["ref"]["type"]]
                animal["state_timer"] = conv.get("eating_duration", 1.0)
            elif animal["target"]["type"] == "animal":
                # Start attack
                animal["state"] = "attacking"
                animal["state_timer"] = 0.5  # Attack windup

        # --- Animal vs Animal interactions ---
        for other in animals:
            if other is animal:
                continue
            if other["health"] <= 0:
                continue

            # Check if this animal can attack the other
            if other["type"] in props.get("convert_animal", {}):
                interaction = props["convert_animal"][other["type"]]

                dx = other["x"] - animal["x"]
                dy = other["y"] - animal["y"]
                dist = math.hypot(dx, dy)

                # You can define a default attack range (e.g., 30 px)
                if dist <= 30:
                    # Apply damage to the target
                    dmg = interaction.get("target_damage", 0)
                    animal["attack_timer"] = animal.get("attack_timer", 0) - dt
                    if dmg > 0 and animal["attack_timer"] <= 0:
                        other["health"] -= dmg
                        other["recently_damaged"] = True

                        # Check if the target dies
                        if other["health"] <= 0:
                            td = interaction.get("target_dead", {})
                            # Heal or feed predator
                            animal["health"] = min(
                                animal["health"] + td.get("heal", 0),
                                props.get("max_health", 10),
                            )
                            animal["hunger"] = min(
                                animal["hunger"] + td.get("hunger", 0),
                                props.get("max_hunger", 10),
                            )

                            # Cancel prey's death drop if specified
                            if td.get("target_drop_cancel", False):
                                other["death_drop"] = []
                            # Remove prey from world
                            animals.remove(other)
                        animal["attack_timer"] = 1.0
                    break  # only attack one target per frame

            dx = animal["x"] - other["x"]
            dy = animal["y"] - other["y"]
            dist = math.hypot(dx, dy)

            # Define collision radius — tweak per animal type if needed
            radius = (props.get("collision_radius", 10) +
                    ANIMAL_PROPS[other["type"]].get("collision_radius", 10))

            if dist < radius and dist > 0:
                # Overlapping — compute push-out vector
                overlap = radius - dist
                nx = dx / dist
                ny = dy / dist

                # Push both animals apart slightly
                animal["x"] += nx * overlap * 0.5
                animal["y"] += ny * overlap * 0.5
                other["x"]  -= nx * overlap * 0.5
                other["y"]  -= ny * overlap * 0.5

        # --- Animal vs Plant collision ---
        for plant in plants:
            plant_type = plant["type"]
            if not PLANT_STATS.get(plant_type, {}).get("can_collide", False):
                continue

            # Assume plants have center position (plant["x"], plant["y"])
            # If they’re tile-based, you can compute from tile index instead.
            dx = animal["x"] - plant["x"]
            dy = animal["y"] - plant["y"]
            dist = math.hypot(dx, dy)

            # Define collision radii
            plant_radius = PLANT_STATS[plant_type].get("collision_radius", PLANT_SIZE / 2)
            animal_radius = props.get("collision_radius", 10)
            radius = plant_radius + animal_radius

            if dist < radius and dist > 0:
                overlap = radius - dist
                nx = dx / dist
                ny = dy / dist

                # Push animal outward only (plants are static)
                animal["x"] += nx * overlap
                animal["y"] += ny * overlap

        # --- Handle eating state ---
        if animal["state"] == "eating":
            animal["state_timer"] -= dt
            if animal["state_timer"] <= 0:
                target = animal["target"]
                if target["type"] == "plant":
                    plant = target["ref"]
                    conv = props["convert_plant"][plant["type"]]
                    # Apply damage and effects
                    plant["health"] -= conv.get("plant_damage", 0)
                    animal["health"] = min(props["max_health"], 
                                         animal["health"] + conv.get("heal", 0))
                    animal["hunger"] = min(props["max_hunger"],
                                         animal["hunger"] + conv.get("hunger", 0))
                    
                    # Convert/remove plant
                    if plant["health"] <= 0:
                        if plant in plants:
                            plants.remove(plant)
                            
                    # Spawn conversion item
                    if conv.get("item_converts"):
                        items.append({
                            "type": conv["item_converts"],
                            "x": plant["x"] + random.randint(-10, 10),
                            "y": plant["y"] + random.randint(-10, 10)
                        })
                
                elif target["type"] == "item":
                    item = target["ref"]
                    conv = props["convert_item"][item["type"]]
                    # Apply effects
                    animal["health"] = min(props["max_health"],
                                         animal["health"] + conv.get("heal", 0))
                    animal["hunger"] = min(props["max_hunger"],
                                         animal["hunger"] + conv.get("hunger", 0))
                    
                    # Convert/remove item
                    if conv.get("item_converts"):
                        item["type"] = conv["item_converts"]
                    else:
                        if item in items:
                            items.remove(item)
                
                # Reset state
                animal["state"] = "idle"
                animal["target"] = None
                
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
STRUCTURE_STATS = {
    "burning_sticks_pile": {
        "max_health": 20,
        "heal": {
            "when": [],
            "heal": 0
        }
    },
    "fire_place": {
        "max_health": 30,
        "heal": {
            "when": ["refueled"],
            "heal": 30
        }
    },
}
STRUCTURE_SPECIALS = {
    "burning_sticks_pile": {
        "mined_with": {
            "stone_hatchet": {"damage": 10, "dur_damage": 2}
        },
        "broken_drop": ["ashes", "ashes", "charcoal"],
        "light_radius": 3, # Tiles
        "light_intensity": 1, # starting intensity; max intensity = light_radius
        "light_flickering": [0.5, 1, 2], # [timer_secs, min_intensity, max_intensity]
        "timer_convertion": [90, ["ashes", "ashes", "ashes"], []] # [timer_secs, items_convert, structures_convert]
    },
    "fire_place": {
        "mined_with": {
            "stone_hatchet": {"damage": 5, "dur_damage": 2}
        },
        "broken_drop": ["ashes", "ashes", "charcoal", "ashes", "charcoal"],
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

def handle_cooking(structure, item, dt):
    """Handle cooking items in structures that support it. dt is seconds since last frame."""
    if structure["type"] in STRUCTURE_SPECIALS:
        specs = STRUCTURE_SPECIALS[structure["type"]]
        
        if "cooks" in specs and item["type"] in specs["cooks"]:
            cook_data = specs["cooks"][item["type"]]
            
            # Initialize cooking timer (in seconds)
            if "cook_timer" not in item:
                item["cook_timer"] = float(cook_data["timer"])
            
            # decrement in seconds
            item["cook_timer"] -= dt
            
            # Convert item when done cooking
            if item["cook_timer"] <= 0:
                item["type"] = cook_data["cooks_into"]
                if item["type"] in MAX_ITEM_DUR:
                    item["dur"] = MAX_ITEM_DUR[item["type"]]
                del item["cook_timer"]
                return True
    
    return False

# --- START: NEW ANIMATION / TOOL ACTION QUEUE ---
pending_animations = []  # list of dicts representing current animations

def start_tool_animation(tool_slot, action, tool_item, tile_x=None, tile_y=None, target_plant=None):
    """Queue a mining/chop animation. action = 'mine' or 'chop'.
    This version prevents starting a new animation if one is already running."""
    if not tool_item:
        return
    # If any animation is running, ignore new requests
    if pending_animations:
        return
    
    target_x = target_plant["x"] if target_plant is not None else tile_x
    target_y = target_plant["y"] if target_plant is not None else tile_y
    if target_x is not None and target_y is not None:
        dx = player_center_x - target_x
        dy = player_center_y - target_y
        dist = math.sqrt(dx**2 + dy**2)
        if dist > player_size * 1.3:
            return
    else:
        return 

    # small durations; hit_time is when the effect is applied
    duration = 0.6 if action == "mine" else 0.5
    hit_time = duration * 0.45

    # Capture current mouse angle relative to player center so swing is stable
    mx, my = pygame.mouse.get_pos()
    px, py = WIDTH // 2, HEIGHT // 2  # player is rendered at screen center
    dx = mx - px
    dy = my - py
    base_angle = math.degrees(math.atan2(dy, dx))  # degrees

    # define arc: sweep around base_angle. tweak arc_width for bigger/smaller swings
    arc_width = 90
    start_angle = base_angle - arc_width * 0.6
    end_angle = base_angle + arc_width * 0.4

    anim = {
        "tool_slot": tool_slot,
        "tool_item": tool_item,
        "action": action,
        "tile_x": tile_x,
        "tile_y": tile_y,
        "target_plant": target_plant,
        "duration": duration,
        "elapsed": 0.0,
        "hit_applied": False,
        "particles": [],
        # swing profile
        "swing": {
            "start_angle": start_angle,
            "end_angle": end_angle,
            "radius": player_size // 2 + 18  # distance from player center to tool pivot
        }
    }
    pending_animations.append(anim)

def update_animations(dt):
    """Progress animations, apply tool effects at hit frame."""
    for anim in pending_animations[:]:
        anim["elapsed"] += dt
        # Apply hit effects once at hit_time
        hit_time = anim["duration"] * 0.45
        if not anim["hit_applied"] and anim["elapsed"] >= hit_time:
            # Call your existing handler to actually produce drops / change tiles / dur
            tool_item = anim["tool_item"]
            slot = anim["tool_slot"]
            if anim["action"] == "mine":
                # ensure tile still known
                tile = get_current_tile(anim["tile_x"], anim["tile_y"])
                if tile is not None:
                    keep_target, keep_tool = handle_tool_action(tool_item, tile, None, anim["tile_x"], anim["tile_y"])
                    if not keep_tool:
                        if 0 <= slot < len(inventory) and inventory[slot] is tool_item:
                            inventory[slot] = None
            elif anim["action"] == "chop":
                plant = anim["target_plant"]
                if plant in plants:
                    keep_target, keep_tool = handle_tool_action(tool_item, None, plant, None, None)
                    if not keep_target and plant in plants:
                        try:
                            plants.remove(plant)
                        except ValueError:
                            pass
                    if not keep_tool:
                        if 0 <= slot < len(inventory) and inventory[slot] is tool_item:
                            inventory[slot] = None
            anim["hit_applied"] = True

        # remove finished animations
        if anim["elapsed"] >= anim["duration"]:
            pending_animations.remove(anim)

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

def get_current_tile(tile_x, tile_y):
    # compute chunk coords using floor division so negatives map correctly
    chunk_x = math.floor(tile_x / CHUNK_SIZE)
    chunk_y = math.floor(tile_y / CHUNK_SIZE)
    local_x = tile_x - chunk_x * CHUNK_SIZE
    local_y = tile_y - chunk_y * CHUNK_SIZE

    # If chunk isn't loaded, do NOT generate it — return None to indicate "unknown/unloaded"
    if (chunk_x, chunk_y) not in world_chunks:
        return None

    chunk = world_chunks[(chunk_x, chunk_y)]
    return chunk[local_y][local_x]

# === DRAW FUNCTIONS ===
def draw_animations(camera_x, camera_y, dt):
    """Draw simple procedural animations (flash + particles) and a tool swing in front of the player."""
    for anim in pending_animations:
        progress = anim["elapsed"] / max(0.0001, anim["duration"])
        # draw the existing particle/flash effects
        if anim["action"] == "mine":
            wx = anim["tile_x"] * TILE_SIZE + TILE_SIZE // 2
            wy = anim["tile_y"] * TILE_SIZE + TILE_SIZE // 2
            sx = int(wx - camera_x)
            sy = int(wy - camera_y)
            radius = int(18 + 24 * (1 - abs(progress*2 - 1)))
            alpha = int(200 * (1 - progress))
            surf = pygame.Surface((radius*2+4, radius*2+4), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 220, 120, alpha), (radius+2, radius+2), radius)
            WIN.blit(surf, (sx - radius - 2, sy - radius - 2))
            if not anim["particles"]:
                for i in range(10):
                    ang = random.random() * math.tau
                    speed = random.uniform(60, 160)
                    anim["particles"].append({
                        "x": sx, "y": sy,
                        "vx": math.cos(ang) * speed,
                        "vy": math.sin(ang) * speed,
                        "life": random.uniform(0.25, 0.6)
                    })
            for p in anim["particles"][:]:
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                p["life"] -= dt
                alpha = int(255 * max(0, min(1, p["life"] / 0.6)))
                pygame.draw.circle(WIN, (200,200,200,alpha), (int(p["x"]), int(p["y"])), 2)
                if p["life"] <= 0:
                    anim["particles"].remove(p)

        elif anim["action"] == "chop":
            plant = anim["target_plant"]
            if plant:
                sx = int(plant["x"] - camera_x)
                sy = int(plant["y"] - camera_y)
                radius = int(14 + 18 * (1 - abs(progress*2 - 1)))
                surf = pygame.Surface((radius*2+4, radius*2+4), pygame.SRCALPHA)
                pygame.draw.circle(surf, (180, 240, 180, int(180*(1-progress))), (radius+2, radius+2), radius)
                WIN.blit(surf, (sx - radius - 2, sy - radius - 2))
                if not anim["particles"]:
                    for i in range(8):
                        ang = random.random() * math.tau
                        speed = random.uniform(40, 120)
                        anim["particles"].append({
                            "x": sx, "y": sy,
                            "vx": math.cos(ang) * speed,
                            "vy": math.sin(ang) * speed,
                            "life": random.uniform(0.25, 0.5)
                        })
                for p in anim["particles"][:]:
                    p["x"] += p["vx"] * dt
                    p["y"] += p["vy"] * dt
                    p["life"] -= dt
                    pygame.draw.circle(WIN, (150, 100, 60), (int(p["x"]), int(p["y"])), 2)
                    if p["life"] <= 0:
                        anim["particles"].remove(p)

        # DRAW TOOL SWING in front of player (for mine/chop actions)
        if anim["action"] in ("mine", "chop") and anim.get("tool_item"):
            swing = anim.get("swing", None)
            tool = anim["tool_item"]
            tool_img = ITEM_IMAGES.get(tool["type"])
            if swing and tool_img:
                t = max(0.0, min(1.0, progress))
                # easing for a nicer arc (fast middle)
                eased = math.sin(t * math.pi)
                angle = swing["start_angle"] + (swing["end_angle"] - swing["start_angle"]) * eased

                # compute screen pivot (player drawn at center)
                player_cx = WIDTH // 2
                player_cy = HEIGHT // 2

                r = swing.get("radius", player_size // 2 + 18)
                ox = math.cos(math.radians(angle)) * r
                oy = math.sin(math.radians(angle)) * r

                # rotate tool sprite so it follows the arc
                # adjust by -90 so sprite points along sweep direction (tweak as needed)
                rotated = pygame.transform.rotate(tool_img, -angle - 90)
                rect = rotated.get_rect(center=(player_cx + ox, player_cy + oy))

                # Optional: fade tool slightly as animation finishes
                # create temp surface to set alpha without changing original
                temp = rotated.copy()
                alpha_val = int(255 * (1 - 0.2 * t))
                temp.set_alpha(alpha_val)
                WIN.blit(temp, rect.topleft)

def draw_inventory():
    slot_rects = get_inventory_slot_rects()
    for i, rect in enumerate(slot_rects):
        pygame.draw.rect(WIN, LIGHT_GRAY, rect)
        pygame.draw.rect(WIN, BLACK, rect, 2)
        text = font.render(f"{i+1}", True, WHITE)
        text_rect = text.get_rect(center=rect.center)
        WIN.blit(text, text_rect.topleft)
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
                    # Combine sine wave with random noise for natural flicker
                    base_flicker = math.sin(time.time() / timer)
                    noise = random.uniform(-0.3, 0.3)  # Add random variation
                    flicker = (base_flicker + noise) * (max_int - min_int) / 2
                    intensity = min_int + (max_int - min_int) / 2 + flicker
                    # Clamp intensity to valid range
                    intensity = max(min_int, min(max_int, intensity))
                
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
        screen_x = int(light["x"] - camera_x)
        screen_y = int(light["y"] - camera_y)
        radius = int(light["radius"])
        intensity = light["intensity"]
        
        # Draw multiple circles with decreasing alpha for smooth gradient
        steps = 10
        for i in range(steps):
            current_radius = radius * (1 - i/steps)
            alpha = int(100 * (intensity/steps) * (1 - i/steps))
            # Use inverse colors for subtractive blending
            pygame.draw.circle(LIGHT_SURFACE, (0, 5, 15, 255-alpha),
                             (screen_x + STRUCTURE_SIZE//2, screen_y + STRUCTURE_SIZE//2), 
                             int(current_radius))
    
    # Blit with subtractive blending
    WIN.blit(LIGHT_SURFACE, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

def draw_animals(camera_x, camera_y):
    """Draw all animals on screen."""
    for animal in animals:
        screen_x = animal["x"] - camera_x
        screen_y = animal["y"] - camera_y
        
        if ANIMAL_IMAGES[animal["type"]]["animated"]:
            frames = ANIMAL_IMAGES[animal["type"]]["frames"]
            img = frames[animal["frame"]]
        else:
            img = ANIMAL_IMAGES[animal["type"]]["image"]

        img = pygame.transform.rotate(img, -animal["texture_angle"]-90)
            
        img_rect = img.get_rect(center=(screen_x, screen_y))
        WIN.blit(img, img_rect.topleft)

# === MAIN LOOP ===
player_x, player_y = find_spawn_location()
paused = False
dead = False

items.append({"type": "ceramic_cup", "x": player_x, "y": player_y})
items.append({"type": "stone_hatchet", "x": player_x, "y": player_y, "dur": 50})

structures.append({"type": "fire_place", "x": player_x-500, "y": player_y-500, "timer": 500})

shown_info = None
shown_button = pygame.Rect(0,0,0,0)

hitboxes = False

running = True
while running:
    for item in items:
        item["entity"] = "item"

    for plant in plants:
        plant["entity"] = "plant"

    for structure in structures:
        structure["entity"] = "structure"

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

# event_here
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
                elif event.key == pygame.K_F3:
                    hitboxes = not hitboxes
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
                keys = pygame.key.get_pressed()
                if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] and not (crafting_structures_visible or crafting_visible):
                    if event.key == pygame.K_1 and inventory[0] is not None:
                        item = inventory[0]
                        inventory[0] = None
                        item["x"] = player_x
                        item["y"] = player_y
                        items.append(item)
                    elif event.key == pygame.K_2 and inventory[1] is not None:
                        item = inventory[1]
                        inventory[1] = None
                        item["x"] = player_x
                        item["y"] = player_y
                        items.append(item)
                elif not (crafting_structures_visible or crafting_visible):
                    if event.key == pygame.K_1 and inventory[0] is not None:
                        item = inventory[0]
                        name = item["type"]
                        if name in FOOD_STATS:
                            food = FOOD_STATS[name]
                            hunger = min(MAX_HUNGER, hunger + food["hunger"])
                            thirst = max(0, min(MAX_THIRST, thirst + food["thirst"]))
                            stamina = min(MAX_STAMINA, stamina + food["stamina"])
                            # remove eaten item
                            if inventory[0] and inventory[0]["type"] == name:
                                food_converts = FOOD_CONVERTS[inventory[0]["type"]]
                                if food_converts is not None:
                                    inventory[0]["type"] = food_converts
                                    shown_info = None
                                else:
                                    inventory[0] = None
                                break
                        elif name in STORAGE_ITEMS:
                            if storage_open is not None:
                                storage_open = None
                            else:
                                open_storage(0)
                    elif event.key == pygame.K_2 and inventory[1] is not None:
                        item = inventory[1]
                        name = item["type"]
                        if name in FOOD_STATS:
                            food = FOOD_STATS[name]
                            hunger = min(MAX_HUNGER, hunger + food["hunger"])
                            thirst = max(0, min(MAX_THIRST, thirst + food["thirst"]))
                            stamina = min(MAX_STAMINA, stamina + food["stamina"])
                            # remove eaten item
                            if inventory[1] and inventory[1]["type"] == name:
                                food_converts = FOOD_CONVERTS[inventory[1]["type"]]
                                if food_converts is not None:
                                    inventory[1]["type"] = food_converts
                                    shown_info = None
                                else:
                                    inventory[1] = None
                                break
                        elif name in STORAGE_ITEMS:
                            if storage_open is not None:
                                storage_open = None
                            else:
                                open_storage(1)

            # === Mouse down ===
            if event.type == pygame.MOUSEBUTTONDOWN:
                # If a storage window is open, handle simple transfers first
                if storage_open is not None:
                    if event.button == 1 and shown_button.collidepoint(mouse_pos):
                        storage_open = None
                        break

                    # validate storage item still present
                    if storage_open < len(inventory):
                        st_item = inventory[storage_open]
                    else:
                        st_item = None
                    if not st_item or st_item["type"] not in STORAGE_ITEMS:
                        close_storage()
                    else:
                        st_def = STORAGE_ITEMS[st_item["type"]]
                        slot_rects = get_storage_slot_rects(st_def)
                        # Click on storage slot -> try to move to first empty inventory slot
                        for si, srect in enumerate(slot_rects):
                            if srect.collidepoint(mouse_pos) and event.button == 1:
                                contents = st_item.setdefault("contents", [None]*st_def["slots"])
                                if si < len(contents) and contents[si]:
                                    for j in range(len(inventory)):
                                        if inventory[j] is None:
                                            inventory[j] = contents[si]
                                            contents[si] = None
                                            break
                                break
                        else:
                            # Click on inventory to put item into storage
                            st_def = STORAGE_ITEMS[st_item["type"]]
                            forbidden_items = st_def["not_allowed_items"]
                            for inv_i, inv_rect in enumerate(get_inventory_slot_rects()):
                                if inv_rect.collidepoint(mouse_pos) and event.button == 1:
                                    if inventory[inv_i] and inv_i != storage_open:
                                        contents = st_item.setdefault("contents", [None]*st_def["slots"])
                                        for k in range(len(contents)):
                                            if contents[k] is None and inventory[inv_i]["type"] not in forbidden_items:
                                                contents[k] = inventory[inv_i]
                                                inventory[inv_i] = None
                                                break
                                    break
                        # prevent other click handlers from running when interacting with storage
                        continue

                # GUI closed → pick/drop
                if not (crafting_visible or crafting_structures_visible):
                    if event.button == 1:
                        # Handle mining/chopping when holding appropriate tool
                        for slot in range(2):
                            if inventory[slot] and inventory[slot]["type"] in MINING_TOOLS:
                                # Try mining ores
                                tile_x = int(world_mouse_x // TILE_SIZE)
                                tile_y = int(world_mouse_y // TILE_SIZE)
                                tile = get_current_tile(tile_x, tile_y)
                                
                                if tile in ["sedimentary_iron", "laterite_soil"]:
                                    # start mining animation; effect applied at hit frame
                                    start_tool_animation(slot, "mine", inventory[slot], tile_x=tile_x, tile_y=tile_y)
                                    break
                                        
                                # Try chopping plants
                                for plant in plants[:]:
                                    plant_rect = pygame.Rect(
                                        plant["x"] - PLANT_SIZE//2,
                                        plant["y"] - PLANT_SIZE//2,
                                        PLANT_SIZE, PLANT_SIZE
                                    )
                                    if plant_rect.collidepoint(world_mouse_x, world_mouse_y):
                                        # queue a chop animation; effect will be applied at the hit moment
                                        start_tool_animation(slot, "chop", inventory[slot], target_plant=plant)
                                        break
                    if event.button == 1 and shown_info and shown_info[3].collidepoint(mouse_pos):
                        # determine which hotbar slot is hovered
                        hot_i = get_inventory_slot_rects().index(shown_info[1]) if shown_info else -1
                        name = shown_info[0]
                        # storage open (toggle now)
                        if hot_i != -1 and inventory[hot_i] and inventory[hot_i]["type"] in STORAGE_ITEMS:
                            if storage_open == hot_i:
                                close_storage()
                            else:
                                open_storage(hot_i)
                        # consumable handling (existing)
                        elif name in FOOD_STATS:
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
# event_here

    if not paused:
        past_dt = dt
        dt = min(dt, MAX_DELTA_TIME)
        # === Movement ===
        keys = pygame.key.get_pressed()
        # Apply acceleration based on input
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            player_x -= player_acceleration
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            player_x += player_acceleration
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            player_y -= player_acceleration
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_y += player_acceleration

        # Clamp velocity to prevent excessive speed
        player_vel_x = max(-MAX_VELOCITY, min(MAX_VELOCITY, player_vel_x))
        player_vel_y = max(-MAX_VELOCITY, min(MAX_VELOCITY, player_vel_y))

        # Calculate new position using clamped values
        new_x = player_x + player_vel_x * dt
        new_y = player_y + player_vel_y * dt

        player_vel_x *= player_friction
        player_vel_y *= player_friction
        
        # Check plant collisions using circles
        player_radius = player_size / 2
        plant_radius = PLANT_SIZE / 2
        collided = False

        for plant in plants:
            if PLANT_STATS[plant["type"]]["can_collide"]:
                # Get the actual radius for this plant type and growth stage
                plant_radius = PLANT_MASKS[plant["type"]][plant["growth_stage"]]
                player_radius = player_mask_radius
                
                # Calculate centers
                plant_center_x = plant["x"] + plant_radius
                plant_center_y = plant["y"] + plant_radius
                player_center_x = new_x 
                player_center_y = new_y

                # Calculate distance between centers
                dx = player_center_x - plant_center_x
                dy = player_center_y - plant_center_y
                distance = math.sqrt(dx * dx + dy * dy)

                # Check if circles overlap using actual texture-based radii
                if distance < (player_radius + plant_radius):
                    # Collision detected!
                    collided = True
                    
                    # Add collision response
                    if distance > 0:  # Avoid division by zero
                        # Calculate normalized direction vector
                        nx = dx / distance
                        ny = dy / distance
                        
                        # Calculate overlap using actual radii
                        overlap = (player_radius + plant_radius) - distance
                        
                        # Push player away from collision
                        new_x = player_center_x + nx * overlap
                        new_y = player_center_y + ny * overlap

                # Only update if no collision
                if not collided:
                    player_x = new_x
                    player_y = new_y

        # Only update position if no collision or after collision response
        player_x = new_x
        player_y = new_y

        # === UPDATE PLAYER STATS ===
        dt = past_dt
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
            if hunger > 60 and thirst > 60:
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
                    handle_cooking(structure, item, dt)

    if not paused:
        update_animals(dt)

        # === UPDATE PLANTS ===
        for plant in plants:
            tile = get_current_tile(int(plant["x"] // TILE_SIZE), int(plant["y"] // TILE_SIZE))
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
        for item in items[:]:
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
            tile_x = int(item["x"] // TILE_SIZE)
            tile_y = int(item["y"] // TILE_SIZE)
            tile = get_current_tile(tile_x, tile_y)
            if item["type"] in ITEM_TILE_INTERACTION:
                interaction = ITEM_TILE_INTERACTION[item["type"]]
                if tile in interaction:
                    tile_interaction = interaction[tile]
                    # item conversion (existing)
                    item_converts = tile_interaction.get("item_converts")
                    if item_converts is not None:
                        item["type"] = item_converts
                        if item["type"] in MAX_ITEM_DUR:
                            item["dur"] = MAX_ITEM_DUR[item["type"]]

                    # tile conversion (new)
                    tile_converts = tile_interaction.get("tile_converts")
                    if tile_converts is not None:
                        # compute chunk + local indices (handle negatives)
                        chunk_x = tile_x // CHUNK_SIZE
                        chunk_y = tile_y // CHUNK_SIZE
                        local_x = tile_x % CHUNK_SIZE
                        local_y = tile_y % CHUNK_SIZE
                        if local_x < 0:
                            local_x += CHUNK_SIZE
                            chunk_x -= 1
                        if local_y < 0:
                            local_y += CHUNK_SIZE
                            chunk_y -= 1

                        # ensure chunk is loaded, then set tile
                        chunk = get_chunk(chunk_x, chunk_y)
                        chunk[local_y][local_x] = tile_converts
            
            if "dur" in item and item["dur"] <= 0:
                items.remove(item)

    # === HOTBAR ITEMS INFO ===
    slot_rects = get_inventory_slot_rects()
    new_info = None
    for i in range(2):
        if slot_rects[i].collidepoint(mouse_pos) and inventory[i] is not None:
            # store extra flag for storage items
            is_food = (inventory[i]["type"] in FOOD_STATS)
            is_storage_item = (inventory[i]["type"] in STORAGE_ITEMS)
            new_info = [inventory[i]["type"], slot_rects[i], is_food, pygame.Rect(0,0,0,0), is_storage_item]
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

    update_animations(dt)

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
        img_rect = img.get_rect(center=(screen_x, screen_y))
        plant_radius = PLANT_MASKS[plant["type"]][plant["growth_stage"]]
        pygame.draw.circle(WIN, (0, 0, 255), (screen_x, screen_y), 10)
        WIN.blit(img, img_rect.topleft)

    # === STRUCTURES ===
    for structure in structures:
        screen_x = structure["x"] - camera_x
        screen_y = structure["y"] - camera_y
        img = STRUCTURE_IMAGES[structure["type"]]
        WIN.blit(img, (screen_x, screen_y))

    # === ANIMALS ===
    draw_animals(camera_x, camera_y)

    # === PLAYER ===
    player_screen_x = WIDTH // 2 - player_size // 2
    player_screen_y = HEIGHT // 2 - player_size // 2
    mouse_player_atan2 = math.atan2((mouse_pos[1] - player_screen_y) - player_size//2, (mouse_pos[0] - player_screen_x) - player_size//2)
    player_texture_rotated = pygame.transform.rotate(player_texture, -math.degrees(mouse_player_atan2) - 90)
    player_rect = player_texture_rotated.get_rect(center=(WIDTH//2, HEIGHT//2))
    WIN.blit(player_texture_rotated, player_rect.topleft)

    draw_animations(camera_x, camera_y, dt)

    # === LIGHTING === (add this)
    draw_lighting(camera_x, camera_y)

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
            timer_pos = [mouse_pos[0] + 15, mouse_pos[1] + 35]
            cook_pos = [mouse_pos[0] + 15, mouse_pos[1] + 35]
            if "dur" in item:
                dur_text = font.render(f"Durability: {(item['dur'] / MAX_ITEM_DUR[item['type']])*100:.2f}%", True, BLACK)
                timer_pos[1] = WIN.blit(dur_text, (mouse_pos[0] + 15, mouse_pos[1] + 35)).bottom
                cook_pos[1] = timer_pos[1]
            if "timer" in item:
                timer_text = font.render(f"{ITEM_CONVERT_LABELS[item['type']]}{item['timer']:.1f}s", True, BLACK)
                cook_pos[1] = WIN.blit(timer_text, timer_pos).bottom
            if "cook_timer" in item:
                timer_text = font.render(f"Cooks in: {item['cook_timer']:.1f}s", True, BLACK)
                WIN.blit(timer_text, cook_pos)
            break

    struct = False
    for structure in structures:
        screen_x = structure["x"] - camera_x
        screen_y = structure["y"] - camera_y
        screen_rect = pygame.Rect(screen_x, screen_y, STRUCTURE_SIZE, STRUCTURE_SIZE)
        if screen_rect.collidepoint(mouse_pos):
            info_text = font.render(structure["type"], True, BLACK)
            WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 15))
            if "timer" in structure:
                info_text = font.render(f"Burns in: {structure['timer']:.1f}", True, BLACK)
                WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 35))
            struct = True
            break

    if not struct:
        for plant in plants:
            screen_x = plant["x"] - camera_x
            screen_y = plant["y"] - camera_y
            screen_rect = pygame.Rect(screen_x-PLANT_SIZE//2, screen_y-PLANT_SIZE//2, PLANT_SIZE, PLANT_SIZE)
            if screen_rect.collidepoint(mouse_pos):
                info_text = font.render(plant["type"], True, BLACK)
                WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 15))
                info_text = font.render(plant["growth_stage"], True, BLACK)
                WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 35))
                info_text = font.render(f"Health: {plant['health']}", True, BLACK)
                WIN.blit(info_text, (mouse_pos[0] + 15, mouse_pos[1] - 55))
                break

    if crafting_structures_visible:
        draw_structure_crafting_gui()
    elif crafting_visible:
        draw_crafting_gui()
    elif shown_info is not None:
        # unpack extended shown_info: name, rect, is_edible, button_rect, is_storage
        name, rect, is_edible, name_rect, is_storage = shown_info
        if not is_edible and not is_storage:
            name_text = font.render(name, True, (0, 0, 0))
            text_rect = name_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-12
            shown_info[3] = WIN.blit(name_text, text_rect.topleft)
        elif is_storage:
            # determine which hotbar slot this info belongs to
            try:
                hot_i = get_inventory_slot_rects().index(rect)
            except ValueError:
                hot_i = -1
            is_open = (storage_open == hot_i)
            label = "> Close" if is_open else "> Open"
            open_text = font.render(label, True, (100, 230, 100) if shown_button.collidepoint(mouse_pos) else (0,0,0))
            text_rect = open_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-12
            shown_button = WIN.blit(open_text, text_rect.topleft)
            shown_info[3] = shown_button
            name_text = font.render(name, True, (0,0,0))
            text_rect = name_text.get_rect(center=rect.center)
            text_rect.centery = rect.top-32
            WIN.blit(name_text, text_rect.topleft)
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
    
    # draw storage gui on top of other GUI elements
    draw_storage_gui()
        
    pygame.display.update()

pygame.quit()
sys.exit()
