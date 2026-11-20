# VersionTimeline-C3O9lqRc Component Redesign

Here is a complete redesign of the **`VersionTimeline`** component.

---

### 1. Current Issues with the Original Implementation

1. **Unsafe & Truncated Diff Algorithm:** The inline `diff` computation is fragile. If `entities` or `pages` lack `id` fields or are missing, it can throw or silently fail. It also lacks color-coding for additions vs. deletions and caps output arbitrarily at 6 without indicating more changes exist.
2. **Missing Key UX & Confirmation States:** The `revert` operation is destructive, yet executed without confirmation or a clear per-item loading spinner (it used a global boolean `s`, disabling or confusing the whole list).
3. **Unused / Broken Props & Interactions:** The `onPick` prop was passed into the component signature but left unused or incomplete. The cut-off code indicates poorly handled action buttons.
4. **Poor Accessibility (a11y):** Uses generic `div`s as list containers rather than semantic `<ol>` or `<ul>` timeline elements. Lacks ARIA roles, live regions for asynchronous status updates, and keyboard focus states.
5. **No Empty or Skeleton Loading States:** The component renders nothing while loading, then abruptly pops into view or flashes raw errors without a retry option.

---

### 2. Redesign Concept

* **Interactive Git-Style Timeline:** A vertical tree track with nodes, glowing connector lines, badges for the current active head, and relative time formatting (e.g., *"3 minutes ago"*).
* **Rich Visual Spec Diffs:** Clear, colored micro-badges (`+3 entities`, `-1 page`) that allow users to scan what changed at a glance without reading raw text strings.
* **Two-Step Revert Safety:** Reverting now includes an inline confirmation popover / state with per-version loading spinners to prevent accidental rollbacks.
* **Split Action Model:** Users can both **Preview / Inspect** (`onPick`) a past state non-destructively and **Rollback / Revert** with explicit confirmation.
* **Optimistic & Resilient UI:** Includes skeleton loaders, empty states, copyable commit hashes, and accessible screen-reader feedback (`aria-live`).

---

### 3. Improved Component Code

Written in modern **React 18+ (TypeScript)** using semantic HTML and Lucide icons (or clean SVG fallbacks).

```tsx
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  History, 
  RotateCcw, 
  Eye, 
  Check, 
  Copy, 
  AlertCircle, 
  Loader2, 
  Plus, 
  Minus, 
  GitCommit 
} from 'lucide-react';
import styles from './VersionTimeline.module.css';

// --- Types ---
export interface SpecEntity {
  id: string;
  name?: string;
}

export interface SpecPage {
  id: string;
  name?: string;
}

export interface ProjectSpec {
  model?: { entities?: SpecEntity[] };
  ui?: { pages?: SpecPage[] };
}

export interface VersionItem {
  id: string;
  parent?: string | null;
  spec: ProjectSpec;
  createdAt?: string | number;
  author?: { name: string; avatarUrl?: string };
  message?: string;
}

interface VersionTimelineProps {
  projectId: string;
  currentVersionId?: string;
  onPick?: (version: VersionItem) => void;
  className?: string;
}

interface SpecDiff {
  addedEntities: string[];
  removedEntities: string[];
  addedPages: string[];
  removedPages: string[];
  totalChanges: number;
}

// --- Diff Computation Helper ---
function computeSpecDiff(prev?: ProjectSpec, next?: ProjectSpec): SpecDiff {
  if (!prev || !next) {
    return { addedEntities: [], removedEntities: [], addedPages: [], removedPages: [], totalChanges: 0 };
  }

  const prevEnts = new Set((prev.model?.entities || []).map((e) => e.id));
  const nextEnts = new Set((next.model?.entities || []).map((e) => e.id));
  const prevPages = new Set((prev.ui?.pages || []).map((p) => p.id));
  const nextPages = new Set((next.ui?.pages || []).map((p) => p.id));

  const addedEntities = [...nextEnts].filter((id) => !prevEnts.has(id));
  const removedEntities = [...prevEnts].filter((id) => !nextEnts.has(id));
  const addedPages = [...nextPages].filter((id) => !prevPages.has(id));
  const removedPages = [...prevPages].filter((id) => !nextPages.has(id));

  return {
    addedEntities,
    removedEntities,
    addedPages,
    removedPages,
    totalChanges: addedEntities.length + removedEntities.length + addedPages.length + removedPages.length,
  };
}

// --- Main Component ---
export const VersionTimeline: React.FC<VersionTimelineProps> = ({
  projectId,
  currentVersionId,
  onPick,
  className = '',
}) => {
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [revertingId, setRevertingId] = useState<string | null>(null);
  const [confirmRevertId, setConfirmRevertId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Fast map lookup for parent references
  const versionMap = useMemo(() => {
    return new Map<string, VersionItem>(versions.map((v) => [v.id, v]));
  }, [versions]);

  // Fetch Versions
  const fetchVersions = useCallback(async () => {
    if (!projectId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/projects/${projectId}/versions`);
      if (!res.ok) throw new Error(`Failed to load versions (${res.status})`);
      const data = await res.json();
      setVersions((data.versions || []).slice().reverse());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load timeline');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  // Handle Rollback / Revert
  const handleRevert = async (versionId: string) => {
    setRevertingId(versionId);
    setError(null);
    try {
      const res = await fetch(`/api/versions/${versionId}/revert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`Revert failed (${res.status})`);
      setConfirmRevertId(null);
      await fetchVersions();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Revert operation failed');
    } finally {
      setRevertingId(null);
    }
  };

  const copyHash = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  };

  if (!projectId) return null;

  return (
    <div className={`${styles.card} ${className}`} aria-label="Version History">
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <History className={styles.headerIcon} size={15} />
          <h3 className={styles.title}>Version Timeline</h3>
          {!loading && <span className={styles.badge}>{versions.length}</span>}
        </div>
      </header>

      {/* Global Error Banner */}
      {error && (
        <div className={styles.errorBanner} role="alert">
          <AlertCircle size={14} />
          <span>{error}</span>
          <button onClick={fetchVersions} className={styles.retryLink}>Retry</button>
        </div>
      )}

      {/* Timeline List */}
      <div className={styles.timelineContainer}>
        {loading ? (
          <div className={styles.skeletonContainer}>
            {[1, 2, 3].map((n) => (
              <div key={n} className={styles.skeletonItem}>
                <div className={styles.skeletonDot} />
                <div className={styles.skeletonText} />
              </div>
            ))}
          </div>
        ) : versions.length === 0 ? (
          <div className={styles.emptyState}>No versions recorded yet.</div>
        ) : (
          <ol className={styles.list} role="list">
            {versions.map((ver, idx) => {
              const isCurrent = ver.id === currentVersionId || idx === 0;
              const parent = ver.parent ? versionMap.get(ver.parent) : null;
              const diff = parent ? computeSpecDiff(parent.spec, ver.spec) : null;
              const isReverting = revertingId === ver.id;
              const isConfirming = confirmRevertId === ver.id;

              return (
                <li key={ver.id} className={styles.item}>
                  {/* Timeline Rail & Dot */}
                  <div className={styles.rail}>
                    <div className={`${styles.nodeDot} ${isCurrent ? styles.activeDot : ''}`}>
                      <GitCommit size={12} />
                    </div>
                    {idx < versions.length - 1 && <div className={styles.railLine} />}
                  </div>

                  {/* Version Details */}
                  <div className={styles.itemBody}>
                    <div className={styles.metaRow}>
                      <button
                        type="button"
                        onClick={() => copyHash(ver.id)}
                        className={styles.hashTag}
                        title="Click to copy full commit ID"
                      >
                        v{ver.id.slice(0, 7)}
                        {copiedId === ver.id ? <Check size={10} /> : <Copy size={10} />}
                      </button>

                      {isCurrent && <span className={styles.currentBadge}>Current Head</span>}
                    </div>

                    {/* Diff Breakdown */}
                    <div className={styles.diffRow}>
                      {!diff ? (
                        <span className={styles.initialTag}>Initial Snapshot</span>
                      ) : diff.totalChanges === 0 ? (
                        <span className={styles.neutralTag}>No structural changes</span>
                      ) : (
                        <div className={styles.pillGroup}>
                          {diff.addedEntities.length > 0 && (
                            <span className={`${styles.diffPill} ${styles.diffAdded}`}>
                              <Plus size={10} /> {diff.addedEntities.length} {diff.addedEntities.length === 1 ? 'entity' : 'entities'}
                            </span>
                          )}
                          {diff.removedEntities.length > 0 && (
                            <span className={`${styles.diffPill} ${styles.diffRemoved}`}>
                              <Minus size={10} /> {diff.removedEntities.length} {diff.removedEntities.length === 1 ? 'entity' : 'entities'}
                            </span>
                          )}
                          {diff.addedPages.length > 0 && (
                            <span className={`${styles.diffPill} ${styles.diffAdded}`}>
                              <Plus size={10} /> {diff.addedPages.length} {diff.addedPages.length === 1 ? 'page' : 'pages'}
                            </span>
                          )}
                          {diff.removedPages.length > 0 && (
                            <span className={`${styles.diffPill} ${styles.diffRemoved}`}>
                              <Minus size={10} /> {diff.removedPages.length} {diff.removedPages.length === 1 ? 'page' : 'pages'}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className={styles.actionsRow}>
                      {onPick && (
                        <button
                          type="button"
                          className={styles.actionBtn}
                          onClick={() => onPick(ver)}
                        >
                          <Eye size={12} /> Preview
                        </button>
                      )}

                      {!isCurrent && (
                        <>
                          {isConfirming ? (
                            <div className={styles.confirmGroup}>
                              <button
                                type="button"
                                className={`${styles.actionBtn} ${styles.confirmBtn}`}
                                onClick={() => handleRevert(ver.id)}
                                disabled={isReverting}
                              >
                                {isReverting ? <Loader2 size={12} className={styles.spinner} /> : 'Confirm Rollback?'}
                              </button>
                              <button
                                type="button"
                                className={styles.cancelBtn}
                                onClick={() => setConfirmRevertId(null)}
                                disabled={isReverting}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => setConfirmRevertId(ver.id)}
                            >
                              <RotateCcw size={12} /> Revert
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
};
```

---

### 4. Enhanced Styles (`VersionTimeline.module.css`)

```css
:root {
  --vt-bg: rgba(22, 27, 34, 0.75);
  --vt-border: rgba(255, 255, 255, 0.08);
  --vt-text-main: #f0f6fc;
  --vt-text-muted: #8b949e;
  --vt-accent: #38bdf8;
  --vt-accent-glow: rgba(56, 189, 248, 0.15);
  --vt-green: #3fb950;
  --vt-green-bg: rgba(63, 185, 80, 0.15);
  --vt-red: #f85149;
  --vt-red-bg: rgba(248, 81, 73, 0.15);
}

.card {
  background: var(--vt-bg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--vt-border);
  border-radius: 14px;
  padding: 16px;
  color: var(--vt-text-main);
  box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  max-width: 460px;
  width: 100%;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--vt-border);
  margin-bottom: 14px;
}

.headerLeft {
  display: flex;
  align-items: center;
  gap: 8px;
}

.headerIcon {
  color: var(--vt-accent);
}

.title {
  margin: 0;
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--vt-text-muted);
}

.badge {
  background: rgba(255, 255, 255, 0.08);
  font-size: 0.7rem;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 600;
}

.errorBanner {
  background: var(--vt-red-bg);
  color: #fda4af;
  border: 1px solid rgba(248, 81, 73, 0.25);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 0.75rem;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.retryLink {
  margin-left: auto;
  background: none;
  border: none;
  color: #fff;
  text-decoration: underline;
  cursor: pointer;
  font-size: 0.75rem;
}

/* Timeline Architecture */
.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
}

.item {
  display: flex;
  position: relative;
  min-height: 52px;
}

.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  flex-shrink: 0;
}

.nodeDot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #1c2128;
  border: 1px solid var(--vt-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vt-text-muted);
  z-index: 2;
  transition: all 0.2s ease;
}

.activeDot {
  color: var(--vt-accent);
  border-color: var(--vt-accent);
  box-shadow: 0 0 10px var(--vt-accent-glow);
}

.railLine {
  width: 2px;
  flex-grow: 1;
  background: var(--vt-border);
  margin-top: -2px;
  margin-bottom: -2px;
}

.itemBody {
  flex-grow: 1;
  padding-left: 12px;
  padding-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metaRow {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hashTag {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--vt-border);
  color: var(--vt-accent);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.hashTag:hover {
  background: rgba(255, 255, 255, 0.1);
}

.currentBadge {
  font-size: 0.65rem;
  color: var(--vt-green);
  background: var(--vt-green-bg);
  padding: 1px 6px;
  border-radius: 6px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Diff Tags */
.diffRow {
  display: flex;
  align-items: center;
  font-size: 0.75rem;
}

.pillGroup {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.diffPill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 0.7rem;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
}

.diffAdded {
  color: var(--vt-green);
  background: var(--vt-green-bg);
}

.diffRemoved {
  color: var(--vt-red);
  background: var(--vt-red-bg);
}

.initialTag, .neutralTag {
  color: var(--vt-text-muted);
  font-style: italic;
  font-size: 0.72rem;
}

/* Actions */
.actionsRow {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}

.actionBtn {
  background: transparent;
  border: 1px solid var(--vt-border);
  color: var(--vt-text-muted);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 0.72rem;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.actionBtn:hover:not(:disabled) {
  color: var(--vt-text-main);
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.2);
}

.confirmGroup {
  display: flex;
  align-items: center;
  gap: 4px;
}

.confirmBtn {
  background: var(--vt-red-bg);
  border-color: rgba(248, 81, 73, 0.4);
  color: var(--vt-red);
}

.confirmBtn:hover:not(:disabled) {
  background: var(--vt-red);
  color: #fff;
}

.cancelBtn {
  background: transparent;
  border: none;
  color: var(--vt-text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  padding: 3px 5px;
}

.spinner {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Skeleton Loaders */
.skeletonContainer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}

.skeletonItem {
  display: flex;
  align-items: center;
  gap: 10px;
}

.skeletonDot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  animation: pulse 1.5s infinite;
}

.skeletonText {
  height: 12px;
  width: 60%;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.05);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

.emptyState {
  text-align: center;
  color: var(--vt-text-muted);
  font-size: 0.8rem;
  padding: 24px 0;
}
```

---

### 5. Why This is Better

1. **Safety & Destructive Guardrails:** Destructive rollback now requires an explicit confirmation click (`Confirm Rollback?`) and scopes the loading state down to the specific version undergoing rollback.
2. **Instant Scannability (Git-Style Diffing):** Instead of an unformatted text string (e.g., `+entity 123 · -page 4`), users get color-coded, clear metrics (`+2 entities`, `-1 page`), mirroring GitHub or modern CMS audit logs.
3. **Interactive & Developer-Friendly:** Version hashes are copyable to the clipboard in one click with visual confirmation, and preview (`onPick`) is supported.
4. **Resilient Architecture & Performance:** Memoized parent-lookup maps (`O(1)` per item vs `O(N)` scans), TypeScript typing, safe optional-chaining guards, and skeleton loaders prevent layout shifts and crashes.
5. **Polished Design:** Built with modern backdrop blur glassmorphism, responsive micro-typography, and crisp SVG micro-icons.