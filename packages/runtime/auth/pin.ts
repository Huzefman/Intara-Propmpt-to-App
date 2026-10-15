/**
 * Single-user PIN lock (Phase 8): device-grade app lock, no server, no email.
 * The PIN hash lives in the adapter (`_auth` entity) so it follows the data
 * across memory/dexie/supabase. PBKDF2-SHA256, per-app salt, constant-time
 * compare. Honest limits: stops casual access, not forensics — server-side
 * auth lands with multi-tenant (email/password or magic link then).
 */
import type { StorageAdapter } from "../adapters/types.ts";

const AUTH_ENTITY = "_auth";
const AUTH_ID = "pin";
const ITERATIONS = 100000;

function subtle(): SubtleCrypto {
  const s = (globalThis as Record<string, unknown>)["crypto"] as Crypto | undefined;
  const sub = s?.subtle;
  if (!sub) throw new Error("WebCrypto unavailable");
  return sub;
}

function bytesToHex(b: ArrayBuffer): string {
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(h: string): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(new ArrayBuffer(h.length / 2));
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function newSalt(): string {
  const b = new Uint8Array(16);
  const c = (globalThis as Record<string, unknown>)["crypto"] as Crypto | undefined;
  if (!c?.getRandomValues) throw new Error("WebCrypto unavailable");
  c.getRandomValues(b);
  return bytesToHex(b.buffer as ArrayBuffer);
}

export async function hashPin(pin: string, saltHex: string): Promise<string> {
  const key = await subtle().importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveBits"]);
  const bits = await subtle().deriveBits(
    { name: "PBKDF2", salt: hexToBytes(saltHex), iterations: ITERATIONS, hash: "SHA-256" },
    key, 256);
  return bytesToHex(bits);
}

function timingSafeEqual(aHex: string, bHex: string): boolean {
  if (aHex.length !== bHex.length) return false;
  let diff = 0;
  for (let i = 0; i < aHex.length; i++) diff |= aHex.charCodeAt(i) ^ bHex.charCodeAt(i);
  return diff === 0;
}

export function validPinFormat(pin: string): boolean {
  return /^\d{4,8}$/.test(pin);
}

export async function enrollPin(db: StorageAdapter, pin: string): Promise<void> {
  if (!validPinFormat(pin)) throw new Error("PIN must be 4–8 digits");
  const salt = newSalt();
  await db.put(AUTH_ENTITY, { id: AUTH_ID, hash: await hashPin(pin, salt), salt });
}

export async function isEnrolled(db: StorageAdapter): Promise<boolean> {
  return (await db.get(AUTH_ENTITY, AUTH_ID)) !== null;
}

export async function verifyPin(db: StorageAdapter, pin: string): Promise<boolean> {
  const rec = await db.get(AUTH_ENTITY, AUTH_ID);
  if (!rec || typeof rec["hash"] !== "string" || typeof rec["salt"] !== "string") return false;
  const candidate = await hashPin(pin, rec["salt"] as string);
  return timingSafeEqual(candidate, rec["hash"] as string);
}

export async function clearPin(db: StorageAdapter): Promise<void> {
  await db.remove(AUTH_ENTITY, AUTH_ID);
}
