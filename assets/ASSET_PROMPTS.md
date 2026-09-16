# Intara — Asset Generation Prompts

> **How to use:** Copy each prompt into Midjourney / DALL·E 3 / Stable Diffusion XL / Firefly. Generate, download, compress via tinypng.com, and **place exactly** as `assets/<filename>` (names matter — code imports by path). After placing, run `ls assets` to confirm. If an asset is missing, the app falls back to CSS.

**Folder after generation:**
```
assets/
  ASSET_PROMPTS.md        # this file
  README.md               # import map (create after)
  planet-intara.png       # 1024x1024
  starfield.jpg           # 1920x1080
  wish-orb.png            # 512x512
  constellation.svg       # 800x400
  nebula-gradient.png     # 1200x800
  glyphs/
    schema.png            # 256x256
    frontend.png          # 256x256
    backend.png           # 256x256
    scroll.png            # 256x256
```

---

## 1. Planet Intara — `assets/planet-intara.png`

**Prompt (Midjourney v6 / DALL·E):**
```
Dark nebula planet Intara, obsidian sphere with violet #8B5CF6 bioluminescent veins and subtle aurora rings, floating in deep space starfield bokeh, ultra-detailed, cinematic lighting, soft glow, centered composition, transparent background, 8k, photorealistic, space art --ar 1:1 --style raw --v 6.0
```
**Negative:** `no text, no humans, no spacecraft, no bright sun`

**Spec:** 1024×1024 PNG, transparent BG, <500KB, sRGB. Used in `src/components/PlanetOrb.tsx` hero (pulse animation on `loading`).

**Fallback if missing:** CSS radial gradient circle `bg: radial-gradient(circle, #8B5CF6 0%, #0a0a12 70%)`.

---

## 2. Starfield Background — `assets/starfield.jpg`

**Prompt:**
```
Infinite dark cosmos starfield, deep navy #0a0a12 fading to indigo and purple nebula dust clouds, thousands of tiny white stars, subtle milky way band, not busy, seamless tileable texture, calm, elegant, 4k, space photography
```
**Spec:** 1920×1080 JPG, <300KB, used as `body` background in `src/theme/intara.css` (`background: url('/assets/starfield.jpg') cover, opacity 0.6 overlay`).

**Tile:** Should tile without visible seam if repeated.

---

## 3. Wish Orb Icon — `assets/wish-orb.png`

**Prompt:**
```
Glowing wish orb, perfect glass sphere with inner violet #8B5CF6 light, soft bloom and caustics, minimal, icon style, centered, transparent background, studio lighting, 512x512, 8k
```
**Spec:** 512×512 PNG, transparent, <150KB, for wish input button + loading spinner (`src/components/WishInput.tsx`).

**Alternative:** If you prefer SVG, export as `wish-orb.svg` (keep 512 viewBox).

---

## 4. Constellation Map — `assets/constellation.svg`

**Prompt (for vector — generate PNG then trace, or use SVG directly):**
```
Minimal constellation line art, connected stars forming an elegant Intara sigil (geometric, not zodiac), thin white lines 1.5px on transparent background, dots at vertices, clean, modern, 800x400, vector style
```
**Spec:** 800×400 SVG (preferred) or PNG transparent, stroke `rgba(255,255,255,0.35)`, used in `src/pages/Constellation.tsx` as background for star map. If generating as PNG, keep transparent and we will overlay stars via SVG `circle` elements.

**Manual option:** If AI SVG is messy, create simple SVG in Figma: 8 points connected, export.

---

## 5. Nebula Gradient — `assets/nebula-gradient.png`

**Prompt:**
```
Abstract nebula gradient mesh, fluid glass, dark purple #8B5CF6 to indigo #6366f1 to near-black #0a0a12, soft blur, organic blobs, 1200x800, high resolution, subtle grain, for card glow highlights
```
**Spec:** 1200×800 PNG, <200KB, used as `::before` glow for glass cards in `src/theme/intara.css` (`filter: blur(40px); opacity: 0.15`).

---

## 6. Glyphs — `assets/glyphs/*.png` (4x)

Generate 4 small icons, **consistent style** (line icon, violet glow, dark circle bg).

**Shared style prefix:**
```
Line icon, minimal, violet #8B5CF6 glow on dark circular background #0a0a12, 2px stroke, centered, 256x256, transparent background, icon design, 8k
```

**Individual prompts:**

*   **`glyphs/schema.png` — Schemas:**
    `+ database schema icon, tables and columns, cylinder with grid, line icon`

*   **`glyphs/frontend.png` — Frontend:**
    `+ frontend icon, browser window with components and cursor, line icon`

*   **`glyphs/backend.png` — Backend:**
    `+ backend icon, server rack with code brackets { }, line icon`

*   **`glyphs/scroll.png` — Scroll/Spec:**
    `+ scroll document icon, parchment with API lines and checkmarks, line icon`

**Spec:** Each 256×256 PNG, transparent, <80KB, for vault tabs `src/components/ArtifactVault.tsx`.

---

## Generation Tips

*   **Midjourney:** Add `--ar 1:1 --style raw --v 6.0` for planet/orb/glyphs, `--ar 16:9` for starfield/nebula. Use `/imagine`.
*   **DALL·E 3:** Paste prompt verbatim, choose "wide" for starfield, "square" for planet. Download PNG.
*   **Firefly:** Use "Photo" for planet/starfield, "Graphic" for glyphs.
*   **After generation:** 
    1.  Downscale to spec via `sips -Z 1024 planet-intara.png` (mac) or `tinypng.com`.
    2.  Remove background if needed via `remove.bg`.
    3.  Verify `ls -lh assets/` matches names/sizes.
    4.  Commit `assets/` (or keep locally, `.gitignore` not ignore it).

## Fallbacks (If You Skip Generation)

If you place **no assets**, the app will use:
*   Planet → CSS gradient orb
*   Starfield → CSS gradient `linear-gradient(#0a0a12, #1a103a)`
*   Wish orb → Unicode `✦`
*   Constellation → Inline SVG placeholder
*   Nebula → CSS `blur` glow
*   Glyphs → Emoji (🗄️, 🖥️, ⚙️, 📜)

App remains fully functional — assets only enhance theme.

---

*Once assets are placed, notify me with `ls assets` — I will verify imports and wire them into `src/theme/intara.css` and components.*
