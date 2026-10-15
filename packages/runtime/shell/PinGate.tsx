/**
 * PinGate (Phase 8): setup mode (no PIN yet: set + confirm) and lock mode
 * (PIN exists: enter to unlock). Calls back, holds no secrets in state
 * longer than the keystroke.
 */
import React from "react";

export function PinGate({ mode, onSubmit, error }: {
  mode: "setup" | "lock";
  onSubmit: (pin: string) => void;
  error?: string | null;
}) {
  const [a, setA] = React.useState("");
  const [b, setB] = React.useState("");
  const ready = mode === "lock" ? a.length >= 4 : a.length >= 4 && a === b;
  return (
    <div className="glass" style={{ padding: 24, textAlign: "center", maxWidth: 320, margin: "40px auto" }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
        {mode === "setup" ? "Set an app PIN" : "Enter PIN"}
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 12 }}>
        {mode === "setup" ? "4–8 digits. Locks this app on this device." : "This app is locked on this device."}
      </div>
      <input
        aria-label="pin" type="password" inputMode="numeric" maxLength={8} value={a}
        onChange={(e) => setA(e.target.value.replace(/\D/g, ""))}
        onKeyDown={(e) => { if (e.key === "Enter" && ready) { onSubmit(a); setA(""); setB(""); } }}
        style={{ fontSize: 20, letterSpacing: 8, textAlign: "center", width: 160 }}
      />
      {mode === "setup" && (
        <input
          aria-label="confirm pin" type="password" inputMode="numeric" maxLength={8} value={b}
          placeholder="repeat" onChange={(e) => setB(e.target.value.replace(/\D/g, ""))}
          style={{ display: "block", margin: "8px auto", fontSize: 16, letterSpacing: 6, textAlign: "center", width: 160 }}
        />
      )}
      {error && <div style={{ color: "#FDA4AF", fontSize: 12, marginTop: 8 }}>{error}</div>}
      <div style={{ marginTop: 12 }}>
        <button className="btn-primary btn-sm" disabled={!ready}
          onClick={() => { onSubmit(a); setA(""); setB(""); }}>
          {mode === "setup" ? "Set PIN" : "Unlock"}
        </button>
      </div>
    </div>
  );
}
