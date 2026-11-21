-- one free "Notes" field per vehicle: what was kept in parts_note is appended to notes, then the column goes away
UPDATE vehicles SET notes = CASE WHEN notes IS NULL OR notes = '' THEN parts_note ELSE notes || char(10) || parts_note END
  WHERE parts_note IS NOT NULL AND parts_note <> '';
ALTER TABLE vehicles DROP COLUMN parts_note;
