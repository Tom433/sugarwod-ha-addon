# Changelog

## 0.1.1

- Sicherheit: Die Web-Oberfläche/API nimmt im Add-on nur noch Anfragen über Home-Assistant-Ingress an
  (andere Container im Supervisor-Netz bekommen 403).
- Sicherheit: Abhängigkeiten aktualisiert (waitress 3.0.2, requests 2.34.2, Flask 3.1.3).
- Sicherheits-Header (CSP, nosniff, Referrer-Policy) ergänzt.
- Upload-Limit von 50 MB auf 5 MB gesenkt; `limit` bei `/api/workouts` wird sauber geprüft.
- Ordner-Import ignoriert Symlinks.
- Fix: Sonderzeichen wie „&“ wurden im Verlaufs-Tooltip doppelt escaped angezeigt (z. B. „&amp;“).

## 0.1.0

- Erste Version: CSV-Import (Upload und Ordner), 1RM-Schätzung, Gewichtsvorschläge, Verlauf,
  Stärken/Schwächen, Home-Assistant-Sensoren.
