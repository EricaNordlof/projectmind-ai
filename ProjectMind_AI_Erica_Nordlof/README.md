# ProjectMind AI – komplett dokumentintelligent version

Privat AI-arbetsyta för projekt, studiematerial, dokument, bilder, ZIP-versioner och projektspecifika AI-chattar.

## Det som är nytt

- Läser **faktiskt innehåll** ur PDF, DOCX, XLSX, PPTX och textbaserade filer.
- PDF-text delas upp sida för sida med källmarkörer.
- Dokumentinnehåll cachelagras i databasen och behöver inte extraheras på nytt för varje fråga.
- AI:n instrueras att ange källor som `[Källa: filnamn.pdf, sida 2]`.
- Reviderade filer och högre utgåvor prioriteras, men motsägelser redovisas.
- Breda frågor som "granska alla filer" skickar hela dokumentunderlaget när det ryms.
- Riktade frågor väljer de mest relevanta källavsnitten.
- Kan kontrollera datum, poäng, timmar, versionsnummer och andra motstridiga uppgifter.
- Har stöd för bilder i chatten, ZIP-versioner, SQLite/PostgreSQL och lokal/S3-lagring.

## Filstruktur

```text
ProjectMind_AI_Erica_Nordlof/
├── app.py
├── ai_service.py
├── config.py
├── db.py
├── documents.py
├── markdown_utils.py
├── storage.py
├── templates/
├── static/
├── scripts/
├── Dockerfile
├── render.yaml
├── render.production.yaml
└── requirements.txt
```

## Byt ut hela projektet på GitHub

1. Öppna mappen `ProjectMind_AI_Erica_Nordlof` i ditt repository.
2. Välj **Add file → Upload files**.
3. Dra in **hela innehållet** i denna mapp.
4. GitHub visar att befintliga filer ersätts och nya filer läggs till.
5. Commit direkt till `main` om Render redan följer `main`.
6. Render bygger om tjänsten automatiskt.

Den befintliga SQLite-databasen och uppladdade filer ligger på Render-disken `/app/storage` och raderas inte när koden byts ut.

## Render Starter med persistent disk

`render.yaml` är färdig för detta driftläge:

```env
DATA_DIR=/app/storage
STORAGE_BACKEND=local
PERSISTENT_DISK=true
```

Disken ska vara monterad på `/app/storage`.

## Obligatoriska hemligheter i Render

```env
APP_PASSWORD=...
OPENAI_API_KEY=...
```

`SESSION_SECRET` genereras av Blueprint-konfigurationen.

## Kontroll efter deploy

Öppna `/health`. Det bör bland annat visa:

```json
{
  "database": "sqlite",
  "database_ok": true,
  "storage": "local",
  "storage_ok": true,
  "persistent": true
}
```

Öppna därefter projektet och klicka **Indexera om alla**. Gamla uppladdningar får då dokumenttext i den nya cachen.

## Första testfrågan

```text
Granska alla uppladdade filer. Gör en samlad bedömning, kontrollera datum och poäng, hitta motsägelser och ange filnamn och sida efter varje faktapåstående.
```

## Begränsning

Skannade PDF-sidor utan maskinläsbar text markeras som sådana. Vanliga digitala PDF-filer fungerar direkt. OCR ingår inte i denna version eftersom felaktig OCR kan ge sämre källsäkerhet.

## Lokal start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload
```

Miljövariabler från `.env` måste laddas av terminalen eller din utvecklingsmiljö.

## Verktyg

```bash
python scripts/verify_persistence.py
python scripts/reindex_documents.py
```

## Tester

```bash
pip install -r requirements-dev.txt
pytest -q
```
