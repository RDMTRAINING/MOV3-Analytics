-- =====================================================================
-- M0V3 ANALYTICS - SETUP DATABASE TEST FISICI & NEUROMUSCOLARI
-- Esegui questo script nell'SQL Editor del pannello di Supabase
-- =====================================================================

-- 0. FUNZIONE DI AGGIORNAMENTO TIMESTAMP (se non presente)
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 1. TABELLA: catalogo_protocolli
CREATE TABLE IF NOT EXISTS catalogo_protocolli (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codice_univoco TEXT UNIQUE NOT NULL,
    creatore_id UUID REFERENCES profili(id) ON DELETE SET NULL,
    nome_protocollo TEXT NOT NULL,
    macro_area TEXT NOT NULL,
    categoria TEXT NOT NULL,
    schema_metriche JSONB NOT NULL DEFAULT '[]'::jsonb,
    manuale_obiettivi TEXT DEFAULT NULL,
    manuale_esecuzione TEXT DEFAULT NULL,
    manuale_interpretazione TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL
);

-- Indici per catalogo_protocolli
CREATE INDEX IF NOT EXISTS idx_cat_prot_macro ON catalogo_protocolli(macro_area);
CREATE INDEX IF NOT EXISTS idx_cat_prot_cat ON catalogo_protocolli(categoria);
CREATE INDEX IF NOT EXISTS idx_cat_prot_creatore ON catalogo_protocolli(creatore_id);

-- 2. TABELLA: sessioni_test
CREATE TABLE IF NOT EXISTS sessioni_test (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    atleta_id UUID NOT NULL REFERENCES atleti(id) ON DELETE CASCADE,
    nome_giocatore TEXT NOT NULL,
    protocollo_id UUID NOT NULL REFERENCES catalogo_protocolli(id) ON DELETE CASCADE,
    data DATE NOT NULL DEFAULT CURRENT_DATE,
    condizione_ambiente TEXT DEFAULT 'Outdoor',
    strumentazione TEXT DEFAULT NULL,
    valori JSONB NOT NULL DEFAULT '{}'::jsonb,
    note TEXT DEFAULT NULL,
    inserito_da UUID REFERENCES profili(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, NOW()) NOT NULL
);

-- Trigger per updated_at su sessioni_test
DROP TRIGGER IF EXISTS trg_sessioni_test_updated_at ON sessioni_test;
CREATE TRIGGER trg_sessioni_test_updated_at
BEFORE UPDATE ON sessioni_test
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();

-- Indici di performance per sessioni_test
CREATE INDEX IF NOT EXISTS idx_sess_test_atleta_data ON sessioni_test(atleta_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_sess_test_prot ON sessioni_test(protocollo_id);
CREATE INDEX IF NOT EXISTS idx_sess_test_nome ON sessioni_test(nome_giocatore);

-- 3. ABILITAZIONE ROW LEVEL SECURITY (RLS)
ALTER TABLE catalogo_protocolli ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessioni_test ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- POLICIES: catalogo_protocolli
-- ---------------------------------------------------------------------
DROP POLICY IF EXISTS "cat_prot_select" ON catalogo_protocolli;
CREATE POLICY "cat_prot_select" ON catalogo_protocolli
FOR SELECT
USING (
    creatore_id IS NULL 
    OR creatore_id = auth.uid() 
    OR EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

DROP POLICY IF EXISTS "cat_prot_insert" ON catalogo_protocolli;
CREATE POLICY "cat_prot_insert" ON catalogo_protocolli
FOR INSERT
WITH CHECK (
    creatore_id = auth.uid() 
    OR EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

DROP POLICY IF EXISTS "cat_prot_update" ON catalogo_protocolli;
CREATE POLICY "cat_prot_update" ON catalogo_protocolli
FOR UPDATE
USING (
    creatore_id = auth.uid() 
    OR EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

DROP POLICY IF EXISTS "cat_prot_delete" ON catalogo_protocolli;
CREATE POLICY "cat_prot_delete" ON catalogo_protocolli
FOR DELETE
USING (
    creatore_id = auth.uid() 
    OR EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

-- ---------------------------------------------------------------------
-- POLICIES: sessioni_test
-- ---------------------------------------------------------------------
DROP POLICY IF EXISTS "sess_test_super_admin_all" ON sessioni_test;
CREATE POLICY "sess_test_super_admin_all" ON sessioni_test
FOR ALL
USING (
    EXISTS (SELECT 1 FROM profili WHERE id = auth.uid() AND ruolo = 'Super-Admin')
);

DROP POLICY IF EXISTS "sess_test_coach_all" ON sessioni_test;
CREATE POLICY "sess_test_coach_all" ON sessioni_test
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = sessioni_test.atleta_id
    )
);

DROP POLICY IF EXISTS "sess_test_atleta_select" ON sessioni_test;
CREATE POLICY "sess_test_atleta_select" ON sessioni_test
FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM associazioni 
        WHERE profilo_id = auth.uid() AND atleta_id = sessioni_test.atleta_id
    )
);
