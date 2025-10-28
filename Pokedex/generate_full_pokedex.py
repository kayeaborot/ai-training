import requests, json, time, os
from io import BytesIO
from PIL import Image, ImageOps

OUTPUT_FILE = "pokedex_metadata_ready.json"
CHECKPOINT_FILE = "pokedex_checkpoint.json"
SILHOUETTE_DIR = "silhouettes"

os.makedirs(SILHOUETTE_DIR, exist_ok=True)

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
            else:
                print(f"⚠️ HTTP {r.status_code} on {url}, retrying...")
        except Exception as e:
            print(f"⚠️ Error fetching {url}: {e}")
        time.sleep(delay)
    print(f"❌ Failed after {retries} attempts: {url}")
    return None

# === CREATE SILHOUETTE ===
def create_silhouette(image_url, name):
    try:
        response = requests.get(image_url, timeout=15)
        img = Image.open(BytesIO(response.content)).convert("RGBA")
        # Convert all non-transparent pixels to black
        data = img.getdata()
        new_data = []
        for item in data:
            if item[3] > 0:  # if pixel not transparent
                new_data.append((0, 0, 0, 255))
            else:
                new_data.append((0, 0, 0, 0))
        img.putdata(new_data)

        silhouette_path = os.path.join(SILHOUETTE_DIR, f"{name.lower().replace(' ', '_')}_silhouette.png")
        img.save(silhouette_path)
        return silhouette_path
    except Exception as e:
        print(f"⚠️ Failed to create silhouette for {name}: {e}")
        return None

# === GET POKÉMON DATA ===
def get_pokemon_data(name_or_id):
    poke_data = safe_request(f"https://pokeapi.co/api/v2/pokemon/{name_or_id}")
    species_data = safe_request(f"https://pokeapi.co/api/v2/pokemon-species/{name_or_id}")
    if not poke_data or not species_data:
        return None

    poke_id = poke_data["id"]
    name = poke_data["name"].replace("-", " ").title()
    types = [t["type"]["name"].capitalize() for t in poke_data["types"]]
    sprite = poke_data["sprites"]["front_default"]
    artwork = poke_data["sprites"]["other"]["official-artwork"]["front_default"]
    generation = get_generation(poke_id)

    # Description (English only)
    flavor_entries = species_data.get("flavor_text_entries", [])
    description = next(
        (entry["flavor_text"].replace("\n", " ").replace("\x0c", " ")
         for entry in flavor_entries if entry["language"]["name"] == "en"),
        "No description available."
    )

    # Evolution chain
    evo_chain_url = species_data.get("evolution_chain", {}).get("url")
    evo_list = []
    if evo_chain_url:
        evo_data = safe_request(evo_chain_url)
        if evo_data:
            evo = evo_data["chain"]
            while evo:
                evo_list.append(evo["species"]["name"].capitalize())
                evo = evo["evolves_to"][0] if evo["evolves_to"] else None

    # Strengths & Weaknesses
    strong, weak = set(), set()
    for t in types:
        if t in TYPE_CHART:
            strong.update(TYPE_CHART[t]["strong"])
            weak.update(TYPE_CHART[t]["weak"])

    # Create silhouette
    silhouette_path = create_silhouette(artwork, name) if artwork else None

    # Build JSON entry
    pokemon_entry = {
        "id": poke_id,
        "name": name,
        "generation": generation,
        "types": types,
        "description": description,
        "evolutions": evo_list if evo_list else [],
        "strengths": sorted(list(strong)) if strong else [],
        "weaknesses": sorted(list(weak)) if weak else [],
        "sprite": sprite,
        "artwork": artwork,
        "silhouette": silhouette_path
    }

    return pokemon_entry

# === MAIN ===
def main():
    pokedex = []
    start_id = 1

    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            checkpoint = json.load(f)
        pokedex = checkpoint.get("pokedex", [])
        start_id = checkpoint.get("last_id", 1) + 1
        print(f"🔁 Resuming from ID #{start_id} ({len(pokedex)} entries already saved)")
    else:
        print("🚀 Starting new Pokédex build...")

    for i in range(start_id, 1026):
        data = get_pokemon_data(i)
        if data:
            pokedex.append(data)
            print(f"✅ Added #{i}: {data['name']}")
        else:
            print(f"❌ Skipped #{i} (failed to fetch)")
        time.sleep(0.25)

        if i % 25 == 0:
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_id": i, "pokedex": pokedex}, f, indent=2, ensure_ascii=False)
            print(f"💾 Checkpoint saved at #{i}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(pokedex, f, indent=2, ensure_ascii=False)

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    print(f"\n🎉 Done! Saved {len(pokedex)} Pokémon entries to {OUTPUT_FILE}")
    print(f"🖤 Silhouettes stored in: {SILHOUETTE_DIR}/")

if __name__ == "__main__":
    main()
