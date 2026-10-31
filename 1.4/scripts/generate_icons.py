#!/usr/bin/env python3
"""
Dream Hub - High-Resolution Vector & Raster App Icon Generator
Generates:
  - frontend/icons/icon.svg (Vector Master SVG)
  - frontend/icons/icon-512.png (512x512)
  - frontend/icons/icon-192.png (192x192)
  - frontend/icons/icon-maskable-512.png (512x512 with 80% safe zone)
  - frontend/icons/apple-touch-icon.png (180x180 with 80% safe zone)
"""
import os
import subprocess
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
ICONS_DIR = os.path.join(PROJECT_DIR, 'frontend', 'icons')
os.makedirs(ICONS_DIR, exist_ok=True)

SVG_CONTENT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Background Squircle Gradient -->
    <linearGradient id="bgSquircle" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#141a24"/>
      <stop offset="50%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#05070a"/>
    </linearGradient>

    <!-- Metallic Glass Border -->
    <linearGradient id="borderSquircle" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="rgba(255, 255, 255, 0.28)"/>
      <stop offset="35%" stop-color="#475569"/>
      <stop offset="70%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="rgba(255, 255, 255, 0.08)"/>
    </linearGradient>

    <!-- Ambient Center Radial Glow -->
    <radialGradient id="ambientCenter" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.22"/>
      <stop offset="40%" stop-color="#0f172a" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#05070a" stop-opacity="0"/>
    </radialGradient>

    <!-- Core Hub Glow -->
    <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
      <stop offset="25%" stop-color="#e0f2fe" stop-opacity="0.80"/>
      <stop offset="55%" stop-color="#38bdf8" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
    </radialGradient>

    <!-- Cardinal Pathway Gradients (Outward from Hub) -->
    <linearGradient id="gradNorth" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#e0f2fe"/>
      <stop offset="30%" stop-color="#7dd3fc"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>

    <linearGradient id="gradEast" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#fef3c7"/>
      <stop offset="30%" stop-color="#fde68a"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>

    <linearGradient id="gradSouth" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#d1fae5"/>
      <stop offset="30%" stop-color="#6ee7b7"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>

    <linearGradient id="gradWest" x1="100%" y1="0%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#ede9fe"/>
      <stop offset="30%" stop-color="#c4b5fd"/>
      <stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>

    <!-- Interconnecting Orbital Arcs (Quadrant Gradients) -->
    <linearGradient id="gradArcNE" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>

    <linearGradient id="gradArcSE" x1="100%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#fbbf24"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>

    <linearGradient id="gradArcSW" x1="100%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>

    <linearGradient id="gradArcNW" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#a78bfa"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>

    <!-- Node Glow Gradients -->
    <radialGradient id="glowNorth" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#38bdf8" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowEast" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fbbf24" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#fbbf24" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowSouth" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#10b981" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#10b981" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#10b981" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowWest" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#a78bfa" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#a78bfa" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#a78bfa" stop-opacity="0"/>
    </radialGradient>

    <!-- Drop Shadow / Glow Filters -->
    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>

    <filter id="nodeGlow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- 1. Pure OLED Black Canvas Background -->
  <rect width="512" height="512" fill="#000000"/>

  <!-- 2. Dark Slate Rounded Squircle Badge -->
  <rect x="24" y="24" width="464" height="464" rx="116" fill="url(#bgSquircle)" stroke="url(#borderSquircle)" stroke-width="2.5"/>

  <!-- 3. Ambient Central Radiance -->
  <circle cx="256" cy="256" r="215" fill="url(#ambientCenter)"/>

  <!-- 4. Subtle Concentric Orbital Geometry -->
  <!-- Outer Dotted Orbit (r=176) -->
  <circle cx="256" cy="256" r="176" fill="none" stroke="#334155" stroke-width="1.5" stroke-dasharray="6 6" stroke-opacity="0.45"/>
  <!-- Secondary Orbit (r=152) -->
  <circle cx="256" cy="256" r="152" fill="none" stroke="#1e293b" stroke-width="1.2" stroke-opacity="0.35"/>
  <!-- Primary Orbital Track (r=126) -->
  <circle cx="256" cy="256" r="126" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-opacity="0.6"/>
  <!-- Inner Dotted Orbit (r=74) -->
  <circle cx="256" cy="256" r="74" fill="none" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4" stroke-opacity="0.5"/>
  <!-- Core Guide Ring (r=48) -->
  <circle cx="256" cy="256" r="48" fill="none" stroke="#1e293b" stroke-width="1" stroke-opacity="0.4"/>

  <!-- 5. 45-Degree Diagonal Orbital Rays & Anchor Pips -->
  <g stroke="#334155" stroke-width="1.2" stroke-dasharray="3 5" stroke-opacity="0.35">
    <line x1="168" y1="168" x2="204" y2="204"/>
    <line x1="308" y1="308" x2="344" y2="344"/>
    <line x1="344" y1="168" x2="308" y2="204"/>
    <line x1="204" y1="308" x2="168" y2="344"/>
  </g>
  <!-- Diagonal Micro Pips at r=176 (256 +/- 124.5) -->
  <circle cx="380" cy="132" r="2.5" fill="#475569" opacity="0.6"/>
  <circle cx="380" cy="380" r="2.5" fill="#475569" opacity="0.6"/>
  <circle cx="132" cy="380" r="2.5" fill="#475569" opacity="0.6"/>
  <circle cx="132" cy="132" r="2.5" fill="#475569" opacity="0.6"/>

  <!-- 6. Interconnected Dynamic Orbital Arcs (r=126) -->
  <path d="M 256 130 A 126 126 0 0 1 382 256" fill="none" stroke="url(#gradArcNE)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
  <path d="M 382 256 A 126 126 0 0 1 256 382" fill="none" stroke="url(#gradArcSE)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
  <path d="M 256 382 A 126 126 0 0 1 130 256" fill="none" stroke="url(#gradArcSW)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
  <path d="M 130 256 A 126 126 0 0 1 256 130" fill="none" stroke="url(#gradArcNW)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>

  <!-- 7. Four Cardinal Converging Radiant Pathways -->
  <!-- North Pathway (Sky Blue) -->
  <line x1="256" y1="228" x2="256" y2="130" stroke="#38bdf8" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
  <line x1="256" y1="228" x2="256" y2="130" stroke="url(#gradNorth)" stroke-width="5" stroke-linecap="round"/>
  <line x1="256" y1="228" x2="256" y2="130" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

  <!-- East Pathway (Amber Gold) -->
  <line x1="284" y1="256" x2="382" y2="256" stroke="#fbbf24" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
  <line x1="284" y1="256" x2="382" y2="256" stroke="url(#gradEast)" stroke-width="5" stroke-linecap="round"/>
  <line x1="284" y1="256" x2="382" y2="256" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

  <!-- South Pathway (Emerald Mint) -->
  <line x1="256" y1="284" x2="256" y2="382" stroke="#10b981" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
  <line x1="256" y1="284" x2="256" y2="382" stroke="url(#gradSouth)" stroke-width="5" stroke-linecap="round"/>
  <line x1="256" y1="284" x2="256" y2="382" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

  <!-- West Pathway (Amethyst Violet) -->
  <line x1="228" y1="256" x2="130" y2="256" stroke="#a78bfa" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
  <line x1="228" y1="256" x2="130" y2="256" stroke="url(#gradWest)" stroke-width="5" stroke-linecap="round"/>
  <line x1="228" y1="256" x2="130" y2="256" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

  <!-- 8. Four Cardinal Nodes with Double Halos -->
  <!-- Top Node (North - Sky Blue #38BDF8) -->
  <circle cx="256" cy="130" r="30" fill="url(#glowNorth)"/>
  <circle cx="256" cy="130" r="22" fill="none" stroke="#38bdf8" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
  <circle cx="256" cy="130" r="14" fill="#0d1117" stroke="#38bdf8" stroke-width="2.6" filter="url(#nodeGlow)"/>
  <circle cx="256" cy="130" r="7.5" fill="#38bdf8"/>
  <circle cx="254" cy="128" r="2.2" fill="#ffffff" opacity="0.9"/>

  <!-- Right Node (East - Amber Gold #FBBF24) -->
  <circle cx="382" cy="256" r="30" fill="url(#glowEast)"/>
  <circle cx="382" cy="256" r="22" fill="none" stroke="#fbbf24" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
  <circle cx="382" cy="256" r="14" fill="#0d1117" stroke="#fbbf24" stroke-width="2.6" filter="url(#nodeGlow)"/>
  <circle cx="382" cy="256" r="7.5" fill="#fbbf24"/>
  <circle cx="380" cy="254" r="2.2" fill="#ffffff" opacity="0.9"/>

  <!-- Bottom Node (South - Emerald Mint #10B981) -->
  <circle cx="256" cy="382" r="30" fill="url(#glowSouth)"/>
  <circle cx="256" cy="382" r="22" fill="none" stroke="#10b981" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
  <circle cx="256" cy="382" r="14" fill="#0d1117" stroke="#10b981" stroke-width="2.6" filter="url(#nodeGlow)"/>
  <circle cx="256" cy="382" r="7.5" fill="#10b981"/>
  <circle cx="254" cy="380" r="2.2" fill="#ffffff" opacity="0.9"/>

  <!-- Left Node (West - Amethyst Violet #A78BFA) -->
  <circle cx="130" cy="256" r="30" fill="url(#glowWest)"/>
  <circle cx="130" cy="256" r="22" fill="none" stroke="#a78bfa" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
  <circle cx="130" cy="256" r="14" fill="#0d1117" stroke="#a78bfa" stroke-width="2.6" filter="url(#nodeGlow)"/>
  <circle cx="130" cy="256" r="7.5" fill="#a78bfa"/>
  <circle cx="128" cy="254" r="2.2" fill="#ffffff" opacity="0.9"/>

  <!-- 9. Central Multifaceted Luminous Hub Core -->
  <!-- Ambient Core Radiance -->
  <circle cx="256" cy="256" r="54" fill="url(#coreGlow)"/>

  <!-- Outer Faceted Octagon (r=32, angles: 0, 45, 90, 135, 180, 225, 270, 315) -->
  <!-- (288,256), (278.6,278.6), (256,288), (233.4,278.6), (224,256), (233.4,233.4), (256,224), (278.6,233.4) -->
  <g stroke="#ffffff" stroke-width="0.8" stroke-opacity="0.5">
    <!-- Facet: Top-North -->
    <polygon points="256,224 278.6,233.4 256,256" fill="#e0f2fe" opacity="0.92"/>
    <!-- Facet: Top-East -->
    <polygon points="278.6,233.4 288,256 256,256" fill="#bae6fd" opacity="0.90"/>
    <!-- Facet: Bottom-East -->
    <polygon points="288,256 278.6,278.6 256,256" fill="#7dd3fc" opacity="0.88"/>
    <!-- Facet: Bottom-South -->
    <polygon points="278.6,278.6 256,288 256,256" fill="#38bdf8" opacity="0.92"/>
    <!-- Facet: Bottom-West -->
    <polygon points="256,288 233.4,278.6 256,256" fill="#7dd3fc" opacity="0.88"/>
    <!-- Facet: Mid-West -->
    <polygon points="233.4,278.6 224,256 256,256" fill="#bae6fd" opacity="0.90"/>
    <!-- Facet: Top-West -->
    <polygon points="224,256 233.4,233.4 256,256" fill="#e0f2fe" opacity="0.92"/>
    <!-- Facet: Top-NorthWest -->
    <polygon points="233.4,233.4 256,224 256,256" fill="#f0f9ff" opacity="0.95"/>
  </g>

  <!-- Inner Sparkling Core Diamond (r=18) -->
  <g stroke="#ffffff" stroke-width="1.2" stroke-opacity="0.9">
    <polygon points="256,238 274,256 256,256" fill="#ffffff" opacity="0.98"/>
    <polygon points="274,256 256,274 256,256" fill="#e0f2fe" opacity="0.95"/>
    <polygon points="256,274 238,256 256,256" fill="#bae6fd" opacity="0.92"/>
    <polygon points="238,256 256,238 256,256" fill="#f0f9ff" opacity="0.98"/>
  </g>

  <!-- Specular Center Micro Star Highlight -->
  <polygon points="256,248 258,254 264,256 258,258 256,264 254,258 248,256 254,254" fill="#ffffff"/>
  <circle cx="256" cy="256" r="2.5" fill="#ffffff"/>
</svg>
'''

# Maskable SVG variant: scaled to 80% to ensure 100% of all artwork sits comfortably inside the safe circular cut
SVG_MASKABLE_CONTENT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Background Squircle Gradient -->
    <linearGradient id="bgSquircleM" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#141a24"/>
      <stop offset="50%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#05070a"/>
    </linearGradient>

    <!-- Metallic Glass Border -->
    <linearGradient id="borderSquircleM" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="rgba(255, 255, 255, 0.28)"/>
      <stop offset="35%" stop-color="#475569"/>
      <stop offset="70%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="rgba(255, 255, 255, 0.08)"/>
    </linearGradient>

    <!-- Ambient Center Radial Glow -->
    <radialGradient id="ambientCenterM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.22"/>
      <stop offset="40%" stop-color="#0f172a" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#05070a" stop-opacity="0"/>
    </radialGradient>

    <!-- Core Hub Glow -->
    <radialGradient id="coreGlowM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
      <stop offset="25%" stop-color="#e0f2fe" stop-opacity="0.80"/>
      <stop offset="55%" stop-color="#38bdf8" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
    </radialGradient>

    <!-- Cardinal Pathway Gradients -->
    <linearGradient id="gradNorthM" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#e0f2fe"/>
      <stop offset="30%" stop-color="#7dd3fc"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>

    <linearGradient id="gradEastM" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#fef3c7"/>
      <stop offset="30%" stop-color="#fde68a"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>

    <linearGradient id="gradSouthM" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#d1fae5"/>
      <stop offset="30%" stop-color="#6ee7b7"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>

    <linearGradient id="gradWestM" x1="100%" y1="0%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#ede9fe"/>
      <stop offset="30%" stop-color="#c4b5fd"/>
      <stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>

    <linearGradient id="gradArcNEM" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>

    <linearGradient id="gradArcSEM" x1="100%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#fbbf24"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>

    <linearGradient id="gradArcSWM" x1="100%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>

    <linearGradient id="gradArcNWM" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#a78bfa"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>

    <radialGradient id="glowNorthM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#38bdf8" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowEastM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fbbf24" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#fbbf24" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowSouthM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#10b981" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#10b981" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#10b981" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="glowWestM" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#a78bfa" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#a78bfa" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#a78bfa" stop-opacity="0"/>
    </radialGradient>

    <filter id="nodeGlowM" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- 1. Pure OLED Black Edge-to-Edge Canvas -->
  <rect width="512" height="512" fill="#000000"/>

  <!-- 2. Scaled to Safe Zone (80% centered, scale 0.8 around (256, 256)) -->
  <g transform="matrix(0.8 0 0 0.8 51.2 51.2)">
    <!-- Badge -->
    <rect x="24" y="24" width="464" height="464" rx="116" fill="url(#bgSquircleM)" stroke="url(#borderSquircleM)" stroke-width="2.5"/>
    <!-- Ambient Radiance -->
    <circle cx="256" cy="256" r="215" fill="url(#ambientCenterM)"/>
    <!-- Orbital Rings -->
    <circle cx="256" cy="256" r="176" fill="none" stroke="#334155" stroke-width="1.5" stroke-dasharray="6 6" stroke-opacity="0.45"/>
    <circle cx="256" cy="256" r="152" fill="none" stroke="#1e293b" stroke-width="1.2" stroke-opacity="0.35"/>
    <circle cx="256" cy="256" r="126" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-opacity="0.6"/>
    <circle cx="256" cy="256" r="74" fill="none" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4" stroke-opacity="0.5"/>
    <circle cx="256" cy="256" r="48" fill="none" stroke="#1e293b" stroke-width="1" stroke-opacity="0.4"/>

    <!-- Diagonal Rays & Pips -->
    <g stroke="#334155" stroke-width="1.2" stroke-dasharray="3 5" stroke-opacity="0.35">
      <line x1="168" y1="168" x2="204" y2="204"/>
      <line x1="308" y1="308" x2="344" y2="344"/>
      <line x1="344" y1="168" x2="308" y2="204"/>
      <line x1="204" y1="308" x2="168" y2="344"/>
    </g>
    <circle cx="380" cy="132" r="2.5" fill="#475569" opacity="0.6"/>
    <circle cx="380" cy="380" r="2.5" fill="#475569" opacity="0.6"/>
    <circle cx="132" cy="380" r="2.5" fill="#475569" opacity="0.6"/>
    <circle cx="132" cy="132" r="2.5" fill="#475569" opacity="0.6"/>

    <!-- Orbital Arcs -->
    <path d="M 256 130 A 126 126 0 0 1 382 256" fill="none" stroke="url(#gradArcNEM)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
    <path d="M 382 256 A 126 126 0 0 1 256 382" fill="none" stroke="url(#gradArcSEM)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
    <path d="M 256 382 A 126 126 0 0 1 130 256" fill="none" stroke="url(#gradArcSWM)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>
    <path d="M 130 256 A 126 126 0 0 1 256 130" fill="none" stroke="url(#gradArcNWM)" stroke-width="3.2" stroke-linecap="round" opacity="0.85"/>

    <!-- Radiant Pathways -->
    <line x1="256" y1="228" x2="256" y2="130" stroke="#38bdf8" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
    <line x1="256" y1="228" x2="256" y2="130" stroke="url(#gradNorthM)" stroke-width="5" stroke-linecap="round"/>
    <line x1="256" y1="228" x2="256" y2="130" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

    <line x1="284" y1="256" x2="382" y2="256" stroke="#fbbf24" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
    <line x1="284" y1="256" x2="382" y2="256" stroke="url(#gradEastM)" stroke-width="5" stroke-linecap="round"/>
    <line x1="284" y1="256" x2="382" y2="256" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

    <line x1="256" y1="284" x2="256" y2="382" stroke="#10b981" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
    <line x1="256" y1="284" x2="256" y2="382" stroke="url(#gradSouthM)" stroke-width="5" stroke-linecap="round"/>
    <line x1="256" y1="284" x2="256" y2="382" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

    <line x1="228" y1="256" x2="130" y2="256" stroke="#a78bfa" stroke-width="12" stroke-opacity="0.18" stroke-linecap="round"/>
    <line x1="228" y1="256" x2="130" y2="256" stroke="url(#gradWestM)" stroke-width="5" stroke-linecap="round"/>
    <line x1="228" y1="256" x2="130" y2="256" stroke="#ffffff" stroke-width="1.4" stroke-opacity="0.85" stroke-linecap="round"/>

    <!-- Nodes with Halos -->
    <circle cx="256" cy="130" r="30" fill="url(#glowNorthM)"/>
    <circle cx="256" cy="130" r="22" fill="none" stroke="#38bdf8" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
    <circle cx="256" cy="130" r="14" fill="#0d1117" stroke="#38bdf8" stroke-width="2.6" filter="url(#nodeGlowM)"/>
    <circle cx="256" cy="130" r="7.5" fill="#38bdf8"/>
    <circle cx="254" cy="128" r="2.2" fill="#ffffff" opacity="0.9"/>

    <circle cx="382" cy="256" r="30" fill="url(#glowEastM)"/>
    <circle cx="382" cy="256" r="22" fill="none" stroke="#fbbf24" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
    <circle cx="382" cy="256" r="14" fill="#0d1117" stroke="#fbbf24" stroke-width="2.6" filter="url(#nodeGlowM)"/>
    <circle cx="382" cy="256" r="7.5" fill="#fbbf24"/>
    <circle cx="380" cy="254" r="2.2" fill="#ffffff" opacity="0.9"/>

    <circle cx="256" cy="382" r="30" fill="url(#glowSouthM)"/>
    <circle cx="256" cy="382" r="22" fill="none" stroke="#10b981" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
    <circle cx="256" cy="382" r="14" fill="#0d1117" stroke="#10b981" stroke-width="2.6" filter="url(#nodeGlowM)"/>
    <circle cx="256" cy="382" r="7.5" fill="#10b981"/>
    <circle cx="254" cy="380" r="2.2" fill="#ffffff" opacity="0.9"/>

    <circle cx="130" cy="256" r="30" fill="url(#glowWestM)"/>
    <circle cx="130" cy="256" r="22" fill="none" stroke="#a78bfa" stroke-width="1.4" stroke-opacity="0.4" stroke-dasharray="3 2"/>
    <circle cx="130" cy="256" r="14" fill="#0d1117" stroke="#a78bfa" stroke-width="2.6" filter="url(#nodeGlowM)"/>
    <circle cx="130" cy="256" r="7.5" fill="#a78bfa"/>
    <circle cx="128" cy="254" r="2.2" fill="#ffffff" opacity="0.9"/>

    <!-- Central Faceted Hub -->
    <circle cx="256" cy="256" r="54" fill="url(#coreGlowM)"/>
    <g stroke="#ffffff" stroke-width="0.8" stroke-opacity="0.5">
      <polygon points="256,224 278.6,233.4 256,256" fill="#e0f2fe" opacity="0.92"/>
      <polygon points="278.6,233.4 288,256 256,256" fill="#bae6fd" opacity="0.90"/>
      <polygon points="288,256 278.6,278.6 256,256" fill="#7dd3fc" opacity="0.88"/>
      <polygon points="278.6,278.6 256,288 256,256" fill="#38bdf8" opacity="0.92"/>
      <polygon points="256,288 233.4,278.6 256,256" fill="#7dd3fc" opacity="0.88"/>
      <polygon points="233.4,278.6 224,256 256,256" fill="#bae6fd" opacity="0.90"/>
      <polygon points="224,256 233.4,233.4 256,256" fill="#e0f2fe" opacity="0.92"/>
      <polygon points="233.4,233.4 256,224 256,256" fill="#f0f9ff" opacity="0.95"/>
    </g>
    <g stroke="#ffffff" stroke-width="1.2" stroke-opacity="0.9">
      <polygon points="256,238 274,256 256,256" fill="#ffffff" opacity="0.98"/>
      <polygon points="274,256 256,274 256,256" fill="#e0f2fe" opacity="0.95"/>
      <polygon points="256,274 238,256 256,256" fill="#bae6fd" opacity="0.92"/>
      <polygon points="238,256 256,238 256,256" fill="#f0f9ff" opacity="0.98"/>
    </g>
    <polygon points="256,248 258,254 264,256 258,258 256,264 254,258 248,256 254,254" fill="#ffffff"/>
    <circle cx="256" cy="256" r="2.5" fill="#ffffff"/>
  </g>
</svg>
'''

def main():
    print("[*] Generating master SVG icons...")
    svg_path = os.path.join(ICONS_DIR, 'icon.svg')
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(SVG_CONTENT.strip() + '\n')
    print(f"    Saved: {svg_path}")

    maskable_svg_path = '/tmp/dreamhub_maskable.svg'
    with open(maskable_svg_path, 'w', encoding='utf-8') as f:
        f.write(SVG_MASKABLE_CONTENT.strip() + '\n')

    # Render ultra-high-res raster masters at 2048x2048 (4x supersampling)
    print("[*] Rendering 4x supersampled raster targets with ImageMagick...")
    master_png = '/tmp/dreamhub_icon_2048.png'
    maskable_master_png = '/tmp/dreamhub_maskable_2048.png'

    subprocess.run([
        'magick',
        '-density', '576',
        '-background', 'none',
        svg_path,
        '-resize', '2048x2048',
        master_png
    ], check=True)

    subprocess.run([
        'magick',
        '-density', '576',
        '-background', 'none',
        maskable_svg_path,
        '-resize', '2048x2048',
        maskable_master_png
    ], check=True)

    print("[*] Downsampling with Pillow Lanczos filtering for anti-aliasing perfection...")
    # Standard Icons from master_png
    with Image.open(master_png) as img:
        # 512x512
        p512 = os.path.join(ICONS_DIR, 'icon-512.png')
        img.resize((512, 512), Image.Resampling.LANCZOS).save(p512, format='PNG', optimize=True)
        print(f"    Saved: {p512} (512x512)")

        # 192x192
        p192 = os.path.join(ICONS_DIR, 'icon-192.png')
        img.resize((192, 192), Image.Resampling.LANCZOS).save(p192, format='PNG', optimize=True)
        print(f"    Saved: {p192} (192x192)")

    # Maskable Icons from maskable_master_png (80% safe zone centered over pure #000000)
    with Image.open(maskable_master_png) as img_m:
        # icon-maskable-512.png
        p_mask = os.path.join(ICONS_DIR, 'icon-maskable-512.png')
        img_m.resize((512, 512), Image.Resampling.LANCZOS).save(p_mask, format='PNG', optimize=True)
        print(f"    Saved: {p_mask} (512x512 maskable)")

        # apple-touch-icon.png (180x180)
        p_apple = os.path.join(ICONS_DIR, 'apple-touch-icon.png')
        img_m.resize((180, 180), Image.Resampling.LANCZOS).save(p_apple, format='PNG', optimize=True)
        print(f"    Saved: {p_apple} (180x180 apple-touch-icon)")

    print("[SUCCESS] All icons generated successfully with high visual fidelity!")

if __name__ == '__main__':
    main()
