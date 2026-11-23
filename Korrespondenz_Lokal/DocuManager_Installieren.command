#!/bin/zsh
# Installiert oder aktualisiert DocuManager als Programm auf diesem Mac.
#
# - Programmdateien nach ~/DocuManager (Ihre Daten in ~/DocuManager/Daten bleiben bei Updates erhalten)
# - Programm „DocuManager“ unter Programme, startbar per Doppelklick, Launchpad oder Spotlight
# - Liegen im entpackten Download bereits Daten (Ordner „Daten“) und am Ziel noch keine, werden sie übernommen
#
# Für ein Update: neue ZIP entpacken und diese Datei erneut doppelklicken.

quelle="${0:A:h}"
ziel="$HOME/DocuManager"
if [[ -w /Applications ]]; then programme="/Applications"; else programme="$HOME/Applications"; fi
app="$programme/DocuManager.app"

ende() { print; read -r '?Eingabetaste zum Schließen drücken …'; exit "${1:-0}"; }

print "DocuManager wird installiert …\n"
if ! /usr/bin/xcrun --find python3 >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  print -u2 "Python 3 fehlt. Bitte im Terminal einmal „xcode-select --install“ ausführen und danach erneut versuchen."
  ende 1
fi
if [[ ! -f "$quelle/app.py" ]]; then
  print -u2 "Diese Datei muss im Ordner „Korrespondenz_Lokal“ des entpackten Downloads liegen."
  ende 1
fi
if [[ "$quelle" == "$ziel" ]]; then
  print -u2 "Bitte das Installationsprogramm aus dem entpackten Download starten, nicht aus $ziel."
  ende 1
fi

# Laufende Version beenden, damit Dateien ersetzt werden können
/usr/sbin/lsof -ti tcp:8765 | xargs kill 2>/dev/null
sleep 1

# Programmdateien aktualisieren; der Ordner „Daten“ am Ziel wird nie angefasst
mkdir -p "$ziel"
/usr/bin/rsync -a --delete --exclude '/Daten/' --exclude '.DS_Store' "$quelle/" "$ziel/" || { print -u2 "Kopieren fehlgeschlagen."; ende 1; }
if [[ ! -f "$ziel/Daten/Rechtsberatung.sqlite3" && -f "$quelle/Daten/Rechtsberatung.sqlite3" ]]; then
  /usr/bin/ditto "$quelle/Daten" "$ziel/Daten" && print "Ihre bisherigen Daten aus dem Download-Ordner wurden übernommen."
fi
/usr/bin/xattr -dr com.apple.quarantine "$ziel" 2>/dev/null

# Programm „DocuManager.app“ erzeugen (lokal erzeugt, daher ohne Gatekeeper-Rückfrage)
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>DocuManager</string>
  <key>CFBundleDisplayName</key><string>DocuManager</string>
  <key>CFBundleIdentifier</key><string>local.documanager.start</string>
  <key>CFBundleExecutable</key><string>DocuManager</string>
  <key>CFBundleIconFile</key><string>DocuManager</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSAppleEventsUsageDescription</key><string>DocuManager holt markierte E-Mails aus Apple Mail.</string>
</dict></plist>
PLIST
cat > "$app/Contents/MacOS/DocuManager" <<'LAUNCHER'
#!/bin/zsh
# Startet DocuManager und öffnet die Oberfläche im Browser. Läuft er schon, nur öffnen.
# Das Programm bleibt aktiv (im Dock sichtbar), solange DocuManager läuft. Scheitert der Start, erscheint ein Hinweis.
ziel="$HOME/DocuManager"
cd "$ziel" 2>/dev/null || { /usr/bin/osascript -e 'display alert "DocuManager" message "Der Ordner ~/DocuManager fehlt. Bitte DocuManager_Installieren.command erneut ausführen."'; exit 1; }
if /usr/bin/curl -s -m 2 -o /dev/null "http://127.0.0.1:8765/api/cases"; then
  /usr/bin/open "http://127.0.0.1:8765"
  exit 0
fi
/usr/sbin/lsof -ti tcp:8765 | xargs kill 2>/dev/null
mkdir -p Daten/Logs
print "--- Start $(date '+%Y-%m-%d %H:%M:%S')" >> Daten/Logs/start.log
/usr/bin/python3 ./app.py --open >> Daten/Logs/start.log 2>&1 < /dev/null &
dienst=$!
trap 'kill $dienst 2>/dev/null' TERM INT HUP
wait $dienst
ergebnis=$?
if (( ergebnis != 0 && ergebnis != 143 )); then
  grund="$(tail -n 6 Daten/Logs/start.log | tr '"' "'")"
  /usr/bin/osascript -e "display alert \"DocuManager konnte nicht starten\" message \"$grund\n\nProtokoll: ~/DocuManager/Daten/Logs/start.log\""
fi
exit 0
LAUNCHER
chmod +x "$app/Contents/MacOS/DocuManager"

# Symbol aus icon.svg erzeugen (falls etwas fehlt, bleibt das Standardsymbol)
tmp="$(mktemp -d)"
if /usr/bin/qlmanage -t -s 1024 -o "$tmp" "$ziel/icon.svg" >/dev/null 2>&1 && [[ -f "$tmp/icon.svg.png" ]]; then
  set="$tmp/DocuManager.iconset"; mkdir -p "$set"
  for g in 16 32 128 256 512; do
    /usr/bin/sips -z $g $g "$tmp/icon.svg.png" --out "$set/icon_${g}x${g}.png" >/dev/null 2>&1
    /usr/bin/sips -z $((g*2)) $((g*2)) "$tmp/icon.svg.png" --out "$set/icon_${g}x${g}@2x.png" >/dev/null 2>&1
  done
  /usr/bin/iconutil -c icns "$set" -o "$app/Contents/Resources/DocuManager.icns" 2>/dev/null
fi
rm -rf "$tmp"
/usr/bin/touch "$app"

print "\nFertig."
print "• Programm:  $app"
print "• Daten:     $ziel/Daten"
print "\nStarten Sie DocuManager ab jetzt wie jedes Programm: über Launchpad, Spotlight (⌘ Leertaste, „DocuManager“)"
print "oder ziehen Sie es aus dem Finder ins Dock. Beenden über „Beenden“ unten links in der Anwendung."
/usr/bin/open -R "$app"
read -r '?Jetzt starten? [J/n] ' antwort
if [[ "$antwort" != [nN]* ]]; then /usr/bin/open "$app"; fi
exit 0
