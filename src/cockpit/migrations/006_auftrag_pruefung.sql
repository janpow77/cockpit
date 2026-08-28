-- Aufträge: Qualitätstor (Prüfbefehle im Worktree) und Pull Request
ALTER TABLE cockpit_auftraege ADD COLUMN pruefung TEXT;
ALTER TABLE cockpit_auftraege ADD COLUMN pruefung_ok INTEGER;
ALTER TABLE cockpit_auftraege ADD COLUMN pr_url TEXT;
ALTER TABLE cockpit_auftraege ADD COLUMN pr_checks TEXT;
