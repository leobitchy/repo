# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import urllib.parse as urlparse
import re

ADDON = xbmcaddon.Addon('plugin.video.bb_global_lastship_search')
ADDON_ID = ADDON.getAddonInfo('id')

def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)

def clean_search_title(title):
    clean_title = re.split(r'\[.*?\]|\(.*?\)', title)[0].strip()
    clean_title = re.sub(
        r'\b(Webrip|WEBRIP|WebRip|BluRay|BRRip|HDRip|DVDRip|HDTV|1080p|720p|4K)\b',
        '',
        clean_title,
        flags=re.IGNORECASE
    ).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    clean_title = clean_title.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
    clean_title = re.sub(r'[^\w\s-]', '', clean_title)
    return clean_title.strip()

def search_tvshow(title):
    try:
        if not title:
            log("No title provided for TV show search", xbmc.LOGDEBUG)
            return

        clean_title = clean_search_title(title)
        log(f"Cleaned TV show title: {clean_title}", xbmc.LOGDEBUG)

        query = urlparse.quote(clean_title)
        lastship_url = f"plugin://plugin.video.lastship.reborn/?action=tvshows&page=1&query={query}"

        xbmc.executebuiltin(f'ActivateWindow(Videos,{lastship_url})')

        xbmcgui.Dialog().notification(
            "Serie suchen",
            f"Suche gestartet für '{clean_title}'",
            xbmcgui.NOTIFICATION_INFO,
            2000
        )
        log(f"Lastship TV show search executed: {lastship_url}", xbmc.LOGDEBUG)

    except Exception as e:
        log(f"Error starting TV show search: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Serie suchen",
            "Suche fehlgeschlagen",
            xbmcgui.NOTIFICATION_ERROR,
            1500
        )

def main():
    try:
        title = xbmc.getInfoLabel('ListItem.Title') or xbmc.getInfoLabel('ListItem.Label')
        if not title:
            log("No title found for TV show search", xbmc.LOGDEBUG)
            return

        search_tvshow(title)

    except Exception as e:
        log(f"Error in TV show context main: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Serie suchen",
            f"Fehler: {str(e)}",
            xbmcgui.NOTIFICATION_ERROR,
            1500
        )

if __name__ == '__main__':
    main()