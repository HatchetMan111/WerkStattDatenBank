# Rechtliche Hinweise und Datenquellen

Stand: November 2026. Dies ist eine Zusammenstellung der Bedingungen, keine Rechtsberatung.

## 1. Quellcode

Der Quellcode steht unter der **MIT-Lizenz** (siehe `LICENSE`), © 2026 LichtValleyApps. Die Software wird „wie besehen“ ohne Gewährleistung und Haftung bereitgestellt.

## 2. Datenquellen und Lizenzen

| Quelle | Inhalt | Bedingungen |
|---|---|---|
| **Europäische Umweltagentur (EEA)** – „Monitoring of CO2 emissions from passenger cars“ (Verordnung (EU) 2019/631), [Datenseite](https://www.eea.europa.eu/en/datahub/datahubitem-view/fa8b1229-3db6-495d-b18e-9c9b3267c02b) | Marke, Modell, Kraftstoff, Hubraum, Leistung, CO2, Zulassungszahlen | CC BY 4.0 laut Metadaten der Ausgabe 2024 und [EEA-Urheberrechtshinweis](https://www.eea.europa.eu/legal/copyright). Quellenangabe Pflicht, Änderungen kenntlich machen, Inhalt nicht sinnentstellt wiedergeben. Einzelne Datensätze/Jahrgänge können abweichende Bedingungen haben – vor dem Import auf der EEA-Seite prüfen. **Fremde Inhalte (Dritte) sind ausgenommen.** |
| Demo-Daten | erfundene Fahrzeuge („Musterwagen“) und Teile („DEMO-…“) | frei erfunden, nur zum Ausprobieren |
| Eigene Einträge und eigene/Händler-Listen | Teile, OE-Nummern, Preise, Zuordnungen | liegen in der Verantwortung des Betreibers (siehe Abschnitt 4) |

**Änderungsvermerk (EEA):** Die EEA-Daten werden beim Import zeilenweise zu Fahrzeugvarianten zusammengefasst (aggregiert), Zulassungszahlen werden summiert, CO2-Werte gemittelt, und Schreibweisen von Marken- und Modellnamen werden vereinheitlicht (z. B. „VOLKSWAGEN“ → „Volkswagen“). Die Oberfläche weist im Seitenfuß darauf hin. Die Ergebnisse geben nicht notwendig die Meinung der EEA oder anderer EU-Organe wieder; die EEA übernimmt keine Haftung.

## 3. Was die Software nicht tut

* Es werden **keine Daten proprietärer Teilekataloge** kopiert, abgerufen oder nachgebaut (Datenbankherstellerrecht, Urheberrecht, AGB). Teile und Zuordnungen stammen ausschließlich aus eigenen Einträgen oder Listen, die der Betreiber verwenden darf.
* Es gibt keine Hersteller-Logos oder -Bilder. Hersteller- und Modellnamen dienen nur der Bezeichnung der Fahrzeuge.
* Die Passgenauigkeit ist **nicht gewährleistet**. Vor der Bestellung ist sie über Fahrgestellnummer/Teilenummer zu prüfen.

## 4. Pflichten des Betreibers

* **Importierte Listen:** Händler- und Lieferantenlisten nur verwenden, soweit deren Bedingungen es erlauben.
* **Datenschutz (DSGVO):** „Auftragsnummer“ und „Kilometerstand“ in den Verbaut-Buchungen können über den Auftrag einem Kunden zugeordnet werden und sind dann personenbezogene Daten. Keine Namen, Kennzeichen oder Fahrgestellnummern in die Felder eintragen; Verarbeitung ggf. im Verzeichnis von Verarbeitungstätigkeiten aufnehmen und Aufbewahrungsfristen beachten.
* **Betrieb im Internet:** Ist die Oberfläche öffentlich erreichbar, sind Impressum und Datenschutzerklärung sowie ein Zugriffsschutz (Reverse-Proxy mit Anmeldung, TLS) nötig. Vorgesehen ist der Betrieb im Werkstattnetz.

## 5. Bibliotheken von Dritten

Das Frontend enthält React, React DOM und Scheduler (MIT-Lizenz, © Meta Platforms, Inc. und Mitwirkende). Die Lizenztexte liegen in `frontend/public/third-party-licenses.txt` und werden mit der Oberfläche unter `/third-party-licenses.txt` ausgeliefert. Das Backend nutzt nur die Python-Standardbibliothek.
