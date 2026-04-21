import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import os
import zipfile
import shutil
import json
import urllib.request

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))

BUILD_ZIP_URL = "https://github.com/leobitchy/leosystems-repo/releases/download/leoaddons/addons.zip"

TEMP_DIR = xbmcvfs.translatePath("special://temp/plugin.program.leowizard")
DOWNLOADED_ZIP = os.path.join(TEMP_DIR, "addons.zip")

SRC_SOURCES = os.path.join(ADDON_PATH, "resources", "sources.xml")

KODI_HOME = xbmcvfs.translatePath("special://home")
KODI_USERDATA = xbmcvfs.translatePath("special://home/userdata")
DEST_SOURCES = os.path.join(KODI_USERDATA, "sources.xml")

BLOCKED_ADDONS = [
    "plugin.video.xship",
    "plugin.video.global.xship_search"
]

SETTING_RESTORE_PENDING = "restore_pending"


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)


def jsonrpc(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        payload["params"] = params
    return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def download_file(url, dest_path, progress):
    ensure_dir(os.path.dirname(dest_path))

    try:
        with urllib.request.urlopen(url) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break

                    out_file.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        file_percent = int(downloaded * 100 / total)
                        overall_percent = 15 + int(file_percent * 25 / 100)  # 15-40%
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        progress.update(
                            overall_percent,
                            "Lade Build herunter...",
                            f"{mb_done:.1f} / {mb_total:.1f} MB"
                        )
                    else:
                        progress.update(20, "Lade Build herunter...")

                    if progress.iscanceled():
                        raise Exception("Download abgebrochen")

        log(f"Build ZIP heruntergeladen: {dest_path}")
        return True

    except Exception as e:
        log(f"Download Fehler: {e}", xbmc.LOGERROR)
        return False


def extract_build_zip(zip_path, progress):
    progress.update(45, "Entpacke Build...")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        members = zip_ref.namelist()
        total = len(members) or 1

        for i, member in enumerate(members, start=1):
            if member.startswith("addons/"):
                rel = member.replace("addons/", "", 1)
                target = os.path.join(KODI_HOME, "addons", rel)

            elif member.startswith("addon_data/") or member.startswith("addondata/"):
                rel = member.replace("addon_data/", "", 1).replace("addondata/", "", 1)
                target = os.path.join(KODI_USERDATA, "addon_data", rel)

            else:
                continue

            if member.endswith("/"):
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zip_ref.open(member) as s, open(target, "wb") as t:
                    shutil.copyfileobj(s, t)

            percent = 45 + int(i * 15 / total)  # 45-60%
            progress.update(percent, "Entpacke Build...")

            if progress.iscanceled():
                raise Exception("Entpacken abgebrochen")


def addon_exists(addon_id):
    try:
        result = jsonrpc("Addons.GetAddons", {"properties": ["name", "enabled"]})
        for addon in result.get("result", {}).get("addons", []):
            if addon.get("addonid") == addon_id:
                return True
    except Exception as e:
        log(f"Fehler bei Addon-Prüfung für {addon_id}: {e}", xbmc.LOGERROR)
    return False


def disable_addon(addon_id):
    try:
        result = jsonrpc("Addons.SetAddonEnabled", {
            "addonid": addon_id,
            "enabled": False
        })
        if "error" in result:
            log(f"Addon konnte nicht deaktiviert werden: {addon_id} - {result['error']}", xbmc.LOGERROR)
            return False
        log(f"Addon deaktiviert: {addon_id}")
        return True
    except Exception as e:
        log(f"Fehler beim Deaktivieren von {addon_id}: {e}", xbmc.LOGERROR)
        return False


def disable_blocked_addons_if_present():
    for addon_id in BLOCKED_ADDONS:
        if addon_exists(addon_id):
            disable_addon(addon_id)


def remove_addon_files(addon_id):
    addon_dir = xbmcvfs.translatePath(os.path.join("special://home", "addons", addon_id))
    addon_data_dir = xbmcvfs.translatePath(os.path.join("special://profile", "addon_data", addon_id))

    try:
        if os.path.exists(addon_dir):
            shutil.rmtree(addon_dir, ignore_errors=True)
            log(f"Addon-Ordner gelöscht: {addon_dir}")
    except Exception as e:
        log(f"Fehler beim Löschen von {addon_dir}: {e}", xbmc.LOGERROR)

    try:
        if os.path.exists(addon_data_dir):
            shutil.rmtree(addon_data_dir, ignore_errors=True)
            log(f"Addon-Daten gelöscht: {addon_data_dir}")
    except Exception as e:
        log(f"Fehler beim Löschen von {addon_data_dir}: {e}", xbmc.LOGERROR)


def purge_blocked_addons():
    for addon_id in BLOCKED_ADDONS:
        if addon_exists(addon_id):
            disable_addon(addon_id)
            xbmc.sleep(300)
            remove_addon_files(addon_id)


def enable_all_addons():
    result = jsonrpc("Addons.GetAddons", {"enabled": False})
    for addon in result.get("result", {}).get("addons", []):
        addonid = addon.get("addonid")
        if addonid:
            jsonrpc("Addons.SetAddonEnabled", {
                "addonid": addonid,
                "enabled": True
            })
    log("Alle Addons aktiviert.")


def copy_sources_xml():
    try:
        if os.path.exists(SRC_SOURCES):
            shutil.copyfile(SRC_SOURCES, DEST_SOURCES)
            log("sources.xml kopiert.")
    except Exception as e:
        log(f"Fehler beim Kopieren von sources.xml: {e}", xbmc.LOGERROR)


def cleanup():
    try:
        if os.path.exists(DOWNLOADED_ZIP):
            os.remove(DOWNLOADED_ZIP)
    except Exception as e:
        log(f"ZIP löschen fehlgeschlagen: {e}", xbmc.LOGERROR)

    try:
        packages_path = xbmcvfs.translatePath(os.path.join(KODI_HOME, "addons", "packages"))
        if os.path.exists(packages_path):
            shutil.rmtree(packages_path, ignore_errors=True)
    except Exception as e:
        log(f"Fehler beim Löschen von packages: {e}", xbmc.LOGERROR)


def mark_restore_pending():
    ADDON.setSettingBool(SETTING_RESTORE_PENDING, True)
    log("restore_pending gesetzt.")


def run_wizard():
    progress = xbmcgui.DialogProgress()
    progress.create("LeoWizard", "Installation startet...")

    try:
        progress.update(5, "Prüfe unerwünschte Addons...")
        purge_blocked_addons()

        progress.update(15, "Bereite Download vor...")
        if not download_file(BUILD_ZIP_URL, DOWNLOADED_ZIP, progress):
            progress.close()
            xbmcgui.Dialog().ok("Fehler", "Download fehlgeschlagen.")
            return

        extract_build_zip(DOWNLOADED_ZIP, progress)

        progress.update(65, "Initialisiere Addons...")
        mark_restore_pending()
        xbmc.executebuiltin("UpdateLocalAddons")
        xbmc.sleep(5000)

        progress.update(75, "Aktiviere Addons...")
        enable_all_addons()
        xbmc.sleep(2000)

        progress.update(85, "Deaktiviere Konflikt-Addons...")
        disable_blocked_addons_if_present()
        xbmc.sleep(1000)

        progress.update(92, "Übernehme Quellen...")
        copy_sources_xml()

        progress.update(97, "Räume auf...")
        cleanup()

        progress.update(100, "Fertig!")
        xbmc.sleep(1000)
        progress.close()

        xbmcgui.Dialog().ok(
            "LeoWizard",
            "Installation abgeschlossen.\n\nKodi wird jetzt neu gestartet.\nBitte die App danach ca. 10 Sekunden nicht öffnen."
        )

        xbmc.sleep(1000)
        xbmc.executebuiltin("RestartApp")

    except Exception as e:
        try:
            progress.close()
        except Exception:
            pass
        log(f"Wizard Fehler: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Fehler", f"Installation fehlgeschlagen:\n{e}")


if __name__ == "__main__":
    run_wizard()