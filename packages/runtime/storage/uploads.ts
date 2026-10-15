/**
 * Uploads (Phase 8, slice 3): files into the `intara-uploads` bucket (007→008).
 * Client-shaped (works with supabase-js or fakes); object paths are
 * uuid-prefixed + sanitized so concurrent uploads never collide.
 */
export interface StorageBucket {
  upload(path: string, body: unknown, opts?: Record<string, unknown>): Promise<{ error?: { message: string } | null }>;
  getPublicUrl(path: string): { data: { publicUrl: string } };
}

export interface StorageClient {
  storage: { from(bucket: string): StorageBucket };
}

export const UPLOAD_BUCKET = "intara-uploads";

export function objectPath(entity: string, filename: string): string {
  const safe = (filename || "file").toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+/, "").slice(-80) || "file";
  const rand = Math.random().toString(36).slice(2, 10);
  const stamp = Date.now().toString(36);
  return `${entity}/${stamp}-${rand}-${safe}`;
}

export async function uploadBlob(client: StorageClient, entity: string, filename: string, body: unknown): Promise<string> {
  const path = objectPath(entity, filename);
  const { error } = await client.storage.from(UPLOAD_BUCKET).upload(path, body);
  if (error) throw new Error(`upload failed: ${error.message}`);
  return client.storage.from(UPLOAD_BUCKET).getPublicUrl(path).data.publicUrl;
}
