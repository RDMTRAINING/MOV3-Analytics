-- =====================================================================
-- M0V3 ANALYTICS - DATA GOVERNANCE & AUDIT TRAIL (GDPR ART. 9)
-- Migrazione Schema Supabase: Soft-Delete (is_valid) e Tracciamento Modifiche
-- =====================================================================

-- 1. ESTENSIONE TABELLA: rpe_sessioni
-- is_valid: determina se il record partecipa ai calcoli analitici (default TRUE)
-- modificato_da_staff: flag che scatta alla prima modifica del coach (default FALSE)
-- rpe_originale: archivia il primo voto RPE inserito dall'atleta
-- durata_originale_min: archivia la durata originale inserita dall'atleta
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS is_valid BOOLEAN DEFAULT TRUE;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS modificato_da_staff BOOLEAN DEFAULT FALSE;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS rpe_originale NUMERIC;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS durata_originale_min NUMERIC;

-- Imposta default retroattivo per righe esistenti
UPDATE rpe_sessioni SET is_valid = TRUE WHERE is_valid IS NULL;
UPDATE rpe_sessioni SET modificato_da_staff = FALSE WHERE modificato_da_staff IS NULL;

-- 2. ESTENSIONE TABELLA: wellness_mattutino
-- is_valid: determina se il record partecipa ai calcoli analitici (default TRUE)
-- modificato_da_staff: flag che scatta alla prima modifica del coach (default FALSE)
-- wellness_originale_json: archivia i 5 parametri originali (Sonno, Fatica, DOMS, Stress, Umore)
ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS is_valid BOOLEAN DEFAULT TRUE;
ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS modificato_da_staff BOOLEAN DEFAULT FALSE;
ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS wellness_originale_json JSONB;

-- Imposta default retroattivo per righe esistenti
UPDATE wellness_mattutino SET is_valid = TRUE WHERE is_valid IS NULL;
UPDATE wellness_mattutino SET modificato_da_staff = FALSE WHERE modificato_da_staff IS NULL;

-- 3. INDICI DI PERFORMANCE SUI RECORD VALIDI
CREATE INDEX IF NOT EXISTS idx_rpe_is_valid ON rpe_sessioni(atleta_id, is_valid, data DESC);
CREATE INDEX IF NOT EXISTS idx_wellness_is_valid ON wellness_mattutino(atleta_id, is_valid, data DESC);
