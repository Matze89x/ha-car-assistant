-- Documents: a note, the date on the document and until when it is valid (all optional).
ALTER TABLE documents ADD COLUMN notes TEXT;
ALTER TABLE documents ADD COLUMN doc_date TEXT;
ALTER TABLE documents ADD COLUMN valid_until TEXT;
