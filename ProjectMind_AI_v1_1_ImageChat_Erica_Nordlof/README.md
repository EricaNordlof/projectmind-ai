# ProjectMind AI

Privat AI-arbetsyta för projekt, filer, ZIP-versioner och projektspecifika AI-chattar.

## Det som fungerar i denna MVP

- Endast admin-inloggning.
- Projektbibliotek med namn, status, stack, beskrivning och anteckningar.
- Filuppladdning, nedladdning och radering.
- Separat versionsarkiv för ZIP-filer.
- ZIP-säkerhetskontroll mot path traversal innan versionen registreras.
- Flera AI-chattar, fristående eller kopplade till ett projekt.
- Dra och släpp skärmbilder direkt i chatten.
- Klistra in skärmbilder från urklipp med Ctrl+V/Cmd+V.
- Välj flera PNG/JPG/WEBP/GIF-bilder och skicka dem tillsammans med text till AI:n.
- AI-chatten får projektets metadata, fillista och versionslista som kontext.
- SQLite-databas.
- CSRF-skydd för skrivande formulär.
- Mobilanpassat mörkt gränssnitt.
- `preview.html` i projektroten.

## Starta lokalt

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Installera och starta:

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Öppna `http://127.0.0.1:8000`.

## Miljövariabler

Kopiera `.env.example` och sätt minst:

```text
APP_PASSWORD=ett-starkt-lösenord
SESSION_SECRET=en-lång-slumpmässig-hemlighet
SESSION_SECURE=false
OPENAI_API_KEY=din-api-nyckel
OPENAI_MODEL=gpt-5-mini
DATA_DIR=./storage
```

OpenAI-nyckeln används endast från backend.

## Render

`Dockerfile` och `render.yaml` ingår.

För test kan tjänsten köras på Render Free. För verkligt permanent lokal SQLite- och fillagring behöver tjänsten senare en persistent disk monterad på `/app/storage`, eller så flyttas lagringen till exempelvis Postgres + objektlagring.

När persistent disk används:

```text
DATA_DIR=/app/storage
```

## Viktig avgränsning i första versionen

ProjectMind läser ännu inte automatiskt innehållet i alla ZIP-filer och dokument. AI:n får i MVP:n projektets metadata, fillista och versionslista som projektkontext. Det gör första versionen stabilare.

## Nästa steg

1. Läsa valda text- och kodfiler och lägga dem i projektkontext.
2. File Search/vector store för större projektarkiv.
3. S3/R2-kompatibel objektlagring.
4. Postgres.
5. Streaming av AI-svar.
6. Sökning över projekt, chattar och filer.
7. Versionsjämförelse mellan två ZIP-filer.

## Säkerhet

Detta är en privat MVP, inte en färdig multi-user SaaS. Gör egen säkerhetsgranskning och sätt upp permanent lagring/backuper innan känsligt produktionsmaterial lagras.


## Bildstöd i AI-chatten

Chatten stödjer nu skärmbilder på tre sätt:

1. Dra en bild direkt över meddelanderutan.
2. Klistra in en skärmbild från urklipp med Ctrl+V/Cmd+V.
3. Klicka på `+` bredvid meddelanderutan och välj bilder.

Standardgränser:
- högst 4 bilder per meddelande
- högst 8 MB per bild
- PNG, JPG/JPEG, WEBP och GIF

Bilderna sparas under `DATA_DIR/chat_uploads` och visas i chatthistoriken.
Den aktuella meddelandebilden skickas som bildinput till AI:n tillsammans med texten.
