import math
import opensimplex
import random as rn
import hashlib

def make_perlin(seed=None):
    random = rn.Random()
    random.seed(seed)
    p = list(range(256))
    random.shuffle(p)
    p += p

    def fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def lerp(a, b, t):
        return a + t * (b - a)

    def grad(hash, x, y):
        h = hash & 3
        if h == 0:
            return x + y
        elif h == 1:
            return -x + y
        elif h == 2:
            return x - y
        else:
            return -x - y

    def perlin(x, y):
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255
        xf = x - math.floor(x)
        yf = y - math.floor(y)
        u = fade(xf)
        v = fade(yf)

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]

        x1 = lerp(grad(aa, xf, yf), grad(ba, xf - 1, yf), u)
        x2 = lerp(grad(ab, xf, yf - 1), grad(bb, xf - 1, yf - 1), u)
        return (lerp(x1, x2, v) + 1) / 2

    return perlin

def make_simplex(seed=None):
    opns = opensimplex.OpenSimplex(seed if seed is not None else rn.randint(0, 1000000))
    def simplex_noise(x, y):
        return (opns.noise2(x, y) + 1) / 2  # normalize to 0–1
    return simplex_noise

def make_fractal(seed=None, octaves=4, persistence=0.5, lacunarity=2.0):
    perlin = make_perlin(seed)
    def fractal_noise(x, y):
        total = 0
        amplitude = 1
        frequency = 1
        max_value = 0
        for _ in range(octaves):
            total += perlin(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= lacunarity
        return total / max_value  # normalize to 0–1
    return fractal_noise

def make_fractal_binary(seed=None, octaves=4, persistence=0.5, lacunarity=2.0, threshold=0.5):
    fractal = make_fractal(seed, octaves, persistence, lacunarity)
    def fractal_binary_noise(x, y):
        value = fractal(x, y)
        return 1.0 if value >= threshold else 0.0
    return fractal_binary_noise

def make_perlin_binary(seed=None, threshold=0.5):
    perlin = make_perlin(seed)
    def perlin_binary_noise(x, y):
        value = perlin(x, y)
        return 1.0 if value >= threshold else 0.0
    return perlin_binary_noise

def combine_noise_binary(binary_noise, continuous_noise):
    def combined_noise(x, y):
        if binary_noise(x, y) >= 1.0:
            return continuous_noise(x, y)
        else:
            return 0.0
    return combined_noise

def combine_noise_smooth(mask_noise, detail_noise, binary_scale=1.0, continuous_scale=1.0):
    def combined(x, y):
        mask_val = mask_noise(x * binary_scale, y * binary_scale)
        detail_val = detail_noise(x * continuous_scale, y * continuous_scale)
        # Blend smoothly — mask acts as a multiplier for "how much land"
        return mask_val * detail_val
    return combined

def make_fractal_mask(seed=None, octaves=4, persistence=0.5, lacunarity=2.0, threshold=0.5, blend=0.1):
    fractal = make_fractal(seed, octaves, persistence, lacunarity)
    def mask(x, y):
        value = fractal(x, y)
        # Smooth transition around threshold ± blend
        low = threshold - blend
        high = threshold + blend
        if value <= low:
            return 0.0
        elif value >= high:
            return 1.0
        else:
            # linear interpolation between 0 and 1 in the blend zone
            return (value - low) / (high - low)
    return mask

def make_perlin_mask(seed=None, threshold=0.5, blend=0.1):
    perlin = make_perlin(seed)
    def mask(x, y):
        value = perlin(x, y)
        low = threshold - blend
        high = threshold + blend
        if value <= low:
            return 0.0
        elif value >= high:
            return 1.0
        else:
            return (value - low) / (high - low)
    return mask

def make_random_ores(seed=None, rarities=[0.1]):
    simplex = make_simplex(seed)
    def random_ores(x, y):
        h = hashlib.sha256(f"{seed}_{x}_{y}".encode()).hexdigest()
        v = simplex(x, y)
        value = (((int(h, 16) % 10000) / 10000.0) + v) / 2
        for i, rarity in enumerate(rarities):
            if value < rarity:
                return i + 1
        return 0
    return random_ores

def make_ore_patches(seed=None, frequencies=[], rarities=[], max_depth=3, min_depth=1):
    perlin = make_perlin(seed)
    arranged_rarities = sorted(rarities)
    arranged_frequencies = []
    for r in arranged_rarities:
        idx = rarities.index(r)
        arranged_frequencies.append(frequencies[idx])

    def ore_patches(x, y, depth=1):
        dv = (max_depth - depth) / min_depth
        for i, (freq, rarity) in enumerate(zip(arranged_frequencies, arranged_rarities)):
            v = perlin(x * freq, y * freq) * dv
            if v < rarity:
                return i + 1
        return 0
    return ore_patches

def make_ore_veins(seed=None, chunk_size=32, vein_length=20, vein_radius=3, ore_types=None):
    """
    Deterministic hash + pattern ore vein generator.
    
    Args:
        seed (int): World seed for deterministic behavior.
        chunk_size (int): Region size used for hashing vein seeds.
        vein_length (int): Approx. length of each vein (in tiles).
        vein_radius (int): Radius of vein influence (thickness).
        ore_types (list): List of ore definitions, e.g.
                          [{'name': 'iron', 'rarity': 0.02},
                           {'name': 'gold', 'rarity': 0.01}]
    Returns:
        func(x, y) -> ore_id or 0
    """
    simplex = make_simplex(seed)
    if ore_types is None:
        ore_types = [{'name': 'iron', 'rarity': 0.02}]

    def hash2d(ix, iy):
        data = f"{seed}_{ix}_{iy}".encode()
        return int(hashlib.sha256(data).hexdigest(), 16) & 0xFFFFFFFF

    def vein_noise(x, y):
        # Use smooth noise for natural distortion
        return simplex(x * 0.1, y * 0.1)

    def ore_vein(x, y):
        # Identify which chunk this coordinate belongs to
        chunk_x = x // chunk_size
        chunk_y = y // chunk_size

        # Deterministic pseudo-random value for this chunk
        h = hash2d(chunk_x, chunk_y)
        rn = (h % 100000) / 100000.0

        # Select ore type based on rarity thresholds
        ore_id = 0
        acc = 0.0
        for i, ore in enumerate(ore_types):
            acc += ore['rarity']
            if rn < acc:
                ore_id = i + 1
                break

        if ore_id == 0:
            return 0  # no vein in this region

        # Compute a deterministic “center line” for the vein
        local_seed = hash2d(chunk_x + ore_id, chunk_y - ore_id)
        angle = (local_seed % 360) * math.pi / 180.0
        cx = (chunk_x + 0.5) * chunk_size
        cy = (chunk_y + 0.5) * chunk_size

        # Project point onto the vein’s axis
        dx = x - cx
        dy = y - cy
        along = dx * math.cos(angle) + dy * math.sin(angle)
        dist = abs(-dx * math.sin(angle) + dy * math.cos(angle))

        # Add noise-based distortion to width and placement
        n = vein_noise(x, y)
        dist -= (n - 0.5) * vein_radius

        # Determine whether the point lies inside the vein
        if 0 <= along <= vein_length and dist < vein_radius:
            return ore_id
        return 0

    return ore_vein
