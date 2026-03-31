# Kyrkoordningen RAG Preprocessing

Preprocessing-pipeline for PDF-dokumentet **"Kyrkoordning för Svenska kyrkan (lydelse 1 januari 2026)"**.

Pipeline:
1. extraherar och rensar PDF-text
2. parserar avdelning/kapitel/paragraf/inledning
3. separerar `intro` från `provision`
4. chunkar för RAG
5. exporterar till JSONL + CSV

## Projektstruktur

```text
/project
  /data
    kyrkoordningen.pdf
  /src
    extract_pdf.py
    parse_structure.py
    chunk_document.py
    export_outputs.py
    eval_retrieval.py
    utils.py
  /tests
    conftest.py
    test_parser.py
    test_chunking.py
    test_metadata.py
  /output
  README.md
  requirements.txt
```

## Installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Kör pipeline

```bash
.venv/bin/python src/extract_pdf.py
.venv/bin/python src/parse_structure.py --input output/extracted_pages.json
.venv/bin/python src/chunk_document.py --input output/structured_nodes.json --output output/chunks.json
.venv/bin/python src/export_outputs.py --input output/chunks.json
```

Alternativ: kör allt i ett steg (parsa + chunka + exportera):

```bash
.venv/bin/python src/export_outputs.py --pdf data/kyrkoordningen.pdf
```

## Output

Primärt outputformat:
- `output/kyrkoordningen_chunks.jsonl`

Sekundärt outputformat:
- `output/kyrkoordningen_chunks.csv`

Exempel på metadata per chunk:

```json
{
  "document_title": "Kyrkoordning för Svenska kyrkan",
  "document_version": "Lydelse 1 januari 2026",
  "amendments_through": "SvKB 2025:7",
  "section_ordinal": "Femte avdelningen",
  "section_title": "Gudstjänst",
  "chapter_number": "17",
  "chapter_title": "Gudstjänstliv",
  "paragraph_number": "3",
  "paragraph_label": "3 §",
  "text_type": "provision",
  "is_legal_norm": true,
  "citation_label": "17 kap. 3 §",
  "hierarchy_path": "Femte avdelningen: Gudstjänst > 17 kap. Gudstjänstliv > 3 §"
}
```

## Regler i implementationen

- `text_type="intro"`:
  - skapas från `Inledning`-block
  - `is_legal_norm=false`
  - chunkas separat från paragrafer
- `text_type="provision"`:
  - skapas från paragrafmönster (`1 §`, `1 a §`, osv.)
  - `is_legal_norm=true`
- primär chunking: en paragraf per chunk
- långa paragrafer delas i delchunkar med samma paragrafmetadata
- valfri sammanslagning av korta paragrafer finns via:
  - `--merge-short-paragraphs`
  - `--short-chunk-tokens`

## Tester

Kör:

```bash
.venv/bin/python -m pytest -q
```

Testerna verifierar bland annat:
- dokumentversion + ändringsstatus
- kapitelidentifiering för `1 kap.` och `17 kap.`
- paragrafidentifiering för `1 kap. 1 §`, `17 kap. 3 §`, `23 kap. 1 a §`
- `17 kap. Inledning` => `text_type="intro"`
- intro/provision separeras
- rimliga sidintervall
- unika chunk-id:n

## Kända begränsningar

- Vissa mellanrubriker/övergångsblock i PDF:en är oregelbundna och kan ge parservarningar (`Oklassificerad rad`).
- Parsern prioriterar spårbarhet framför aggressiva gissningar: osäker struktur loggas hellre som varning.
- Hyfen-återställning i normalisering används endast i säkra fall (radbrytning efter bindestreck + gemen start nästa rad).

## Rekommendation för RAG-indexering

- Indexera i första hand `content_normalized`.
- Behåll `content` parallellt för texttrohet vid visning.
- Inkludera `citation_label`, `hierarchy_path`, `text_type`, `is_legal_norm` som filterbara metadata.
- Vid retrieval: prioritera `text_type="provision"` för rättsliga svar och använd `intro` som tolkningsstöd.

## Bonus: enkel retrieval-eval

Kör:

```bash
.venv/bin/python src/eval_retrieval.py --input output/kyrkoordningen_chunks.jsonl --output output/eval_queries.json
```

Skriptet kör de fem exempelfrågorna och sparar toppträffar med citationer.

## API for ChatGPT / Render

Det finns nu en deploybar FastAPI-tjänst i `app/main.py` som använder OpenAI Responses API + `file_search` mot din Vector Store.

### Lokalt API-test

1. Sätt miljövariabler:

```bash
export OPENAI_API_KEY="<YOUR_OPENAI_API_KEY>"
export OPENAI_VECTOR_STORE_ID="vs_69cbe4965304819188c7b8cd7f68de2f"
```

2. Starta API:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Testa fråga:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Vad gäller för vigsel?"}'
```

## GitHub setup

Om du vill publicera detta repo till GitHub:

```bash
git init
git add .
git commit -m "Kyrkoordningen RAG pipeline + API + Render deploy"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

## Render setup

Projektet innehåller `render.yaml` för Blueprint-deploy:

- Service name: `kyrkoordningen-rag-api`
- Runtime: Python
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

### Deploy via Render Dashboard

1. Gå till Render Dashboard.
2. `New` -> `Blueprint`.
3. Välj ditt GitHub-repo.
4. Render läser `render.yaml`.
5. Sätt env vars:
   - `OPENAI_API_KEY`
   - `OPENAI_VECTOR_STORE_ID` (din Vector Store ID)
6. Deploy.

## OpenAI Vector Store upload helper

För att ladda upp `output/kyrkoordningen_chunks.txt` till en befintlig Vector Store via API:

```bash
.venv/bin/python scripts/upload_to_vector_store.py \
  --api-key "$OPENAI_API_KEY" \
  --vector-store-id "vs_69cbe4965304819188c7b8cd7f68de2f" \
  --file-path output/kyrkoordningen_chunks.txt
```

Scriptet skriver ut `uploaded_file_id` och `vector_store_file_id`.
