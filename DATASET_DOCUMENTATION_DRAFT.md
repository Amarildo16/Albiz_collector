# Dokumentacion i Grupit të të Dhënave — Draft

**Projekti:** Albiz Collector  
**Versioni:** 0.1.0  
**Data e hartimit:** 2026-05-09  
**Gjuha:** Shqip (Formal Akademik)

---

## 1. Qëllimi i Grupit të të Dhënave

Grupi i të dhënave i ndërtuar nga ky projekt synon të ofrojë bazë empirike për analizën kërkimore të prokurimit publik dhe regjistrit tregtar shqiptar. Dy burime kryesore publike bashkohen brenda një pipeline të unifikuar:

1. **Eksportet e prokurimit të APP-it** — eksporte vjetore CSV të prokurimeve publike të disponueshme në `app.gov.al`, që dokumentojnë procedura, vlera kontratash, subjekte fituese dhe organe kontraktuese.
2. **Rezultatet e kërkimit të QKB-it** — të dhëna të regjistrit tregtar të disponueshme nëpërmjet faqes së kërkimit `format.qkb.gov.al/kerko-per-subjekt/`, që dokumentojnë identitetin e subjekteve tregtare, statusin regjistrues, formën ligjore dhe informacione të tjera regjistrale.

Qëllimi themelor i grupit është mundësimi i analizave të besueshme dhe të verifikueshme mbi marrëdhëniet midis aktivitetit të prokurimit publik dhe karakteristikave të regjistrit tregtar, duke ruajtur gjithmonë proveniencën e plotë nga burimi deri në tabelën analitike.

---

## 2. Rëndësia e të Dhënave të Regjistrit Tregtar QKB

Qendra Kombëtare e Biznesit (QKB) administron regjistrin zyrtar tregtar të Shqipërisë. Të dhënat e disponueshme nëpërmjet faqes së tij publike të kërkimit kanë rëndësi të veçantë për kërkimin akademik dhe empirik për arsyet e mëposhtme:

- **Identifikimi unik i subjekteve:** Numri unik i identifikimit të tatimpaguesit (NIPT) lejon lidhjen precize dhe të verifikueshme midis të dhënave të prokurimit dhe të dhënave të regjistrit, duke eliminuar ambiguitetin e emrave tregtarë.
- **Statusi regjistrues dhe ligjshmëria operative:** Fusha `subject_status` tregon nëse subjekti është aktiv, i pezulluar ose i çregjistruar, gjë e cila ka rëndësi direkte për analizat e riskut dhe integritetit të prokurimit.
- **Forma juridike:** Klasifikimi i subjekteve sipas formës ligjore (`legal_form`) mundëson krahasime strukturore dhe analiza sipas kategorisë organizative.
- **Data e regjistrimit:** Data e themelimit të subjektit lejon llogaritjen e moshës së kompanisë në momentin e çdo aktiviteti prokurues, gjë e cila është e rëndësishme për studimin e sjelljes së tregut.
- **Sinjalet e rrezikut:** Fushat si `has_red_flags` pasqyrojnë informacione prezentacionale të regjistrit mbi gjendjen e subjektit dhe mund të shërbejnë si indikatorë eksplorativë në analizat e riskut.
- **Informacione mbi pronësinë dhe aktivitetin:** Fushat si `ownership_text` dhe `activity_text`, edhe pse të nivelit të kujdesit, ofrojnë kontekst themelor mbi strukturën e kapitalit dhe fushën e veprimtarisë.

---

## 3. Emërtimi i Propozuar i Grupit të të Dhënave

Sipas konventave ekzistuese të projektit dhe strukturës aktuale të tabelave, grupi i të dhënave propozohet të emërtohet si vijon:

| Shtresë | Emërtimi i Tabelës | Përshkrimi |
|---|---|---|
| Råe (Raw) | `raw_fetches` | Referencat e artefakteve të papërpunuara të mbledhura |
| Strukturore | `structured_records` | Momentet logjike burimore të normalizuara para ndarjes |
| Normalizim APP | `normalized_app_export_rows` | Rreshtat e prokurimit nga eksportet CSV të APP-it |
| Normalizim QKB | `normalized_qkb_search_rows` | Rreshtat e rezultateve të kërkimit të QKB-it |
| Karakteristika APP | `app_company_features` | Agregate në nivel kompanie nga të dhënat e APP-it |
| Karakteristika QKB | `qkb_company_features` | Karakteristika në nivel kompanie nga të dhënat e QKB-it |
| Karakteristika të bashkuara | `joined_company_features` | Karakteristika të bashkuara APP–QKB me përputhje ekzakte NIPT |

Emërtimi i grupit të plotë kërkimor është:  
**`albiz_procurement_registry_dataset_v0.1`**

---

## 4. Teknologjitë dhe Teknikat e Mbledhjes së të Dhënave

### 4.1 Stack Teknologjik

Projekti është ndërtuar mbi Python 3.11/3.12 dhe përdor bibliotekat e mëposhtme kryesore:

| Biblioteka | Versioni | Roli |
|---|---|---|
| `httpx` | 0.27.0 | Klient HTTP asinkron për mbledhjen e të dhënave |
| `beautifulsoup4` | 4.12.3 | Analizim HTML dhe ekstraksion i elementeve |
| `lxml` | 5.2.2 | Motor i shpejtë XML/HTML për analizim |
| `SQLAlchemy` | 2.0.36 | ORM dhe menaxhim i shtresës së bazës së të dhënave |
| `Alembic` | 1.14.1 | Menaxhim i migrimeve të skemës së bazës |
| `APScheduler` | 3.10.4 | Planifikues periodik i detyrave të mbledhjes |
| `playwright` | 1.52.0 | Automatizim i shfletuesit (vetëm për kolektorin eksperimental) |
| `tenacity` | 9.0.0 | Logjika e riprovimeve për kërkesat HTTP |
| `PyMySQL` | 1.1.1 | Driver MySQL për lidhjen me bazën e të dhënave |
| `python-dotenv` | 1.0.1 | Ngarkimi i konfigurimit nga variablat e mjedisit |
| `typer` | 0.12.5 | Ndërtimi i ndërfaqes CLI |

### 4.2 Teknikat e Mbledhjes

**Mbledhja e eksporteve APP:**
- Klienti HTTP kryen një kërkesë GET në faqen e indeksit `app.gov.al/export-public-calls/` për të zbuluar vitet e disponueshme.
- Për çdo vit, shkarkimet bëhen nëpërmjet URL-së `app.gov.al/GetData/ExportDocument?year=YYYY`.
- Artefaktet CSV ruhen në disk dhe regjistrohen në `raw_fetches`.

**Mbledhja e kërkimit QKB:**
- Klienti HTTP kryen fillimisht një GET në `format.qkb.gov.al/kerko-per-subjekt/` për të vendosur cookie-t e sesionit.
- Më pas, POST-on ngarkesën e formularit të koduar si `application/x-www-form-urlencoded` në të njëjtin endpoint.
- Faqja HTML e kthyer ruhet e papërpunuar dhe variabla JavaScript inline `response` dekodikohet në një moment të strukturuar.
- Kërkesat me gamë datash ekzekutohen si kërkesa një-ditore inkluzive (chunking ditor), duke mbajtur gjendjen e progresit në bazën e të dhënave.
- Mbledhja QKB është qëllimisht vetëm HTTP; pa automatizim të shfletuesit.

**Kolektor eksperimental i njoftimeve QKB:**
- Pagina-kategori të njoftimeve nga `format.qkb.gov.al` ruhen si fotografi të papërpunuara HTML.
- Playwright mund të përdoret opsionalisht për ndihmë me renderimin e JS.
- Ky rrugëtim është eksperimental dhe nuk ushqen asnjë tabelë normalizimi, karakteristikash ose profilizimi.

### 4.3 Riprovimi dhe Qëndrueshmëria

- Statuset HTTP `408`, `425`, `429` dhe `5xx` riprovohen automatikisht deri në 3 herë.
- Kërkesat e gamës së datave QKB janë të rifillushme: gjendja e progresit ruhet pas çdo dite të suksesshme; ekzekutimi mund të rifillojë nga dita e fundit e pa përfunduar.
- Ditët që kthejnë saktësisht 50 rreshta shënohen si potencialisht të kufizuara (`potentially_truncated_days`).

---

## 5. Arkitektura e të Dhënave të Papërpunuara dhe të Normalizuara

### 5.1 Shtresa e të Dhënave të Papërpunuara

Çdo artefakt i mbledhur ruhet në disk nën strukturën:

```
<RAW_STORAGE_DIR>/<source_name>/<YYYY>/<MM>/<DD>/<fetch_kind>/<filename-sha256suffix>
```

Metadata e çdo artefakti ruhet në tabelën `raw_fetches`, duke përfshirë:
- `storage_path` — rruga relative në disk
- `content_hash` — hash SHA-256 i përmbajtjes
- `source_name`, `fetch_kind`, `url`, `http_status_code`
- `is_corrupted`, `corruption_reason` — gjendje e integritetit

Kjo qasje siguron auditueshmëri të plotë: artefaktet mund të verifikohen pas mbledhjes me komandën `audit raw-fetches`, e cila krahason hash-et e ruajtura me hash-et aktuale të skedarëve në disk.

### 5.2 Shtresa Strukturore

Tabela `structured_records` ruan momentin logjik më të fundit për çdo kombinim `source_name` / `record_type` / çelës identifikues. Kjo shtresë ndërmjetëse lejon rinormalizimin pa riprovimin e burimit të gjallë.

### 5.3 Shtresa e Normalizimit

Dy tabela normalizimi janë materializuar nga `structured_records`:

**`normalized_app_export_rows`:**
- Fusha kryesore: `procurement_reference`, `winner_nipt`, `publication_date`, `budget_limit_amount`, `winner_value_amount`, `procedure_type`, `contract_type`, `is_cancelled`, `is_suspended`
- Provenienca mbahet gjithmonë deri te snapshot-i strukturor dhe artefakti i papërpunuar

**`normalized_qkb_search_rows`:**
- Fusha kryesore: `business_nipt`, `business_name`, `legal_form`, `registration_date`, `subject_status`
- Fusha shtesë: `trade_name`, `ownership_text`, `activity_text`, `has_red_flags`, `city`

### 5.4 Shtresa e Karakteristikave

Tre tabela karakteristikash materializohen nga normalizimi:

- **`app_company_features`** — Agregate për çdo NIPT fitues unik: numri i prokurimeve, vlera totale, numri i procedurave të anuluara/pezulluara, organe kontraktuese të dallueshme etj.
- **`qkb_company_features`** — Karakteristika për çdo NIPT biznesi unik nga QKB: emri, forma ligjore, statusi, viti i regjistrimit etj.
- **`joined_company_features`** — Bashkim ekzakt `winner_nipt == business_nipt`; mosha e kompanisë në momentin e prokurimit të parë/fundit llogaritet këtu.

### 5.5 Shtresa e Profilizimit dhe Auditimit

- Komanda `profile` mat mbulimin e fushave, mungesën, mbulimin e bashkimit APP–QKB dhe gatishmërinë analitike.
- Komanda `audit raw-fetches` verifikon integritetin SHA-256 të çdo artefakti të ruajtur.
- Komanda `audit qkb-search-runs` liston gjendjen e ekzekutimeve të ruajtura të gamës së datave.
- Komanda `smoke` kontrollon marrëveshjet e gjalla të burimit për kolektorët e mbështetur.

---

## 6. Kufizimet e Burimit

### 6.1 APP

- Burimi ekspozon të dhëna historike si eksporte vjetore CSV; nuk ofron API të strukturuar.
- Formati i skedarëve CSV dhe URL-ja e shkarkimit mund të ndryshojnë pa paralajmërim nëse portali i APP-it modifikohet.
- Parsimi i indeksit të viteve mbështetet në selektorë HTML që mund të ndryshojnë.

### 6.2 QKB

- Faqja e kërkimit kthen maksimum 50 rreshta për çdo kërkesë. Ditët që kthejnë saktësisht 50 rreshta mund të jenë të kufizuara pa asnjë tregues të qartë nga burimi.
- Ngarkesa e rezultateve është e koduar si variabël JavaScript inline; ndryshimet në kontraktin e JavaScript-it të faqes mund të prishin parsimin.
- Faqja mbështetet në cookies sesioni që vendosen nga kërkesa GET fillestare; ndryshimet e menaxhimit të sesionit nga QKB mund të prishin mbledhjen.
- Kolektor i njoftimeve QKB (`qkb_notices_experimental`) mbetet eksperimental dhe nuk ofron të dhëna analitike të besueshme.
- Mbledhja historike e plotë nëpërmjet QKB-it nuk mbështetet aktualisht; vetëm kërkesat e datave ose NIPT specifik janë të disponueshëm.

### 6.3 Bashkimi midis Burimeve

- Bashkimi i vetëm i mbrojtur automatikisht është ekzakt `winner_nipt == business_nipt`.
- Rreshtat e APP-it pa `winner_nipt` nuk mund të bashkohen me QKB-in me siguri automatike.
- Bashkimet e bazuara vetëm në emra janë të rrezikshme dhe nuk mbështeten si parazgjedhje.

---

## 7. Konsideratat Etike dhe Ligjore

### 7.1 Burimi Publik dhe Aksesi

Të dhënat e mbledhura janë plotësisht publike: eksportet e APP-it janë publikuar zyrtarisht nga autoriteti publik i prokurimit, ndërkohë që QKB-i është regjistri tregtar zyrtar i aksesueshëm nga publiku. Asnjë mekanizëm autentifikimi i mbrojtur, asnjë të dhënë private dhe asnjë informacion i kufizuar nuk shkelet.

### 7.2 Mbledhja Responsabile

- Kolektori respekton kufijt e burimeve nëpërmjet riprovimeve të moderuara dhe chunking ditor.
- Sesionet janë transaksionale dhe nuk mbajnë cookie sesioni apo token autentifikimi.
- Asnjë e dhënë sensitive (fjalëkalime, token, kredenciale) nuk ruhet në kod ose skedarë të gjurmueshëm.
- Skedari `.env` me konfigurim real është i përjashtuar nga git dhe nuk ruhet kurrë në depo.

### 7.3 Mbrojtja e të Dhënave Personale

- Të dhënat e regjistrit tregtar të QKB-it mund të përmbajnë emra administratorësh ose aksionarësh (nëpërmjet fushave `administrators_text`, `ownership_text`). Këto fusha trajtohen si kontekst explorativ dhe jo si identifikues individualë parësorë.
- Analizat e propozuara mbështeten kryesisht në identifikues legjalistë (NIPT) dhe metrikë agregate, jo në të dhëna individuale personale.
- Projekti funksionon si prototip kërkimor akademik; çdo përdorim tjetër i të dhënave duhet të respektojë legjislacionin e aplikueshëm mbi mbrojtjen e të dhënave personale.

### 7.4 Transparenca dhe Auditueshmëria

- Çdo artefakt i papërpunuar mbahet në disk me hash SHA-256 për verifikim të mëvonshëm.
- Provenienca e plotë ruhet nga burimi i gjallë deri te tabela analitike.
- Sistemi i auditimit mundëson identifikimin dhe karantinimin e rreshtave të dëmtuara.

---

## 8. Analizat e Pritshme pas Mbledhjes

Bazuar në strukturën aktuale të shtresave të normalizimit dhe karakteristikave, analizat kryesore kërkimore të pritshme janë:

### 8.1 Analiza e Prokurimit

- Shpërndarja e vlerave të kontratave sipas llojit të procedurës dhe organiit kontraktues
- Norma e anulimit dhe pezullimit të prokurimeve sipas subjektit fitues
- Numri dhe vlera e prokurimit sipas periudhës kohore (vit, muaj)
- Ekspozimi kumulativ i prokurimit për secilën kompani me NIPT ekzakt

### 8.2 Analiza e Regjistrit

- Shpërndarja e kompanive sipas formës ligjore dhe statusit regjistrues
- Viti dhe koha e regjistrimit si kontekst historik
- Mbulimi i sinjalizimeve të riskut (`has_red_flags`) në universin e kompanive fituese

### 8.3 Analiza e Bashkuar APP–QKB

- Mosha e kompanisë në momentin e prokurimit të parë dhe të fundit (`company_age_days_at_first_procurement`, `company_age_days_at_last_procurement`)
- Statusi regjistrues i kompanive fituese të prokurimit
- Ndërlidhja midis karakteristikave të regjistrit dhe vëllimit/vlerës së prokurimit
- Analiza e kompanive me NIPT të bashkueshëm si universi parësor i studimit

### 8.4 Analiza Explorativë

- Profilizimi i mungesës së të dhënave dhe mbulimit të bashkimit
- Identifikimi i ditëve të kufizuara me 50 rreshta QKB si tregues i vëllimit të lartë
- Auditimi i integritetit të artefakteve të papërpunuara para analizave finale

---

## 9. Gjendja Aktuale e Implementimit

### 9.1 Kolektorët e Mbështetur

| Komponentë | Gjendja |
|---|---|
| Kolektori APP (`app_exports`) | Operacional dhe i mbështetur |
| Kolektori QKB (`qkb_search`) | Operacional dhe i mbështetur |
| Kolektor eksperimental njoftimesh QKB | Eksperimental; nuk ushqen tabelat analitike |
| Normalizimi APP | Operacional dhe i ripërsëritshëm |
| Normalizimi QKB | Operacional dhe i ripërsëritshëm |
| Karakteristikat APP, QKB, të bashkuara | Operacionale dhe të ripërsëritshme |
| Profilizimi | Operacional; vetëm-lexim |
| Auditimi i integritetit | Operacional |
| Kontrollet e tymit (smoke checks) | Operacionale; të jashtme dhe manuale |
| Planifikuesi (scheduler) | Operacional; vetëm APP dhe QKB-search |
| Menaxhimi i migrimeve (Alembic) | Operacional |
| Rifillimi i gamës së datave QKB | Operacional; i mbështetur nga baza e të dhënave |

### 9.2 Baza e të Dhënave

Baza e të dhënave e parazgjedhur është MySQL (nëpërmjet PyMySQL), e menaxhuar me migrime Alembic. Mbështetja për PostgreSQL dhe SQLite është e disponueshme nëpërmjet konfigurimit të `DATABASE_URL`.

### 9.3 Suite-i i Testeve

Suite-i aktual i testeve përfshin:
- Teste të shpejta njësite (unit) për parsimin, normalizimin, karakteristikat, profilizimin, semantikën, planifikuesin, auditimin, kontrollet e tymit dhe utilitetet
- Teste të bazës së të dhënave
- Suite opsionale e integrimit MySQL
- Asnjë test automatik live mbi burimet e gjalla

---

## 10. Kufizimet Aktuale të Projektit

1. **Kufiri i 50 rreshtave QKB:** Çdo kërkesë QKB kthen maksimum 50 rreshta. Kërkesat ditore me saktësisht 50 rreshta sinjalizohen si potencialisht të kufizuara, por nuk ka mjet automatik për t'i kapërcyer ato pa ndërhyrje manuale.

2. **Varësia ndaj JavaScript-it inline të QKB-it:** Parsimi i rezultateve të kërkimit QKB mbështetet në ekstraksionin e variablit JavaScript inline `response`. Çdo ndryshim në faqen e burimit mund të prishë mbledhjen.

3. **Nuk ka API të strukturuar nga burimet:** As APP-i dhe as QKB-i nuk ofrojnë API zyrtarë për aksesin programatik; mbledhja bëhet nëpërmjet HTML form-POST dhe eksporteve CSV.

4. **Kolektor njoftimesh jo i plotë:** Kolektor `qkb_notices_experimental` nuk ushqen asnjë tabelë normalizimi ose karakteristikash; mbetet vetëm fotografim explorativ.

5. **Bashkimi i kufizuar automatik:** Vetëm bashkimi ekzakt NIPT mbështetet si parazgjedhje. Kompanite pa `winner_nipt` të APP-it mbeten në grupin vetëm APP.

6. **Mbledhja historike e kufizuar QKB:** Nuk ka mekanizëm të plotë për mbledhjen e të dhënave historike të regjistrit QKB para periudhës aktuale operative të kolektorit.

7. **Prototip, jo prodhim:** Projekti është i dizajnuar si prototip kërkimor. Nuk ka monitorim automatik të thyerjes, alarm ndaj drift-it të kontratës, ose pipeline prodhimi të harden-izuar.

8. **Eksportet APP sipas vitit:** Kolektori APP mbledh eksporte vjetore; granulariteti sub-vjetor nuk është i disponueshëm nëpërmjet këtij mekanizmi.

---

## 11. Fazat e Planifikuara Pasuese

Fazat e mëposhtme janë identifikuar si prioritete për evoluimin e projektit, bazuar në gjendjen aktuale dhe kufizimet e dokumentuara:

### Faza 1 — Harden-izimi i Kolektorit QKB
- Zbulimi dhe zbatimi i strategjive për kapërcimin e kufirit 50-rreshta QKB (p.sh. ndarje sipas kategorisë, NIPT, ose parametrave të tjerë të disponueshëm)
- Shtimi i monitorimit automatik ndaj drift-it të selektorëve të faqes QKB

### Faza 2 — Mbledhja e Dokumenteve QKB
- Zbatimi i logjikës për mbledhjen e dokumenteve dhe njoftimeve individuale të QKB-it bazuar në NIPT të mbledhur tashmë nga `qkb_search`
- Integrimi i artefakteve PDF dhe strukturimi i metadatave të tyre

### Faza 3 — Pasurimi i Shtresës Analitike
- Implementimi i kandidatëve të karakteristikave temporale (mosha e kompanisë, kadenca e prokurimit)
- Shtimi i normave të anulimit/pezullimit si karakteristika në nivel kompanie
- Krijimi i raporit buxhet-ndaj-vlerë-fituese ku të dy shumat janë të disponueshme

### Faza 4 — Automatizimi dhe Monitorimi
- Automatizimi i kontrollit të integritetit të artefakteve pas çdo ekzekutimi kolektori
- Shtimi i alarmeve për ditë potencialisht të kufizuara QKB
- Vendosja e monitorimit të detyrueshëm të kontratës së burimit si pjesë e pipeline-it CI/CD

### Faza 5 — Shkallëzimi dhe Infrastruktura
- Migrimi nga arkitektura prototip drejt një pipeline prodhimi të qëndrueshëm
- Shqyrtimi i ruajtjes së artefakteve në objekt-storage (p.sh. S3 ose ekuivalent) për koleksione të mëdha
- Shtimi i shtresës dashboard/API (Laravel ose ekuivalent) për vizualizim dhe akses të të dhënave
