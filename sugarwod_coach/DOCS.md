# SugarWOD Coach

Nach dem Start in der Seitenleiste **SugarWOD Coach** öffnen und unter **Import** den CSV-Export aus
der SugarWOD-App hochladen (More → Tools & Resources → Export Workouts; die Datei kommt per Mail).

Alternativ die CSV in `/share/sugarwod` ablegen, sie wird automatisch importiert.

Wichtig: SugarWOD exportiert Gewichte meist in lbs. Die Option „Einheit im SugarWOD-Export“ muss
dazu passen.

Sensoren: `sensor.sugarwod_<übung>_1rm`, `sensor.sugarwod_letztes_training`,
`sensor.sugarwod_trainingstage_30_tage`. Sie werden nach jedem Import und alle 30 Minuten
aktualisiert.

Ausführliche Beschreibung der Berechnungen: siehe README im Repository.
