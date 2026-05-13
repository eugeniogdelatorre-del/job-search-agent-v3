-- Audit M10: short-circuit the expensive pdfjs parse when the same
-- binary has been uploaded before. Adds a bytes_hash column and a
-- per-user unique index. Existing rows get a backfill of NULL — they
-- still dedup via text_hash after the parse, so no regression.
--
-- Deployment: paste into Supabase Studio > SQL Editor.

alter table resumes
    add column if not exists bytes_hash text;

create unique index if not exists resumes_user_bytes_hash_unique
    on resumes (user_id, bytes_hash)
    where bytes_hash is not null;
