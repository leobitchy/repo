# -*- coding: utf-8 -*-
import sys
import json
from xml.etree import ElementTree as ET
import urllib.parse as urlparse
import os
import re
import time
import datetime
import glob
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

import xbmcvfs
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)

# Plugin Handle
try:
    HANDLE = int(sys.argv[1])
except (IndexError, ValueError):
    HANDLE = -1
    log("No valid handle, using -1", xbmc.LOGDEBUG)

try:
    xbmcplugin.setPluginCategory(HANDLE, "MyMovies")
    xbmcplugin.setContent(HANDLE, 'videos')
except Exception as e:
    log(f"Error setting plugin properties: {e}", xbmc.LOGERROR)

# Paths
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
if not PROFILE_PATH.endswith(os.sep):
    PROFILE_PATH += os.sep
FAV_FILE_SRC = xbmcvfs.translatePath('special://profile/favourites.xml')
MYMOVIES_FILE = os.path.join(PROFILE_PATH, 'mymovies.json')
CAT_FILE = os.path.join(PROFILE_PATH, 'categories.json')
MOVIES_PATH = os.path.join(PROFILE_PATH, 'movies/')
BACKUP_PATH = os.path.join(PROFILE_PATH, 'backups/')
BACKUP_FILE = os.path.join(BACKUP_PATH, 'mymovies_backup.json')
AUTO_BACKUP_STATUS_FILE = os.path.join(PROFILE_PATH, 'auto_backup.json')

# Paths to Icons
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ICON_PATH = os.path.join(ADDON_PATH, 'icon_folders.png')
ICON_IMPORT = os.path.join(ADDON_PATH, 'icon_import.png')
ICON_CATEGORY = os.path.join(ADDON_PATH, 'icon_categories.png')
ICON_MOVIES = os.path.join(ADDON_PATH, 'icon_mymovies.png')
ICON_FAVORITES = os.path.join(ADDON_PATH, 'icon_favorites.png')
ICON_BACKUP = os.path.join(ADDON_PATH, 'icon_backups.png')
ICON_SEARCH = os.path.join(ADDON_PATH, 'icon_search.png')

# Cache for data
CACHE = {
    'movies': None,
    'cats': None
}

def ensure_files():
    try:
        if not xbmcvfs.exists(PROFILE_PATH):
            xbmcvfs.mkdirs(PROFILE_PATH)
            log(f"Profile directory created: {PROFILE_PATH}", xbmc.LOGDEBUG)
        if not xbmcvfs.exists(MYMOVIES_FILE):
            with xbmcvfs.File(MYMOVIES_FILE, 'w') as f:
                f.write(bytearray(json.dumps([], ensure_ascii=False), 'utf-8'))
            log(f"MyMovies file created: {MYMOVIES_FILE}", xbmc.LOGDEBUG)
        if not xbmcvfs.exists(CAT_FILE):
            default_cats = ["Horror", "Comedy", "Drama", "Anime", "Series"]
            with xbmcvfs.File(CAT_FILE, 'w') as f:
                f.write(bytearray(json.dumps(default_cats, ensure_ascii=False), 'utf-8'))
            log(f"Categories file created: {CAT_FILE}", xbmc.LOGDEBUG)
        if not xbmcvfs.exists(BACKUP_PATH):
            xbmcvfs.mkdirs(BACKUP_PATH)
            log(f"Backup directory created: {BACKUP_PATH}", xbmc.LOGDEBUG)
        if not xbmcvfs.exists(MOVIES_PATH):
            xbmcvfs.mkdirs(MOVIES_PATH)
            log(f"Movies directory created: {MOVIES_PATH}", xbmc.LOGDEBUG)
        if not xbmcvfs.exists(AUTO_BACKUP_STATUS_FILE):
            status_data = {'auto_backup_enabled': False, 'last_backup_time': 0}
            with xbmcvfs.File(AUTO_BACKUP_STATUS_FILE, 'w') as f:
                f.write(bytearray(json.dumps(status_data, ensure_ascii=False), 'utf-8'))
            log(f"Auto-Backup status file created: {AUTO_BACKUP_STATUS_FILE}", xbmc.LOGDEBUG)
    except Exception as e:
        log(f"Error creating files: {e}", xbmc.LOGERROR)

def normalize_url(url):
    url = urlparse.unquote(url.replace('&mymovies=1', '').strip())
    normalized = url.lower()
    if normalized.startswith('playmedia('):
        match = re.match(r'playmedia\("?(.*?)"?\)$', normalized, re.IGNORECASE | re.DOTALL)
        if match:
            url = urlparse.unquote(match.group(1).strip())
    elif normalized.startswith('activatewindow(10025,"plugin'):
        match = re.match(r'activatewindow\(10025,"(plugin://[^"]+)",return\)', url, re.IGNORECASE)
        if match:
            url = match.group(1)
    return url.lower()  # Final lower für Vergleich, aber originale case für Execution erhalten

def get_media_type_from_url(url):
    if not url:
        return 'movie'

    url_l = url.lower()

    if 'tmdb_type=tv' in url_l or 'info=seasons' in url_l:
        return 'tv'

    return 'movie'
    
def is_in_great_movies(title, stream_url):
    clean_title = title.strip()
    clean_stream_url = normalize_url(stream_url)
    movies = read_movies()
    for m in movies:
        m_url = normalize_url(m['stream_url'])
        if m.get('fav') and m['title'].strip() == clean_title and m_url == clean_stream_url:
            return True
    return False
 
def read_auto_backup_status():
    try:
        with xbmcvfs.File(AUTO_BACKUP_STATUS_FILE, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
        if not data:
            log("Auto-Backup status file is empty, setting to defaults", xbmc.LOGWARNING)
            return False, 0
        status_data = json.loads(data)
        auto_backup_enabled = status_data.get('auto_backup_enabled', False)
        last_backup_time = status_data.get('last_backup_time', 0)
        try:
            last_backup_time = float(last_backup_time)
        except (ValueError, TypeError):
            log("Invalid last_backup_time in auto_backup.json, setting to 0", xbmc.LOGWARNING)
            last_backup_time = 0
        log(f"Auto-Backup status read: enabled={auto_backup_enabled}, last_backup_time={last_backup_time}", xbmc.LOGDEBUG)
        return bool(auto_backup_enabled), last_backup_time
    except Exception as e:
        log(f"Error reading auto_backup.json: {e}, setting to defaults", xbmc.LOGERROR)
        return False, 0

def write_auto_backup_status(enabled, last_backup_time):
    try:
        status_data = {'auto_backup_enabled': enabled, 'last_backup_time': last_backup_time}
        with xbmcvfs.File(AUTO_BACKUP_STATUS_FILE, 'w') as f:
            f.write(bytearray(json.dumps(status_data, ensure_ascii=False), 'utf-8'))
        log(f"Auto-Backup status written: enabled={enabled}, last_backup_time={last_backup_time}", xbmc.LOGDEBUG)
    except Exception as e:
        log(f"Error writing auto_backup.json: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Error saving backup status or timestamp", xbmcgui.NOTIFICATION_ERROR, 1500)

def read_movies():
    try:
        if CACHE['movies'] is not None:
            log(f"Using cached movies", xbmc.LOGDEBUG)
            return CACHE['movies']
        ensure_files()
        with xbmcvfs.File(MYMOVIES_FILE, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
        movies = json.loads(data) if data else []
        CACHE['movies'] = movies
        log(f"Movies file read: {MYMOVIES_FILE}", xbmc.LOGDEBUG)
        return movies
    except Exception as e:
        log(f"Read error {MYMOVIES_FILE}: {e}", xbmc.LOGERROR)
        return []

def write_movies(movies):
    try:
        with xbmcvfs.File(MYMOVIES_FILE, 'w') as f:
            f.write(bytearray(json.dumps(movies, indent=2, ensure_ascii=False), 'utf-8'))
        CACHE['movies'] = movies
        log(f"Movies file written: {MYMOVIES_FILE}", xbmc.LOGDEBUG)
    except Exception as e:
        log(f"Write error {MYMOVIES_FILE}: {e}", xbmc.LOGERROR)

def read_categories():
    log("read_categories called", xbmc.LOGDEBUG)
    try:
        if CACHE['cats'] is not None:
            log("Using cached categories", xbmc.LOGDEBUG)
            return CACHE['cats']
        ensure_files()
        with xbmcvfs.File(CAT_FILE, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
        if not data:
            log("Categories file is empty", xbmc.LOGWARNING)
            return []
        cats = json.loads(data)
        if not isinstance(cats, list):
            log("Categories data is not an array", xbmc.LOGWARNING)
            return []
        CACHE['cats'] = cats
        log(f"Categories loaded: {cats}", xbmc.LOGDEBUG)
        return cats
    except Exception as e:
        log(f"Category read error: {e}", xbmc.LOGWARNING)
        return []

def write_categories(cats):
    if cats is None:
        cats = []
    try:
        cats = sorted(cats, key=str.lower) if cats else []
        with xbmcvfs.File(CAT_FILE, 'w') as f:
            f.write(bytearray(json.dumps(cats, ensure_ascii=False), 'utf-8'))
        CACHE['cats'] = cats
        log(f"Categories written and cached: {cats}", xbmc.LOGDEBUG)
        # Prüfen, ob die Datei korrekt geschrieben wurde
        with xbmcvfs.File(CAT_FILE, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
            written_cats = json.loads(data) if data else []
            if written_cats != cats:
                log(f"Error: Written categories {written_cats} do not match expected {cats}", xbmc.LOGERROR)
    except Exception as e:
        log(f"Category write error: {e}", xbmc.LOGERROR)

def import_from_context(title=None, thumb=None, stream_url=None, category=None):
    log(f"import_from_context called with title={title}, thumb={thumb}, stream_url={stream_url}, category={category}", xbmc.LOGDEBUG)
    try:
        clean_title = urlparse.unquote(title).strip() if title else None
        clean_stream_url = urlparse.unquote(stream_url).replace('&mymovies=1', '').strip() if stream_url else None
        clean_thumb = thumb or ICON_PATH

        if not clean_title or not clean_stream_url:
            log("Invalid parameters for import_from_context", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        movies = read_movies()
        for m in movies:
            if m['title'].strip() == clean_title and normalize_url(m['stream_url']) == normalize_url(clean_stream_url):
                log(f"Movie '{clean_title}' already exists in mymovies.json", xbmc.LOGINFO)
                xbmcgui.Dialog().notification("MyMovies", f"Movie already exists: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1500)
                return

        new_movie = {
            'title': clean_title,
            'thumb': clean_thumb,
            'stream_url': clean_stream_url,
            'is_folder': clean_stream_url.lower().startswith('activatewindow'),
            'fav': False  # Standardmäßig fav auf False setzen
        }

        if not category or category.lower() == 'none' or category == '':
            # Nur bei "No Category" zu mymovies.json hinzufügen
            movies.append(new_movie)
            write_movies(movies)
            log(f"Imported '{clean_title}' to mymovies.json with fav=False (No Category)", xbmc.LOGINFO)
        else:
            # Bei Kategorie: Nur zu category.json, nicht zu mymovies.json
            new_movie['category'] = category  # Füge category-Feld hinzu für Konsistenz
            cat_file = os.path.join(MOVIES_PATH, f"{category}.json")
            cat_movies = []
            if xbmcvfs.exists(cat_file):
                with xbmcvfs.File(cat_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    cat_movies = json.loads(data) if data else []
            cat_movies.append(new_movie)
            with xbmcvfs.File(cat_file, 'w') as f:
                f.write(bytearray(json.dumps(cat_movies, indent=2, ensure_ascii=False), 'utf-8'))
            log(f"Added '{clean_title}' to {category}.json (no add to mymovies.json)", xbmc.LOGINFO)
            CACHE[f'category_{category}'] = None

        xbmcgui.Dialog().notification("MyMovies", f"Imported: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1200)
        CACHE['movies'] = None
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in import_from_context: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to import movie: {clean_title}", xbmcgui.NOTIFICATION_ERROR, 1500)

def remove_from_json(category, title, stream_url):
    log(f"remove_from_json called with category={category!r}, title={title!r}, stream_url={stream_url!r}", xbmc.LOGDEBUG)
    try:
        if not category or category.lower() == 'none':
            log(f"Invalid category: {category}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", f"Invalid category: {category or 'None provided'}", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        # Prüfen, ob die Kategorie in der categories.json existiert
        cats = read_categories()
        if category not in cats:
            log(f"Category '{category}' not found in categories: {cats}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", f"Category '{category}' does not exist", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        movies_file = os.path.join(MOVIES_PATH, f'{category}.json')
        if not xbmcvfs.exists(movies_file):
            log(f"Category file not found: {movies_file}", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("MyMovies", f"Category file '{category}' not found", xbmcgui.NOTIFICATION_WARNING, 1500)
            return

        with xbmcvfs.File(movies_file, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
            movies = json.loads(data) if data else []

        clean_stream_url = urlparse.unquote(stream_url).replace('&mymovies=1', '') if stream_url else None
        clean_title = urlparse.unquote(title) if title else None

        if not clean_title or not clean_stream_url:
            log("Invalid parameters for remove_from_json", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        updated_movies = [movie for movie in movies if not (movie['title'] == clean_title and movie['stream_url'] == clean_stream_url)]
        if len(updated_movies) < len(movies):
            with xbmcvfs.File(movies_file, 'w') as f:
                f.write(bytearray(json.dumps(updated_movies, indent=2, ensure_ascii=False), 'utf-8'))
            log(f"Removed movie '{clean_title}' from {category}", xbmc.LOGINFO)
            xbmcgui.Dialog().notification("MyMovies", f"Removed '{clean_title}' from {category}", xbmcgui.NOTIFICATION_INFO, 1500)
            xbmc.executebuiltin('Container.Refresh')
        else:
            log(f"Movie '{clean_title}' with stream_url '{clean_stream_url}' not found in {movies_file}", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("MyMovies", f"Movie '{clean_title}' not found in {category}", xbmcgui.NOTIFICATION_WARNING, 1500)
    except Exception as e:
        log(f"Error in remove_from_json: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to remove movie", xbmcgui.NOTIFICATION_ERROR, 1500)

def list_import_candidates():
    log("list_import_candidates called", xbmc.LOGDEBUG)
    try:
        root, tree = read_favs(FAV_FILE_SRC)
        favs = root.findall('favourite')
        for index, fav in enumerate(favs):
            name = fav.get('name', 'Unnamed')
            thumb = fav.get('thumb', ICON_PATH)
            url = (fav.text or '').strip()
            if not url:
                log(f"No URL for favourite {name}", xbmc.LOGWARNING)
                continue

            li = xbmcgui.ListItem(label=name)
            li.setArt({'thumb': thumb, 'icon': thumb})
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(name)
            li.setProperty('IsPlayable', 'false')

            params = {'action': 'copy_by_index', 'idx': str(index)}
            encoded_params = urlparse.urlencode(params)
            plugin_url = f"{sys.argv[0]}?{encoded_params}"

            xbmcplugin.addDirectoryItem(HANDLE, plugin_url, li, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
    except Exception as e:
        log(f"Error in list_import_candidates: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to list import candidates", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def read_favs(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        log(f"Favourites file read: {path}", xbmc.LOGDEBUG)
        return root, tree
    except Exception as e:
        log(f"Read error {path}: {e}", xbmc.LOGERROR)
        root = ET.Element('favourites')
        tree = ET.ElementTree(root)
        return root, tree

def copy_by_index(idx_str):
    log(f"copy_by_index called with idx={idx_str}", xbmc.LOGDEBUG)
    try:
        if idx_str is None:
            log("Invalid index: None", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid index", xbmcgui.NOTIFICATION_ERROR, 1500)
            return
        idx = int(idx_str)
        root, tree = read_favs(FAV_FILE_SRC)
        favs = root.findall('favourite')
        if not (0 <= idx < len(favs)):
            log(f"Index {idx} out of bounds", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid index", xbmcgui.NOTIFICATION_ERROR, 1500)
            return
        fav = favs[idx]
        name = fav.get('name', 'Unnamed')
        thumb = fav.get('thumb', ICON_PATH)
        stream_url = (fav.text or '').strip()
        if not stream_url:
            log(f"No valid text for index {idx}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "No valid content", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        log(f"Importing: name={name}, thumb={thumb}, stream_url={stream_url}", xbmc.LOGDEBUG)

        movies = read_movies()
        clean_stream_url = stream_url.replace('&mymovies=1', '').strip()
        for movie in movies:
            if movie['title'].strip() == name.strip() and movie['stream_url'].replace('&mymovies=1', '').strip() == clean_stream_url:
                log(f"Duplicate found: {name}", xbmc.LOGINFO)
                xbmcgui.Dialog().notification("MyMovies", f"Already in MyMovies: {name}", xbmcgui.NOTIFICATION_INFO, 1500)
                return

        is_folder = stream_url.lower().startswith('activatewindow')
        movies.append({
            'title': name.strip(),
            'thumb': thumb,
            'stream_url': clean_stream_url,
            'is_folder': is_folder,
            'fav': False  # Standardmäßig fav auf False setzen
        })
        write_movies(movies)
        log(f"New movie added: title={name}, stream_url={clean_stream_url}, is_folder={is_folder}, fav=False", xbmc.LOGDEBUG)
        xbmcgui.Dialog().notification("MyMovies", f"Imported: {name}", xbmcgui.NOTIFICATION_INFO, 1500)
        CACHE['movies'] = None
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in copy_by_index: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to import", xbmcgui.NOTIFICATION_ERROR, 1500)

def import_from_fav(idx):
    log(f"import_from_fav called with idx={idx}", xbmc.LOGDEBUG)
    try:
        idx = int(idx)
        movies = read_movies()
        if not (0 <= idx < len(CACHE['import'])):
            log(f"Invalid index {idx} for import", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        candidate = CACHE['import'][idx]
        title = candidate.get('label', 'Unnamed')
        thumb = candidate.get('thumb', ICON_PATH)
        stream_url = candidate.get('url', '')

        if not title or not stream_url:
            log("Invalid movie data for import", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid movie data", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        clean_title = title.strip()
        clean_stream_url = stream_url.replace('&mymovies=1', '').strip()

        for m in movies:
            if m['title'].strip() == clean_title and m['stream_url'].replace('&mymovies=1', '').strip() == clean_stream_url:
                log(f"Movie '{clean_title}' already exists in mymovies.json", xbmc.LOGINFO)
                xbmcgui.Dialog().notification("MyMovies", f"Movie already exists: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1500)
                return

        new_movie = {
            'title': clean_title,
            'thumb': thumb,
            'stream_url': clean_stream_url,
            'is_folder': clean_stream_url.lower().startswith('activatewindow'),
            'fav': False  # Standardmäßig fav auf False setzen
        }
        movies.append(new_movie)
        write_movies(movies)
        log(f"Imported '{clean_title}' to mymovies.json with fav=False", xbmc.LOGINFO)
        xbmcgui.Dialog().notification("MyMovies", f"Imported: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1200)
        CACHE['movies'] = None
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in test_import: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to import movie: {clean_title}", xbmcgui.NOTIFICATION_ERROR, 1500)

def home():
    log("home called", xbmc.LOGDEBUG)
    try:
        if CACHE['movies'] is None:
            CACHE['movies'] = read_movies()
        if CACHE['cats'] is None:
            CACHE['cats'] = read_categories()

        # Fixed menu order
        menu_items = [
            {
                'label': "Import from Favorites",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'import_from_fav'})}",
                'icon': ICON_IMPORT,
                'is_folder': True
            },
            {
                'label': "Backup",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_backup_menu'})}",
                'icon': ICON_BACKUP,
                'is_folder': True
            },
            {
                'label': "Categories",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_categories_menu'})}",
                'icon': ICON_CATEGORY,
                'is_folder': True
            },
            {
                'label': "Great Movies",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_favs'})}",
                'icon': ICON_FAVORITES,
                'is_folder': True
            },
            {
                'label': "ALL MOVIES",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_all'})}",
                'icon': ICON_MOVIES,
                'is_folder': True
            }
        ]

        for item in menu_items:
            li = xbmcgui.ListItem(label=item['label'])
            li.setArt({'icon': item['icon'], 'thumb': item['icon']})
            xbmcplugin.addDirectoryItem(HANDLE, item['url'], li, isFolder=item['is_folder'])

        movies = read_movies()
        seen = set()
        unsorted = []
        for i, movie in enumerate(movies):
            key = movie['stream_url']
            if not key or key in seen or movie.get('category') or movie.get('fav'):
                continue
            seen.add(key)
            unsorted.append((i, movie))
        unsorted = sorted(unsorted, key=lambda x: x[1]['title'].lower())
        for idx, movie in unsorted:
            add_movie_listitem(movie, idx, category=None)

        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_NONE)  # Preserve fixed order
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in home: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Error loading the main menu", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def list_categories_menu():
    log("list_categories_menu called", xbmc.LOGDEBUG)
    try:
        url_newcat = f"{sys.argv[0]}?{urlparse.urlencode({'action':'add_category'})}"
        li_newcat = xbmcgui.ListItem(label="Create New Category")
        li_newcat.setArt({'icon': ICON_PATH, 'thumb': ICON_PATH})
        xbmcplugin.addDirectoryItem(HANDLE, url_newcat, li_newcat, isFolder=False)

        cats = sorted(read_categories(), key=str.lower)
        for cat in cats:
            url = f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_category','cat':cat})}"
            li = xbmcgui.ListItem(label=cat)
            li.setArt({'icon': ICON_PATH, 'thumb': ICON_PATH})
            cm = []
            cm.append(("Rename Category", f"RunPlugin({sys.argv[0]}?{urlparse.urlencode({'action':'rename_category','cat':cat})})"))
            cm.append(("Delete Category", f"RunPlugin({sys.argv[0]}?{urlparse.urlencode({'action':'delete_category','cat':cat})})"))
            li.addContextMenuItems(cm, replaceItems=True)
            xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)

        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in list_categories_menu: {e}", xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def list_category(category):
    log(f"list_category called with category={category}", xbmc.LOGDEBUG)
    try:
        if not category or category.lower() == 'none':
            log(f"Invalid category: {category}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", f"Invalid category: {category or 'None provided'}", xbmcgui.NOTIFICATION_ERROR, 1500)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        # Cache für die Kategorie zurücksetzen
        CACHE[f'category_{category}'] = None

        movies_file = os.path.join(MOVIES_PATH, f'{category}.json')
        if not xbmcvfs.exists(movies_file):
            log(f"Category file {movies_file} does not exist, creating empty file", xbmc.LOGWARNING)
            with xbmcvfs.File(movies_file, 'w') as f:
                f.write(bytearray(json.dumps([], ensure_ascii=False), 'utf-8'))
            xbmcgui.Dialog().notification("MyMovies", f"Category '{category}' is empty", xbmcgui.NOTIFICATION_INFO, 1500)

        with xbmcvfs.File(movies_file, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
            movies = json.loads(data) if data else []

        sorted_movies = sorted(movies, key=lambda x: x.get('title', '').lower())
        for movie in sorted_movies:
            add_movie_listitem_from_json(movie, category)

        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in list_category: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to list category '{category}'", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def list_backup_menu():
    log("list_backup_menu called", xbmc.LOGDEBUG)
    try:
        icon = ICON_BACKUP if xbmcvfs.exists(ICON_BACKUP) else ICON_PATH
        log(f"Using icon: {icon}", xbmc.LOGDEBUG)

        if not xbmcvfs.exists(BACKUP_PATH):
            log(f"Backup directory {BACKUP_PATH} missing, creating it", xbmc.LOGDEBUG)
            xbmcvfs.mkdirs(BACKUP_PATH)

        auto_backup_status, last_backup_time = read_auto_backup_status()
        log(f"auto_backup_enabled status: {auto_backup_status}, last_backup_time: {last_backup_time}", xbmc.LOGDEBUG)

        menu_items = [
            {
                'label': "Export",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'export_backup'})}",
                'is_folder': False
            },
            {
                'label': "Import",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'import_backup'})}",
                'is_folder': False
            },
            {
                'label': "Turn Off Automatic Backup" if auto_backup_status else "Turn On Automatic Backup",
                'url': f"{sys.argv[0]}?{urlparse.urlencode({'action':'toggle_auto_backup'})}",
                'is_folder': False
            }
        ]
        menu_items = sorted(menu_items, key=lambda x: x['label'].lower())
        for item in menu_items:
            li = xbmcgui.ListItem(label=item['label'])
            li.setArt({'icon': icon, 'thumb': icon})
            xbmcplugin.addDirectoryItem(HANDLE, item['url'], li, isFolder=item['is_folder'])

        log("Finalizing backup menu", xbmc.LOGDEBUG)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
        log("Backup menu rendered successfully", xbmc.LOGDEBUG)
    except Exception as e:
        log(f"Critical error in list_backup_menu: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Error loading the backup menu: {str(e)}", xbmcgui.NOTIFICATION_ERROR, 5000)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def toggle_auto_backup():
    log("toggle_auto_backup called", xbmc.LOGDEBUG)
    try:
        current_status, last_backup_time = read_auto_backup_status()
        log(f"Old auto_backup_enabled status: {current_status}, last_backup_time: {last_backup_time}", xbmc.LOGDEBUG)

        new_status = not current_status
        write_auto_backup_status(new_status, last_backup_time)

        saved_status, saved_time = read_auto_backup_status()
        log(f"New auto_backup_enabled status: {saved_status}, last_backup_time: {saved_time}", xbmc.LOGDEBUG)

        if saved_status != new_status:
            log("Error: New status not saved correctly", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Error saving backup status", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        status_text = "enabled" if new_status else "disabled"
        xbmcgui.Dialog().notification("MyMovies", f"Automatic Backup {status_text}", xbmcgui.NOTIFICATION_INFO, 1500)

        backup_menu_url = f"{sys.argv[0]}?{urlparse.urlencode({'action':'show_backup_menu'})}"
        xbmc.executebuiltin(f'Container.Update({backup_menu_url})')
    except Exception as e:
        log(f"Error in toggle_auto_backup: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Error toggling automatic backups", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def auto_backup():
    log("auto_backup called", xbmc.LOGDEBUG)
    try:
        auto_backup_enabled, last_backup_time = read_auto_backup_status()
        log(f"auto_backup_enabled: {auto_backup_enabled}, last_backup_time: {last_backup_time}", xbmc.LOGDEBUG)

        if not auto_backup_enabled:
            log("Automatic backups disabled, skipping", xbmc.LOGDEBUG)
            return

        current_time = time.time()
        log(f"Current time: {current_time}", xbmc.LOGDEBUG)
        time_diff = current_time - last_backup_time
        log(f"Time since last backup: {time_diff} seconds", xbmc.LOGDEBUG)

        if time_diff < 3600:
            log("Backup skipped: Not enough time since last backup", xbmc.LOGDEBUG)
            return

        if time_diff < 300:
            log("Backup skipped: Additional lock (less than 5 minutes)", xbmc.LOGDEBUG)
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        backup_file = os.path.join(BACKUP_PATH, f'mymovies_backup_{timestamp}.json')
        log(f"Creating backup: {backup_file}", xbmc.LOGDEBUG)

        backup_data = build_backup_data()
        with xbmcvfs.File(backup_file, 'w') as f:
            f.write(bytearray(json.dumps(backup_data, indent=2, ensure_ascii=False), 'utf-8'))

        write_auto_backup_status(auto_backup_enabled, current_time)

        _, saved_time = read_auto_backup_status()
        log(f"last_backup_time saved: {saved_time}", xbmc.LOGDEBUG)
        if saved_time != current_time:
            log("Error: last_backup_time not saved correctly", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Error saving backup timestamp", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        log(f"Automatic backup created: {backup_file}", xbmc.LOGDEBUG)
        xbmcgui.Dialog().notification("MyMovies", f"Automatic Backup created: {timestamp}", xbmcgui.NOTIFICATION_INFO, 1500)
        manage_backups()
    except Exception as e:
        log(f"Error during automatic backup: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Error during automatic backup: {str(e)}", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def manage_backups():
    log("manage_backups called", xbmc.LOGDEBUG)
    try:
        backup_files = glob.glob(os.path.join(BACKUP_PATH, 'mymovies_backup_*.json'))
        backup_files.sort(key=os.path.getmtime, reverse=True)
        if len(backup_files) > 30:
            for old_file in backup_files[30:]:
                xbmcvfs.delete(old_file)
                log(f"Old backup deleted: {old_file}", xbmc.LOGDEBUG)
    except Exception as e:
        log(f"Error managing backups: {e}", xbmc.LOGERROR)

def add_category():
    log("add_category called", xbmc.LOGDEBUG)
    try:
        kb = xbmc.Keyboard('', 'Enter New Category')
        kb.doModal()
        if not kb.isConfirmed():
            return
        name = (kb.getText() or '').strip()
        if not name:
            return
        cats = read_categories()
        if name in cats:
            xbmcgui.Dialog().notification("MyMovies", "Category already exists", xbmcgui.NOTIFICATION_INFO, 1500)
            return
        cats.append(name)
        cats = sorted(cats, key=str.lower)
        write_categories(cats)
        xbmcgui.Dialog().notification("MyMovies", f"Category created: {name}", xbmcgui.NOTIFICATION_INFO, 1500)
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in add_category: {e}", xbmc.LOGERROR)

def delete_category(cat):
    log(f"delete_category called with cat={cat}", xbmc.LOGDEBUG)
    try:
        if not cat:
            log("No category provided", xbmc.LOGERROR)
            return
        cats = read_categories()
        if cat not in cats:
            log(f"Category '{cat}' not found in categories", xbmc.LOGERROR)
            return
        if not xbmcgui.Dialog().yesno("Delete Category", f"Do you really want to delete the category '{cat}'?"):
            return
        cats.remove(cat)
        write_categories(cats)
        CACHE['cats'] = None  # Cache zurücksetzen
        movies = read_movies()
        updated_movies = [m for m in movies if m.get('category') != cat]
        write_movies(updated_movies)
        movies_file = os.path.join(MOVIES_PATH, f'{cat}.json')
        if xbmcvfs.exists(movies_file):
            xbmcvfs.delete(movies_file)
            log(f"Deleted category file: {movies_file}", xbmc.LOGDEBUG)
        xbmcgui.Dialog().notification("MyMovies", f"Category '{cat}' deleted", xbmcgui.NOTIFICATION_INFO, 1500)
        # Zurück zur Kategorienansicht
        xbmc.executebuiltin(f'Container.Update({sys.argv[0]}?action=show_categories_menu)')
    except Exception as e:
        log(f"Error in delete_category: {e}", xbmc.LOGERROR)

def rename_category(cat):
    log(f"rename_category called with cat={cat}", xbmc.LOGDEBUG)
    try:
        if not cat:
            return
        cats = read_categories()
        if cat not in cats:
            return
        kb = xbmc.Keyboard(cat, 'Rename Category')
        kb.doModal()
        if not kb.isConfirmed():
            return
        new_name = (kb.getText() or '').strip()
        if not new_name or new_name == cat:
            return
        if new_name in cats:
            xbmcgui.Dialog().notification("MyMovies", "Category already exists", xbmcgui.NOTIFICATION_INFO, 1500)
            return
        cats[cats.index(cat)] = new_name
        write_categories(cats)
        movies = read_movies()
        for movie in movies:
            if movie.get('category') == cat:
                movie['category'] = new_name
        write_movies(movies)
        old_file = os.path.join(MOVIES_PATH, f'{cat}.json')
        new_file = os.path.join(MOVIES_PATH, f'{new_name}.json')
        if xbmcvfs.exists(old_file):
            xbmcvfs.rename(old_file, new_file)
            log(f"Renamed category file: {old_file} to {new_file}", xbmc.LOGDEBUG)
        xbmcgui.Dialog().notification("MyMovies", f"Category renamed to '{new_name}'", xbmcgui.NOTIFICATION_INFO, 1500)
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in rename_category: {e}", xbmc.LOGERROR)

def move_to_category(idx_str=None, title=None, thumb=None, stream_url=None):
    log(f"move_to_category called with idx={idx_str!r}, title={title!r}, thumb={thumb!r}, stream_url={stream_url!r}", xbmc.LOGDEBUG)
    try:
        if idx_str is not None:
            try:
                idx = int(idx_str)
                movies = read_movies()
                if idx < 0 or idx >= len(movies):
                    log(f"Invalid index: {idx}", xbmc.LOGERROR)
                    xbmcgui.Dialog().notification("MyMovies", "Invalid movie index", xbmcgui.NOTIFICATION_ERROR, 1500)
                    return
                movie = movies[idx]
                clean_title = movie.get('title', 'Unnamed').strip()
                clean_stream_url = movie.get('stream_url', '').replace('&mymovies=1', '').strip()
                thumb = movie.get('thumb')
                fav_status = movie.get('fav', False)  # fav-Status übernehmen
            except (ValueError, IndexError) as e:
                log(f"Error parsing index {idx_str}: {e}", xbmc.LOGERROR)
                xbmcgui.Dialog().notification("MyMovies", "Invalid movie selection", xbmcgui.NOTIFICATION_ERROR, 1500)
                return
        else:
            clean_title = urlparse.unquote(title).strip() if title else None
            clean_stream_url = urlparse.unquote(stream_url).replace('&mymovies=1', '').strip() if stream_url else None
            if not clean_title or not clean_stream_url:
                log("Invalid parameters for move_to_category", xbmc.LOGERROR)
                xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
                return
            # fav-Status aus mymovies.json suchen
            movies = read_movies()
            fav_status = False
            for m in movies:
                if m['title'].strip() == clean_title and m['stream_url'].replace('&mymovies=1', '').strip() == clean_stream_url:
                    fav_status = m.get('fav', False)
                    break

        cats = read_categories()
        if not cats:
            log("No categories available", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("MyMovies", "No categories available. Add a category first.", xbmcgui.NOTIFICATION_WARNING, 1500)
            return

        # Übernimm Logik aus context.py: Sortiere alphabetisch, füge Optionen hinzu
        categories = sorted(cats, key=str.lower)
        categories.append('No category')
        categories.append('Create new category')
        dialog = xbmcgui.Dialog()
        selected = dialog.select('Choose category', categories)

        if selected == -1:
            log("Category selection canceled", xbmc.LOGDEBUG)
            return
        if selected == len(categories) - 2:  # "No category"
            selected_category = ''
            log("No category selected", xbmc.LOGDEBUG)
        elif selected == len(categories) - 1:  # "Create new category"
            new_category = dialog.input('New category')
            if not new_category:
                log("No new category entered", xbmc.LOGDEBUG)
                xbmcgui.Dialog().notification('MyMovies', 'No category name entered', xbmcgui.NOTIFICATION_INFO, 1500)
                return
            if new_category in cats:
                xbmcgui.Dialog().notification('MyMovies', f'Category "{new_category}" already exists', xbmcgui.NOTIFICATION_INFO, 1500)
                return
            cats.append(new_category)
            write_categories(cats)
            selected_category = new_category
            log(f"New category created: {new_category}", xbmc.LOGDEBUG)
        else:
            selected_category = categories[selected]

        log(f"Selected category: {selected_category}", xbmc.LOGDEBUG)

        movies_file = os.path.join(MOVIES_PATH, f'{selected_category}.json')
        movies = []
        if xbmcvfs.exists(movies_file):
            with xbmcvfs.File(movies_file, 'r') as f:
                data = f.read()
                if isinstance(data, bytes):
                    data = data.decode('utf-8', errors='ignore')
                movies = json.loads(data) if data else []

        if any(m['title'].strip() == clean_title and m['stream_url'].replace('&mymovies=1', '').strip() == clean_stream_url for m in movies):
            log(f"Movie '{clean_title}' already exists in {selected_category}", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("MyMovies", f"Movie '{clean_title}' already in {selected_category}", xbmcgui.NOTIFICATION_WARNING, 1500)
            return

        movie = {
            'title': clean_title,
            'stream_url': clean_stream_url,
            'fav': fav_status  # fav-Status übernehmen
        }
        if thumb:
            movie['thumb'] = thumb
        movie['is_folder'] = clean_stream_url.lower().startswith('activatewindow')
        movies.append(movie)
        with xbmcvfs.File(movies_file, 'w') as f:
            f.write(bytearray(json.dumps(movies, indent=2, ensure_ascii=False), 'utf-8'))

        all_movies = read_movies()
        updated_movies = [m for m in all_movies if not (m.get('title').strip() == clean_title and m.get('stream_url').replace('&mymovies=1', '').strip() == clean_stream_url)]
        if len(updated_movies) < len(all_movies):
            write_movies(updated_movies)
            log(f"Removed movie '{clean_title}' from mymovies.json", xbmc.LOGINFO)

        for cat in cats:
            if cat == selected_category:
                continue
            cat_file = os.path.join(MOVIES_PATH, f'{cat}.json')
            if xbmcvfs.exists(cat_file):
                with xbmcvfs.File(cat_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    cat_movies = json.loads(data) if data else []
                updated_cat_movies = [m for m in cat_movies if not (m['title'].strip() == clean_title and m['stream_url'].replace('&mymovies=1', '').strip() == clean_stream_url)]
                if len(updated_cat_movies) < len(cat_movies):
                    with xbmcvfs.File(cat_file, 'w') as f:
                        f.write(bytearray(json.dumps(updated_cat_movies, indent=2, ensure_ascii=False), 'utf-8'))
                    log(f"Removed movie '{clean_title}' from category {cat}", xbmc.LOGINFO)

        log(f"Added movie '{clean_title}' to {selected_category} with fav={fav_status}", xbmc.LOGINFO)
        xbmcgui.Dialog().notification("MyMovies", f"Added '{clean_title}' to {selected_category}", xbmcgui.NOTIFICATION_INFO, 1200)
        CACHE[f'category_{selected_category}'] = None
        CACHE['movies'] = None
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in move_to_category: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to move movie", xbmcgui.NOTIFICATION_ERROR, 1500)

def toggle_fav(idx_str=None, title=None, thumb=None, stream_url=None):
    log(f"toggle_fav called with idx={idx_str}, title={title}, thumb={thumb}, stream_url={stream_url}", xbmc.LOGDEBUG)
    try:
        clean_title = urlparse.unquote(title).strip() if title else None
        clean_stream_url = urlparse.unquote(stream_url).replace('&mymovies=1', '').strip() if stream_url else None
        clean_thumb = thumb or ICON_PATH

        if not clean_title or not clean_stream_url:
            log("Invalid parameters for toggle_fav", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        # Entferne PlayMedia-Wrapper und dekodiere URL
        clean_stream_url = normalize_url(clean_stream_url)  # Verwende die neue Hilfsfunktion für Normalisierung

        movies = read_movies()
        fav_indices = []
        non_fav_index = None
        is_in_category = False

        # Prüfe, ob der Film in einer Kategorie existiert
        cats = read_categories()
        for cat in cats:
            cat_file = os.path.join(MOVIES_PATH, f'{cat}.json')
            if xbmcvfs.exists(cat_file):
                with xbmcvfs.File(cat_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    cat_movies = json.loads(data) if data else []
                for m in cat_movies:
                    json_stream_url = normalize_url(m['stream_url'])  # Normalisiere auch hier
                    if m['title'].strip() == clean_title and json_stream_url == clean_stream_url:
                        is_in_category = True
                        break
                if is_in_category:
                    break

        # Prüfe mymovies.json auf bestehende Einträge
        for i, m in enumerate(movies):
            json_stream_url = normalize_url(m['stream_url'])  # Normalisiere
            if m['title'].strip() == clean_title and json_stream_url == clean_stream_url:
                if m.get('fav', False):
                    fav_indices.append(i)
                elif not m.get('category'):
                    non_fav_index = i

        if fav_indices:
            # Film ist in Great Movies: Entferne alle fav=true Einträge
            movies = [m for i, m in enumerate(movies) if i not in fav_indices]
            action = "Removed"
            log(f"Removed {len(fav_indices)} '{clean_title}' entries from Great Movies", xbmc.LOGINFO)
        else:
            # Film ist nicht in Great Movies: Füge Kopie mit fav=true hinzu
            # Nur hinzufügen, wenn kein fav=true Eintrag existiert
            movies.append({
                'title': clean_title,
                'thumb': clean_thumb,
                'stream_url': clean_stream_url,
                'is_folder': clean_stream_url.lower().startswith('activatewindow'),
                'fav': True
            })
            action = "Added"
            log(f"Added copy of '{clean_title}' to mymovies.json with fav=True", xbmc.LOGINFO)

        # Stelle sicher, dass ein non-fav Eintrag existiert, falls nicht in Kategorie
        if not is_in_category and non_fav_index is None and not fav_indices:
            movies.append({
                'title': clean_title,
                'thumb': clean_thumb,
                'stream_url': clean_stream_url,
                'is_folder': clean_stream_url.lower().startswith('activatewindow'),
                'fav': False
            })
            log(f"Added non-fav copy of '{clean_title}' to mymovies.json", xbmc.LOGINFO)

        write_movies(movies)
        xbmcgui.Dialog().notification("MyMovies", f"{action}: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1200)
        CACHE['movies'] = None
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in toggle_fav: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to toggle Great Movies", xbmcgui.NOTIFICATION_ERROR, 1500)

def remove_movie(idx_str):
    log(f"remove_movie called with idx={idx_str}", xbmc.LOGDEBUG)
    try:
        idx = int(idx_str)
        movies = read_movies()
        if not (0 <= idx < len(movies)):
            log(f"Index {idx} out of bounds", xbmc.LOGERROR)
            return
        name = movies[idx]['title']
        movies.pop(idx)
        write_movies(movies)
        xbmcgui.Dialog().notification("MyMovies", f"Removed: {name}", xbmcgui.NOTIFICATION_INFO, 1200)
        xbmc.executebuiltin('Container.Refresh')
    except Exception as e:
        log(f"Error in remove_movie: {e}", xbmc.LOGERROR)

def search_in_lastship(title, media_type='movie'):
    try:
        clean_title = re.split(r'\[.*?\]|\(.*?\)', title)[0].strip()
        clean_title = re.sub(r'\b(Webrip|BluRay|HDRip|1080p|720p|4K)\b', '', clean_title, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()

        query = urlparse.quote(clean_title)

        if media_type == 'tv':
            url = f"plugin://plugin.video.lastship.reborn/?action=tvshows&page=1&query={query}"
        else:
            url = f"plugin://plugin.video.lastship.reborn/?action=movies&page=1&query={query}"

        xbmc.executebuiltin(f'ActivateWindow(10025,"{url}",return)')

        xbmcgui.Dialog().notification("MyMovies", f"Searching: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1500)

    except Exception as e:
        log(f"Error in search_in_lastship: {e}", xbmc.LOGERROR)

def add_movie_listitem(movie, index, category=None):
    log(f"add_movie_listitem called with title={movie.get('title', 'Unnamed')}, index={index}, category={category}, stream_url={movie.get('stream_url', '')}, is_folder={movie.get('is_folder', False)}, fav={movie.get('fav', False)}", xbmc.LOGDEBUG)
    try:
        name = movie.get('title', 'Unnamed')
        thumb = movie.get('thumb', ICON_PATH)
        url = movie.get('stream_url', '')
        if not url:
            log(f"No URL for {name}", xbmc.LOGWARNING)
            return

        is_folder = movie.get('is_folder', False)
        is_playable = not is_folder and url.lower().startswith('playmedia(')
        final_url = url

        # Prüfung für ActivateWindow
        if url.lower().startswith('activatewindow(10025,"plugin'):
            match = re.match(r'ActivateWindow\(10025,"(plugin://[^"]+)",return\)', url, re.IGNORECASE)
            if match:
                final_url = match.group(1)
                is_folder = True
                is_playable = False
                log(f"Extracted plugin URL for ActivateWindow: {final_url}", xbmc.LOGDEBUG)
            else:
                log(f"Failed to extract plugin URL from ActivateWindow: {url}", xbmc.LOGERROR)
                return
        # Prüfung für PlayMedia
        elif url.lower().startswith('playmedia('):
            # Robustere Regex für komplexe URLs
            match = re.match(r'PlayMedia\("?(.*?)"?\)$', url, re.IGNORECASE | re.DOTALL)
            if match:
                final_url = match.group(1).strip()
                is_playable = True
                is_folder = False
                log(f"Extracted plugin URL for PlayMedia: {final_url}", xbmc.LOGDEBUG)
            else:
                log(f"Failed to extract plugin URL from PlayMedia: {url}", xbmc.LOGERROR)
                return

        log(f"Creating list item: name={name}, is_folder={is_folder}, is_playable={is_playable}, final_url={final_url}", xbmc.LOGDEBUG)

        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': thumb, 'icon': thumb})
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(name)
        li.setProperty('IsPlayable', 'true' if is_playable else 'false')

        context_menu = []
        params_xship = {'action': 'search_in_xship', 'title': name}
        params_great = {'action': 'toggle_fav', 'title': name, 'thumb': thumb, 'stream_url': url}
        params_remove = {'action': 'remove_movie', 'idx': str(index)}
        params_mv = {'action': 'move_to_category', 'idx': str(index)}

        fav_label = "Remove from Great Movies" if is_in_great_movies(name, url) else "Add to Great Movies"
        context_menu.append((fav_label, f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_great)})'))
        context_menu.append(("Move to Category", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_mv)})'))
        context_menu.append(("Search in Lastship", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_xship)})'))
        if category:
            params_remove_json = {'action': 'remove_from_json', 'category': category, 'title': name, 'stream_url': url}
            context_menu.append(("Remove", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_remove_json)})'))
        else:
            context_menu.append(("Remove", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_remove)})'))
        context_menu.append(("---", "noop"))

        li.addContextMenuItems(context_menu, replaceItems=False)
        media_type = get_media_type_from_url(url)
        params = {
            'action': 'search_in_lastship',
            'title': name,
            'media_type': media_type
        }
        plugin_url = f"{sys.argv[0]}?{urlparse.urlencode(params)}"
        xbmcplugin.addDirectoryItem(HANDLE, plugin_url, li, isFolder=False)
    except Exception as e:
        log(f"Error in add_movie_listitem: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to add {name}", xbmcgui.NOTIFICATION_ERROR, 1500)


def add_movie_listitem_from_json(movie, category):
    if not category or category.lower() == 'none':
        log(f"Invalid category in add_movie_listitem_from_json: {category}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Invalid category: {category or 'None provided'}", xbmcgui.NOTIFICATION_ERROR, 1500)
        return
    log(f"add_movie_listitem_from_json called with title={movie.get('title', 'Unnamed')}, category={category}, stream_url={movie.get('stream_url', '')}, is_folder={movie.get('is_folder', False)}", xbmc.LOGDEBUG)
    try:
        label = movie.get('title', 'Unnamed')
        thumb = movie.get('thumb', ICON_PATH)
        url_to_play = movie.get('stream_url', '')
        if not url_to_play:
            log(f"No valid stream_url for {label}", xbmc.LOGWARNING)
            return

        is_folder = movie.get('is_folder', False)
        is_playable = not is_folder and url_to_play.lower().startswith('playmedia(')
        final_url = url_to_play

        if url_to_play.lower().startswith('activatewindow(10025,"plugin'):
            match = re.match(r'ActivateWindow\(10025,"(plugin://[^"]+)",return\)', url_to_play, re.IGNORECASE)
            if match:
                final_url = match.group(1)
                is_folder = True
                is_playable = False
                log(f"Extracted plugin URL for ActivateWindow: {final_url}", xbmc.LOGDEBUG)
            else:
                log(f"Failed to extract plugin URL from ActivateWindow: {url_to_play}", xbmc.LOGERROR)
                return
        elif url_to_play.lower().startswith('playmedia('):
            match = re.match(r'PlayMedia\("?(.*?)"?\)$', url_to_play, re.IGNORECASE | re.DOTALL)
            if match:
                final_url = match.group(1).strip()
                is_playable = True
                is_folder = False
                log(f"Extracted plugin URL for PlayMedia: {final_url}", xbmc.LOGDEBUG)
            else:
                log(f"Failed to extract plugin URL from PlayMedia: {url_to_play}", xbmc.LOGERROR)
                return

        log(f"Creating JSON list item: label={label}, is_folder={is_folder}, is_playable={is_playable}, final_url={final_url}", xbmc.LOGDEBUG)

        li = xbmcgui.ListItem(label=label)
        li.setArt({'thumb': thumb, 'icon': thumb})
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(label)
        li.setProperty('IsPlayable', 'true' if is_playable else 'false')

        params_xship = {'action': 'search_in_xship', 'title': label}
        params_remove_full = {'action': 'remove_from_json', 'category': category, 'title': label, 'stream_url': url_to_play}
        params_great = {'action': 'toggle_fav', 'title': label, 'thumb': thumb, 'stream_url': url_to_play}
        params_mv = {'action': 'move_to_category', 'title': label, 'thumb': thumb, 'stream_url': url_to_play}

        fav_label = "Remove from Great Movies" if is_in_great_movies(label, url_to_play) else "Add to Great Movies"
        context_menu = [
            (fav_label, f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_great)})'),
            ("Move to Category", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_mv)})'),
            ("Search in Lastship", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_xship)})'),
            ("Remove", f'RunPlugin({sys.argv[0]}?{urlparse.urlencode(params_remove_full)})'),
            ("---", "noop"),
        ]
        li.addContextMenuItems(context_menu, replaceItems=False)

        media_type = get_media_type_from_url(url_to_play)
        params = {
            'action': 'search_in_lastship',
            'title': label,
            'media_type': media_type
        }
        plugin_url = f"{sys.argv[0]}?{urlparse.urlencode(params)}"
        xbmcplugin.addDirectoryItem(HANDLE, plugin_url, li, isFolder=False)
        
    except Exception as e:
        log(f"Error in add_movie_listitem_from_json: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to add movie item: {label}", xbmcgui.NOTIFICATION_ERROR, 1500)

def list_all():
    log("list_all called", xbmc.LOGDEBUG)
    try:
        url_search = f"{sys.argv[0]}?{urlparse.urlencode({'action':'search_movies'})}"
        li_search = xbmcgui.ListItem(label="Search Movies")
        li_search.setArt({'icon': ICON_SEARCH, 'thumb': ICON_SEARCH})
        xbmcplugin.addDirectoryItem(HANDLE, url_search, li_search, isFolder=True)

        movies = read_movies()
        seen = set()
        filtered = []

        # Zuerst Filme mit fav: false (Hauptmenü/Kategorien) indizieren
        for i, m in enumerate(movies):
            key = normalize_url(m['stream_url'])
            if not key or key in seen or m.get('fav', False):
                continue
            seen.add(key)
            filtered.append((i, m, None))  # None für category

        # Dann Kategorien prüfen
        cats = read_categories()
        for cat in cats:
            if not cat or cat.lower() == 'none':
                log(f"Skipping invalid category: {cat}", xbmc.LOGWARNING)
                continue
            movies_file = os.path.join(MOVIES_PATH, f'{cat}.json')
            if xbmcvfs.exists(movies_file):
                with xbmcvfs.File(movies_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    cat_movies = json.loads(data) if data else []
                for movie in cat_movies:
                    key = normalize_url(movie['stream_url'])
                    if key and key not in seen:
                        seen.add(key)
                        filtered.append((None, movie, cat))  # cat explizit übergeben

        # Schließlich Great Movies (fav: true) prüfen
        for i, m in enumerate(movies):
            if m.get('fav', False):
                key = normalize_url(m['stream_url'])
                if key and key not in seen:
                    seen.add(key)
                    filtered.append((i, m, None))

        sorted_items = sorted(filtered, key=lambda x: x[1]['title'].lower())
        for idx, movie, cat in sorted_items:
            if idx is not None:
                add_movie_listitem(movie, idx, category=cat)
            else:
                add_movie_listitem_from_json(movie, category=cat)

        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in list_all: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to list all movies", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def search_movies():
    log("search_movies called", xbmc.LOGDEBUG)
    try:
        search_term = xbmcgui.Dialog().input("Enter search term")
        if not search_term:
            log("No search term entered", xbmc.LOGDEBUG)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

        search_term = search_term.lower()
        xbmcplugin.setPluginCategory(HANDLE, "Search Results")
        xbmcplugin.setContent(HANDLE, 'movies')

        movies = read_movies()
        seen = set()
        for i, m in enumerate(movies):
            key = m['stream_url']
            if not key or key in seen:
                continue
            seen.add(key)
            if search_term in m.get('title', '').lower():
                add_movie_listitem(m, i, category=m.get('category'))

        cats = read_categories()
        for cat in cats:
            movies_file = os.path.join(MOVIES_PATH, f'{cat}.json')
            if xbmcvfs.exists(movies_file):
                with xbmcvfs.File(movies_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    cat_movies = json.loads(data) if data else []
                for movie in cat_movies:
                    if search_term in movie.get('title', '').lower() and movie['stream_url'] not in seen:
                        seen.add(movie['stream_url'])
                        add_movie_listitem_from_json(movie, cat)

        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in search_movies: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Search failed", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def list_favs():
    log("list_favs called", xbmc.LOGDEBUG)
    try:
        CACHE['movies'] = None
        movies = read_movies()
        items = [(i, m) for i, m in enumerate(movies) if m.get('fav')]
        log(f"Found {len(items)} movies with fav=True in mymovies.json: {[m['title'] for i, m in items]}", xbmc.LOGDEBUG)
        for idx, movie in sorted(items, key=lambda x: x[1]['title'].lower()):
            log(f"Listing fav movie: {movie.get('title', 'Unnamed')}, stream_url={movie.get('stream_url')}, fav={movie.get('fav')}", xbmc.LOGDEBUG)
            add_movie_listitem(movie, idx, category=None)
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    except Exception as e:
        log(f"Error in list_favs: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Failed to list favourites", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

def remove_from_json(category=None, title=None, stream_url=None):
    log(f"remove_from_json called with category={category!r}, title={title!r}, stream_url={stream_url!r}", xbmc.LOGDEBUG)
    try:
        if not category or not title or not stream_url:
            log("Invalid parameters for remove_from_json", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid selection", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        clean_title = urlparse.unquote(title).strip()
        clean_stream_url = normalize_url(stream_url)  # Normalisiere mit neuer Funktion

        cat_file = os.path.join(MOVIES_PATH, f"{category}.json")
        if not xbmcvfs.exists(cat_file):
            log(f"Category file {cat_file} does not exist", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", f"Category {category} not found", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        with xbmcvfs.File(cat_file, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
            movies = json.loads(data) if data else []

        log(f"Current movies in {category}.json: {[m['title'] for m in movies]}", xbmc.LOGDEBUG)

        original_count = len(movies)
        updated_movies = []
        found = False
        for m in movies:
            json_stream_url = normalize_url(m['stream_url'])  # Normalisiere auch hier
            log(f"Comparing: title='{m['title'].strip()}' vs '{clean_title}', stream_url='{json_stream_url}' vs '{clean_stream_url}'", xbmc.LOGDEBUG)
            if m['title'].strip() == clean_title and json_stream_url == clean_stream_url:
                found = True
                log(f"Match found for '{clean_title}' in {category}.json", xbmc.LOGDEBUG)
                continue
            updated_movies.append(m)

        if found:
            with xbmcvfs.File(cat_file, 'w') as f:
                f.write(bytearray(json.dumps(updated_movies, indent=2, ensure_ascii=False), 'utf-8'))
            log(f"Removed '{clean_title}' from {category}.json", xbmc.LOGINFO)
            xbmcgui.Dialog().notification("MyMovies", f"Removed: {clean_title}", xbmcgui.NOTIFICATION_INFO, 1200)
            CACHE[f'category_{category}'] = None
            CACHE['movies'] = None
            xbmc.executebuiltin('Container.Refresh')
        else:
            log(f"Movie '{clean_title}' with stream_url '{clean_stream_url}' not found in {category}.json", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("MyMovies", f"Movie not found in {category}", xbmcgui.NOTIFICATION_ERROR, 1500)

    except Exception as e:
        log(f"Error in remove_from_json: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Failed to remove movie: {clean_title}", xbmcgui.NOTIFICATION_ERROR, 1500)

def read_category_movies(category):
    try:
        cat_file = os.path.join(MOVIES_PATH, f"{category}.json")
        if not xbmcvfs.exists(cat_file):
            return []
        with xbmcvfs.File(cat_file, 'r') as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
        movies = json.loads(data) if data else []
        return movies if isinstance(movies, list) else []
    except Exception as e:
        log(f"Error reading category file for '{category}': {e}", xbmc.LOGERROR)
        return []

def write_category_movies(category, movies):
    try:
        cat_file = os.path.join(MOVIES_PATH, f"{category}.json")
        with xbmcvfs.File(cat_file, 'w') as f:
            f.write(bytearray(json.dumps(movies or [], indent=2, ensure_ascii=False), 'utf-8'))
    except Exception as e:
        log(f"Error writing category file for '{category}': {e}", xbmc.LOGERROR)

def build_backup_data():
    ensure_files()
    categories = read_categories()
    category_movies = {}

    for cat in categories:
        if not cat or cat.lower() == 'none':
            continue
        category_movies[cat] = read_category_movies(cat)

    return {
        "version": 2,
        "movies": read_movies(),
        "categories": categories,
        "category_movies": category_movies
    }
    
def export_backup():
    log("export_backup called", xbmc.LOGDEBUG)
    try:
        dialog = xbmcgui.Dialog()
        target_path = dialog.browse(3, "Select Backup Folder", "files", "", False, False, defaultt=BACKUP_PATH)
        if not target_path:
            xbmcgui.Dialog().notification("MyMovies", "Export canceled", xbmcgui.NOTIFICATION_INFO, 1500)
            return

        target_file = os.path.join(target_path, 'mymovies_backup.json')
        backup_data = build_backup_data()

        with xbmcvfs.File(target_file, 'w') as f:
            f.write(bytearray(json.dumps(backup_data, indent=2, ensure_ascii=False), 'utf-8'))

        xbmcgui.Dialog().notification("MyMovies", f"Saved:\n{target_file}", xbmcgui.NOTIFICATION_INFO, 3000)
    except Exception as e:
        log(f"Export error: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", "Export failed", xbmcgui.NOTIFICATION_ERROR, 1500)

def import_backup():
    log("import_backup called", xbmc.LOGDEBUG)
    try:
        dialog = xbmcgui.Dialog()
        source_path = dialog.browse(1, "Select Backup File", "files", ".json", False, False, defaultt=BACKUP_PATH)
        if not source_path:
            xbmcgui.Dialog().notification("MyMovies", "Import canceled", xbmcgui.NOTIFICATION_INFO, 1500)
            return

        log(f"Reading backup file: {source_path}", xbmc.LOGDEBUG)
        with xbmcvfs.File(source_path, 'r') as f:
            raw_data = f.read()
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8', errors='ignore')
        if not raw_data:
            log("Backup file is empty", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Backup file is empty", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            log(f"Invalid JSON format in backup file: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid format in backup file", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        # Altes Format
        if isinstance(data, list):
            movies = read_movies()
            cats = read_categories()
            added = 0
            skipped = 0

            for item in data:
                text = (item.get('stream_url') or '').strip()
                if not text:
                    skipped += 1
                    continue

                is_fav = item.get('fav', False)
                exists = False
                if not is_fav:
                    for movie in movies:
                        if movie['stream_url'] == text and movie['title'] == item.get('title') and not movie.get('fav') and not movie.get('category'):
                            exists = True
                            skipped += 1
                            break
                if exists and not is_fav:
                    continue

                new_movie = {
                    'title': item.get('title', 'Unnamed'),
                    'thumb': item.get('thumb', ICON_PATH),
                    'stream_url': text,
                    'is_folder': text.lower().startswith('activatewindow'),
                    'category': item.get('category', ''),
                    'fav': item.get('fav', False)
                }
                movies.append(new_movie)
                added += 1

                cat = item.get('category')
                if cat and cat not in cats:
                    cats.append(cat)

            write_movies(movies)
            write_categories(cats)

            if added == 0:
                message = "No entries imported"
                if skipped > 0:
                    message += f": {skipped} entries skipped"
                xbmcgui.Dialog().notification("MyMovies", message, xbmcgui.NOTIFICATION_INFO, 2500)
            else:
                xbmcgui.Dialog().notification("MyMovies", f"{added} entries imported", xbmcgui.NOTIFICATION_INFO, 2500)

            xbmc.executebuiltin('Container.Refresh')
            return

        # Neues Format
        if not isinstance(data, dict):
            log(f"Backup data has invalid type: {type(data)}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("MyMovies", "Invalid backup structure", xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        movies = data.get('movies', [])
        categories = data.get('categories', [])
        category_movies = data.get('category_movies', {})

        if not isinstance(movies, list):
            movies = []
        if not isinstance(categories, list):
            categories = []
        if not isinstance(category_movies, dict):
            category_movies = {}

        write_movies(movies)
        write_categories(categories)

        if not xbmcvfs.exists(MOVIES_PATH):
            xbmcvfs.mkdirs(MOVIES_PATH)

        for cat in categories:
            if not cat or cat.lower() == 'none':
                continue
            cat_entries = category_movies.get(cat, [])
            if not isinstance(cat_entries, list):
                cat_entries = []
            write_category_movies(cat, cat_entries)

        CACHE['movies'] = None
        CACHE['cats'] = None

        total_cat_items = sum(len(v) for v in category_movies.values() if isinstance(v, list))
        xbmcgui.Dialog().notification(
            "MyMovies",
            f"Imported: {len(movies)} main + {total_cat_items} category entries",
            xbmcgui.NOTIFICATION_INFO,
            3000
        )
        xbmc.executebuiltin('Container.Refresh')

    except Exception as e:
        log(f"Import error: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Import failed: {str(e)}", xbmcgui.NOTIFICATION_ERROR, 1500)

def router():
    log(f"router called with args={sys.argv}, handle={HANDLE}", xbmc.LOGDEBUG)
    try:
        if CACHE['movies'] is None:
            CACHE['movies'] = read_movies()
        if CACHE['cats'] is None:
            CACHE['cats'] = read_categories()
        query = sys.argv[2][1:] if len(sys.argv) > 2 and sys.argv[2].startswith('?') else ''
        log(f"Raw query: {query}", xbmc.LOGDEBUG)
        params = dict(urlparse.parse_qsl(query))
        log(f"Router params: {params}", xbmc.LOGDEBUG)
        action = params.get('action')
        cat = params.get('cat', params.get('category', ''))
        idx = params.get('idx', params.get('index'))
        title = params.get('title')
        thumb = params.get('thumb')
        stream_url = params.get('stream_url')

        log(f"Parsed params: action={action!r}, cat={cat!r}, idx={idx!r}, title={title!r}, stream_url={stream_url!r}", xbmc.LOGDEBUG)

        if action == 'import_from_fav':
            list_import_candidates()
        elif action == 'copy_by_index':
            copy_by_index(idx)
        elif action == 'add_category':
            add_category()
        elif action == 'delete_category':
            delete_category(cat)
        elif action == 'rename_category':
            rename_category(cat)
        elif action == 'show_category':
            CACHE[f'category_{cat}'] = None  # Cache für Kategorie zurücksetzen
            list_category(cat)
        elif action == 'show_all':
            list_all()
        elif action == 'show_favs':
            CACHE['movies'] = None  # Cache für Great Movies zurücksetzen
            list_favs()
        elif action == 'move_to_category':
            move_to_category(idx, title, thumb, stream_url)
        elif action == 'remove_movie':
            remove_movie(idx)
        elif action == 'toggle_fav':
            toggle_fav(idx, title, thumb, stream_url)
        elif action == 'search_in_lastship':
            search_in_lastship(title, params.get('media_type', 'movie'))
        elif action == 'search_movies':
            search_movies()
        elif action == 'show_categories_menu':
            list_categories_menu()
        elif action == 'show_backup_menu':
            list_backup_menu()
        elif action == 'export_backup':
            export_backup()
        elif action == 'import_backup':
            import_backup()
        elif action == 'toggle_auto_backup':
            toggle_auto_backup()
        elif action == 'import_from_context':
            import_from_context(title, thumb, stream_url, cat)
        elif action == 'remove_from_json':
            remove_from_json(cat, title, stream_url)
        else:
            home()
            auto_backup()
    except Exception as e:
        log(f"Unexpected error in router: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("MyMovies", f"Router error: {str(e)}", xbmcgui.NOTIFICATION_ERROR, 1500)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)

if __name__ == '__main__':
    router()
