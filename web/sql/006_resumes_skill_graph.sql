-- Skill graph extraction (cv_extract.py). One structured JSON per active
-- resume, populated once on first read by cv_score.py. Replaces raw
-- parsed_text dump in the cv_score prompt — the model now scores a
-- structured grid instead of re-reading the CV every batch, which:
--   * makes scores reproducible across runs
--   * cuts per-batch user-message size ~80%
--   * prevents skill hallucination (model can't invent skills not in the graph)
--
-- The column is nullable so existing rows are unaffected. cv_score.py
-- falls back to parsed_text when this is null, then populates it on
-- the next batch and uses the graph from then on.
--
-- Deployment: paste into Supabase Studio > SQL Editor.

alter table resumes
    add column if not exists skill_graph jsonb;

-- Index so cv_score.py's per-batch SELECT doesn't have to scan the
-- parsed_text payload when the graph is what it actually wants. Small
-- table (one row per CV per user) so the index is tiny.
create index if not exists resumes_skill_graph_not_null_idx
    on resumes ((skill_graph is not null))
    where skill_graph is not null;
