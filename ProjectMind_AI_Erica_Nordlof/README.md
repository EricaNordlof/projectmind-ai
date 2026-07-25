# ProjectMind AI v2 – 10/10 Persistent Edition

Privat AI-arbetsyta för projekt, studiematerial, filer, bilder, ZIP-versioner och projektspecifika AI-chattar.

## Den viktiga förändringen

v2 sparar inte längre viktig information enbart i Render-containern.

- Projekt, chattar och metadata sparas i **PostgreSQL**.
- PDF, bilder, dokument och ZIP-versioner sparas i **S3-kompatibel objektlagring**.
- `/health` kontrollerar både databas och fillagring.
- Appen visar en tydlig varning när den startas med osäker lokal lagring.
- Lokal SQLite och lokal disk finns kvar endast för utveckling.
- Ett migreringsskript följer med för att flytta en äldre SQLite-databas till PostgreSQL.

## Produktionsarkitektur

```text
Webbläsare
   |
ProjectMind AI på Render
   |---------------- PostgreSQL: projekt, chattar, filmetadata
   |
   `---------------- S3: PDF, bilder, ZIP och andra uppladdningar
```

## Render-filer

- `render.yaml`: kostnadsfri testmiljö med Free Render Postgres.
- `render.production.yaml`: stabil långtidsmiljö med betald PostgreSQL-plan.
- Objektlagringen skapas hos en S3-kompatibel leverantör och anges som hemliga miljövariabler.

## Viktigt om Render Free

Free-webbtjänsten har ingen permanent lokal disk. Därför är `STORAGE_BACKEND=s3` obligatoriskt för verkliga filer.

En kostnadsfri Render Postgres är lämplig för test, men ska uppgraderas innan ProjectMind används som enda långtidsarkiv. Ha dessutom alltid en separat säkerhetskopia av studiematerialet.

## Miljövariabler

```env
APP_PASSWORD=
SESSION_SECRET=
SESSION_SECURE=true

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=max

DATABASE_URL=postgresql://...

STORAGE_BACKEND=s3
S3_ENDPOINT_URL=
S3_BUCKET=
S3_REGION=eu-central-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_FORCE_PATH_STYLE=false
```

## Deploy på Render

1. Ladda upp mappen `ProjectMind_AI_Erica_Nordlof` direkt till repo-roten.
2. Välj `render.yaml` som Blueprint Path.
3. Fyll i `APP_PASSWORD`, `OPENAI_API_KEY` och S3-värdena.
4. Deploya.
5. Öppna `/health`. Svaret ska visa:
   - `"database": "postgresql"`
   - `"database_ok": true`
   - `"storage": "s3"`
   - `"storage_ok": true`
6. Skapa ett testprojekt, vänta tills tjänsten somnat och öppna den igen. Projektet ska finnas kvar.

## Migrera äldre SQLite-data

```bash
export SQLITE_PATH=./storage/projectmind.db
export DATABASE_URL=postgresql://...
python scripts/migrate_sqlite_to_postgres.py
```

Observera att själva filerna också behöver kopieras till S3. SQLite-skriptet flyttar databasposterna.

## Kontrollera beständigheten

```bash
python scripts/verify_persistence.py
```

## Säkerhet

- Endast admin kan se och ladda ned material.
- CSRF-skydd och säkra sessionscookies finns.
- S3-objekt sätts som privata och laddas genom appen.
- S3 server-side encryption (`AES256`) används vid uppladdning.
- Hemligheter ska enbart finnas i Render Environment, aldrig på GitHub.
- För känsligt studiematerial rekommenderas versionshantering och regelbunden extern backup.


## Lagringsstatus i gränssnittet

ProjectMind skiljer nu mellan tre driftlägen:

- **Permanent lagring aktiv:** SQLite och filer ligger på en ansluten Render Persistent Disk.
- **Produktionslagring aktiv:** PostgreSQL och S3 används.
- **Tillfällig lagring:** lokal disk används utan bekräftad persistent disk.

För din Render Starter-tjänst ska följande värden finnas:

```env
DATA_DIR=/app/storage
STORAGE_BACKEND=local
PERSISTENT_DISK=true
```

Disken ska vara monterad på `/app/storage`. Då visas en grön bekräftelse i stället för den felaktiga varningen.
