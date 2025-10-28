import pygame
import math
import random
import noise
import hashlib
import sys
import os

pygame.init()

# === SCREEN SETUP ===
WIDTH, HEIGHT = 800, 600
WIN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Sciencervival")

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

# === PLAYER ===
player_size = 80
player_x = WIDTH // 2
player_y = HEIGHT // 2
player_speed = 5
player_texture = pygame.transform.scale(pygame.image.load(os.path.join("other", "character.png")), (player_size, player_size))

# === TILE SETTINGS ===
TILE_SIZE = 100

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

# Scale tiles to match TILE_SIZE
for key in TILE_IMAGES:
    TILE_IMAGES[key] = pygame.transform.scale(TILE_IMAGES[key], (TILE_SIZE, TILE_SIZE))

CHUNK_SIZE = 16
WORLD_SEED = 9
NOISE = noise.combine_noise_smooth(noise.make_fractal_mask(WORLD_SEED, ),noise.make_perlin(WORLD_SEED))
ORE_NOISE = noise.make_ore_patches(WORLD_SEED+1, [0.05, 0.1], [0.4, 0.5])
world_chunks = {}
items = []

def generate_item(tile_type, x, y):
    """Generate a deterministic item for a given tile (x,y) and tile type."""
    h = float(int(hashlib.md5(f"{x},{y},{WORLD_SEED}".encode()).hexdigest(), 16) % 100) / 100.0
    
    if tile_type == "grass":
        if h < 0.04:
            return {"type": "rattan", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "cotton_plant", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.1:
            return {"type": "stick", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    elif tile_type == "dirt":
        if h < 0.02:
            return {"type": "limestone", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "magnesite", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    elif tile_type == "sand":
        if h < 0.04:
            return {"type": "rock", "x": x * TILE_SIZE, "y": y * TILE_SIZE}
        elif h < 0.06:
            return {"type": "clam", "x": x * TILE_SIZE, "y": y * TILE_SIZE}

    return None

def generate_chunk(cx, cy):
    """Generate a single chunk of terrain and spawn items into global items list."""
    chunk_tiles = []

    for ty in range(CHUNK_SIZE):
        row = []
        for tx in range(CHUNK_SIZE):
            world_x = cx * CHUNK_SIZE + tx
            world_y = cy * CHUNK_SIZE + ty
            r = NOISE(world_x / 100, world_y / 100)

            print(f"Chunk ({cx},{cy}) Tile ({tx},{ty}) World ({world_x},{world_y}) Noise: {r}")

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
            if item:
                items.append(item)

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
    for (cx, cy) in list(world_chunks.keys()):
        if abs(cx - player_chunk_x) > max_distance or abs(cy - player_chunk_y) > max_distance:
            del world_chunks[(cx, cy)]

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
    "cocoa_beans_bamboo_bottle": [300, "fermented_cocoa_beans_bamboo_bottle"],
}

ITEM_CONVERT_LABELS = {
    "burning_cotton_boll": "Burns in: ",
    "burning_wood_dust": "Burns in: ",
    "cocoa_beans_bamboo_bottle": "Ferments in: ",
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
CRAFT_SLOT_SIZE = 60
craft_output_slots = []

# Base crafting frame
craft_gui_rect = pygame.Rect(WIDTH//2 - 150, HEIGHT//2 - 80, 300, 160)
craft_slot_rects = [
    pygame.Rect(craft_gui_rect.x + 20, craft_gui_rect.y + 50, CRAFT_SLOT_SIZE, CRAFT_SLOT_SIZE),
    pygame.Rect(craft_gui_rect.x + 100, craft_gui_rect.y + 50, CRAFT_SLOT_SIZE, CRAFT_SLOT_SIZE),
]
arrow_rect = pygame.Rect(craft_gui_rect.x + 180, craft_gui_rect.y + 65, 30, 30)

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
    elif sorted(input_types) == sorted(["wood_dust", "burning_cotton"]):
        return ["burning_wood_dust"]
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
    global craft_output_slots, craft_gui_rect, arrow_rect
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
    arrow_rect.x = craft_gui_rect.x + 180

    # Create output slot rects
    craft_output_slots = []
    x_start = arrow_rect.right + 20
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

def draw_arrow():
    pygame.draw.polygon(WIN, BLACK, [
        (arrow_rect.x, arrow_rect.y),
        (arrow_rect.x, arrow_rect.y + arrow_rect.height),
        (arrow_rect.x + arrow_rect.width, arrow_rect.y + arrow_rect.height // 2)
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
    draw_arrow()

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

# === MAIN LOOP ===
player_x, player_y = find_spawn_location()

running = True
while running:
    dt = clock.tick(60) / 1000
    mouse_pos = pygame.mouse.get_pos()
    world_mouse_x = mouse_pos[0] + (player_x - WIDTH // 2)
    world_mouse_y = mouse_pos[1] + (player_y - HEIGHT // 2)
    world_mouse = (world_mouse_x, world_mouse_y)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # === Toggle Crafting GUI ===
        if event.type == pygame.KEYDOWN and event.key == pygame.K_e:
            crafting_visible = not crafting_visible
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

        # === Mouse down ===
        if event.type == pygame.MOUSEBUTTONDOWN:
            # GUI closed → pick/drop
            if event.button == 1 and not crafting_visible:
                player_rect = pygame.Rect(player_x, player_y, player_size, player_size)
                # Drop item
                for i, rect in enumerate(get_inventory_slot_rects()):
                    if rect.collidepoint(mouse_pos) and inventory[i] is not None:
                        dropped = inventory[i]
                        drop_x = player_x + random.randint(-40, 40)
                        drop_y = player_y + random.randint(-40, 40)
                        dropped["x"] = drop_x
                        dropped["y"] = drop_y
                        items.append(dropped)
                        inventory[i] = None
                else:
                    # Pick up nearby item
                    for item in items[:]:
                        item_rect = pygame.Rect(item["x"], item["y"], ITEM_SIZE, ITEM_SIZE)
                        distance = ((player_rect.centerx - item_rect.centerx) ** 2 +
                                    (player_rect.centery - item_rect.centery) ** 2) ** 0.5
                        if item_rect.collidepoint(world_mouse) and distance < 80:
                            for i in range(2):
                                if inventory[i] is None:
                                    inventory[i] = item  # directly store the whole item dict
                                    items.remove(item)
                                    break
                            break

            # GUI open → drag or craft
            else:
                if event.button == 1:
                    # Click arrow to craft
                    if arrow_rect.collidepoint(mouse_pos):
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

            if not placed and drag_origin:
                origin_type, idx = drag_origin
                if origin_type == "inventory":
                    inventory[idx] = drag_item
                elif origin_type == "craft":
                    craft_slots[idx] = drag_item

            drag_item = None
            drag_origin = None

    # === Movement ===
    keys = pygame.key.get_pressed()
    if not crafting_visible:
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            player_x -= player_speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            player_x += player_speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            player_y -= player_speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_y += player_speed

    """player_x = max(0, min(WIDTH - player_size, player_x))
    player_y = max(0, min(HEIGHT - player_size, player_y))"""

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

    # === DRAW EVERYTHING ===
    WIN.fill(WHITE)
    # === CAMERA ===
    camera_x = player_x - WIDTH // 2
    camera_y = player_y - HEIGHT // 2

    # === WORLD DRAW ===
    player_chunk_x = (player_x // TILE_SIZE) // CHUNK_SIZE
    player_chunk_y = (player_y // TILE_SIZE) // CHUNK_SIZE
    unload_far_chunks(player_chunk_x, player_chunk_y)
    draw_world(camera_x, camera_y)

    # === ITEMS ===
    chunk_range = 3 * CHUNK_SIZE * TILE_SIZE
    for item in items:
        if abs(item["x"] - player_x) <= chunk_range and abs(item["y"] - player_y) <= chunk_range:
            screen_x = item["x"] - camera_x
            screen_y = item["y"] - camera_y
            WIN.blit(ITEM_IMAGES[item["type"]], (screen_x, screen_y))

    # === PLAYER ===
    player_screen_x = WIDTH // 2 - player_size // 2
    player_screen_y = HEIGHT // 2 - player_size // 2
    mouse_player_atan2 = math.atan2((mouse_pos[1] - player_screen_y) - player_size//2, (mouse_pos[0] - player_screen_x) - player_size//2)
    player_texture_rotated = pygame.transform.rotate(player_texture, -math.degrees(mouse_player_atan2) - 90)
    player_rect = player_texture_rotated.get_rect(center=(WIDTH//2, HEIGHT//2))
    WIN.blit(player_texture_rotated, player_rect.topleft)
    pygame.draw.circle(WIN, (100, 100, 255), (WIDTH//2,HEIGHT//2), 10)

    # === GUI (no camera offset) ===
    draw_inventory()

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

    if crafting_visible:
        draw_crafting_gui()

    # === DRAGGED ITEM (GUI layer) ===
    if drag_item:
        WIN.blit(ITEM_IMAGES[drag_item["type"]],
                (mouse_pos[0] - drag_offset[0] + 10, mouse_pos[1] - drag_offset[1] + 10))
        
    pygame.display.update()

pygame.quit()
sys.exit()
