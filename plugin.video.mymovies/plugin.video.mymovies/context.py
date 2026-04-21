# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import urllib.parse as urlparse

ADDON = xbmcaddon.Addon('plugin.video.mymovies')
ADDON_ID = ADDON.getAddonInfo('id')

def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)

def main():
    try:
        title = xbmc.getInfoLabel('ListItem.Title') or xbmc.getInfoLabel('ListItem.Label') or ''
        thumb = (xbmc.getInfoLabel('ListItem.Art(thumb)') or
                 xbmc.getInfoLabel('ListItem.Art(poster)') or
                 xbmc.getInfoLabel('ListItem.Thumb') or
                 xbmc.getInfoLabel('ListItem.Icon') or '')
        stream_url = (xbmc.getInfoLabel('ListItem.FileNameAndPath') or
                      xbmc.getInfoLabel('ListItem.Path') or '')

        log(f"Context import values - Title: '{title}', Thumb: '{thumb}', Stream-URL: '{stream_url}'", xbmc.LOGDEBUG)

        if not title or not stream_url:
            log(f"Context import failed: Missing or invalid data - Title: '{title}', Stream-URL: '{stream_url}'", xbmc.LOGERROR)
            xbmcgui.Dialog().notification('MyMovies', f'Missing data: Title={title}, Stream-URL={stream_url}', xbmcgui.NOTIFICATION_ERROR, 1500)
            return

        cat_file = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.mymovies/categories.json')
        categories = ['Horror', 'Comedy', 'Drama', 'Anime', 'Series']
        if xbmcvfs.exists(cat_file):
            try:
                with xbmcvfs.File(cat_file, 'r') as f:
                    data = f.read()
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')
                    if data:
                        categories = json.loads(data)
                        log(f"Loaded categories: {categories}", xbmc.LOGDEBUG)
            except Exception as e:
                log(f"Error loading categories: {e}", xbmc.LOGERROR)

        # Alphabetische Sortierung der Kategorien
        categories = sorted(categories, key=str.lower)
        categories.append('No category')
        categories.append('Create new category')
        dialog = xbmcgui.Dialog()
        selected = dialog.select('Choose category', categories)

        if selected == -1:
            log("Category selection canceled", xbmc.LOGDEBUG)
            return
        if selected == len(categories) - 2:  # "No category"
            category = ''
            log("No category selected", xbmc.LOGDEBUG)
        elif selected == len(categories) - 1:  # "Create new category"
            new_category = dialog.input('New category')
            if not new_category:
                log("No new category entered", xbmc.LOGDEBUG)
                xbmcgui.Dialog().notification('MyMovies', 'No category name entered', xbmcgui.NOTIFICATION_INFO, 1500)
                return
            if new_category in categories[:-2]:
                xbmcgui.Dialog().notification('MyMovies', f'Category "{new_category}" already exists', xbmcgui.NOTIFICATION_INFO, 1500)
                return
            categories = categories[:-2]
            categories.append(new_category)
            with xbmcvfs.File(cat_file, 'w') as f:
                f.write(bytearray(json.dumps(categories, ensure_ascii=False), 'utf-8'))
            category = new_category
            log(f"New category created: {new_category}", xbmc.LOGDEBUG)
        else:
            category = categories[selected]

        log(f"Selected category: {category}", xbmc.LOGDEBUG)

        params = {
            'action': 'import_from_context',
            'title': title,
            'thumb': thumb,
            'stream_url': stream_url,
            'cat': category
        }
        plugin_url = f"plugin://plugin.video.mymovies/?{urlparse.urlencode(params, quote_via=urlparse.quote)}"
        log(f"Calling plugin URL: {plugin_url}", xbmc.LOGDEBUG)
        xbmc.executebuiltin(f'RunPlugin({plugin_url})')
    except Exception as e:
        log(f"Error in context menu: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification('MyMovies', f'Import error: {str(e)}', xbmcgui.NOTIFICATION_ERROR, 1500)

if __name__ == '__main__':
    main()
