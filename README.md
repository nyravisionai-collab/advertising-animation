# ElectricalsKart — Projector Wall Advertising Video

A professional, seamless-looping advertising animation built for continuous wall
projection from a **Lenovo Yoga Tab 3 Pro (YT3-X90F)** built-in projector
(played in VLC Player with Repeat/Loop ON).

## Final files (in `output/`)

| File | Use |
|---|---|
| `ElectricalsKart_WallAd_1080p30.mp4` | **Main video** — includes subtle royalty-free ambient music (synthesised in the render script, safe for commercial use) |
| `ElectricalsKart_WallAd_1080p30_NoAudio.mp4` | Same video, silent version |

## Technical specs

- **Format:** MP4, H.264 (High Profile), yuv420p
- **Resolution:** 1920 × 1080 Full HD, 16:9 landscape
- **Frame rate:** 30 FPS
- **Duration:** 44 seconds, **seamless loop** (final scene fades into the same
  ambient background that opens the video — no visible jump on repeat)
- **Audio (main version):** AAC 128 kbps, gentle original ambient pad
  (loop-crossfaded, no copyrighted material)
- Designed for projection: very large Montserrat typography, bright white text
  on dark background, slow transitions, no flicker/strobing, safe margins

## Scenes (44 s loop)

1. **Brand intro** — HYDRO ELECTRICO / ELECTRICALSKART + tagline
   "Electrical Solutions at One Place"
2. **Product categories** — Electrical Products, LED Lighting,
   Switches & Sockets, Fans, Electrical Accessories, + all general items
   (sequential reveal with icons)
3. **Business type** — RETAIL / WHOLESALE / ONLINE +
   "Quality Electrical Products at Competitive Prices"
4. **Services** — Electrical Installation & Repair Services
5. **Brand reminder** — ELECTRICALSKART — "Your Electrical Store"
6. **Website** — electricalskart.com (large, with underline sweep)
7. **Final brand screen** — name, product line, website (holds ~3.5 s,
   then blends back into scene 1)

## Playing on the Yoga Tab 3 Pro (loop setup)

1. Copy `ElectricalsKart_WallAd_1080p30.mp4` to the tablet's internal storage
   (e.g. via USB or microSD).
2. Open the file in **VLC for Android**.
3. In the player, tap the **Repeat icon** until it shows **"Repeat one"** (loop).
4. Turn on the projector (long-press the projector button), point it at the
   shop wall, adjust focus/keystone.
5. Recommended: in VLC → Settings → enable **"Keep screen on"** / disable
   sleep, and in Android set screen timeout to **Never** while charging —
   keep the tablet plugged in for all-day playback.

Tip: the Yoga Tab 3 Pro's native display resolution is higher, but VLC will
play this 1080p file pixel-perfect; the projector outputs up to its native
resolution without quality loss from upscaling artefacts.

## Rebuilding / editing

```
pip install numpy pillow imageio-ffmpeg
python3 scripts/render_ad.py --mode stills   # quick design stills
python3 scripts/render_ad.py --mode audio    # synthesise music loop
python3 scripts/render_ad.py --mode render   # full render -> output/video_raw.mp4
```

Fonts: Montserrat (SIL Open Font License, see `assets/fonts/OFL.txt`).
All animation, icons and audio are generated programmatically in
`scripts/render_ad.py` — no stock assets, no licensing issues.
