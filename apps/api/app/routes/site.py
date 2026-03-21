from __future__ import annotations

import html
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.db import get_session, session_scope
from app.schemas import PublicReferenceResponse
from app.services.api_health import build_api_health
from app.services.public_reference import build_public_reference
from app.services.public_routes import list_public_endpoints
from app.time_utils import utc_now

router = APIRouter()

REFRESH_INTERVAL_MS = 12000
BRAND_ASSET_PATH = Path(__file__).resolve().parents[2] / "static" / "icon.svg"
METHOD_ORDER = {
    "GET": 0,
    "POST": 1,
    "PUT": 2,
    "PATCH": 3,
    "DELETE": 4,
    "OPTIONS": 5,
    "HEAD": 6,
}
BODY_METHODS = {"POST", "PUT", "PATCH"}
ROWS_PER_PAGE = 8

STATUS_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Artificer API | Status</title>
    <meta
      name="description"
      content="Artificer API status, current public route availability, and live reference data."
    />
    <link rel="icon" type="image/svg+xml" href="/static/icon.svg" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Sora:wght@500;600;700&display=swap"
    />
    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/bulma@1.0.4/css/bulma.min.css"
    />
    <script>
      (() => {
        try {
          const storageKey = "artificer-api-public-theme";
          const storedTheme = window.localStorage.getItem(storageKey);
          document.documentElement.dataset.theme = storedTheme || "dark";
        } catch (error) {
          document.documentElement.dataset.theme = "dark";
        }
      })();
    </script>
    <style>
      :root {
        color-scheme: light dark;
        --bg: #f8fafc;
        --bg-strong: #f1f5f9;
        --surface: rgba(255, 255, 255, 0.92);
        --surface-solid: #ffffff;
        --surface-soft: rgba(241, 245, 249, 0.92);
        --text: #0f172a;
        --muted: #64748b;
        --line: #d1d5db;
        --line-strong: #cbd5e1;
        --primary: #0891b2;
        --primary-strong: #0e7490;
        --primary-contrast: #f8fafc;
        --secondary: #64748b;
        --accent: #22d3ee;
        --success: #16a34a;
        --warning: #d97706;
        --error: #dc2626;
        --shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        --shadow-panel: 0 8px 24px rgba(15, 23, 42, 0.08);
        --radius-xl: 12px;
        --radius-lg: 10px;
        --radius-md: 8px;
        --radius-sm: 6px;
        --page-width: min(1380px, calc(100vw - 40px));
        --content-width: min(1180px, calc(100vw - 40px));
        --topbar-height: 82px;
        --font-ui: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        --font-display: "Sora", "Inter", system-ui, sans-serif;
        --font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
      }

      [data-theme="dark"] {
        color-scheme: dark;
        --bg: #0a0e12;
        --bg-strong: #111827;
        --surface: rgba(17, 24, 39, 0.92);
        --surface-solid: #111827;
        --surface-soft: rgba(31, 41, 51, 0.92);
        --text: #f3f4f6;
        --muted: #a3adbd;
        --line: #2a3442;
        --line-strong: #364152;
        --primary: #22d3ee;
        --primary-strong: #06b6d4;
        --primary-contrast: #0a0e12;
        --secondary: #8b95a7;
        --accent: #67e8f9;
        --success: #22c55e;
        --warning: #f59e0b;
        --error: #ef4444;
        --shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
        --shadow-panel: 0 8px 24px rgba(0, 0, 0, 0.45);
      }

      * {
        box-sizing: border-box;
      }

      html {
        scroll-behavior: smooth;
        scroll-padding-top: calc(var(--topbar-height) + 16px);
      }

      body {
        margin: 0;
        font-family: var(--font-ui);
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(8, 145, 178, 0.08), transparent 24%),
          radial-gradient(circle at top right, rgba(34, 211, 238, 0.06), transparent 20%),
          linear-gradient(180deg, var(--bg) 0%, var(--bg-strong) 100%);
      }

      [data-theme="dark"] body {
        background:
          radial-gradient(circle at top left, rgba(34, 211, 238, 0.14), transparent 24%),
          radial-gradient(circle at top right, rgba(103, 232, 249, 0.08), transparent 22%),
          linear-gradient(180deg, var(--bg) 0%, var(--bg-strong) 100%);
      }

      img {
        display: block;
        max-width: 100%;
      }

      a {
        color: inherit;
        text-decoration: none;
      }

      button {
        font: inherit;
      }

      .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }

      code,
      pre {
        font-family: var(--font-mono);
      }

      .site-shell {
        min-height: 100vh;
      }

      .topbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 40;
        backdrop-filter: blur(18px);
        background: rgba(248, 250, 252, 0.88);
        border-bottom: 1px solid var(--line);
      }

      .topbar .navbar-menu,
      .topbar .navbar-item,
      .topbar .navbar-link,
      .topbar .navbar-dropdown {
        background: transparent;
      }

      .topbar-inner {
        width: var(--page-width);
        min-height: var(--topbar-height);
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
      }

      .brand-lockup {
        display: flex;
        align-items: center;
        gap: 14px;
        min-width: 0;
      }

      .brand-mark {
        width: 64px;
        height: 64px;
        border-radius: 10px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
      }

      .brand-mark img {
        width: 100%;
        height: 100%;
        max-height: none;
        object-fit: contain;
      }

      .brand-kicker,
      .eyebrow {
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--primary);
      }

      .brand-title,
      .hero-title,
      .section-title {
        font-family: var(--font-display);
        letter-spacing: -0.03em;
      }

      .brand-title {
        display: block;
        font-size: 1.45rem;
        line-height: 1;
        font-weight: 700;
      }

      .brand-kicker {
        display: inline-flex;
        align-items: center;
        margin-top: 0.35rem;
        padding: 0.18rem 0.5rem;
        border-radius: 999px;
        border: 1px solid var(--line-strong);
        background: var(--surface-soft);
      }

      .topbar-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .topbar-toolbar {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .topbar .buttons {
        margin: 0;
        gap: 8px;
        padding: 4px;
        border-radius: var(--radius-lg);
        border: 1px solid var(--line);
        background: var(--surface);
      }

      .topbar-toggle {
        width: 48px;
        min-width: 48px;
        min-height: 48px;
        padding: 0;
        border-radius: var(--radius-sm);
      }

      .topbar .buttons .button {
        margin: 0;
      }

      .topbar-links {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .nav-link,
      .hero-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        min-height: 40px;
        padding: 0 0.95rem;
        border-radius: var(--radius-sm);
        font-weight: 600;
        font-size: 0.95rem;
        letter-spacing: -0.01em;
        line-height: 1;
        transition: transform 120ms ease-out, box-shadow 120ms ease-out, border-color 120ms ease-out, background 120ms ease-out;
      }

      .nav-link {
        background: rgba(255, 255, 255, 0);
        border: 1px solid var(--line);
        color: var(--text);
      }

      .nav-link.topbar-utility {
        color: var(--muted);
        background: rgba(255, 255, 255, 0.02);
        font-size: 0.88rem;
      }

      .theme-toggle {
        cursor: pointer;
        color: inherit;
        position: relative;
      }

      .theme-toggle .theme-icon {
        width: 20px;
        height: 20px;
        display: block;
      }

      .theme-toggle .theme-icon-sun {
        display: none;
      }

      .theme-toggle[aria-pressed="false"] .theme-icon-sun {
        display: block;
      }

      .theme-toggle[aria-pressed="false"] .theme-icon-moon {
        display: none;
      }

      .hero-link {
        background: var(--primary);
        border: 1px solid rgba(34, 211, 238, 0.24);
        color: var(--primary-contrast);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
      }

      [data-theme="dark"] .topbar {
        background: rgba(10, 14, 18, 0.88);
      }

      [data-theme="dark"] .topbar .buttons {
        background: rgba(17, 24, 39, 0.9);
        border-color: var(--line-strong);
      }

      [data-theme="dark"] .nav-link {
        background: rgba(255, 255, 255, 0.02);
        border-color: var(--line-strong);
      }

      [data-theme="dark"] .nav-link.topbar-utility {
        color: var(--secondary);
        background: rgba(255, 255, 255, 0.01);
      }

      .topbar .navbar-burger {
        color: var(--text);
        height: auto;
        min-height: 3.25rem;
      }

      .topbar .navbar-burger:hover {
        background: transparent;
      }

      .nav-link:hover,
      .hero-link:hover {
        transform: translateY(-1px);
        border-color: var(--line-strong);
        box-shadow: var(--shadow-panel);
      }

      .nav-link:hover {
        background: var(--surface-soft);
      }

      .hero-link:hover {
        background: var(--primary-strong);
        border-color: rgba(103, 232, 249, 0.28);
      }

      .hero-shell {
        min-height: calc(238vh - var(--topbar-height));
      }

      .hero-pin {
        position: sticky;
        top: var(--topbar-height);
        min-height: calc(100vh - var(--topbar-height));
        display: flex;
        align-items: stretch;
      }

      .hero-stage {
        width: 100%;
        min-height: calc(100vh - var(--topbar-height));
        position: relative;
        overflow: hidden;
      }

      .hero-visual {
        position: absolute;
        inset: 0;
        z-index: 1;
      }

      .hero-window {
        --hero-top-opacity: 1;
        --hero-bottom-opacity: 0;
        height: 100%;
        min-height: calc(100vh - var(--topbar-height));
        overflow: hidden;
        border-radius: 0;
        box-shadow: none;
        border: 0;
        background:
          radial-gradient(circle at 24% 20%, rgba(255, 255, 255, 0.84), transparent 24%),
          linear-gradient(180deg, rgba(201, 221, 236, 0.72), rgba(255, 248, 242, 0.96) 44%, rgba(240, 230, 214, 0.95));
        position: relative;
      }

      [data-theme="dark"] .hero-window {
        background:
          radial-gradient(circle at 24% 20%, rgba(255, 255, 255, 0.1), transparent 24%),
          linear-gradient(180deg, rgba(14, 28, 39, 0.52), rgba(10, 17, 24, 0.3) 44%, rgba(8, 13, 20, 0.42));
      }

      .hero-window::after {
        content: "";
        position: absolute;
        inset: auto 0 0;
        height: 120px;
        background: linear-gradient(180deg, rgba(250, 244, 235, 0), rgba(250, 244, 235, 0.32));
        pointer-events: none;
      }

      [data-theme="dark"] .hero-window::after {
        background: linear-gradient(180deg, rgba(8, 13, 20, 0), rgba(8, 13, 20, 0.42));
      }

      .hero-panel {
        position: absolute;
        inset: 0;
        padding: 0;
        margin: 0;
        overflow: hidden;
        will-change: opacity;
      }

      .hero-panel-top {
        opacity: var(--hero-top-opacity);
      }

      .hero-panel-bottom {
        opacity: var(--hero-bottom-opacity);
      }

      .hero-panel-media {
        display: block;
        width: 100%;
        height: auto;
      }

      .hero-panel-frame {
        position: absolute;
        inset: auto 0 0;
        width: 100%;
        aspect-ratio: 16 / 9;
        overflow: hidden;
      }

      .hero-panel-image {
        display: block;
        width: 100%;
        height: auto;
      }

      .hero-panel-image--legacy-bottom {
        transform: translateY(-50%);
      }

      .hero-panel::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.18));
        pointer-events: none;
      }

      [data-theme="dark"] .hero-panel::after {
        background: linear-gradient(180deg, rgba(8, 13, 20, 0.02), rgba(8, 13, 20, 0.22));
      }

      .hero-placeholder {
        width: 100%;
        height: 100%;
        display: grid;
        place-items: center;
        padding: 40px;
        background:
          radial-gradient(circle at 18% 20%, rgba(255, 255, 255, 0.88), transparent 18%),
          radial-gradient(circle at 78% 24%, rgba(34, 211, 238, 0.08), transparent 20%),
          linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.98));
      }

      [data-theme="dark"] .hero-placeholder {
        background:
          radial-gradient(circle at 18% 20%, rgba(103, 232, 249, 0.16), transparent 18%),
          radial-gradient(circle at 78% 24%, rgba(255, 255, 255, 0.08), transparent 20%),
          linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(10, 14, 18, 0.98));
      }

      .hero-placeholder-card {
        width: min(380px, 100%);
        padding: 28px;
        border-radius: var(--radius-lg);
        background: var(--surface);
        border: 1px solid var(--line);
        box-shadow: var(--shadow-panel);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 18px;
        text-align: center;
      }

      [data-theme="dark"] .hero-placeholder-card {
        background: var(--surface);
      }

      .hero-placeholder-card img {
        width: 84px;
        height: 84px;
      }

      .hero-placeholder-label {
        font-family: var(--font-display);
        font-size: clamp(2.2rem, 4vw, 3.4rem);
        line-height: 0.96;
      }

      .hero-copy {
        position: relative;
        z-index: 2;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        min-height: calc(100vh - var(--topbar-height));
        padding:
          clamp(16px, 2vw, 24px)
          clamp(18px, 3vw, 36px)
          clamp(18px, 3vw, 32px);
      }

      .hero-copy-inner {
        padding: clamp(18px, 2.1vw, 26px) clamp(22px, 2.6vw, 30px);
        margin: 0;
        border-radius: var(--radius-xl);
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid var(--line);
        backdrop-filter: blur(18px);
        box-shadow: var(--shadow-panel);
        display: grid;
        grid-template-columns: minmax(0, 1.42fr) minmax(560px, 0.88fr);
        gap: clamp(24px, 3vw, 52px);
        align-items: start;
      }

      [data-theme="dark"] .hero-copy-inner {
        background: rgba(17, 24, 39, 0.78);
      }

      .hero-copy-lede {
        min-width: 0;
      }

      .hero-copy-body {
        min-width: 0;
        max-width: 38rem;
        justify-self: end;
      }

      .hero-title {
        margin: 10px 0 0;
        max-width: 14ch;
        font-size: clamp(3.2rem, 6.3vw, 5.55rem);
        line-height: 0.92;
      }

      .hero-title .hero-title-accent {
        color: var(--primary);
      }

      .hero-description {
        max-width: 38rem;
        font-size: 1.1rem;
        line-height: 1.7;
        color: var(--muted);
        margin: 0 0 18px;
      }

      .hero-warning {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        margin: 0 0 20px;
        padding: 0.65rem 0.9rem;
        border-radius: 999px;
        border: 1px solid rgba(8, 145, 178, 0.2);
        background: rgba(34, 211, 238, 0.1);
        color: var(--primary);
        font-size: 0.92rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        white-space: nowrap;
      }

      .hero-warning-icon {
        font-size: 0.95rem;
        line-height: 1;
      }

      .hero-stat-row,
      .hero-actions,
      .section-actions,
      .endpoint-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }

      .hero-stat,
      .endpoint-method,
      .endpoint-tag,
      .reference-status {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: var(--surface-soft);
        padding: 0.7rem 1rem;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      .hero-stat-strong {
        border-color: rgba(8, 145, 178, 0.2);
        background: rgba(34, 211, 238, 0.1);
      }

      .reference-status.status-success {
        border-color: rgba(22, 163, 74, 0.2);
        background: rgba(22, 163, 74, 0.12);
        color: #166534;
      }

      .reference-status.status-warning {
        border-color: rgba(217, 119, 6, 0.18);
        background: rgba(217, 119, 6, 0.12);
        color: #92400e;
      }

      .reference-status.status-error {
        border-color: rgba(220, 38, 38, 0.18);
        background: rgba(220, 38, 38, 0.12);
        color: #991b1b;
      }

      .reference-status.status-neutral {
        border-color: rgba(100, 116, 139, 0.18);
        background: rgba(100, 116, 139, 0.12);
        color: #475569;
      }

      [data-theme="dark"] .reference-status.status-success {
        border-color: rgba(34, 197, 94, 0.24);
        background: rgba(5, 46, 26, 0.88);
        color: #86efac;
      }

      [data-theme="dark"] .reference-status.status-warning {
        border-color: rgba(245, 158, 11, 0.24);
        background: rgba(58, 42, 5, 0.88);
        color: #fcd34d;
      }

      [data-theme="dark"] .reference-status.status-error {
        border-color: rgba(239, 68, 68, 0.24);
        background: rgba(59, 10, 10, 0.88);
        color: #fca5a5;
      }

      [data-theme="dark"] .reference-status.status-neutral {
        border-color: rgba(139, 149, 167, 0.22);
        background: rgba(36, 48, 64, 0.92);
        color: #cbd5e1;
      }

      .hero-actions {
        margin-top: 20px;
      }

      .hero-actions .nav-link,
      .hero-actions .hero-link {
        padding-left: 1.35rem;
        padding-right: 1.35rem;
      }

      .status-shell,
      .reference-shell {
        width: var(--content-width);
        margin: 0 auto;
      }

      .status-shell {
        padding: calc(var(--topbar-height) + 44px) 0 24px;
      }

      .status-summary-grid {
        margin-top: 8px;
      }

      .status-dependency-header {
        margin: 34px 0 18px;
        align-items: start;
      }

      .status-card {
        height: 100%;
        border-radius: var(--radius-md);
        border: 1px solid var(--line);
        background: var(--surface-soft);
        box-shadow: var(--shadow);
        padding: 1.2rem 1.25rem;
      }

      .status-card-value {
        margin-top: 0.55rem;
        font-family: var(--font-display);
        font-size: 2rem;
        letter-spacing: -0.04em;
      }

      .status-card-copy {
        margin: 0.6rem 0 0;
        color: var(--muted);
        line-height: 1.6;
      }

      .reference-shell {
        padding: 84px 0 96px;
      }

      .reference-header {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 26px;
      }

      .section-title {
        margin: 10px 0 12px;
        font-size: clamp(2.5rem, 6vw, 4.2rem);
        line-height: 0.94;
      }

      .section-title-small {
        font-size: clamp(1.8rem, 4vw, 2.6rem);
        line-height: 1;
      }

      .section-description {
        max-width: 42rem;
        margin: 0;
        color: var(--muted);
        font-size: 1.04rem;
        line-height: 1.8;
      }

      .reference-toolbar {
        margin-bottom: 20px;
      }

      .reference-toolbar.columns {
        margin-bottom: 20px;
      }

      .reference-toolbar-label {
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 0.5rem;
      }

      .reference-field .input,
      .reference-field .select select {
        border-color: var(--line);
        background: var(--surface-solid);
        color: var(--text);
      }

      [data-theme="dark"] .reference-field .input,
      [data-theme="dark"] .reference-field .select select {
        background: var(--surface-solid);
        border-color: var(--line);
        color: var(--text);
      }

      .reference-field .input::placeholder {
        color: var(--muted);
      }

      .reference-field .select,
      .reference-field .select select {
        width: 100%;
      }

      .method-filter-list {
        margin: 0;
      }

      .reference-table-shell {
        padding: 0;
        border: 0;
        background: transparent;
        box-shadow: none;
        overflow: visible;
      }

      .reference-table-scroll {
        overflow: visible;
      }

      .reference-table {
        width: 100%;
        min-width: 0;
        border-collapse: separate;
        border-spacing: 0;
        table-layout: auto;
        border: 1px solid var(--line);
        background: var(--surface-solid);
        border-radius: var(--radius-md);
        overflow: hidden;
      }

      .reference-table th {
        padding: 16px 22px;
        text-align: left;
        border-bottom: 1px solid var(--line);
        background: transparent;
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
      }

      .reference-table thead th {
        background: var(--surface-solid);
        box-shadow: inset 0 -1px 0 var(--line);
      }

      [data-theme="dark"] .reference-table th {
        background: var(--surface-solid);
      }

      .reference-table th:nth-child(1),
      .reference-table td:nth-child(1) {
        width: 96px;
      }

      .reference-table th:nth-child(2),
      .reference-table td:nth-child(2) {
        width: 26%;
      }

      .reference-table th:nth-child(3),
      .reference-table td:nth-child(3) {
        width: 36%;
      }

      .reference-table th:nth-child(4),
      .reference-table td:nth-child(4) {
        width: 132px;
      }

      .reference-table th:nth-child(5),
      .reference-table td:nth-child(5) {
        width: 144px;
      }

      .reference-table th:nth-child(6),
      .reference-table td:nth-child(6) {
        width: 120px;
      }

      .reference-table td {
        padding: 18px 22px;
        border-bottom: 1px solid var(--line);
        vertical-align: top;
      }

      .reference-table tbody tr:last-child td {
        border-bottom: 0;
      }

      .reference-table td.reference-table-about,
      .reference-table td.reference-table-path {
        min-width: 0;
      }

      .endpoint-name {
        margin: 0;
        font-size: 1.12rem;
        font-weight: 800;
      }

      .endpoint-summary {
        margin: 8px 0 0;
        color: var(--muted);
        line-height: 1.6;
      }

      .endpoint-about {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .endpoint-path {
        font-family: var(--font-mono);
        font-size: 0.92rem;
        line-height: 1.6;
        font-weight: 700;
        overflow-wrap: anywhere;
      }

      .endpoint-path-note {
        margin-top: 6px;
        font-size: 0.8rem;
        color: var(--muted);
        font-family: var(--font-mono);
        overflow-wrap: anywhere;
      }

      .endpoint-inline-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 4px;
      }

      .endpoint-tag.tag,
      .endpoint-category.tag,
      .endpoint-status.tag,
      .endpoint-method.tag {
        border: 1px solid transparent;
        font-weight: 700;
      }

      .endpoint-category.tag {
        background: rgba(100, 116, 139, 0.12);
        border-color: rgba(100, 116, 139, 0.18);
        color: #334155;
      }

      [data-theme="dark"] .endpoint-category.tag {
        background: rgba(36, 48, 64, 0.92);
        border-color: rgba(139, 149, 167, 0.18);
        color: #cbd5e1;
      }

      .endpoint-method.method-get {
        background: rgba(22, 163, 74, 0.12);
        border-color: rgba(22, 163, 74, 0.18);
        color: #166534;
      }

      .endpoint-method.method-post {
        background: rgba(8, 145, 178, 0.12);
        border-color: rgba(8, 145, 178, 0.18);
        color: #0f766e;
      }

      .endpoint-method.method-put,
      .endpoint-method.method-patch {
        background: rgba(217, 119, 6, 0.12);
        border-color: rgba(217, 119, 6, 0.18);
        color: #92400e;
      }

      .endpoint-method.method-delete {
        background: rgba(220, 38, 38, 0.12);
        border-color: rgba(220, 38, 38, 0.18);
        color: #991b1b;
      }

      .endpoint-method.method-options,
      .endpoint-method.method-head {
        background: rgba(100, 116, 139, 0.12);
        border-color: rgba(100, 116, 139, 0.18);
        color: #475569;
      }

      .endpoint-status.tag {
        font-variant-numeric: tabular-nums;
      }

      .endpoint-status.status-success {
        background: rgba(22, 163, 74, 0.12);
        border-color: rgba(22, 163, 74, 0.18);
        color: #166534;
      }

      .endpoint-status.status-error {
        background: rgba(220, 38, 38, 0.12);
        border-color: rgba(220, 38, 38, 0.18);
        color: #991b1b;
      }

      .endpoint-status.status-neutral {
        background: rgba(100, 116, 139, 0.12);
        border-color: rgba(100, 116, 139, 0.18);
        color: #475569;
      }

      .endpoint-status.status-warning {
        background: rgba(217, 119, 6, 0.12);
        border-color: rgba(217, 119, 6, 0.18);
        color: #92400e;
      }

      [data-theme="dark"] .endpoint-status.status-success {
        background: rgba(5, 46, 26, 0.88);
        border-color: rgba(34, 197, 94, 0.24);
        color: #86efac;
      }

      [data-theme="dark"] .endpoint-status.status-error {
        background: rgba(59, 10, 10, 0.88);
        border-color: rgba(239, 68, 68, 0.24);
        color: #fca5a5;
      }

      [data-theme="dark"] .endpoint-status.status-neutral {
        background: rgba(36, 48, 64, 0.92);
        border-color: rgba(139, 149, 167, 0.22);
        color: #cbd5e1;
      }

      [data-theme="dark"] .endpoint-status.status-warning {
        background: rgba(58, 42, 5, 0.88);
        border-color: rgba(245, 158, 11, 0.24);
        color: #fcd34d;
      }

      .reference-pagination {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 16px 20px;
        border-top: 1px solid var(--line);
        background: var(--surface);
      }

      [data-theme="dark"] .reference-pagination {
        background: var(--surface);
      }

      .pagination-status {
        font-size: 0.82rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
      }

      .pagination-controls {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }

      .reference-toolbar .button,
      .reference-pagination .button {
        border-color: var(--line);
      }

      .reference-toolbar .button.is-light,
      .reference-pagination .button.is-light {
        background: var(--surface-solid);
        color: var(--text);
      }

      [data-theme="dark"] .reference-toolbar .button.is-light,
      [data-theme="dark"] .reference-pagination .button.is-light {
        background: var(--surface-solid);
        color: var(--text);
      }

      .sample-block {
        margin: 0;
        max-height: none;
        overflow: visible;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        word-break: break-word;
        background: var(--surface-soft);
        color: var(--text);
        border: 1px solid var(--line);
        border-radius: var(--radius-sm);
        padding: 1rem;
        font-family: var(--font-mono);
        font-size: 0.86rem;
        line-height: 1.6;
      }

      .payload-popover .modal-background {
        background: rgba(8, 12, 18, 0.68);
        backdrop-filter: blur(12px);
      }

      .payload-popover .modal-card {
        width: min(760px, calc(100vw - 32px));
        box-shadow: var(--shadow-panel);
        overflow: hidden;
      }

      .payload-popover .modal-card-head,
      .payload-popover .modal-card-body {
        background: var(--surface-solid);
        border-color: var(--line);
        color: var(--text);
        box-shadow: none;
      }

      .payload-popover .modal-card-head {
        align-items: flex-start;
      }

      .payload-popover .modal-card-head-content {
        flex: 1 1 auto;
        min-width: 0;
      }

      .payload-popover .modal-card-title {
        color: var(--text);
        font-family: var(--font-display);
      }

      .payload-popover .modal-card-head .delete {
        margin-left: auto;
        flex: 0 0 auto;
      }

      .payload-meta {
        margin-top: 0.5rem;
        color: var(--muted);
        font-size: 0.95rem;
        line-height: 1.6;
      }

      .sample-sections {
        display: grid;
        gap: 18px;
      }

      .sample-section {
        display: grid;
        gap: 10px;
      }

      .sample-section-header {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
      }

      .sample-section-title {
        font-size: 0.92rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--primary);
      }

      .sample-section-meta {
        color: var(--muted);
        font-size: 0.94rem;
      }

      [data-theme="dark"] .sample-block {
        background: var(--surface-soft);
      }

      .empty-state {
        border-radius: var(--radius-md);
        border: 1px solid var(--line);
        background: var(--surface-soft);
        padding: 28px;
        color: var(--muted);
      }

      [data-theme="dark"] .empty-state {
        background: var(--surface-soft);
      }

      .footer-shell {
        width: var(--content-width);
        margin: 0 auto;
        padding: 0 0 48px;
        color: var(--muted);
        display: flex;
        justify-content: space-between;
        gap: 16px;
        flex-wrap: wrap;
      }

      @media (max-width: 1040px) {
        .hero-copy-inner {
          width: min(100%, calc(100% - 28px));
          grid-template-columns: 1fr;
          gap: 18px;
        }

        .hero-copy-body {
          max-width: none;
          justify-self: stretch;
        }

        .hero-warning {
          white-space: normal;
        }

        .hero-title {
          max-width: 9ch;
        }

        .reference-toolbar {
          grid-template-columns: 1fr;
          align-items: stretch;
        }

        .reference-table-scroll {
          overflow-x: auto;
        }

        .reference-table {
          min-width: 820px;
        }

        .reference-pagination {
          flex-direction: column;
          align-items: stretch;
        }

        .pagination-controls {
          justify-content: space-between;
        }
      }

      @media (max-width: 720px) {
        :root {
          --page-width: min(100vw - 24px, 100vw - 24px);
          --content-width: min(100vw - 24px, 100vw - 24px);
          --topbar-height: 74px;
        }

        .topbar-inner {
          padding: 10px 0;
        }

        .brand-mark {
          width: 56px;
          height: 56px;
        }

        .topbar .navbar-menu {
          background: var(--surface);
          border-radius: var(--radius-lg);
          border: 1px solid var(--line);
          box-shadow: var(--shadow-panel);
          padding: 0.65rem;
          margin-top: 0.5rem;
        }

        [data-theme="dark"] .topbar .navbar-menu {
          background: var(--surface);
        }

        .topbar .buttons {
          width: 100%;
          justify-content: stretch;
        }

        .topbar-toolbar {
          width: 100%;
          display: grid;
          gap: 8px;
        }

        .topbar .buttons .button {
          width: 100%;
        }

        .topbar-toggle {
          width: 48px;
          min-width: 48px;
          justify-self: start;
        }

        .hero-shell {
          min-height: calc(214vh - var(--topbar-height));
        }

        .hero-pin {
          top: var(--topbar-height);
          min-height: calc(100vh - var(--topbar-height));
        }

        .hero-stage {
          min-height: calc(100vh - var(--topbar-height));
        }

        .hero-title {
          font-size: clamp(3.2rem, 17vw, 4.9rem);
        }

        .hero-description {
          font-size: 1.04rem;
        }

        .hero-copy {
          min-height: calc(100vh - var(--topbar-height));
          align-items: flex-start;
          justify-content: stretch;
          padding:
            12px
            16px
            16px;
        }

        .hero-copy-inner {
          width: 100%;
          border-radius: 24px;
          padding: 18px;
        }

        .hero-window {
          min-height: calc(100vh - var(--topbar-height));
        }

        .reference-header,
        .footer-shell {
          display: block;
        }

        .section-actions {
          margin-top: 18px;
        }

        .payload-popover .modal-card {
          width: calc(100vw - 24px);
          margin: 12px auto;
        }
      }
    </style>
  </head>
  <body>
    <div class="site-shell">
      <header>
        <nav class="navbar is-fixed-top topbar" role="navigation" aria-label="main navigation">
          <div class="topbar-inner">
            <div class="navbar-brand">
              <a class="navbar-item brand-lockup" href="#top">
                <span class="brand-mark"><img src="/static/icon.svg" alt="Artificer logo" /></span>
                <span>
                  <span class="brand-title">Artificer</span>
                  <span class="brand-kicker">API status</span>
                </span>
              </a>

              <a
                role="button"
                class="navbar-burger"
                aria-label="menu"
                aria-expanded="false"
                data-target="homepage-nav"
              >
                <span aria-hidden="true"></span>
                <span aria-hidden="true"></span>
                <span aria-hidden="true"></span>
                <span aria-hidden="true"></span>
              </a>
            </div>

            <div class="navbar-menu" id="homepage-nav">
              <div class="navbar-end topbar-actions">
                <div class="navbar-item">
                  <div class="topbar-toolbar">
                    <button
                      class="button is-light nav-link theme-toggle topbar-toggle"
                      id="theme-toggle"
                      type="button"
                      aria-pressed="false"
                      aria-label="Switch to light mode"
                      title="Switch to light mode"
                    >
                      <span class="sr-only">Toggle color theme</span>
                      <svg class="theme-icon theme-icon-moon" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                        <path d="M18 15.2A7.2 7.2 0 0 1 8.8 6a7.8 7.8 0 1 0 9.2 9.2Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                      <svg class="theme-icon theme-icon-sun" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.8" />
                        <path d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5M18.7 5.3l-1.5 1.5M6.8 17.2l-1.5 1.5M18.7 18.7l-1.5-1.5M6.8 6.8 5.3 5.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                      </svg>
                    </button>
                    <div class="buttons">
                      <a class="button is-light nav-link" href="#status">Status</a>
                      <a class="button is-light nav-link" href="#reference">Routes</a>
                    </div>
                    <div class="buttons">
                      <a class="button is-light nav-link topbar-utility" href="/api/reference.json">Reference</a>
                      <a class="button is-light nav-link topbar-utility" href="/openapi.json">OpenAPI</a>
                      <a class="button is-link hero-link" href="/docs">Docs</a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </nav>
      </header>

      <main id="top">
        <section class="section status-shell" id="status">
          <div class="reference-header">
            <div>
              <div class="eyebrow">API status</div>
              <h1 class="section-title">Artificer API status.</h1>
              <p class="section-description">
                Health, reference links, and published routes.
              </p>
            </div>

            <div class="section-actions">
              <span class="reference-status __INITIAL_HEALTH_TONE__" id="status-health-pill">__INITIAL_HEALTH_STATUS__</span>
              <span class="reference-status" id="reference-refresh">Updated just now</span>
            </div>
          </div>

          <div class="columns is-variable is-4 is-multiline status-summary-grid">
            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">Health</div>
                <div class="status-card-value" data-health-status>__INITIAL_HEALTH_STATUS__</div>
                <p class="status-card-copy">Derived from dependency checks.</p>
              </article>
            </div>

            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">Public routes</div>
                <div class="status-card-value"><span data-endpoint-count>__ENDPOINT_COUNT__</span></div>
                <p class="status-card-copy">Routes in the public reference.</p>
              </article>
            </div>

            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">Live runtime</div>
                <div class="status-card-value" data-live-route-count>__INITIAL_LIVE_ROUTE_COUNT__</div>
                <p class="status-card-copy">Routes on active deployments.</p>
              </article>
            </div>

            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">Legacy mock</div>
                <div class="status-card-value" data-legacy-route-count>__INITIAL_LEGACY_ROUTE_COUNT__</div>
                <p class="status-card-copy">Routes still using the legacy mock path.</p>
              </article>
            </div>
          </div>

          <div class="reference-header status-dependency-header">
            <div>
              <div class="eyebrow">Dependency health</div>
              <h2 class="section-title section-title-small">Dependency checks.</h2>
              <p class="section-description">
                Each dependency reports its own status and latency.
              </p>
            </div>
          </div>

          <div class="columns is-variable is-4 is-multiline status-summary-grid" id="dependency-health-grid">__INITIAL_HEALTH_ROWS__</div>
        </section>

        <section class="section reference-shell" id="reference">
          <div class="reference-header">
            <div>
              <div class="eyebrow">Quick reference</div>
              <h2 class="section-title">Published routes.</h2>
              <p class="section-description">
                Current public routes. Refreshes every __REFRESH_SECONDS__ seconds.
              </p>
            </div>

            <div class="section-actions">
              <a class="nav-link" href="/api/reference.json">Reference</a>
              <a class="nav-link" href="/openapi.json">OpenAPI</a>
            </div>
          </div>

          <div class="columns is-variable is-4 is-multiline reference-toolbar">
            <div class="column is-4-desktop is-12-tablet">
              <div class="field reference-field">
                <label class="label reference-toolbar-label" for="reference-search">Find a route</label>
                <div class="control">
                  <input
                    class="input"
                    id="reference-search"
                    type="search"
                    placeholder="Search by path, name, category, or tag"
                  />
                </div>
              </div>
            </div>

            <div class="column is-4-desktop is-12-tablet">
              <div class="field">
                <label class="label reference-toolbar-label">Method</label>
                <div class="buttons method-filter-list" id="reference-method-filters">__INITIAL_METHOD_FILTERS__</div>
              </div>
            </div>

            <div class="column is-2-desktop is-6-tablet">
              <div class="field reference-field">
                <label class="label reference-toolbar-label" for="reference-category-filter">Category</label>
                <div class="control select is-fullwidth">
                  <select id="reference-category-filter">__INITIAL_CATEGORY_OPTIONS__</select>
                </div>
              </div>
            </div>

            <div class="column is-2-desktop is-6-tablet">
              <div class="field">
                <label class="label reference-toolbar-label">Visible</label>
                <span class="tag is-medium is-info is-light is-rounded" id="reference-results">
                  Showing __ENDPOINT_COUNT__ routes
                </span>
              </div>
            </div>
          </div>

          <div class="reference-table-shell">
            <div class="table-container reference-table-scroll">
              <table class="table is-fullwidth is-hoverable is-striped reference-table">
                <thead>
                  <tr>
                    <th scope="col">Method</th>
                    <th scope="col">Path</th>
                    <th scope="col">About</th>
                    <th scope="col">Category</th>
                    <th scope="col">Published</th>
                    <th scope="col">Examples</th>
                  </tr>
                </thead>
                <tbody id="reference-table-body">__INITIAL_ROWS__</tbody>
              </table>
            </div>
            <div class="reference-pagination">
              <span class="pagination-status" id="reference-page-status">__INITIAL_PAGE_STATUS__</span>
              <nav class="pagination is-right" role="navigation" aria-label="pagination">
                <button class="button is-light pagination-previous is-rounded" id="reference-prev-page" type="button" __INITIAL_PREV_DISABLED__>
                  Previous
                </button>
                <button class="button is-light pagination-next is-rounded" id="reference-next-page" type="button" __INITIAL_NEXT_DISABLED__>
                  Next
                </button>
              </nav>
            </div>
          </div>
        </section>
      </main>

      <footer class="footer-shell">
        <span>Artificer API</span>
        <span>OpenAPI at <code>/openapi.json</code></span>
      </footer>
    </div>

    <div class="modal payload-popover" id="payload-popover" aria-live="polite" aria-hidden="true">
      <div class="modal-background" id="payload-popover-backdrop"></div>
      <div class="modal-card" role="dialog" aria-modal="true">
        <header class="modal-card-head">
          <div class="modal-card-head-content">
            <div class="eyebrow">Sample JSON</div>
            <p class="modal-card-title" id="payload-popover-title">Route sample</p>
            <div class="payload-meta" id="payload-popover-meta"></div>
          </div>
          <button class="delete" id="payload-popover-close" type="button" aria-label="Close sample JSON"></button>
        </header>
        <section class="modal-card-body">
          <div class="sample-sections">
            <section class="sample-section" id="payload-popover-request-section" hidden>
              <div class="sample-section-header">
                <div class="sample-section-title">Request JSON</div>
                <div class="sample-section-meta" id="payload-popover-request-meta"></div>
              </div>
              <pre class="sample-block" id="payload-popover-request-body"></pre>
            </section>
            <section class="sample-section">
              <div class="sample-section-header">
                <div class="sample-section-title">Response example</div>
                <div class="sample-section-meta" id="payload-popover-response-meta"></div>
              </div>
              <pre class="sample-block" id="payload-popover-response-body"></pre>
            </section>
          </div>
        </section>
      </div>
    </div>

    <script id="initial-reference-data" type="application/json">__INITIAL_REFERENCE_JSON__</script>
    <script id="initial-health-data" type="application/json">__INITIAL_HEALTH_JSON__</script>
    <script>
      function readInitialPayload(scriptId, label) {
        const payloadNode = document.getElementById(scriptId);
        if (!payloadNode) {
          return {};
        }

        try {
          return JSON.parse(payloadNode.textContent || "{}");
        } catch (error) {
          console.warn(`Unable to parse initial ${label} payload`, error);
          return {};
        }
      }

      const themeStorageKey = "artificer-api-public-theme";
      const initialReference = readInitialPayload("initial-reference-data", "reference");
      const initialHealth = readInitialPayload("initial-health-data", "health");
      const refreshIntervalMs = __REFRESH_INTERVAL_MS__;
      const rowsPerPage = __ROWS_PER_PAGE__;
      const themeToggle = document.getElementById("theme-toggle");
      const referenceTableBody = document.getElementById("reference-table-body");
      const methodFilters = document.getElementById("reference-method-filters");
      const categoryFilter = document.getElementById("reference-category-filter");
      const searchInput = document.getElementById("reference-search");
      const resultsLabel = document.getElementById("reference-results");
      const refreshLabel = document.getElementById("reference-refresh");
      const pageStatus = document.getElementById("reference-page-status");
      const prevPageButton = document.getElementById("reference-prev-page");
      const nextPageButton = document.getElementById("reference-next-page");
      const payloadBackdrop = document.getElementById("payload-popover-backdrop");
      const payloadPopover = document.getElementById("payload-popover");
      const payloadTitle = document.getElementById("payload-popover-title");
      const payloadMeta = document.getElementById("payload-popover-meta");
      const payloadRequestSection = document.getElementById("payload-popover-request-section");
      const payloadRequestMeta = document.getElementById("payload-popover-request-meta");
      const payloadRequestBody = document.getElementById("payload-popover-request-body");
      const payloadResponseMeta = document.getElementById("payload-popover-response-meta");
      const payloadResponseBody = document.getElementById("payload-popover-response-body");
      const payloadClose = document.getElementById("payload-popover-close");
      const navbarBurger = document.querySelector(".navbar-burger");
      const navbarMenu = document.getElementById("homepage-nav");
      const statusHealthPill = document.getElementById("status-health-pill");
      const dependencyHealthGrid = document.getElementById("dependency-health-grid");
      const countTargets = Array.from(document.querySelectorAll("[data-endpoint-count]"));
      const healthStatusTargets = Array.from(document.querySelectorAll("[data-health-status]"));
      const liveRouteCountTargets = Array.from(document.querySelectorAll("[data-live-route-count]"));
      const legacyRouteCountTargets = Array.from(document.querySelectorAll("[data-legacy-route-count]"));
      const methodPreference = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"];
      const bodyMethods = new Set(["POST", "PUT", "PATCH"]);
      const filterState = {
        query: "",
        method: "all",
        category: "all",
        page: 1,
      };
      let currentReference = initialReference;
      let currentHealth = initialHealth;
      let renderedEndpoints = [];

      function escapeHtml(value) {
        return String(value ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function formatJson(value) {
        return escapeHtml(JSON.stringify(value ?? null, null, 2));
      }

      function applyTheme(theme) {
        const nextTheme = theme === "dark" ? "dark" : "light";
        document.documentElement.dataset.theme = nextTheme;

        if (themeToggle) {
          const darkActive = nextTheme === "dark";
          themeToggle.setAttribute("aria-pressed", String(darkActive));
          themeToggle.setAttribute("aria-label", darkActive ? "Switch to light mode" : "Switch to dark mode");
          themeToggle.setAttribute("title", darkActive ? "Switch to light mode" : "Switch to dark mode");
        }
      }

      function toggleTheme() {
        const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        applyTheme(nextTheme);
        try {
          window.localStorage.setItem(themeStorageKey, nextTheme);
        } catch (error) {
          console.warn("Unable to persist theme preference", error);
        }
      }

      function timeAgo(isoValue) {
        if (!isoValue) {
          return "Updated just now";
        }

        const updatedAt = new Date(isoValue).getTime();
        if (Number.isNaN(updatedAt)) {
          return "Updated just now";
        }

        const diffSeconds = Math.max(Math.round((Date.now() - updatedAt) / 1000), 0);
        if (diffSeconds < 5) {
          return "Updated just now";
        }
        if (diffSeconds < 60) {
          return `Updated ${diffSeconds}s ago`;
        }

        const diffMinutes = Math.round(diffSeconds / 60);
        if (diffMinutes < 60) {
          return `Updated ${diffMinutes}m ago`;
        }

        const diffHours = Math.round(diffMinutes / 60);
        return `Updated ${diffHours}h ago`;
      }

      function endpointMethod(endpoint) {
        return String(endpoint?.method || "GET").toUpperCase();
      }

      function endpointCategory(endpoint) {
        return String(endpoint?.category || "uncategorized").trim() || "uncategorized";
      }

      function statusToneClass(tone) {
        if (tone === "success" || tone === "healthy") {
          return "status-success";
        }
        if (tone === "warning" || tone === "degraded") {
          return "status-warning";
        }
        if (tone === "error" || tone === "unhealthy") {
          return "status-error";
        }
        return "status-neutral";
      }

      function endpointPublicationStatus(endpoint) {
        return endpoint?.publication_status || {
          label: "Unknown",
          tone: "neutral",
        };
      }

      function healthStatusLabel(status) {
        const normalized = String(status || "").trim().toLowerCase();
        if (normalized === "healthy") {
          return "Healthy";
        }
        if (normalized === "degraded") {
          return "Degraded";
        }
        if (normalized === "unhealthy") {
          return "Unhealthy";
        }
        return "Unknown";
      }

      function renderDependencyCards(dependencies) {
        if (!dependencyHealthGrid) {
          return;
        }

        const safeDependencies = Array.isArray(dependencies) ? dependencies : [];
        if (!safeDependencies.length) {
          dependencyHealthGrid.innerHTML = `
            <div class="column is-12">
              <article class="status-card">
                <div class="eyebrow">Dependencies</div>
                <div class="status-card-value">Unavailable</div>
                <p class="status-card-copy">Dependency health data is currently unavailable.</p>
              </article>
            </div>
          `;
          return;
        }

        dependencyHealthGrid.innerHTML = safeDependencies.map((dependency) => {
          const label = escapeHtml(dependency?.label || dependency?.name || "Dependency");
          const status = healthStatusLabel(dependency?.status);
          const toneClass = statusToneClass(dependency?.status);
          const latencyMarkup = dependency?.latency_ms !== undefined && dependency?.latency_ms !== null
            ? `<div class="endpoint-inline-tags"><span class="tag is-light is-rounded endpoint-status ${toneClass}">${escapeHtml(`${dependency.latency_ms} ms`)}</span></div>`
            : "";

          return `
            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">${label}</div>
                <div class="status-card-value">${escapeHtml(status)}</div>
                <p class="status-card-copy">${escapeHtml(dependency?.detail || "No dependency detail available.")}</p>
                ${latencyMarkup}
              </article>
            </div>
          `;
        }).join("");
      }

      function renderHealth(payload) {
        currentHealth = payload || {};

        const overallStatus = healthStatusLabel(currentHealth?.status);
        const overallToneClass = statusToneClass(currentHealth?.status);
        const summary = currentHealth?.summary || {};

        if (statusHealthPill) {
          statusHealthPill.textContent = overallStatus;
          statusHealthPill.classList.remove("status-success", "status-warning", "status-error", "status-neutral");
          statusHealthPill.classList.add(overallToneClass);
        }

        healthStatusTargets.forEach((node) => {
          node.textContent = overallStatus;
        });
        liveRouteCountTargets.forEach((node) => {
          node.textContent = String(summary?.published_live_routes ?? 0);
        });
        legacyRouteCountTargets.forEach((node) => {
          node.textContent = String(summary?.legacy_mock_routes ?? 0);
        });

        renderDependencyCards(currentHealth?.dependencies);
      }

      function sortMethods(methods) {
        return methods.sort((left, right) => {
          const leftIndex = methodPreference.indexOf(left);
          const rightIndex = methodPreference.indexOf(right);

          if (leftIndex === -1 && rightIndex === -1) {
            return left.localeCompare(right);
          }
          if (leftIndex === -1) {
            return 1;
          }
          if (rightIndex === -1) {
            return -1;
          }
          return leftIndex - rightIndex;
        });
      }

      function collectMethods(endpoints) {
        return sortMethods(Array.from(new Set(endpoints.map((endpoint) => endpointMethod(endpoint)))));
      }

      function collectCategories(endpoints) {
        return Array.from(new Set(endpoints.map((endpoint) => endpointCategory(endpoint)))).sort((left, right) =>
          left.localeCompare(right),
        );
      }

      function normalizeSearchText(endpoint) {
        const terms = [
          endpoint?.name,
          endpoint?.summary,
          endpoint?.description,
          endpoint?.path,
          endpoint?.example_path,
          endpointCategory(endpoint),
          endpointMethod(endpoint),
          ...(Array.isArray(endpoint?.tags) ? endpoint.tags : []),
        ];

        return terms
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
      }

      function renderMethodFilters(endpoints) {
        if (!methodFilters) {
          return;
        }

        const methods = collectMethods(endpoints);
        if (filterState.method !== "all" && !methods.includes(filterState.method)) {
          filterState.method = "all";
        }

        methodFilters.innerHTML = [
          `<button type="button" class="button is-small is-rounded method-filter ${filterState.method === "all" ? "is-link" : "is-light"}" data-method-filter="all">All methods</button>`,
          ...methods.map(
            (method) =>
              `<button type="button" class="button is-small is-rounded method-filter ${filterState.method === method ? "is-link" : "is-light"}" data-method-filter="${escapeHtml(method)}">${escapeHtml(method)}</button>`,
          ),
        ].join("");
      }

      function renderCategoryOptions(endpoints) {
        if (!categoryFilter) {
          return;
        }

        const categories = collectCategories(endpoints);
        if (filterState.category !== "all" && !categories.includes(filterState.category)) {
          filterState.category = "all";
        }

        categoryFilter.innerHTML = [
          '<option value="all">All categories</option>',
          ...categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`),
        ].join("");
        categoryFilter.value = filterState.category;
      }

      function matchesFilters(endpoint) {
        if (filterState.method !== "all" && endpointMethod(endpoint) !== filterState.method) {
          return false;
        }

        if (filterState.category !== "all" && endpointCategory(endpoint) !== filterState.category) {
          return false;
        }

        if (filterState.query && !normalizeSearchText(endpoint).includes(filterState.query)) {
          return false;
        }

        return true;
      }

      function hasRequestExample(endpoint) {
        return bodyMethods.has(endpointMethod(endpoint)) && endpoint?.sample_request !== undefined && endpoint?.sample_request !== null;
      }

      function renderEndpointRow(endpoint, index) {
        const tags = Array.isArray(endpoint.tags) ? endpoint.tags : [];
        const method = endpointMethod(endpoint);
        const methodClass = `method-${method.toLowerCase()}`;
        const publicationStatus = endpointPublicationStatus(endpoint);
        const publicationLabel = String(publicationStatus?.label || "Unknown");
        const publicationTone = statusToneClass(publicationStatus?.tone);
        const examplePath = endpoint.example_path || endpoint.path || "/api/example";
        const templatePath =
          endpoint.path && endpoint.path !== examplePath
            ? `<div class="endpoint-path-note">${escapeHtml(endpoint.path)}</div>`
            : "";
        const tagMarkup = tags.length
          ? `<div class="endpoint-inline-tags">${tags
              .map((tag) => `<span class="tag is-light is-rounded endpoint-tag">${escapeHtml(tag)}</span>`)
              .join("")}</div>`
          : "";
        const exampleLabel = hasRequestExample(endpoint) ? "Examples" : "Example";

        return `
          <tr>
            <td>
              <span class="tag is-light is-rounded endpoint-method ${methodClass}">${escapeHtml(method)}</span>
            </td>
            <td class="reference-table-path">
              <div class="endpoint-path">${escapeHtml(examplePath)}</div>
              ${templatePath}
            </td>
            <td class="reference-table-about">
              <div class="endpoint-about">
                <h3 class="endpoint-name">${escapeHtml(endpoint.name || "Endpoint")}</h3>
                <p class="endpoint-summary">${escapeHtml(endpoint.summary || endpoint.description || "Live mock route")}</p>
                ${tagMarkup}
              </div>
            </td>
            <td>
              <span class="tag is-light is-rounded endpoint-category">${escapeHtml(endpointCategory(endpoint))}</span>
            </td>
            <td>
              <span class="tag is-light is-rounded endpoint-status ${publicationTone}">${escapeHtml(publicationLabel)}</span>
            </td>
            <td>
              <button type="button" class="button is-small is-info is-light is-rounded sample-trigger" data-sample-index="${index}" aria-haspopup="dialog">
                ${exampleLabel}
              </button>
            </td>
          </tr>
        `;
      }

      function closeSamplePopover() {
        if (!payloadPopover) {
          return;
        }

        payloadPopover.classList.remove("is-active");
        payloadPopover.setAttribute("aria-hidden", "true");
        document.documentElement.classList.remove("is-clipped");
        document.body.style.overflow = "";
      }

      function openSamplePopover(endpoint) {
        if (
          !payloadPopover ||
          !payloadTitle ||
          !payloadMeta ||
          !payloadRequestSection ||
          !payloadRequestMeta ||
          !payloadRequestBody ||
          !payloadResponseMeta ||
          !payloadResponseBody
        ) {
          return;
        }

        const method = endpointMethod(endpoint);
        const examplePath = endpoint?.example_path || endpoint?.path || "/api/example";
        const statusCode = String(endpoint?.success_status_code || 200);
        const requestVisible = hasRequestExample(endpoint);

        payloadTitle.textContent = endpoint?.name || "Route sample";
        payloadMeta.textContent = `${method} ${examplePath} • ${endpointCategory(endpoint)}`;
        payloadRequestSection.hidden = !requestVisible;
        payloadRequestMeta.textContent = requestVisible ? "Send this JSON body" : "";
        payloadRequestBody.textContent = requestVisible ? JSON.stringify(endpoint?.sample_request ?? null, null, 2) : "";
        payloadResponseMeta.textContent = `Returns ${statusCode} application/json`;
        payloadResponseBody.textContent = JSON.stringify(endpoint?.sample_response ?? null, null, 2);

        payloadPopover.classList.add("is-active");
        payloadPopover.setAttribute("aria-hidden", "false");
        document.documentElement.classList.add("is-clipped");
        document.body.style.overflow = "hidden";
      }

      function renderReference(payload) {
        currentReference = payload || {};

        const endpoints = Array.isArray(currentReference?.endpoints) ? currentReference.endpoints : [];
        countTargets.forEach((node) => {
          node.textContent = String(currentReference?.endpoint_count ?? endpoints.length ?? 0);
        });

        refreshLabel.textContent = timeAgo(currentReference?.refreshed_at);
        renderMethodFilters(endpoints);
        renderCategoryOptions(endpoints);

        const filteredEndpoints = endpoints.filter((endpoint) => matchesFilters(endpoint));
        const totalPages = Math.max(1, Math.ceil(filteredEndpoints.length / rowsPerPage));
        filterState.page = Math.min(Math.max(filterState.page, 1), totalPages);
        const start = (filterState.page - 1) * rowsPerPage;
        const visibleEndpoints = filteredEndpoints.slice(start, start + rowsPerPage);
        renderedEndpoints = visibleEndpoints;

        if (resultsLabel) {
          if (!filteredEndpoints.length) {
            resultsLabel.textContent = `Showing 0 of ${endpoints.length} routes`;
          } else {
            const rangeStart = start + 1;
            const rangeEnd = Math.min(start + visibleEndpoints.length, filteredEndpoints.length);
            resultsLabel.textContent = `Showing ${rangeStart}-${rangeEnd} of ${filteredEndpoints.length} routes`;
          }
        }

        if (pageStatus) {
          pageStatus.textContent = `Page ${filterState.page} of ${totalPages}`;
        }

        if (prevPageButton) {
          prevPageButton.disabled = filterState.page <= 1;
        }

        if (nextPageButton) {
          nextPageButton.disabled = filterState.page >= totalPages;
        }

        if (!endpoints.length) {
          referenceTableBody.innerHTML = '<tr><td colspan="6"><div class="empty-state">No published routes are currently available.</div></td></tr>';
          return;
        }

        if (!filteredEndpoints.length) {
          referenceTableBody.innerHTML = '<tr><td colspan="6"><div class="empty-state">No routes match the current filters. Clear a filter and try again.</div></td></tr>';
          return;
        }

        referenceTableBody.innerHTML = visibleEndpoints.map((endpoint, index) => renderEndpointRow(endpoint, index)).join("");
      }

      async function refreshStatus() {
        try {
          const [referenceResponse, healthResponse] = await Promise.allSettled([
            fetch("/api/reference.json", {
              headers: { Accept: "application/json" },
              cache: "no-store",
            }),
            fetch("/api/health", {
              headers: { Accept: "application/json" },
              cache: "no-store",
            }),
          ]);

          if (referenceResponse.status === "fulfilled" && referenceResponse.value.ok) {
            renderReference(await referenceResponse.value.json());
          }

          if (healthResponse.status === "fulfilled") {
            try {
              renderHealth(await healthResponse.value.json());
            } catch (error) {
              console.warn("Unable to parse health feed", error);
            }
          }
        } catch (error) {
          console.warn("Unable to refresh status feeds", error);
        }
      }

      if (themeToggle) {
        applyTheme(document.documentElement.dataset.theme || "dark");
        themeToggle.addEventListener("click", toggleTheme);
      }

      if (navbarBurger && navbarMenu) {
        navbarBurger.addEventListener("click", () => {
          const isActive = navbarBurger.classList.toggle("is-active");
          navbarMenu.classList.toggle("is-active", isActive);
          navbarBurger.setAttribute("aria-expanded", String(isActive));
        });

        navbarMenu.querySelectorAll("a").forEach((link) => {
          link.addEventListener("click", () => {
            navbarBurger.classList.remove("is-active");
            navbarMenu.classList.remove("is-active");
            navbarBurger.setAttribute("aria-expanded", "false");
          });
        });
      }

      if (searchInput) {
        searchInput.addEventListener("input", (event) => {
          filterState.query = String(event.target?.value || "").trim().toLowerCase();
          filterState.page = 1;
          renderReference(currentReference);
        });
      }

      if (categoryFilter) {
        categoryFilter.addEventListener("change", (event) => {
          filterState.category = String(event.target?.value || "all");
          filterState.page = 1;
          renderReference(currentReference);
        });
      }

      if (methodFilters) {
        methodFilters.addEventListener("click", (event) => {
          const button = event.target.closest("[data-method-filter]");
          if (!button) {
            return;
          }

          filterState.method = String(button.getAttribute("data-method-filter") || "all");
          filterState.page = 1;
          renderReference(currentReference);
        });
      }

      if (referenceTableBody) {
        referenceTableBody.addEventListener("click", (event) => {
          const button = event.target.closest("[data-sample-index]");
          if (!button) {
            return;
          }

          const index = Number(button.getAttribute("data-sample-index"));
          const endpoint = renderedEndpoints[index];
          if (!endpoint) {
            return;
          }

          openSamplePopover(endpoint);
        });
      }

      if (prevPageButton) {
        prevPageButton.addEventListener("click", () => {
          if (filterState.page <= 1) {
            return;
          }

          filterState.page -= 1;
          renderReference(currentReference);
        });
      }

      if (nextPageButton) {
        nextPageButton.addEventListener("click", () => {
          filterState.page += 1;
          renderReference(currentReference);
        });
      }

      if (payloadClose) {
        payloadClose.addEventListener("click", closeSamplePopover);
      }

      if (payloadBackdrop) {
        payloadBackdrop.addEventListener("click", closeSamplePopover);
      }

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          closeSamplePopover();
        }
      });

      renderHealth(initialHealth);
      renderReference(initialReference);
      window.setInterval(refreshStatus, refreshIntervalMs);
    </script>
  </body>
</html>
"""

def _sort_reference_endpoints(reference_payload: dict) -> list[dict]:
    endpoints = reference_payload.get("endpoints", []) or []
    return sorted(
        endpoints,
        key=lambda endpoint: (
            METHOD_ORDER.get(str(endpoint.get("method", "GET")).upper(), 999),
            str(endpoint.get("category") or "uncategorized"),
            str(endpoint.get("path") or ""),
            str(endpoint.get("name") or ""),
        ),
    )


def _render_method_filters(reference_payload: dict) -> str:
    methods = sorted(
        {str(endpoint.get("method", "GET")).upper() for endpoint in _sort_reference_endpoints(reference_payload)},
        key=lambda method: (METHOD_ORDER.get(method, 999), method),
    )
    buttons = ['<button type="button" class="button is-small is-rounded is-link method-filter" data-method-filter="all">All methods</button>']
    buttons.extend(
        f'<button type="button" class="button is-small is-rounded is-light method-filter" data-method-filter="{html.escape(method)}">{html.escape(method)}</button>'
        for method in methods
    )
    return "".join(buttons)


def _render_category_options(reference_payload: dict) -> str:
    categories = sorted(
        {str(endpoint.get("category") or "uncategorized") for endpoint in _sort_reference_endpoints(reference_payload)}
    )
    options = ['<option value="all">All categories</option>']
    options.extend(
        f'<option value="{html.escape(category)}">{html.escape(category)}</option>'
        for category in categories
    )
    return "".join(options)


def _render_reference_rows(reference_payload: dict, page: int = 1) -> str:
    endpoints = _sort_reference_endpoints(reference_payload)
    if not endpoints:
        return '<tr><td colspan="6"><div class="empty-state">No published routes are currently available.</div></td></tr>'

    start = max(page - 1, 0) * ROWS_PER_PAGE
    visible_endpoints = endpoints[start:start + ROWS_PER_PAGE]
    rows: list[str] = []

    for index, endpoint in enumerate(visible_endpoints):
        tags = "".join(
            f'<span class="tag is-light is-rounded endpoint-tag">{html.escape(str(tag))}</span>'
            for tag in endpoint.get("tags", []) or []
        )
        tag_markup = f'<div class="endpoint-inline-tags">{tags}</div>' if tags else ""
        method = str(endpoint.get("method", "GET")).upper()
        method_class = f"method-{method.lower()}"
        example_path = str(endpoint.get("example_path") or endpoint.get("path") or "/api/example")
        template_path = str(endpoint.get("path") or "")
        publication_status = endpoint.get("publication_status") or {}
        publication_label = str(publication_status.get("label") or "Unknown")
        publication_tone = _status_tone(publication_status.get("tone"))
        example_label = "Examples" if method in BODY_METHODS and endpoint.get("sample_request") is not None else "Example"
        path_note = ""
        if template_path and template_path != example_path:
            path_note = f'<div class="endpoint-path-note">{html.escape(template_path)}</div>'

        rows.append(
            """
            <tr>
              <td>
                <span class="tag is-light is-rounded endpoint-method {method_class}">{method}</span>
              </td>
              <td class="reference-table-path">
                <div class="endpoint-path">{example_path}</div>
                {path_note}
              </td>
              <td class="reference-table-about">
                <div class="endpoint-about">
                  <h3 class="endpoint-name">{name}</h3>
                  <p class="endpoint-summary">{summary}</p>
                  {tag_markup}
                </div>
              </td>
              <td>
                <span class="tag is-light is-rounded endpoint-category">{category}</span>
              </td>
              <td>
                <span class="tag is-light is-rounded endpoint-status {publication_tone}">{publication_label}</span>
              </td>
              <td>
                <button type="button" class="button is-small is-info is-light is-rounded sample-trigger" data-sample-index="{index}" aria-haspopup="dialog">
                  {example_label}
                </button>
              </td>
            </tr>
            """.format(
                method_class=html.escape(method_class),
                method=html.escape(method),
                example_path=html.escape(example_path),
                path_note=path_note,
                name=html.escape(str(endpoint.get("name", "Endpoint"))),
                summary=html.escape(str(endpoint.get("summary") or endpoint.get("description") or "Live mock route")),
                tag_markup=tag_markup,
                category=html.escape(str(endpoint.get("category") or "uncategorized")),
                publication_label=html.escape(publication_label),
                publication_tone=html.escape(publication_tone),
                example_label=html.escape(example_label),
                index=index,
            )
        )

    return "\n".join(rows)


def _page_count(reference_payload: dict) -> int:
    endpoint_count = len(_sort_reference_endpoints(reference_payload))
    return max(1, (endpoint_count + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)


def _page_status(reference_payload: dict, page: int = 1) -> str:
    return f"Page {max(page, 1)} of {_page_count(reference_payload)}"


def _status_tone(status_code: object) -> str:
    normalized = str(status_code or "").strip().lower()
    if normalized in {"success", "healthy"}:
        return "status-success"
    if normalized in {"warning", "degraded"}:
        return "status-warning"
    if normalized in {"error", "unhealthy"}:
        return "status-error"
    return "status-neutral"


def _health_status_label(status: object) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "healthy":
        return "Healthy"
    if normalized == "degraded":
        return "Degraded"
    if normalized == "unhealthy":
        return "Unhealthy"
    return "Unknown"


def _render_health_rows(health_payload: dict) -> str:
    dependencies = health_payload.get("dependencies", []) or []
    if not dependencies:
        return (
            '<div class="column is-12"><article class="status-card"><div class="eyebrow">Dependencies</div>'
            '<div class="status-card-value">Unavailable</div>'
            '<p class="status-card-copy">Dependency health data is currently unavailable.</p></article></div>'
        )

    rows: list[str] = []
    for dependency in dependencies:
        label = html.escape(str(dependency.get("label") or dependency.get("name") or "Dependency"))
        status_label = html.escape(_health_status_label(dependency.get("status")))
        status_tone = html.escape(_status_tone(dependency.get("status")))
        detail = html.escape(str(dependency.get("detail") or "No dependency detail available."))
        latency_ms = dependency.get("latency_ms")
        latency_markup = ""
        if latency_ms is not None:
            latency_markup = (
                '<div class="endpoint-inline-tags">'
                f'<span class="tag is-light is-rounded endpoint-status {status_tone}">{html.escape(str(latency_ms))} ms</span>'
                "</div>"
            )

        rows.append(
            """
            <div class="column is-3-desktop is-6-tablet">
              <article class="status-card">
                <div class="eyebrow">{label}</div>
                <div class="status-card-value">{status_label}</div>
                <p class="status-card-copy">{detail}</p>
                {latency_markup}
              </article>
            </div>
            """.format(
                label=label,
                status_label=status_label,
                detail=detail,
                latency_markup=latency_markup,
            )
        )

    return "\n".join(rows)


def _build_reference(session: Session) -> dict:
    endpoints = list_public_endpoints(session, limit=1000)
    payload = build_public_reference(endpoints, session=session)
    response = PublicReferenceResponse(**payload).model_dump()
    response["endpoints"] = _sort_reference_endpoints(response)
    return response


def _empty_reference_payload() -> dict:
    return PublicReferenceResponse(
        product_name="Artificer API",
        description="Public reference data is temporarily unavailable.",
        endpoint_count=0,
        refreshed_at=utc_now(),
        endpoints=[],
    ).model_dump()


def _build_reference_safely() -> dict:
    try:
        with session_scope() as session:
            return _build_reference(session)
    except Exception:
        return _empty_reference_payload()


def _json_for_script_tag(value: object) -> str:
    return (
        json.dumps(value, default=str)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _render_status_page(reference_payload: dict, health_payload: dict) -> str:
    total_pages = _page_count(reference_payload)
    health_label = _health_status_label(health_payload.get("status"))
    health_tone = _status_tone(health_payload.get("status"))
    summary = health_payload.get("summary", {}) or {}
    return (
        STATUS_TEMPLATE.replace("__INITIAL_REFERENCE_JSON__", _json_for_script_tag(reference_payload))
        .replace("__INITIAL_HEALTH_JSON__", _json_for_script_tag(health_payload))
        .replace("__INITIAL_METHOD_FILTERS__", _render_method_filters(reference_payload))
        .replace("__INITIAL_CATEGORY_OPTIONS__", _render_category_options(reference_payload))
        .replace("__INITIAL_ROWS__", _render_reference_rows(reference_payload))
        .replace("__INITIAL_HEALTH_ROWS__", _render_health_rows(health_payload))
        .replace("__INITIAL_PAGE_STATUS__", _page_status(reference_payload))
        .replace("__INITIAL_PREV_DISABLED__", "disabled aria-disabled=\"true\"")
        .replace("__INITIAL_NEXT_DISABLED__", "disabled aria-disabled=\"true\"" if total_pages <= 1 else "")
        .replace("__REFRESH_INTERVAL_MS__", str(REFRESH_INTERVAL_MS))
        .replace("__ROWS_PER_PAGE__", str(ROWS_PER_PAGE))
        .replace("__REFRESH_SECONDS__", str(REFRESH_INTERVAL_MS // 1000))
        .replace("__INITIAL_HEALTH_STATUS__", health_label)
        .replace("__INITIAL_HEALTH_TONE__", health_tone)
        .replace("__INITIAL_LIVE_ROUTE_COUNT__", str(summary.get("published_live_routes", 0)))
        .replace("__INITIAL_LEGACY_ROUTE_COUNT__", str(summary.get("legacy_mock_routes", 0)))
        .replace("__ENDPOINT_COUNT__", str(reference_payload.get("endpoint_count", 0)))
    )


@router.get("/", include_in_schema=False)
@router.head("/", include_in_schema=False)
def root_page() -> Response:
    return RedirectResponse(url="/status", status_code=307, headers={"Cache-Control": "no-store"})


@router.get("/api", include_in_schema=False)
@router.head("/api", include_in_schema=False)
def api_root_page() -> Response:
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/status", include_in_schema=False)
@router.head("/status", include_in_schema=False)
def status_page() -> HTMLResponse:
    reference_payload = _build_reference_safely()
    health_payload = build_api_health().model_dump()
    return HTMLResponse(content=_render_status_page(reference_payload, health_payload), headers={"Cache-Control": "no-store"})


@router.get("/assets/icon.svg", include_in_schema=False)
def brand_icon() -> Response:
    if not BRAND_ASSET_PATH.exists():
        raise HTTPException(status_code=404, detail="Brand asset not found")

    return Response(content=BRAND_ASSET_PATH.read_text(encoding="utf-8"), media_type="image/svg+xml")


@router.get("/reference.json", include_in_schema=False)
@router.get("/api/reference.json", include_in_schema=False)
def reference_feed(session: Session = Depends(get_session)) -> PublicReferenceResponse:
    return PublicReferenceResponse(**_build_reference(session))
