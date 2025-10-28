import requests, json, time, os, concurrent.futures
from PIL import Image, ImageOps
from io import BytesIO

OUTPUT_FILE = "pokedex_flowise_ready.json"
CHECKPOINT_FILE = "pokedex_checkpoint.json"
SILHOUETTE_DIR = "silhouettes"
os.makedirs(SILHOUETTE_DIR, exist_ok=True)

# === CONFIG ===
SILHOUETTE_BASE_URL = "/silhouettes/"  # 👈 change this to your hosting URL

# === GENERATION MAPPING ===
def get_generation(pokedex_id):
    if pokedex_id <= 151: return "Gen 1 (Kanto)"
    elif pokedex_id <= 251: return "Gen 2 (Johto)"
    elif pokedex_id <= 386: return "Gen 3 (Hoenn)"
    elif pokedex_id <= 493: return "Gen 4 (Sinnoh)"
    elif pokedex_id <= 649: return "Gen 5 (Unova)"
    elif pokedex_id <= 721: return "Gen 6 (Kalos)"
    elif pokedex_id <= 809: return "Gen 7 (Alola)"
    elif pokedex_id <= 905: return "Gen 8 (Galar)"
    else: return "Gen 9 (Paldea)"

# === TYPE CHART ===
TYPE_CHART = {
    "Fire": {"strong": ["Grass", "Bug", "Ice", "Steel"], "weak": ["Water", "Rock", "Ground"]},
    "Water": {"strong": ["Fire", "Ground", "Rock"], "weak": ["Electric", "Grass"]},
    "Grass": {"strong": ["Water", "Ground", "Rock"], "weak": ["Fire", "Bug", "Ice", "Flying"]},
    "Electric": {"strong": ["Water", "Flying"], "weak": ["Ground"]},
    "Ice": {"strong": ["Dragon", "Grass", "Ground", "Flying"], "weak": ["Fire", "Rock", "Steel"]},
    "Rock": {"strong": ["Fire", "Flying", "Bug", "Ice"], "weak": ["Water", "Grass", "Ground"]},
    "Psychic": {"strong": ["Fighting", "Poison"], "weak": ["Dark", "Bug", "Ghost"]},
    "Dark": {"strong": ["Psychic", "Ghost"], "weak": ["Fighting", "Fairy", "Bug"]},
    "Fairy": {"strong": ["Dark", "Dragon", "Fighting"], "weak": ["Steel", "Poison"]},
    "Dragon": {"strong": ["Dragon"], "weak": ["Ice", "Fairy", "Dragon"]},
    "Steel": {"strong": ["Rock", "Ice", "Fairy"], "weak": ["Fire", "Ground", "Fighting"]},
    "Ground": {"strong": ["Fire", "Rock", "Electric", "Steel"], "weak": ["Water", "Grass", "Ice"]},
    "Poison": {"strong": ["Fairy", "Grass"], "weak": ["Ground", "Psychic"]},
    "Bug": {"strong": ["Dark", "Psychic", "Grass"], "weak": ["Rock", "Flying", "Fire"]},
    "Flying": {"strong": ["Bug", "Grass", "Fighting"], "weak": ["Rock", "Ice", "Electric"]},
    "Fighting": {"strong": ["Dark", "Ice", "Rock"], "weak": ["Psychic", "Flying", "Fairy"]},
    "Ghost": {"strong": ["Psychic", "Ghost"], "weak": ["Dark", "Ghost"]},
    "Normal": {"strong": [], "weak": ["Fighting", "Ghost"]}
}

# === SAFE REQUEST ===
def safe_request(url, retries=3, delay=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"⚠️ Error fetching {url}: {e}")
        time.sleep(delay)
    return None

# === SILHOUETTE CREATOR ===
def create_silhouette(url, poke_name):
    if not url:
        return None
    filename = f"{SILHOUETTE_DIR}/{poke_name.lower().replace(' ', '_')}.png"
    if os.path.exists(filename):
        return f"{SILHOUETTE_BASE_URL}{os.path.basename(filename)}"
    try:
        img_data = requests.get(url, timeout=15).content
        img = Image.open(BytesIO(img_data)).convert("RGBA")
        gray = ImageOps.grayscale(img)
        black = ImageOps.colorize(gray, black="black", white="black")
        black.putalpha(img.getchannel("A"))
        black.save(filename)
        return f"{SILHOUETTE_BASE_URL}{os.path.basename(filename)}"
    except Exception as e:
        print(f"⚠️ Silhouette error for {poke_name}: {e}")
        return None

# === EVOLUTION PARSER (simplified) ===
def parse_evolution_chain(evo_json, target_name):
    evolves_from, evolves_to = None, []
    try:
        def traverse(node, prev=None):
            nonlocal evolves_from, evolves_to
            if not node or not node.get("species"):
                return
            current_name = node["species"]["name"].capitalize()
            if current_name == target_name:
                if prev:
                    evolves_from = prev
                evolves_to = [evo["species"]["name"].capitalize() for evo in node.get("evolves_to", [])]
            for evo in node.get("evolves_to", []):
                traverse(evo, current_name)
        traverse(evo_json.get("chain", {}))
    except Exception as e:
        print(f"⚠️ Evolution parse error for {target_name}: {e}")
    return evolves_from, evolves_to

# === POKÉMON DATA ===
def get_pokemon_data(poke_id):
    poke_data = safe_request(f"https://pokeapi.co/api/v2/pokemon/{poke_id}")
    species_data = safe_request(f"https://pokeapi.co/api/v2/pokemon-species/{poke_id}")
    if not poke_data or not species_data:
        return None

    name = poke_data["name"].replace("-", " ").title()
    types = [t["type"]["name"].capitalize() for t in poke_data["types"]]
    sprite = poke_data["sprites"]["front_default"]
    artwork = poke_data["sprites"]["other"]["official-artwork"]["front_default"]
    generation = get_generation(poke_id)

    region_name = next((g["genus"] for g in species_data.get("genera", [])
                        if g["language"]["name"] == "en"), None)

    desc = next((entry["flavor_text"].replace("\n", " ").replace("\x0c", " ")
                 for entry in species_data["flavor_text_entries"]
                 if entry["language"]["name"] == "en"), "No description available.")

    evo_url = species_data.get("evolution_chain", {}).get("url")
    evolves_from, evolves_to = None, []
    if evo_url:
        evo_data = safe_request(evo_url)
        if evo_data:
            evolves_from, evolves_to = parse_evolution_chain(evo_data, name)

    strong, weak = set(), set()
    for t in types:
        if t in TYPE_CHART:
            strong.update(TYPE_CHART[t]["strong"])
            weak.update(TYPE_CHART[t]["weak"])

    silhouette_url = create_silhouette(artwork, name)

    return {
        "id": poke_id,
        "name": name,
        "generation": generation,
        "region_name": region_name,
        "types": types,
        "description": desc,
        "strengths": sorted(strong),
        "weaknesses": sorted(weak),
        "evolves_from": evolves_from,
        "evolves_to": evolves_to,
        "sprite_url": sprite,
        "artwork_url": artwork,
        "silhouette_url": silhouette_url,
    }

# === MAIN ===
def main():
    pokedex = []
    start_id = 1

    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            checkpoint = json.load(f)
        pokedex = checkpoint.get("pokedex", [])
        start_id = checkpoint.get("last_id", 1) + 1
        print(f"🔁 Resuming from ID #{start_id} ({len(pokedex)} entries saved)")
    else:
        print("🚀 Starting new Pokédex build...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_pokemon_data, i): i for i in range(start_id, 1026)}
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            try:
                data = future.result()
                if data:
                    pokedex.append(data)
                    print(f"✅ Added #{i}: {data['name']}")
                else:
                    print(f"❌ Skipped #{i}")
            except Exception as e:
                print(f"⚠️ Error on #{i}: {e}")
            if i % 25 == 0:
                with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                    json.dump({"last_id": i, "pokedex": pokedex}, f, indent=2, ensure_ascii=False)
                print(f"💾 Checkpoint saved at #{i}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(pokedex, f, indent=2, ensure_ascii=False)
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
    print(f"\n🎉 Done! Saved {len(pokedex)} Pokémon entries to {OUTPUT_FILE}")
    print(f"🖤 Silhouette URLs prefixed with: {SILHOUETTE_BASE_URL}")

if __name__ == "__main__":
    main()
