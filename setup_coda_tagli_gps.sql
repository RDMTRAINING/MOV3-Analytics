-- =====================================================================
-- M0V3 ANALYTICS - DIGITAL HANDSHAKE: CODA TAGLI GPS K-SPORT
-- Architettura To-Do List e Ticketing Leggero Staff/Atleta -> Admin
-- Autore: Riccardo Di Maio | Release Novembre 2026
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.coda_tagli_gps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    atleta TEXT NOT NULL,
    data_sessione DATE NOT NULL,
    tipologia_sessione TEXT DEFAULT 'Non definita',
    tipologia_superficie TEXT NOT NULL,
    orari_note_taglio TEXT,
    completato BOOLEAN DEFAULT FALSE NOT NULL
);

-- Aggiornamento retroattivo per installazioni esistenti
ALTER TABLE public.coda_tagli_gps ADD COLUMN IF NOT EXISTS tipologia_sessione TEXT DEFAULT 'Non definita';

-- Indici di performance per query veloci e ordinamento To-Do
CREATE INDEX IF NOT EXISTS idx_coda_tagli_completato ON public.coda_tagli_gps (completato, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coda_tagli_atleta ON public.coda_tagli_gps (atleta, data_sessione DESC);

-- Abilitazione Row Level Security (RLS)
ALTER TABLE public.coda_tagli_gps ENABLE ROW LEVEL SECURITY;

-- 1. Inserimento consentito a qualsiasi utente autenticato (Staff, Coach, Atleti, Admin)
DROP POLICY IF EXISTS "Consenti inserimento coda_tagli_gps" ON public.coda_tagli_gps;
CREATE POLICY "Consenti inserimento coda_tagli_gps"
    ON public.coda_tagli_gps
    FOR INSERT
    TO authenticated
    WITH CHECK (true);

-- 2. Lettura consentita agli utenti autenticati
DROP POLICY IF EXISTS "Consenti lettura coda_tagli_gps" ON public.coda_tagli_gps;
CREATE POLICY "Consenti lettura coda_tagli_gps"
    ON public.coda_tagli_gps
    FOR SELECT
    TO authenticated
    USING (true);

-- 3. Update consentito agli utenti autenticati (gestione To-Do Admin)
DROP POLICY IF EXISTS "Consenti update coda_tagli_gps" ON public.coda_tagli_gps;
CREATE POLICY "Consenti update coda_tagli_gps"
    ON public.coda_tagli_gps
    FOR UPDATE
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- 4. Service-Role bypass completo
DROP POLICY IF EXISTS "Service role bypass coda_tagli_gps" ON public.coda_tagli_gps;
CREATE POLICY "Service role bypass coda_tagli_gps"
    ON public.coda_tagli_gps
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
