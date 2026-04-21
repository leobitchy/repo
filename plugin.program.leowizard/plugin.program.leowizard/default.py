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


def wait_with_progress(progress, start_percent, end_percent, heading, message, seconds):
    """
    Wartet sichtbar mit Fortschrittsanimation, damit der User nicht denkt Kodi hängt.
    """
    steps = max(1, int(seconds * 10))  # 10 Updates pro Sekunde
    for i in range(steps + 1):
        percent = start_percent + int((end_percent - start_percent) * i / steps)
        remaining = max(0, seconds - (i / 10.0))
        progress.update(percent, heading, f"{message} ({remaining:.1f}s)")
        if progress.iscanceled():
            raise Exception("Vorgang abgebrochen")
        xbmc.sleep(100)


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
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        progress.update(
                            file_percent,
                            "Lade Build herunter...",
                            f"{mb_done:.1f} / {mb_total:.1f} MB"
                        )
                    else:
                        progress.update(50, "Lade Build herunter...", "Dateigröße unbekannt...")

                    if progress.iscanceled():
                        raise Exception("Download abgebrochen")

        log(f"Build ZIP heruntergeladen: {dest_path}")
        return True

    except Exception as e:
        log(f"Download Fehler: {e}", xbmc.LOGERROR)
        return False


def extract_build_zip(zip_path, progress):
    progress.update(5, "Entpacke Build...", "Dateien werden kopiert...")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        members = zip_ref.namelist()
        total = len(members) or 1
        processed = 0

        for member in members:
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

            processed += 1
            percent = 5 + int(processed * 25 / total)  # 5 -> 30
            progress.update(percent, "Entpacke Build...", f"{processed}/{total} Dateien verarbeitet")

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
            log(f"Fehler beim Löschen von {addon_data_dir}: {e}", xbmc.LOGERROR)


def purge_blocked_addons():
    for addon_id in BLOCKED_ADDONS:
        if addon_exists(addon_id):
            disable_addon(addon_id)
            xbmc.sleep(300)
            remove_addon_files(addon_id)


def enable_all_addons(progress=None, start_percent=55, end_percent=75):
    result = jsonrpc("Addons.GetAddons", {"enabled": False})
    addons = result.get("result", {}).get("addons", [])
    total = len(addons) or 1

    for i, addon in enumerate(addons, start=1):
        addonid = addon.get("addonid")
        if addonid:
            jsonrpc("Addons.SetAddonEnabled", {
                "addonid": addonid,
                "enabled": True
            })

        if progress:
            percent = start_percent + int(i * (end_percent - start_percent) / total)
            progress.update(percent, "Aktiviere Addons...", f"{i}/{total} Addons verarbeitet")

            if progress.iscanceled():
                raise Exception("Aktivierung abgebrochen")

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
    download_progress = xbmcgui.DialogProgress()
    install_progress = None

    try:
        # PHASE 1: Download
        download_progress.create("LeoWizard", "Lade Build herunter...")
        if not download_file(BUILD_ZIP_URL, DOWNLOADED_ZIP, download_progress):
            download_progress.close()
            xbmcgui.Dialog().ok("Fehler", "Download fehlgeschlagen.")
            return

        download_progress.update(100, "Download abgeschlossen", "Build wurde heruntergeladen")
        xbmc.sleep(500)
        download_progress.close()

        # PHASE 2: Installation / Vorbereitung Neustart
        install_progress = xbmcgui.DialogProgress()
        install_progress.create("LeoWizard", "Installiere Build...", "Bitte nichts anklicken.")

        install_progress.update(0, "Prüfe unerwünschte Addons...", "Bereite Installation vor...")
        purge_blocked_addons()

        extract_build_zip(DOWNLOADED_ZIP, install_progress)

        install_progress.update(35, "Initialisiere Addons...", "Setze Restore-Status...")
        mark_restore_pending()

        install_progress.update(40, "Aktualisiere lokale Addons...", "Kodi verarbeitet neue Dateien...")
        xbmc.executebuiltin("UpdateLocalAddons")
        wait_with_progress(
            install_progress, 40, 55,
            "Aktualisiere lokale Addons...",
            "Bitte warten",
            5
        )

        enable_all_addons(install_progress, 55, 75)

        install_progress.update(80, "Deaktiviere Konflikt-Addons...", "Bereinige inkompatible Addons...")
        disable_blocked_addons_if_present()
        wait_with_progress(
            install_progress, 80, 85,
            "Deaktiviere Konflikt-Addons...",
            "Übernehme Änderungen",
            1.5
        )

        install_progress.update(88, "Übernehme Quellen...", "sources.xml wird kopiert...")
        copy_sources_xml()

        install_progress.update(93, "Räume auf...", "Temporäre Dateien werden gelöscht...")
        cleanup()
        wait_with_progress(
            install_progress, 93, 97,
            "Räume auf...",
            "Temporäre Dateien werden entfernt",
            1.5
        )

        wait_with_progress(
            install_progress, 97, 100,
            "Vorbereitung Neustart...",
            "Kodi wird gleich neu gestartet",
            3
        )

        install_progress.close()

        xbmcgui.Dialog().ok(
            "LeoWizard",
            "Installation abgeschlossen.\n\nKodi wird jetzt neu gestartet.\nBitte die App danach ca. 10 Sekunden nicht öffnen."
        )

        xbmc.sleep(1000)
        xbmc.executebuiltin("RestartApp")

    except Exception as e:
        try:
            download_progress.close()
        except Exception:
            pass
        try:
            if install_progress:
                install_progress.close()
        except Exception:
            pass

        log(f"Wizard Fehler: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Fehler", f"Installation fehlgeschlagen:\n{e}")


if __name__ == "__main__":
    run_wizard()