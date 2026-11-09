-- =========================================================================
-- M0V3 ANALYTICS — MODULO CALENDARIO & AREA MEDICA
-- Script di inizializzazione PostgreSQL per Supabase
-- Tabella: registro_medico_fisio
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.registro_medico_fisio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    atleta_id UUID NOT NULL REFERENCES public.atleti(id) ON DELETE CASCADE,
    nome_giocatore TEXT NOT NULL,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL, -- Uguale a data_inizio per eventi singoli, maggiore per periodi di infortunio/stop
    tipo_scheda TEXT NOT NULL, 
    -- Valori ammessi per tipo_scheda:
    -- 'TRATTAMENTO' (Terapia/Prevenzione routine)
    -- 'SOVRACCARICO' (Fastidio / Warning / Carico Adattato)
    -- 'INFORTUNIO' (Stop medico / Riabilitazione)
    -- 'MALATTIA' (Sindromi influenzali / Indisposizione medica)
    -- 'LOGISTICA' (Viaggio / Trasferta / Giorno Off programmato)
    
    status_operativo TEXT NOT NULL DEFAULT 'DISPONIBILE',
    -- Valori ammessi per status_operativo:
    -- 'DISPONIBILE' (Verde - Full Training)
    -- 'LIMITATO' (Ambra - Carico Adattato / RTP parziale)
    -- 'INDISPONIBILE' (Rosso - Out / Stop Medico)
    -- 'RIPOSO_VIAGGIO' (Blu/Grigio - Giorno Off o Trasferta)

    sottotipo_evento TEXT, 
    -- Per LOGISTICA: 'Giorno Off / Riposo Programmato', 'Viaggio / Trasferta Torneo'
    -- Per TRATTAMENTO: 'Terapia Manuale / Osteopatia', 'Terapia Fisica (Tecar/Laser/Onde d''urto)', 'Massaggio Scarico', 'Dry Needling / Fibrolisi', 'Esercizio Terapeutico / Rieducazione', 'Taping / Bendaggio'
    -- Per SOVRACCARICO/INFORTUNIO: 'Muscolare', 'Tendineo / Entesopatia', 'Articolare / Legamentoso', 'Osseo / Cartilagineo', 'Neurologico / Rachide'

    distretto_anatomico TEXT,
    -- Valori: 'Nessuno / Sistemico', 'Cervicale', 'Spalla', 'Gomito', 'Polso / Mano', 'Tronco / Costato', 'Rachide Lombare / Bacino', 'Anca / Inguine', 'Gluteo', 'Quadricipite (Anteriore Coscia)', 'Ischiocrurali (Posteriore Coscia)', 'Adduttori', 'Ginocchio', 'Polpaccio / Gastrocnemio', 'Tendine d''Achille', 'Caviglia', 'Piede / Fascia Plantare'

    lato TEXT DEFAULT 'N/A', -- 'Destro', 'Sinistro', 'Bilaterale', 'Centrale / Rachide', 'N/A'
    meccanismo TEXT, -- 'Sovraccarico (Overuse)', 'Traumatico / Acuto in Match', 'Traumatico / Acuto in Allenamento', 'Prevenzione / Routine', 'N/A'
    scala_dolore_vas INTEGER CHECK (scala_dolore_vas >= 0 AND scala_dolore_vas <= 10), -- 0-10
    
    indicazioni_staff TEXT, -- Indicazioni operative per Coach/Preparatore
    note_cliniche_dettaglio TEXT, -- Anamnesi, test clinici, esami strumentali, dettagli seduta fisioterapica
    
    autore_id UUID REFERENCES public.profili(id),
    autore_nome TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indici per query ad alte prestazioni su calendario
CREATE INDEX IF NOT EXISTS idx_reg_medico_atleta_date ON public.registro_medico_fisio(nome_giocatore, data_inizio, data_fine);
CREATE INDEX IF NOT EXISTS idx_reg_medico_atleta_id ON public.registro_medico_fisio(atleta_id);

-- Abilitazione Row-Level Security (RLS)
ALTER TABLE public.registro_medico_fisio ENABLE ROW LEVEL SECURITY;

-- 1. Policy Super-Admin: Accesso completo
DROP POLICY IF EXISTS "Super-Admin full access registro_medico_fisio" ON public.registro_medico_fisio;
CREATE POLICY "Super-Admin full access registro_medico_fisio"
    ON public.registro_medico_fisio
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profili
            WHERE profili.id = auth.uid()
            AND profili.ruolo = 'Super-Admin'
        )
    );

-- 2. Policy Coach e Fisio / Medico: Accesso agli atleti associati
DROP POLICY IF EXISTS "Coach e Fisio access registro_medico_fisio" ON public.registro_medico_fisio;
CREATE POLICY "Coach e Fisio access registro_medico_fisio"
    ON public.registro_medico_fisio
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.associazioni
            WHERE associazioni.profilo_id = auth.uid()
            AND associazioni.atleta_id = registro_medico_fisio.atleta_id
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.associazioni
            WHERE associazioni.profilo_id = auth.uid()
            AND associazioni.atleta_id = registro_medico_fisio.atleta_id
        )
    );

-- 3. Policy Atleta: Nessun accesso (DENY totale esplicito)
DROP POLICY IF EXISTS "Atleta no access registro_medico_fisio" ON public.registro_medico_fisio;
CREATE POLICY "Atleta no access registro_medico_fisio"
    ON public.registro_medico_fisio
    FOR SELECT
    TO authenticated
    USING (
        NOT EXISTS (
            SELECT 1 FROM public.profili
            WHERE profili.id = auth.uid()
            AND profili.ruolo = 'Atleta'
        )
    );
