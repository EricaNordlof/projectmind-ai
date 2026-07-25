# ProjectMind – smart dokumentanalys

Denna uppgradering gör att ProjectMind läser innehållet i projektets uppladdade dokument i stället för att bara skicka filnamn och filstorlek till AI:n.

## Ersätt/lägg till i `ProjectMind_AI_Erica_Nordlof`

1. Lägg till `smart_app.py`.
2. Ersätt `requirements.txt`.
3. Ersätt `Dockerfile`.
4. Låt alla andra filer vara kvar.

Render bygger därefter automatiskt om tjänsten. Första frågan efter deploy kan ta längre tid eftersom dokumenten läses och cachelagras. Senare frågor använder cachen.

## Vad som tillkommit

- PDF-text per sida med källmarkörer.
- DOCX, XLSX, PPTX, text, kod, CSV, JSON, HTML, XML och YAML.
- Databascache med SHA-256, så oförändrade filer inte läses om.
- Prioritering av reviderade/högre utgåvor.
- Större projektkontext.
- Krav på källhänvisningar i formatet `[Källa: filnamn, sida X]`.
- Aktiv kontroll av motsägelser, datum, summor, poäng och versioner.
- Tydlig skillnad mellan dokumentfakta, slutsats och sådant som måste bekräftas.

## Frivilliga Render-variabler

```env
SMART_CONTEXT_MAX_CHARS=180000
SMART_MAX_FILE_CHARS=120000
SMART_HISTORY_MESSAGES=40
SMART_MAX_OUTPUT_TOKENS=8000
```

Standardvärdena används även om variablerna inte läggs till.
