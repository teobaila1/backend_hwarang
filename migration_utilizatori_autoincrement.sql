-- ===== BACKUP & SAFETY =====
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- 1) back-up non-destructive: păstrăm vechiul tabel ca să te poți întoarce dacă vrei
ALTER TABLE utilizatori RENAME TO utilizatori_backup_legacy;

-- 2) schema nouă: id INTEGER PRIMARY KEY AUTOINCREMENT
CREATE TABLE utilizatori_new (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  username           TEXT,
  parola             TEXT,
  rol                TEXT,
  email              TEXT,
  grupe              TEXT,
  copii              TEXT,
  is_placeholder     INTEGER DEFAULT 0,
  claim_code         TEXT,
  created_by_trainer INTEGER DEFAULT 0
);

-- 3) copiem rândurile CU id (le păstrăm identice)
INSERT INTO utilizatori_new (
  id, username, parola, rol, email, grupe, copii, is_placeholder, claim_code, created_by_trainer
)
SELECT
  id, username, parola, rol, email, grupe, copii,
  COALESCE(is_placeholder, 0), claim_code, COALESCE(created_by_trainer, 0)
FROM utilizatori_backup_legacy
WHERE id IS NOT NULL
ORDER BY id;

-- 4) sincronizăm seq-ul AUTOINCREMENT cu MAX(id) existent
--    (dacă tabela sqlite_sequence nu există încă, INSERT OR REPLACE o va crea la primul AUTOINCREMENT)
INSERT OR REPLACE INTO sqlite_sequence (name, seq)
SELECT 'utilizatori_new', IFNULL(MAX(id), 0) FROM utilizatori_new;

-- 5) copiem rândurile FĂRĂ id (le lăsăm să primească autoincrement)
INSERT INTO utilizatori_new (
  username, parola, rol, email, grupe, copii, is_placeholder, claim_code, created_by_trainer
)
SELECT
  username, parola, rol, email, grupe, copii,
  COALESCE(is_placeholder, 0), claim_code, COALESCE(created_by_trainer, 0)
FROM utilizatori_backup_legacy
WHERE id IS NULL;

-- 6) indexuri utile (non-UNIQUE ca să nu-ți pice pe duplicatele existente)
CREATE INDEX IF NOT EXISTS idx_utilizatori_username_nocase
  ON utilizatori_new(username COLLATE NOCASE);

CREATE INDEX IF NOT EXISTS idx_utilizatori_rol_nocase
  ON utilizatori_new(rol COLLATE NOCASE);

-- 7) redenumim tabela nouă la numele original
ALTER TABLE utilizatori_new RENAME TO utilizatori;

COMMIT;
PRAGMA foreign_keys = ON;
