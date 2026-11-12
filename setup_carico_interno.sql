-- =====================================================================
-- M0V3 ANALYTICS - SETUP DATABASE CARICO INTERNO & WELLNESS
-- Esegui questo script nell'SQL Editor del pannello di Supabase
-- =====================================================================

-- 1. Funzione di utilità per aggiornare in automatico il campo updated_at
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. TABELLA: wellness_mattutino
-- Raccoglie la rilevazione soggettiva mattutina (1 volta al giorno per atleta)
CREATE TABLE IF NOT EXISTS wellness_mattutino (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    atleta_id UUID NOT NULL REFERENCES atleti(id) ON DELETE CASCADE,
    profilo_id UUID REFERENCES profili(id) ON DELETE SET NULL,
    data DATE NOT NULL DEFAULT CURRENT_DATE,
    sonno_qualita INT NOT NULL CHECK (sonno_qualita BETWEEN 1 AND 10),
    fatica INT NOT NULL CHECK (fatica BETWEEN 1 AND 10),
    stress INT NOT NULL CHECK (stress BETWEEN 1 AND 10),
    umore INT NOT NULL CHECK (umore BETWEEN 1 AND 10),
    doms INT NOT NULL CHECK (doms BETWEEN 1 AND 10),
    note TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL,
    -- Vincolo: massimo 1 compilazione al giorno per atleta (consente UPSERT pulito)
    CONSTRAINT uq_wellness_atleta_data UNIQUE (atleta_id, data)
);

-- Trigger per updated_at su wellness_mattutino
DROP TRIGGER IF EXISTS trg_wellness_updated_at ON wellness_mattutino;
CREATE TRIGGER trg_wellness_updated_at
BEFORE UPDATE ON wellness_mattutino
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();

-- 3. TABELLA: rpe_sessioni
-- Raccoglie il carico interno di ogni seduta (sRPE = durata_minuti * rpe)
CREATE TABLE IF NOT EXISTS rpe_sessioni (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    atleta_id UUID NOT NULL REFERENCES atleti(id) ON DELETE CASCADE,
    profilo_id UUID REFERENCES profili(id) ON DELETE SET NULL,
    data DATE NOT NULL DEFAULT CURRENT_DATE,
    slot INT NOT NULL DEFAULT 1 CHECK (slot >= 1),
    tipologia TEXT NOT NULL CHECK (tipologia IN ('Tennis', 'Preparazione Fisica', 'Gym', 'Recupero', 'Altro')),
    durata_minuti INT NOT NULL CHECK (durata_minuti > 0),
    rpe INT NOT NULL CHECK (rpe BETWEEN 0 AND 10),
    -- Calcolo matematico automatico a livello di database
    carico_interno INT GENERATED ALWAYS AS (durata_minuti * rpe) STORED,
    note TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL,
    -- Vincolo: uno slot univoco per data per atleta
    CONSTRAINT uq_rpe_atleta_data_slot UNIQUE (atleta_id, data, slot)
);

-- Trigger per updated_at su rpe_sessioni
DROP TRIGGER IF EXISTS trg_rpe_updated_at ON rpe_sessioni;
CREATE TRIGGER trg_rpe_updated_at
BEFORE UPDATE ON rpe_sessioni
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();

-- 4. INDICI DI PERFORMANCE (per query rapide nel portale coach e mobile)
CREATE INDEX IF NOT EXISTS idx_wellness_atleta_data ON wellness_mattutino(atleta_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_rpe_atleta_data ON rpe_sessioni(atleta_id, data DESC);

-- 5. ABILITAZIONE ROW LEVEL SECURITY (RLS)
ALTER TABLE wellness_mattutino ENABLE ROW LEVEL SECURITY;
ALTER TABLE rpe_sessioni ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- POLICIES PER: wellness_mattutino
-- ---------------------------------------------------------------------

-- A. Super-Admin: controllo totale
DROP POLICY IF EXISTS "wellness_super_admin_all" ON wellness_mattutino;
CREATE POLICY "wellness_super_admin_all" ON wellness_mattutino
FOR ALL
USING (
    EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

-- B. Coach / Staff: lettura degli atleti assegnati
DROP POLICY IF EXISTS "wellness_coach_select" ON wellness_mattutino;
CREATE POLICY "wellness_coach_select" ON wellness_mattutino
FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = wellness_mattutino.atleta_id
    )
);

-- C. Atleta: lettura dei propri dati
DROP POLICY IF EXISTS "wellness_atleta_select" ON wellness_mattutino;
CREATE POLICY "wellness_atleta_select" ON wellness_mattutino
FOR SELECT
USING (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = wellness_mattutino.atleta_id
    )
);

-- D. Atleta: inserimento dei propri dati
DROP POLICY IF EXISTS "wellness_atleta_insert" ON wellness_mattutino;
CREATE POLICY "wellness_atleta_insert" ON wellness_mattutino
FOR INSERT
WITH CHECK (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = wellness_mattutino.atleta_id
    )
);

-- E. Atleta: aggiornamento dei propri dati (modifica libera dello storico)
DROP POLICY IF EXISTS "wellness_atleta_update" ON wellness_mattutino;
CREATE POLICY "wellness_atleta_update" ON wellness_mattutino
FOR UPDATE
USING (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = wellness_mattutino.atleta_id
    )
);

-- ---------------------------------------------------------------------
-- POLICIES PER: rpe_sessioni
-- ---------------------------------------------------------------------

-- A. Super-Admin: controllo totale
DROP POLICY IF EXISTS "rpe_super_admin_all" ON rpe_sessioni;
CREATE POLICY "rpe_super_admin_all" ON rpe_sessioni
FOR ALL
USING (
    EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

-- B. Coach / Staff: lettura degli atleti assegnati
DROP POLICY IF EXISTS "rpe_coach_select" ON rpe_sessioni;
CREATE POLICY "rpe_coach_select" ON rpe_sessioni
FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = rpe_sessioni.atleta_id
    )
);

-- C. Atleta: lettura delle proprie sessioni
DROP POLICY IF EXISTS "rpe_atleta_select" ON rpe_sessioni;
CREATE POLICY "rpe_atleta_select" ON rpe_sessioni
FOR SELECT
USING (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = rpe_sessioni.atleta_id
    )
);

-- D. Atleta: inserimento delle proprie sessioni
DROP POLICY IF EXISTS "rpe_atleta_insert" ON rpe_sessioni;
CREATE POLICY "rpe_atleta_insert" ON rpe_sessioni
FOR INSERT
WITH CHECK (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = rpe_sessioni.atleta_id
    )
);

-- E. Atleta: aggiornamento delle proprie sessioni
DROP POLICY IF EXISTS "rpe_atleta_update" ON rpe_sessioni;
CREATE POLICY "rpe_atleta_update" ON rpe_sessioni
FOR UPDATE
USING (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = rpe_sessioni.atleta_id
    )
);

-- F. Atleta: cancellazione di una sessione (es. rimozione di uno slot errato)
DROP POLICY IF EXISTS "rpe_atleta_delete" ON rpe_sessioni;
CREATE POLICY "rpe_atleta_delete" ON rpe_sessioni
FOR DELETE
USING (
    profilo_id = auth.uid() OR
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = rpe_sessioni.atleta_id
    )
);

-- =====================================================================
-- 6. MIGRAZIONE: MODULO "PALESTRA & PREPARAZIONE FISICA" (70/30 SPLIT)
-- E RICONCILIAZIONE TEMPO ATLETA / STAFF
-- =====================================================================
-- Esegui questo blocco per estendere rpe_sessioni con il supporto
-- alle durate separate atleta/staff e alla profilazione biomeccanica 70/30.

ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS durata_atleta_min NUMERIC;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS durata_staff_min NUMERIC;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS rpe_staff NUMERIC;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS stimolo_primario TEXT;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS distretto_primario TEXT;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS peso_primario_pct INTEGER DEFAULT 100;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS stimolo_secondario TEXT;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS distretto_secondario TEXT;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS stress_eccentrico_atteso TEXT DEFAULT 'Moderato';

