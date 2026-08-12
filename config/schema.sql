PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  license TEXT,
  sha256 TEXT,
  downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  testament TEXT NOT NULL CHECK(testament IN ('OT','NT')),
  osis TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS texts (
  id INTEGER PRIMARY KEY,
  testament TEXT NOT NULL CHECK(testament IN ('OT','NT')),
  edition TEXT NOT NULL,
  source_id INTEGER REFERENCES sources(id),
  UNIQUE(testament, edition)
);

CREATE TABLE IF NOT EXISTS verses (
  id INTEGER PRIMARY KEY,
  book_id INTEGER NOT NULL REFERENCES books(id),
  chapter INTEGER NOT NULL,
  verse INTEGER NOT NULL,
  reference TEXT NOT NULL UNIQUE,
  text_id INTEGER REFERENCES texts(id),
  UNIQUE(book_id, chapter, verse)
);

CREATE TABLE IF NOT EXISTS lemmas (
  id INTEGER PRIMARY KEY,
  testament TEXT NOT NULL CHECK(testament IN ('OT','NT')),
  language TEXT NOT NULL CHECK(language IN ('Hebrew','Aramaic','Greek')),
  lemma TEXT NOT NULL,
  normalized TEXT NOT NULL,
  transliteration TEXT,
  root TEXT,
  UNIQUE(testament, language, normalized)
);

CREATE TABLE IF NOT EXISTS strongs (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  language TEXT NOT NULL,
  lemma_id INTEGER REFERENCES lemmas(id),
  gloss TEXT,
  definition TEXT,
  source_id INTEGER REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS morphology (
  id INTEGER PRIMARY KEY,
  language TEXT NOT NULL,
  code TEXT NOT NULL,
  description TEXT,
  source_id INTEGER REFERENCES sources(id),
  UNIQUE(language, code, source_id)
);

CREATE TABLE IF NOT EXISTS lexicon_entries (
  id INTEGER PRIMARY KEY,
  lemma_id INTEGER REFERENCES lemmas(id),
  strongs_id INTEGER REFERENCES strongs(id),
  source TEXT NOT NULL,
  headword TEXT,
  definition TEXT,
  entry_text TEXT,
  source_id INTEGER REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS words (
  id INTEGER PRIMARY KEY,
  verse_id INTEGER NOT NULL REFERENCES verses(id),
  position INTEGER NOT NULL,
  surface TEXT NOT NULL,
  normalized TEXT,
  lemma_id INTEGER REFERENCES lemmas(id),
  morphology_id INTEGER REFERENCES morphology(id),
  strongs_id INTEGER REFERENCES strongs(id),
  source_id INTEGER REFERENCES sources(id),
  edition TEXT NOT NULL,
  edition_membership TEXT,
  gloss TEXT,
  UNIQUE(verse_id, position, edition)
);

CREATE TABLE IF NOT EXISTS glossary (
  id INTEGER PRIMARY KEY,
  lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
  language TEXT NOT NULL DEFAULT 'id',
  core_gloss TEXT,
  semantic_range TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','approved','deprecated')),
  UNIQUE(lemma_id, language)
);

CREATE TABLE IF NOT EXISTS translations (
  id INTEGER PRIMARY KEY,
  verse_id INTEGER NOT NULL REFERENCES verses(id),
  literal TEXT,
  natural TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','audited','approved')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(verse_id)
);

CREATE TABLE IF NOT EXISTS translation_decisions (
  id INTEGER PRIMARY KEY,
  translation_id INTEGER NOT NULL REFERENCES translations(id),
  word_id INTEGER REFERENCES words(id),
  lemma_id INTEGER REFERENCES lemmas(id),
  source_form TEXT,
  chosen_rendering TEXT NOT NULL,
  reason TEXT,
  alternative TEXT,
  decided_by TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audits (
  id INTEGER PRIMARY KEY,
  translation_id INTEGER NOT NULL REFERENCES translations(id),
  auditor TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT,
  raw_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_words_lemma ON words(lemma_id);
CREATE INDEX IF NOT EXISTS idx_words_strongs ON words(strongs_id);
CREATE INDEX IF NOT EXISTS idx_words_verse ON words(verse_id);
CREATE INDEX IF NOT EXISTS idx_decisions_lemma ON translation_decisions(lemma_id);
CREATE INDEX IF NOT EXISTS idx_lexicon_lemma ON lexicon_entries(lemma_id);

CREATE VIEW IF NOT EXISTS v_lemma_occurrences AS
SELECT l.id AS lemma_id, l.lemma, l.language,
       w.id AS word_id, w.surface, w.edition,
       v.reference, m.code AS morphology_code,
       s.code AS strongs_code
FROM words w
JOIN lemmas l ON l.id = w.lemma_id
JOIN verses v ON v.id = w.verse_id
LEFT JOIN morphology m ON m.id = w.morphology_id
LEFT JOIN strongs s ON s.id = w.strongs_id;
