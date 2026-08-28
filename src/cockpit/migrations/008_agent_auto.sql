-- Aufträge: automatische Agentenwahl
ALTER TABLE cockpit_auftraege ADD COLUMN agent_auto INTEGER;
ALTER TABLE cockpit_auftraege ADD COLUMN agent_grund TEXT;
