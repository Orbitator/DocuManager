#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  print -u2 'Python 3 wird zum Starten benötigt.'
  read -r '?Eingabetaste zum Schließen drücken …'
  exit 1
fi
# Eine noch laufende frühere Version beenden, sonst ist die Adresse 127.0.0.1:8765 belegt
lsof -ti tcp:8765 | xargs kill 2>/dev/null
sleep 1
python3 ./app.py --open
ergebnis=$?
if (( ergebnis != 0 )); then
  read -r '?Eingabetaste zum Schließen drücken …'
fi
exit "$ergebnis"
