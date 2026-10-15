-- Migration 008 — Storage for app uploads (Phase 8, slice 3).
-- ADDITIVE ONLY: one bucket + policies on storage.objects, nothing else.
-- Demo-open posture (cf. AGENT.md §5 #7): public reads so preview images
-- render without signed URLs; open inserts scoped to the bucket (filenames
-- are uuid-prefixed client-side). Harden with auth-scoped policies at
-- multi-tenant time.
insert into storage.buckets (id, name, public)
values ('intara-uploads', 'intara-uploads', true)
on conflict (id) do nothing;

drop policy if exists "intara public read" on storage.objects;
create policy "intara public read" on storage.objects for select
  using (bucket_id = 'intara-uploads');

drop policy if exists "intara open insert" on storage.objects;
create policy "intara open insert" on storage.objects for insert
  with check (bucket_id = 'intara-uploads');

drop policy if exists "intara open delete" on storage.objects;
create policy "intara open delete" on storage.objects for delete
  using (bucket_id = 'intara-uploads');
