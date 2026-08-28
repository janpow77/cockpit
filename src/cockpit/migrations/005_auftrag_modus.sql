-- Aufträge: Modus (bericht | plan_freigabe | umsetzen) und Freigabezeitpunkt
ALTER TABLE cockpit_auftraege ADD COLUMN modus TEXT NOT NULL DEFAULT 'umsetzen';
ALTER TABLE cockpit_auftraege ADD COLUMN freigegeben TEXT;
