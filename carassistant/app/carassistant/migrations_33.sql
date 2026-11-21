-- the icon a source's index gives a package (a name from the app's icon set)
ALTER TABLE source_packages ADD COLUMN icon TEXT NOT NULL DEFAULT '';
