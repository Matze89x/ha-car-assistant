-- Tyre sets: "DOT / age" and "rear axle name" are gone as fields; what was typed there moves into the notes (nothing is lost), the columns stay unused.
UPDATE tires SET notes = TRIM('DOT ' || dot || CASE WHEN notes IS NOT NULL AND notes != '' THEN char(10) || notes ELSE '' END) WHERE dot IS NOT NULL AND dot != '';
UPDATE tires SET notes = TRIM('Rear: ' || rear_name || CASE WHEN notes IS NOT NULL AND notes != '' THEN char(10) || notes ELSE '' END) WHERE rear_name IS NOT NULL AND rear_name != '';
UPDATE tires SET dot = NULL, rear_name = NULL;
