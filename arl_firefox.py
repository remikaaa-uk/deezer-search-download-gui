#!/home/user/python-envs/tools/bin/python
"""
Skrypt do odczytu cookie 'arl' z Deezer w Firefox
Firefox jest dużo prostszy - cookies są w SQLite bez szyfrowania!
Automatycznie ustawia ARL w config.toml StreamRip.

~/python-envs/tools/bin/pip install brakujacy_modul
Użycie: python arl_firefox.py
"""
import sys
import os
import sqlite3
import shutil
import tempfile
from pathlib import Path
import re


def find_streamrip_config():
    """Znajduje plik config.toml StreamRip"""
    possible_paths = [
        os.path.expanduser('~/.config/streamrip/config.toml'),  # Linux/Mac
        os.path.join(os.environ.get('APPDATA', ''), 'streamrip', 'config.toml'),  # Windows APPDATA
        os.path.join(os.environ.get('USERPROFILE', ''), '.config', 'streamrip', 'config.toml'),  # Windows HOME
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def update_streamrip_config(arl):
    """Automatycznie aktualizuje config.toml StreamRip"""
    config_path = find_streamrip_config()

    if not config_path:
        print("⚠️  Nie znaleziono pliku config.toml StreamRip")
        print()
        print("Uruchom najpierw StreamRip aby utworzyć config:")
        print("   rip config --open")
        print()
        return False

    print(f"✅ Znaleziono config.toml: {config_path}")
    print()

    try:
        # Wczytaj config
        with open(config_path, 'r', encoding='utf-8') as f:
            config_content = f.read()

        # Backup
        backup_path = config_path + '.backup'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        print(f"💾 Utworzono backup: {backup_path}")

        # Zamień wartość ARL w sekcji [deezer]
        # Pattern: szukaj arl = "cokolwiek" w sekcji [deezer]
        pattern = r'(arl\s*=\s*")[^"]*(")'

        if re.search(pattern, config_content):
            # Zamień istniejącą wartość
            new_content = re.sub(pattern, f'\\1{arl}\\2', config_content)
            print("✅ Zaktualizowano istniejącą wartość ARL")
        else:
            # Jeśli nie znaleziono, dodaj po [deezer]
            if '[deezer]' in config_content:
                new_content = re.sub(
                    r'(\[deezer\]\n)',
                    f'\\1arl = "{arl}"\n',
                    config_content
                )
                print("✅ Dodano wartość ARL do sekcji [deezer]")
            else:
                print("⚠️  Nie znaleziono sekcji [deezer] w config.toml")
                return False

        # Zapisz
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print()
        print(f"   ARL: {arl[:30]}...{arl[-10:]}")
        print()
        return True

    except Exception as e:
        print(f"❌ Błąd aktualizacji config.toml: {e}")
        print()
        return False


def find_firefox_profile():
    """Znajduje ścieżkę do profilu Firefox"""
    if os.name == 'nt':  # Windows
        firefox_path = os.path.join(os.environ['APPDATA'], 'Mozilla', 'Firefox', 'Profiles')
    elif sys.platform == 'darwin':  # macOS
        firefox_path = os.path.expanduser('~/Library/Application Support/Firefox/Profiles')
    else:  # Linux
        firefox_path = os.path.expanduser('~/.mozilla/firefox')

    if not os.path.exists(firefox_path):
        return None

    # Znajdź domyślny profil (zazwyczaj kończy się na .default-release)
    profiles = []
    for item in os.listdir(firefox_path):
        profile_path = os.path.join(firefox_path, item)
        if os.path.isdir(profile_path):
            cookies_path = os.path.join(profile_path, 'cookies.sqlite')
            if os.path.exists(cookies_path):
                profiles.append(profile_path)

    if not profiles:
        return None

    # Preferuj profil z 'default-release' lub 'default'
    for profile in profiles:
        if 'default-release' in profile.lower() or 'default' in profile.lower():
            return profile

    # Zwróć pierwszy znaleziony
    return profiles[0]


def get_arl_from_firefox():
    """Odczytuje cookie 'arl' z Firefox"""

    # Znajdź profil Firefox
    profile_path = find_firefox_profile()

    if not profile_path:
        print("❌ Nie znaleziono profilu Firefox")
        print()
        print("Sprawdź czy:")
        print("  - Firefox jest zainstalowany")
        print("  - Używałeś kiedyś Firefox (istnieje profil)")
        return None

    print(f"✅ Znaleziono profil Firefox: {os.path.basename(profile_path)}")

    cookies_path = os.path.join(profile_path, 'cookies.sqlite')

    if not os.path.exists(cookies_path):
        print(f"❌ Nie znaleziono pliku cookies: {cookies_path}")
        return None

    print(f"✅ Znaleziono plik cookies")
    print()
    print("[Firefox] Odczyt cookie 'arl'...")

    # Skopiuj do temp (Firefox może mieć zablokowany)
    temp_cookies = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    temp_cookies.close()

    try:
        shutil.copy2(cookies_path, temp_cookies.name)
    except Exception as e:
        print(f"❌ Nie można skopiować cookies (Firefox otwarty?): {e}")
        print()
        print("Zamknij Firefox i spróbuj ponownie!")
        return None

    # Odczytaj z SQLite
    try:
        conn = sqlite3.connect(temp_cookies.name)
        cursor = conn.cursor()

        # Firefox przechowuje cookies w tabeli moz_cookies
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        if 'moz_cookies' in tables:
            # Nowsza wersja Firefox
            cursor.execute(
                "SELECT value FROM moz_cookies WHERE host LIKE '%deezer.com%' AND name = 'arl'"
            )
        else:
            # Starsza wersja
            cursor.execute(
                "SELECT value FROM cookies WHERE host LIKE '%deezer.com%' AND name = 'arl'"
            )

        result = cursor.fetchone()
        conn.close()

        # Usuń temp
        os.unlink(temp_cookies.name)

        if result and result[0]:
            arl = result[0]
            print(f"✅ Znaleziono cookie 'arl'!")
            return arl
        else:
            print("❌ Nie znaleziono cookie 'arl' w Firefox")
            print()
            print("Upewnij się że:")
            print("  - Jesteś zalogowany na deezer.com w Firefox")
            print("  - Masz konto PREMIUM")
            return None

    except Exception as e:
        print(f"❌ Błąd odczytu SQLite: {e}")
        try:
            os.unlink(temp_cookies.name)
        except:
            pass
        return None


def main():
    print("=" * 70)
    print("  ODCZYT COOKIE 'arl' Z DEEZER (Firefox)")
    print("=" * 70)
    print()
    print("Firefox jest PROSTSZY - cookies NIE są szyfrowane! 🎉")
    print()
    print("=" * 70)
    print()

    arl = get_arl_from_firefox()

    print()
    print("=" * 70)

    if arl and len(arl) > 50:
        print("✅ SUCCESS!")
        print("=" * 70)
        print()
        print("Wartość ARL:")
        print(arl)
        print()

        # Zapisz do pliku
        output_file = os.path.join(os.path.dirname(__file__), 'arl.txt')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(arl)

        print(f"📁 Zapisano do pliku: {output_file}")
        print()

        # Automatycznie zaktualizuj config.toml
        print("=" * 70)
        print("AUTOMATYCZNA KONFIGURACJA STREAMRIP")
        print("=" * 70)
        print()

        success = update_streamrip_config(arl)

        if success:
            print("🎉 GOTOWE! StreamRip jest skonfigurowany!")
            print()
            print("Możesz teraz pobierać muzykę z Deezer:")
            print("   rip url https://www.deezer.com/pl/track/...")
        else:
            print("💡 Ręczna konfiguracja:")
            print()
            print("   1. rip config --open")
            print("   2. W sekcji [deezer] ustaw:")
            print(f'      arl = "{arl}"')
            print("   3. Zapisz i zamknij")

    else:
        print("❌ NIE UDAŁO SIĘ ODCZYTAĆ ARL")
        print("=" * 70)
        print()
        print("ROZWIĄZANIE:")
        print()
        print("1. Zainstaluj Firefox (jeśli nie masz)")
        print("   https://www.mozilla.org/firefox/")
        print()
        print("2. Otwórz https://www.deezer.com w Firefox")
        print()
        print("3. Zaloguj się na konto PREMIUM")
        print()
        print("4. Zamknij Firefox")
        print()
        print("5. Uruchom ponownie: python arl_firefox.py")
        print()
        print("LUB użyj ręcznej metody:")
        print("   python arl_manual.py")

    print("=" * 70)
    print()

    return 0 if arl else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        input("\nNaciśnij Enter aby zakończyć...")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nPrzerwano")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ NIEOCZEKIWANY BŁĄD: {e}")
        import traceback
        traceback.print_exc()
        input("\nNaciśnij Enter aby zakończyć...")
        sys.exit(1)
