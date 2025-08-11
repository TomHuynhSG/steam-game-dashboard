import os
import json
import re
import requests
import argparse
import webbrowser
from threading import Timer
from flask import Flask, render_template, url_for
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
GAMES_DIR = os.getenv("GAMES_DIR", "G:\\Games")
CACHE_FILE = "game_cache.json"
STEAMGRIDDB_API_KEY = os.getenv("STEAMGRIDDB_API_KEY")
STEAM_API_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
STEAMGRIDDB_API_URL = "https://www.steamgriddb.com/api/v2"

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Caching ---
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

# --- Helper Functions ---
def clean_game_name(folder_name):
    """Cleans a game folder name by removing common tags and formatting."""
    name = re.sub(r'\[.*?\]', '', folder_name)  # Remove content in brackets
    name = re.sub(r'v\d+(\.\d+)*', '', name)    # Remove version numbers
    name = name.replace('.', ' ').strip()      # Replace dots and strip whitespace
    return name

# --- API Fetching Functions ---
def get_steam_app_id(game_name):
    try:
        response = requests.get(STEAM_API_URL)
        response.raise_for_status()
        apps = response.json().get('applist', {}).get('apps', [])
        # Normalize the cleaned game name by removing non-alphanumeric characters
        normalized_game_name = re.sub(r'[^a-z0-9]', '', game_name.lower())
        
        for app in apps:
            # Normalize the official Steam name
            normalized_app_name = re.sub(r'[^a-z0-9]', '', app['name'].lower())
            
            # Check if the normalized game name is a substring of the normalized app name
            if normalized_game_name in normalized_app_name:
                print(f"  -> Matched '{game_name}' with Steam App '{app['name']}' (ID: {app['appid']})")
                return app['appid']
    except requests.RequestException as e:
        print(f"Error fetching Steam App ID for {game_name}: {e}")
    return None

def get_steam_review(app_id):
    if not app_id:
        return "N/A", 0
    try:
        # This is an undocumented endpoint that the Steam store uses. It provides all-time review stats.
        url = f"https://store.steampowered.com/appreviews/{app_id}?json=1&filter=all&language=all&purchase_type=all&num_per_page=0"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data.get('success') == 1:
            summary = data.get('query_summary', {})
            review_score_desc = summary.get('review_score_desc')
            total_reviews = summary.get('total_reviews', 0)
            if review_score_desc:
                print(f"  -> Found review for App ID {app_id}: {review_score_desc} ({total_reviews} reviews)")
                return review_score_desc, total_reviews
    except requests.RequestException as e:
        print(f"  -> Error fetching review for App ID {app_id}: {e}")
    return "No User Reviews", 0

def get_game_details(app_id):
    if not app_id:
        return 'N/A', [], '', [], None, 'N/A'
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and data.get(str(app_id), {}).get('success'):
            app_data = data[str(app_id)]['data']
            release_date = app_data.get('release_date', {}).get('date', 'N/A')
            genres = [genre['description'] for genre in app_data.get('genres', [])]
            short_description = app_data.get('short_description', '')
            screenshots = [ss['path_full'] for ss in app_data.get('screenshots', [])]
            video_url = None
            if 'movies' in app_data and app_data['movies']:
                video_url = app_data['movies'][0]['mp4']['max']
            
            pc_requirements = app_data.get('pc_requirements', {})
            storage_req = 'N/A'
            if isinstance(pc_requirements, dict) and 'minimum' in pc_requirements:
                # Extract storage requirement using regex
                match = re.search(r'(\d+\s*GB)', pc_requirements['minimum'])
                if match:
                    storage_req = match.group(1)

            print(f"  -> Found details for App ID {app_id}")
            return release_date, genres, short_description, screenshots, video_url, storage_req
    except requests.RequestException as e:
        print(f"  -> Error fetching details for App ID {app_id}: {e}")
    return 'N/A', [], '', [], None, 'N/A'

def get_game_cover(game_name, steam_app_id=None):
    # --- Primary Method: Steam Header Image ---
    if steam_app_id:
        # Steam provides a standard URL for the header image of every app.
        steam_cover_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_app_id}/header.jpg"
        # We can check if this image actually exists by making a HEAD request.
        try:
            response = requests.head(steam_cover_url, allow_redirects=True)
            # If the request is successful (status code 200), the image exists.
            if response.status_code == 200:
                print(f"  -> Found cover on Steam for App ID: {steam_app_id}")
                return steam_cover_url
        except requests.RequestException as e:
            print(f"  -> Error checking Steam header image for {game_name}: {e}")

    # --- Fallback Method: SteamGridDB ---
    if not STEAMGRIDDB_API_KEY:
        return None
    headers = {'Authorization': f'Bearer {STEAMGRIDDB_API_KEY}'}
    
    # Try to find the game on SteamGridDB by name as a fallback
    try:
        print(f"  -> Falling back to SteamGridDB search for '{game_name}'")
        search_url = f"{STEAMGRIDDB_API_URL}/search/autocomplete/{game_name}"
        response = requests.get(search_url, headers=headers)
        if response.status_code == 200:
            games = response.json().get('data', [])
            if games:
                game_id = games[0]['id']
                grid_url = f"{STEAMGRIDDB_API_URL}/grids/game/{game_id}"
                grid_response = requests.get(grid_url, headers=headers)
                if grid_response.status_code == 200:
                    grids = grid_response.json().get('data', [])
                    if grids:
                        print(f"  -> Found cover on SteamGridDB for '{game_name}'")
                        return grids[0]['url']
    except requests.RequestException as e:
        print(f"  -> Error fetching cover from SteamGridDB by name: {e}")
        
    print(f"  -> Could not find a cover for '{game_name}' on any service.")
    return None

def find_installer(game_path):
    if not os.path.isdir(game_path):
        return None
        
    largest_exe = None
    max_size = -1

    for root, _, files in os.walk(game_path):
        for file in files:
            if file.lower().endswith('.exe'):
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    if size > max_size:
                        max_size = size
                        largest_exe = file_path
                except OSError:
                    continue # Ignore files we can't access
    
    if largest_exe:
        print(f"  -> Found installer for '{os.path.basename(game_path)}': {os.path.basename(largest_exe)}")
    return largest_exe

# --- Flask Routes ---
@app.route('/')
def index():
    cache_only = app.config.get('CACHE_ONLY', False)
    games_list = []
    
    if cache_only:
        print("Running in cache-only mode.")
        cache = load_cache()
        games_list = list(cache.values())
    else:
        print("Running in sync mode. Scanning game directory...")
        limit = app.config.get('LIMIT')
        old_cache = load_cache()
        new_cache = {}
        
        if not os.path.exists(GAMES_DIR):
            return "Games directory not found. Please check the GAMES_DIR path in the script.", 404

        current_game_items = []
        for item in os.listdir(GAMES_DIR):
            item_path = os.path.join(GAMES_DIR, item)
            if os.path.isdir(item_path) or item.lower().endswith(('.rar', '.zip')):
                current_game_items.append(item)

        if limit:
            current_game_items = current_game_items[:limit]

        for item_name in current_game_items:
            item_path = os.path.join(GAMES_DIR, item_name)
            
            if os.path.isfile(item_path):
                folder_name, _ = os.path.splitext(item_name)
            else:
                folder_name = item_name
                
            cleaned_name = clean_game_name(folder_name)
            print(f"Processing: {cleaned_name}...")
            
            if cleaned_name in old_cache:
                print(f"  -> Found '{cleaned_name}' in cache.")
                new_cache[cleaned_name] = old_cache[cleaned_name]
                games_list.append(old_cache[cleaned_name])
                continue

            print(f"  -> Fetching data for '{cleaned_name}' from APIs.")
            app_id = get_steam_app_id(cleaned_name)
            cover_url = get_game_cover(cleaned_name, app_id)
            review_desc, total_reviews = get_steam_review(app_id)
            release_date, genres, short_description, screenshots, video_url, storage_req = get_game_details(app_id)
            installer_path = find_installer(item_path) if os.path.isdir(item_path) else item_path
            
            if app_id:
                steam_url = f"https://store.steampowered.com/app/{app_id}"
            else:
                print(f"  -> Could not find a Steam App ID for '{cleaned_name}'. Creating a generic search link.")
                steam_url = f"https://www.google.com/search?q={cleaned_name.replace(' ', '+')}+game"

            game_data = {
                'name': cleaned_name,
                'cover_url': cover_url or url_for('static', filename='default_cover.png'),
                'steam_url': steam_url,
                'review_desc': review_desc,
                'total_reviews': total_reviews,
                'installer_path': installer_path,
                'release_date': release_date,
                'genres': genres,
                'short_description': short_description,
                'screenshots': screenshots,
                'video_url': video_url,
                'storage': storage_req
            }
            games_list.append(game_data)
            new_cache[cleaned_name] = game_data
            print(f"  -> Successfully processed and cached data for '{cleaned_name}'.")

        save_cache(new_cache)

    all_genres = sorted(list(set(genre for game in games_list for genre in game.get('genres', []))))

    return render_template('index.html', games=games_list, all_genres=all_genres, cache_only=cache_only)

@app.route('/install/<game_name>')
def install_game(game_name):
    cache = load_cache()
    game_data = cache.get(game_name)
    if game_data and game_data.get('installer_path'):
        installer_path = game_data['installer_path']
        try:
            print(f"Attempting to open: {installer_path}")
            os.startfile(installer_path)
            return {"status": "success", "message": f"Launched {os.path.basename(installer_path)}"}, 200
        except Exception as e:
            print(f"Error starting file '{installer_path}': {e}")
            return {"status": "error", "message": str(e)}, 500
    return {"status": "error", "message": "Game or installer path not found."}, 404

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Game Dashboard')
    parser.add_argument('--limit', type=int, help='Limit the number of games to display')
    parser.add_argument('--cache-only', action='store_true', help='Run in cache-only mode without scanning the game directory')
    args = parser.parse_args()
    
    app.config['LIMIT'] = args.limit
    app.config['CACHE_ONLY'] = args.cache_only
    
    # Open the browser automatically after a short delay
    def open_browser():
        webbrowser.open_new('http://127.0.0.1:5000/')

    Timer(1, open_browser).start()
    
    app.run(debug=True)
