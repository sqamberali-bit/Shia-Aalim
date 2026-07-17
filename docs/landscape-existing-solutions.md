# Shia Islamic AI & Data Sources — Research Landscape

> **Status:** Research snapshot compiled **2026-07**. This document is produced
> by the project's autonomous research loop (Objective 1c / "Existing Solutions")
> and is refreshed periodically. Every entry links to a real, reachable
> resource. GitHub metadata (license, last activity, stars) was verified via the
> GitHub API; website content was confirmed via web search. Items that could not
> be independently verified are flagged. Vendor accuracy/citation claims for
> closed products are **marketing, not independently validated.**

---

## Deliverable 1 — Existing Solutions Landscape

**Sect column:** Shia = Twelver-focused; General = pan-Islamic / multi-madhab; Sunni = Sunni-source-based.

### 1a. Shia-specific systems

| System | URLs | Owner | Open source / License | Self-host | Knowledge sources | Citations | Lecture gen | Strengths | Weaknesses | Maintenance |
|---|---|---|---|---|---|---|---|---|---|---|
| **Hyder.ai** | [iric.org announcement](https://iric.org/introducing-hyder-ai-the-first-ai-model-trained-on-shia-islamic-teachings/); "Shia Ithna Asheri Toolkit" app | Islamic Research & Information Center (IRIC) | No (proprietary) | No | ~300,000 data points from Twelver Shia books/articles | Claimed source-aligned; unverified | No | First AI marketed as trained specifically on Twelver teachings; large curated corpus | Not conversational; closed; citation quality unverifiable | Product active |
| **WisQu** | [wisqu.ai](https://wisqu.ai/) · [launch post](https://wisqu.ai/2025/03/wisqu-first-shia-ai-chatbot/) | Wisqu.ai team | No (proprietary) | No | Qur'an, hadith, Shia scholarly interpretations | Grounds in Shia texts; self-claimed "96%" (marketing) | No | Explicitly Shia-grounded conversational chatbot; free | Closed; accuracy claim unvalidated; fatwa-like output w/o scholar review | Active (2025) |
| **Thaqalayn.net** | [thaqalayn.net](https://thaqalayn.net/) | Community project | Website free; not a code repo | No | Primary Twelver hadith (Al-Kafi, Faqih, Tahdhib, Istibsar…) + Qur'an, EN translations & metadata | Structured per-hadith references + grading notes | No | Best-structured free digital Twelver hadith library | Not an AI system; keyword search only | Actively maintained |
| **ThaqalaynAPI** | [github](https://github.com/MohammedArab1/ThaqalaynAPI) · [thaqalayn-api.net](https://www.thaqalayn-api.net/) | Mohammed Arab | **Yes — GPL-3.0** | **Yes** (Node/Express + MongoDB; Docker) | Scrapes thaqalayn.net weekly; food-ruling data | Preserves thaqalayn citations; EN+AR search | No | REST **and** GraphQL; Swagger; auto refresh; ideal RAG feed | Depends on upstream scraping; no semantic search | **Active** (last push 2026-07-11; 38★) |
| **Thaqalyn (iOS)** | [github](https://github.com/i4ali/thaqalyn) | i4ali | Public; no license file | Yes (Swift) | Offline Shia hadith + Qur'an + tafsir commentary | Inherits thaqalayn citations | No | AI-enhanced metadata; multi-language; offline | Early stage; iOS-only; no license | Active (2026-07) |

### 1b. General / Sunni Islamic AI systems

| System | URLs | Owner | Open source / License | Self-host | Knowledge sources | Citations | Strengths | Weaknesses | Maintenance |
|---|---|---|---|---|---|---|---|---|---|
| **Ansari** | [ansari.chat](https://ansari.chat/) · [backend](https://github.com/ansari-project/ansari-backend) · [skill](https://github.com/ansari-project/ansari-skill) | Ansari Project | **Yes — MIT** | **Yes** (FastAPI; OpenAI/Claude + Kalemat) | Qur'an (Kalemat API), hadith; Q&A | RAG with citations; improving | Most mature open-source Islamic RAG; Claude-based; Claude Code skill; strong docs | General/Sunni-leaning corpus (not Twelver) | **Active** (119★, 2026-05) |
| **IslamAI (oshoura)** | [github](https://github.com/oshoura/IslamAI) | oshoura | Public; license unconfirmed | Yes (Next.js + Langchain + Pinecone) | Qur'an, hadith, Seerah | Returns 4 source docs/answer | Clean RAG reference implementation | General; activity unconfirmed | Unconfirmed |
| **Quran-Hadith-Chatbot** | [github](https://github.com/hammadali1805/Quran-Hadith-Chatbot) | hammadali1805 | Public | Yes (ChromaDB + MiniLM) | Qur'an + Bukhari & Muslim (Sunni) | Similarity search w/ source | Good beginner RAG w/ query expansion | Sunni-only; small corpus | Community |
| **SunnahGPT** | [github](https://github.com/hazemabdelkawy/SunnahGPT) | hazemabdelkawy | Public | Yes | Scrapes sunnah.com; GPT-3.5 embeddings | Hadith-level embeddings | Demonstrates hadith embedding pipeline | **Sunni**; demo scale | Community |
| **Ask Sheikh AI** | [asksheikh.ai](https://asksheikh.ai/) | Ask Sheikh | No (proprietary) | No | 7 madhabs incl. **Twelver Shia** (selectable) | Not documented | Lets user pick Twelver madhab | Closed; citation quality unverified | Active |
| **SheikhGPT / MuslimGPT** | [sheikhgpt.ai](https://sheikhgpt.ai/) · [themuslimgpt.com](https://themuslimgpt.com/) | resp. vendors | No (proprietary) | No | Undisclosed / Qur'an & Sunnah | Not documented | Polished consumer apps | Closed; opaque/Sunni-oriented | Active |
| **Hudgent** | [publication](https://app.readytensor.ai/publications/hudgent-an-open-source-islamic-ai-agent-54Pa6CrvBvjU) | Ready Tensor author | Described open-source | Likely | Verified sources w/ academic-citation requirement | Enforces citation + checks | Citation-discipline focus | Small/early; general | Publication-stage |

### 1c. Qur'an / hadith data infrastructure (not chatbots, but core infra)

| Platform | URLs | Owner | License | Self-host | Content | Notes |
|---|---|---|---|---|---|---|
| **Quranic Universal Library (QUL)** | [qul.tarteel.ai](https://qul.tarteel.ai/) · [github](https://github.com/TarteelAI/quranic-universal-library) | Tarteel AI | **MIT** | Yes (Rails) | Qur'an scripts, translations, tafsir, word-by-word, morphology, recitations, Mushaf layouts | **Very active** (922★, 2026-07); best single Quran-data hub |
| **Quran Foundation / Quran.com API** | [api-docs.quran.foundation](https://api-docs.quran.foundation/) | Quran.com | Proprietary (OAuth2; **caching >1 wk & scraping prohibited**) | No | Verses, translations, tafsir, audio, search | Restrictive terms — check licensing before ingestion |
| **sunnah.com API** | [developers](https://sunnah.com/developers) · [github](https://github.com/sunnah-com/api) | sunnah.com | Code public; API key | Partial | Canonical **Sunni** hadith | 487★; **Sunni** (note for a Shia system) |
| **Quranic Arabic Corpus** | [corpus.quran.com](https://corpus.quran.com/download/) | Kais Dukes | **GPL** (attribution + link) | Yes | Morphology, syntax, word-by-word | Gold-standard Qur'an morphology |

**Verification notes (D1):** GitHub license/last-push/stars verified via GitHub API, current 2026-07-17. Hosted products are closed-source; their claims are vendor marketing, **not** independently validated. **No surveyed system advertises automated lecture/khutbah generation** — a clear differentiation gap this project targets. Only **Hyder.ai** and **WisQu** are purpose-built for Twelver Shia; **Ask Sheikh AI** offers a selectable Twelver mode; the rest are general or Sunni-sourced.

---

## Deliverable 2 — Open & Verifiable Data Sources

**Sect:** Shia = Twelver; General = pan-Islamic/Quran; Sunni = Sunni hadith.

### 2a. Shia (Twelver) text sources

| Source | URL | Content | Formats | Languages | Licensing / Terms | Access |
|---|---|---|---|---|---|---|
| **Al-Islam.org (DILP)** | [al-islam.org](https://al-islam.org/) | Largest Twelver library: Qur'an+translations, tafsir, hadith, aqaid, fiqh, du'a | HTML; many PDF/EPUB | 40+ (EN/AR/FA/UR…) | Free non-commercial — **verify per-book copyright**; no public API | Scraping / per-book download |
| **Thaqalayn.net** | [thaqalayn.net](https://thaqalayn.net/) | Al-Kafi, Faqih, Tahdhib, Istibsar + others; Qur'an; gradings | HTML; API below | AR+EN | Free; attribution expected | Website + ThaqalaynAPI |
| **ThaqalaynAPI** | [github](https://github.com/MohammedArab1/ThaqalaynAPI) · [api](https://www.thaqalayn-api.net/) · [GraphQL](https://www.thaqalayn-api.net/graphql) | Machine-readable mirror of thaqalayn hadith (weekly) | **REST+GraphQL → JSON**; Mongo dumps | AR+EN | **GPL-3.0** | Public API / self-host — **best structured Shia hadith feed** |
| **Hubeali.com** | [hubeali.com](https://hubeali.com/) · [epub](https://hubeali.com/online-books/epub/) | **Al-Kafi (8 vols), Bihar al-Anwar**, others (translated) | **PDF, EPUB**, HTML | EN, UR (+AR) | Free for religious use; attribution | Direct download (predictable URLs) |
| **Shiavault** | [shiavault.com](https://www.shiavault.com/) · [github](https://github.com/shiavault/shiavault-library) | Broad Twelver collection (hadith, aqaid, history, commentary) | **Markdown source** → HTML/EPUB/MOBI | Mainly EN | Open; contributable | **Clone repo for clean Markdown** — excellent for ingestion |
| **Shia Online Library** | [shiaonlinelibrary.com](https://shiaonlinelibrary.com/) | Large Arabic Twelver corpus | HTML (searchable) | Arabic | Free; no API | Web (scrape) |
| **Shia-Maktab** | [shia-maktab.info](https://www.shia-maktab.info/index.php/en/) | Digitized Shia books, correct AR/UR fonts | PDF (some EPUB) | AR, UR, EN | Free | Direct download |

> **Structured Al-Kafi / Bihar / Nahj al-Balagha / Sahifa Sajjadiya / Mafatih al-Jinan:** The most reliable *structured* editions are **Thaqalayn.net + ThaqalaynAPI** (Al-Kafi, Faqih, Tahdhib, Istibsar as clean JSON) and **Hubeali** (Al-Kafi, Bihar as PDF/EPUB). Al-Islam.org hosts Nahj al-Balagha, Sahifa Sajjadiya, Mafatih al-Jinan (HTML/PDF/EPUB). **No single dedicated GitHub JSON dataset** isolates Nahj al-Balagha / Sahifa / Mafatih — extract from al-islam.org / shiavault / hubeali.

### 2b. General Qur'an sources

| Source | URL | Content | Formats | Licensing | Access |
|---|---|---|---|---|---|
| **Tanzil** | [tanzil.net/download](https://tanzil.net/download/) | Verified Qur'an text + many translations | **XML, plaintext, SQL** | Free w/ **attribution + link** | Direct download / [risan/tanzil-downloader](https://github.com/risan/tanzil-downloader) |
| **QuranEnc** | [quranenc.com](https://quranenc.com/en/home/api/) | Vetted translations, sura/ayah level | **JSON API** | Free; attribution | REST JSON |
| **QUL (Tarteel)** | [qul.tarteel.ai](https://qul.tarteel.ai/) | Text, translations, tafsir, WBW, morphology, recitations | **JSON, SQLite, text** | **MIT** (code) | Web download + open code |
| **quran-json / fawazahmed0** | [risan/quran-json](https://github.com/risan/quran-json) · [fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api) | Qur'an text + translations | JSON / CDN | Open | Clone / CDN |
| **Al Quran Cloud** | [alquran.cloud/api](https://alquran.cloud/api) | Text, translations, audio | JSON REST | Free | REST |

### 2c. Sunni & corpus-scale sources (use with sect awareness)

| Source | URL | Sect | Content | Formats | Licensing | Access |
|---|---|---|---|---|---|---|
| **OpenITI Corpus** | [github](https://github.com/OpenITI/RELEASE) · [openiti.org](https://openiti.org/) | Mixed | ~1.5B-word premodern Arabic/Persian corpus | mARkdown/plaintext | **CC BY-NC-SA** (verify per-text) | Clone / Zenodo (61★) |
| **al-Maktaba al-Shamela** (via OpenITI/KITAB) | [kitab-project.org](https://kitab-project.org/docs/openITI) | Mixed/Sunni-heavy | Largest classical Arabic library | Text | Varies; academic | OpenITI/KITAB tooling |
| **AhmedBaset/hadith-json** | [github](https://github.com/AhmedBaset/hadith-json) | **Sunni** | 50,884 hadith, 17 books (AR+EN) | **JSON** | Open | Clone (291★) |
| **mhashim6/Open-Hadith-Data** | [github](https://github.com/mhashim6/Open-Hadith-Data) | **Sunni** | 9 books incl. the Six, w/ diacritics | **CSV, SQLite** | Open | Clone (220★) |

**Verification notes (D2):** GitHub sources verified via API. Hosted libraries (al-islam.org, thaqalayn.net, hubeali.com, tanzil.net, shiaonlinelibrary.com) return HTTP 403 to automated fetching (bot protection) but are long-established and confirmed via search + known URL structures; **no documented bulk-download API** for al-islam.org or shiaonlinelibrary.com (scraping required). **Licensing caveats for the pipeline:** Quran Foundation API forbids caching >1 wk & scraping; Tanzil and Quranic Arabic Corpus require attribution + backlink; OpenITI is CC BY-NC-SA (non-commercial); per-book copyright on al-islam.org/hubeali varies. **Highest-value clean-ingestion targets for a Twelver system:** ThaqalaynAPI (JSON), Shiavault (Markdown on GitHub), Hubeali (EPUB/PDF), Al-Islam.org (breadth), plus Tanzil/QUL for Qur'an and OpenITI for classical depth.
