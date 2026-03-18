from __future__ import annotations

import html
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.crud import list_endpoints
from app.db import get_session
from app.schemas import PublicReferenceResponse
from app.services.public_reference import build_public_reference

router = APIRouter()

REFRESH_INTERVAL_MS = 12000
LANDING_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "landing"
LANDING_STATIC_DIR.mkdir(parents=True, exist_ok=True)
BRAND_ASSET_PATH = Path(__file__).resolve().parents[2] / "static" / "mockingbird-icon.svg"
SUPPORTED_HERO_EXTENSIONS = (".svg", ".avif", ".webp", ".png", ".jpg", ".jpeg")
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

LANDING_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mockingbird | Public API Surface</title>
    <meta
      name="description"
      content="Mockingbird is a route-first API platform with a live route catalog and realtime OpenAPI."
    />
    <link rel="icon" type="image/svg+xml" href="/static/mockingbird-icon.svg" />
    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/bulma@1.0.4/css/bulma.min.css"
    />
    <script>
      (() => {
        try {
          const storageKey = "mockingbird-public-theme";
          const storedTheme = window.localStorage.getItem(storageKey);
          const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
          document.documentElement.dataset.theme = storedTheme || (prefersDark ? "dark" : "light");
        } catch (error) {
          document.documentElement.dataset.theme = "light";
        }
      })();
    </script>
    <style>
      :root {
        color-scheme: light dark;
        --bg: #f6f0e4;
        --bg-strong: #f1e8d9;
        --surface: rgba(255, 251, 245, 0.78);
        --surface-solid: #fffaf2;
        --surface-soft: rgba(255, 255, 255, 0.56);
        --text: #17202b;
        --muted: #5d6976;
        --line: rgba(28, 40, 53, 0.12);
        --line-strong: rgba(28, 40, 53, 0.18);
        --primary: #1f5f7f;
        --primary-strong: #184d67;
        --secondary: #c76f35;
        --accent: #2f8c7d;
        --shadow: 0 32px 90px rgba(28, 40, 53, 0.14);
        --radius-xl: 34px;
        --radius-lg: 24px;
        --radius-md: 18px;
        --page-width: min(1380px, calc(100vw - 40px));
        --content-width: min(1180px, calc(100vw - 40px));
        --topbar-height: 82px;
      }

      [data-theme="dark"] {
        color-scheme: dark;
        --bg: #0d141b;
        --bg-strong: #12202c;
        --surface: rgba(12, 18, 26, 0.76);
        --surface-solid: #101821;
        --surface-soft: rgba(17, 25, 34, 0.64);
        --text: #edf3fb;
        --muted: #a3b2c2;
        --line: rgba(232, 241, 251, 0.11);
        --line-strong: rgba(232, 241, 251, 0.18);
        --primary: #4ba7d4;
        --primary-strong: #8fd2ef;
        --secondary: #f0a35e;
        --accent: #63c7b7;
        --shadow: 0 32px 90px rgba(0, 0, 0, 0.34);
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
        font-family: "Avenir Next", "Trebuchet MS", sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(192, 217, 236, 0.42), transparent 28%),
          radial-gradient(circle at top right, rgba(255, 214, 177, 0.48), transparent 24%),
          linear-gradient(180deg, #fbf8f2 0%, #f2ebdf 48%, #efe4d5 100%);
      }

      [data-theme="dark"] body {
        background:
          radial-gradient(circle at top left, rgba(55, 112, 146, 0.18), transparent 24%),
          radial-gradient(circle at top right, rgba(240, 163, 94, 0.16), transparent 22%),
          linear-gradient(180deg, #0b1118 0%, #101922 48%, #0f1720 100%);
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
        background: rgba(246, 240, 228, 0.74);
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
        width: 48px;
        height: 48px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(31, 95, 127, 0.12), rgba(199, 111, 53, 0.18));
        display: inline-flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        box-shadow: inset 0 0 0 1px rgba(28, 40, 53, 0.08);
      }

      .brand-mark img {
        width: 84%;
        height: 84%;
        object-fit: contain;
      }

      .brand-kicker,
      .eyebrow {
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--secondary);
      }

      .brand-title,
      .hero-title,
      .section-title {
        font-family: Georgia, "Times New Roman", serif;
        letter-spacing: -0.03em;
      }

      .brand-title {
        font-size: 1.55rem;
        line-height: 0.96;
      }

      .topbar-actions {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        justify-content: flex-end;
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
        padding: 0.86rem 1.18rem;
        border-radius: 999px;
        font-weight: 700;
        transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
      }

      .nav-link {
        background: rgba(255, 255, 255, 0.52);
        border: 1px solid var(--line);
        color: var(--text);
      }

      .theme-toggle {
        cursor: pointer;
        color: inherit;
      }

      .hero-link {
        background: linear-gradient(135deg, var(--primary), #2f86af);
        color: white;
        box-shadow: 0 20px 40px rgba(31, 95, 127, 0.24);
      }

      [data-theme="dark"] .topbar {
        background: rgba(9, 14, 20, 0.74);
      }

      [data-theme="dark"] .brand-mark {
        background: linear-gradient(135deg, rgba(75, 167, 212, 0.18), rgba(240, 163, 94, 0.16));
        box-shadow: inset 0 0 0 1px rgba(232, 241, 251, 0.08);
      }

      [data-theme="dark"] .nav-link {
        background: rgba(255, 255, 255, 0.04);
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
          radial-gradient(circle at 18% 20%, rgba(255, 255, 255, 0.76), transparent 18%),
          radial-gradient(circle at 78% 24%, rgba(255, 255, 255, 0.62), transparent 20%),
          linear-gradient(180deg, rgba(210, 223, 235, 0.86), rgba(255, 249, 244, 0.96) 48%, rgba(242, 231, 217, 0.98));
      }

      [data-theme="dark"] .hero-placeholder {
        background:
          radial-gradient(circle at 18% 20%, rgba(255, 255, 255, 0.18), transparent 18%),
          radial-gradient(circle at 78% 24%, rgba(255, 255, 255, 0.12), transparent 20%),
          linear-gradient(180deg, rgba(15, 29, 40, 0.92), rgba(9, 15, 22, 0.98) 48%, rgba(10, 18, 25, 0.98));
      }

      .hero-placeholder-card {
        width: min(380px, 100%);
        padding: 28px;
        border-radius: 28px;
        background: rgba(255, 252, 246, 0.76);
        border: 1px solid rgba(255, 255, 255, 0.78);
        box-shadow: 0 24px 60px rgba(28, 40, 53, 0.12);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 18px;
        text-align: center;
      }

      [data-theme="dark"] .hero-placeholder-card {
        background: rgba(10, 17, 24, 0.78);
        border-color: rgba(255, 255, 255, 0.08);
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
      }

      .hero-placeholder-card img {
        width: 84px;
        height: 84px;
      }

      .hero-placeholder-label {
        font-family: Georgia, "Times New Roman", serif;
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
        border-radius: 30px;
        background: rgba(255, 250, 242, 0.42);
        border: 1px solid rgba(255, 255, 255, 0.34);
        backdrop-filter: blur(18px);
        box-shadow: 0 24px 48px rgba(23, 32, 43, 0.12);
        display: grid;
        grid-template-columns: minmax(0, 1.42fr) minmax(560px, 0.88fr);
        gap: clamp(24px, 3vw, 52px);
        align-items: start;
      }

      [data-theme="dark"] .hero-copy-inner {
        background: rgba(8, 13, 20, 0.46);
        border-color: rgba(255, 255, 255, 0.08);
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.3);
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
        color: var(--secondary);
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
        border: 1px solid rgba(199, 111, 53, 0.25);
        background: rgba(199, 111, 53, 0.12);
        color: var(--secondary);
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
        background: rgba(255, 255, 255, 0.46);
        padding: 0.7rem 1rem;
        font-size: 0.82rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      .hero-stat-strong {
        border-color: rgba(31, 95, 127, 0.18);
        background: rgba(31, 95, 127, 0.08);
      }

      [data-theme="dark"] .hero-stat,
      [data-theme="dark"] .endpoint-tag,
      [data-theme="dark"] .reference-status {
        background: rgba(255, 255, 255, 0.06);
      }

      [data-theme="dark"] .hero-stat-strong {
        border-color: rgba(75, 167, 212, 0.22);
        background: rgba(75, 167, 212, 0.14);
      }

      .hero-actions {
        margin-top: 20px;
      }

      .hero-actions .nav-link,
      .hero-actions .hero-link {
        padding-left: 1.35rem;
        padding-right: 1.35rem;
      }

      .reference-shell {
        width: var(--content-width);
        margin: 0 auto;
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
        table-layout: fixed;
        border: 1px solid var(--line);
        background: var(--surface-solid);
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
        position: sticky;
        top: calc(var(--topbar-height) - 1px);
        z-index: 8;
        background: var(--surface-solid);
        box-shadow: inset 0 -1px 0 var(--line);
      }

      [data-theme="dark"] .reference-table th {
        background: var(--surface-solid);
      }

      .reference-table th:nth-child(1),
      .reference-table td:nth-child(1) {
        width: 112px;
      }

      .reference-table th:nth-child(2),
      .reference-table td:nth-child(2) {
        width: 24%;
      }

      .reference-table th:nth-child(3),
      .reference-table td:nth-child(3) {
        width: 34%;
      }

      .reference-table th:nth-child(4),
      .reference-table td:nth-child(4) {
        width: 14%;
      }

      .reference-table th:nth-child(5),
      .reference-table td:nth-child(5) {
        width: 100px;
      }

      .reference-table th:nth-child(6),
      .reference-table td:nth-child(6) {
        width: 144px;
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
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 0.92rem;
        line-height: 1.6;
        font-weight: 700;
        overflow-wrap: anywhere;
      }

      .endpoint-path-note {
        margin-top: 6px;
        font-size: 0.8rem;
        color: var(--muted);
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
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
        background: rgba(93, 105, 118, 0.14);
        border-color: rgba(93, 105, 118, 0.2);
        color: #42505f;
      }

      [data-theme="dark"] .endpoint-category.tag {
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.12);
        color: #d5dee7;
      }

      .endpoint-method.method-get {
        background: rgba(47, 140, 125, 0.12);
        border-color: rgba(47, 140, 125, 0.2);
        color: #1e6b60;
      }

      .endpoint-method.method-post {
        background: rgba(31, 95, 127, 0.12);
        border-color: rgba(31, 95, 127, 0.18);
        color: #1a5370;
      }

      .endpoint-method.method-put,
      .endpoint-method.method-patch {
        background: rgba(199, 111, 53, 0.12);
        border-color: rgba(199, 111, 53, 0.18);
        color: #9f5324;
      }

      .endpoint-method.method-delete {
        background: rgba(173, 63, 63, 0.12);
        border-color: rgba(173, 63, 63, 0.18);
        color: #8c3131;
      }

      .endpoint-method.method-options,
      .endpoint-method.method-head {
        background: rgba(94, 108, 128, 0.12);
        border-color: rgba(94, 108, 128, 0.18);
        color: #4d5a69;
      }

      .endpoint-status.tag {
        font-variant-numeric: tabular-nums;
      }

      .endpoint-status.status-success {
        background: rgba(47, 140, 125, 0.12);
        border-color: rgba(47, 140, 125, 0.2);
        color: #1e6b60;
      }

      .endpoint-status.status-error {
        background: rgba(173, 63, 63, 0.12);
        border-color: rgba(173, 63, 63, 0.18);
        color: #8c3131;
      }

      .endpoint-status.status-neutral {
        background: rgba(94, 108, 128, 0.12);
        border-color: rgba(94, 108, 128, 0.18);
        color: #4d5a69;
      }

      [data-theme="dark"] .endpoint-status.status-success {
        background: rgba(99, 199, 183, 0.16);
        border-color: rgba(99, 199, 183, 0.26);
        color: #94ece0;
      }

      [data-theme="dark"] .endpoint-status.status-error {
        background: rgba(255, 107, 107, 0.16);
        border-color: rgba(255, 107, 107, 0.24);
        color: #ffb1b1;
      }

      [data-theme="dark"] .endpoint-status.status-neutral {
        background: rgba(163, 178, 194, 0.16);
        border-color: rgba(163, 178, 194, 0.22);
        color: #d5dee7;
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
        background: rgba(23, 32, 43, 0.04);
        color: var(--text);
      }

      .payload-popover .modal-background {
        background: rgba(8, 12, 18, 0.68);
        backdrop-filter: blur(12px);
      }

      .payload-popover .modal-card {
        width: min(760px, calc(100vw - 32px));
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
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
        font-family: Georgia, "Times New Roman", serif;
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
        color: var(--secondary);
      }

      .sample-section-meta {
        color: var(--muted);
        font-size: 0.94rem;
      }

      [data-theme="dark"] .sample-block {
        background: rgba(255, 255, 255, 0.05);
      }

      .empty-state {
        border-radius: var(--radius-lg);
        border: 1px dashed var(--line-strong);
        background: rgba(255, 255, 255, 0.44);
        padding: 28px;
        color: var(--muted);
      }

      [data-theme="dark"] .empty-state {
        background: rgba(255, 255, 255, 0.04);
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
          min-width: 960px;
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

        .topbar .navbar-menu {
          background: rgba(246, 240, 228, 0.92);
          border-radius: 22px;
          box-shadow: 0 20px 45px rgba(28, 40, 53, 0.14);
          padding: 0.65rem;
          margin-top: 0.5rem;
        }

        [data-theme="dark"] .topbar .navbar-menu {
          background: rgba(9, 14, 20, 0.94);
        }

        .topbar .buttons {
          width: 100%;
          justify-content: stretch;
        }

        .topbar .buttons .button {
          width: 100%;
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
                <span class="brand-mark"><img src="/static/mockingbird-icon.svg" alt="Mockingbird logo" /></span>
                <span>
                  <span class="brand-title">Mockingbird</span>
                  <span class="brand-kicker">Public API surface</span>
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
                  <div class="buttons">
                    <button class="button is-light nav-link theme-toggle" id="theme-toggle" type="button" aria-pressed="false">
                      Dark mode
                    </button>
                    <a class="button is-light nav-link" href="#reference">Routes</a>
                    <a class="button is-light nav-link" href="/openapi.json">OpenAPI JSON</a>
                    <a class="button is-link hero-link" href="/docs">API docs</a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </nav>
      </header>

      <main id="top">
        <section class="hero hero-shell" data-hero-shell>
          <div class="hero-pin">
            <div class="hero-stage">
              <div class="hero-visual">
                <div class="hero-window" data-hero-window>
                  __HERO_MEDIA__
                </div>
              </div>

              <div class="hero-copy">
                <div class="hero-copy-inner">
                  <div class="hero-copy-lede">
                    <div class="eyebrow">Mock API</div>
                    <h1 class="hero-title">Mock routes with realistic <span class="hero-title-accent">data and no bedside manner.</span></h1>
                  </div>

                  <div class="hero-copy-body">
                    <p class="hero-description">
                      Browse live routes, inspect example payloads, and pull the current OpenAPI spec from one place.
                    </p>
                    <p class="hero-warning">
                      <span class="hero-warning-icon" aria-hidden="true">&#9888;</span>
                      <span>WARNING: The API may sometimes mock back.</span>
                    </p>

                    <div class="hero-stat-row">
                      <span class="hero-stat hero-stat-strong"><span data-endpoint-count>__ENDPOINT_COUNT__</span> live routes</span>
                    </div>

                    <div class="hero-actions">
                      <a class="hero-link" href="#reference">Browse routes</a>
                      <a class="nav-link" href="/openapi.json">OpenAPI JSON</a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="section reference-shell" id="reference">
          <div class="reference-header">
            <div>
              <div class="eyebrow">Quick reference</div>
              <h2 class="section-title">Routes currently live.</h2>
              <p class="section-description">
                This table reflects the active routes and refreshes every __REFRESH_SECONDS__ seconds.
              </p>
            </div>

            <div class="section-actions">
              <span class="reference-status" id="reference-refresh">Updated just now</span>
              <a class="nav-link" href="/api/reference.json">Reference JSON</a>
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
                    <th scope="col">Status</th>
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
        <span>Mockingbird public API</span>
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
    <script>
      function readInitialReference() {
        const payloadNode = document.getElementById("initial-reference-data");
        if (!payloadNode) {
          return {};
        }

        try {
          return JSON.parse(payloadNode.textContent || "{}");
        } catch (error) {
          console.warn("Unable to parse initial reference payload", error);
          return {};
        }
      }

      const themeStorageKey = "mockingbird-public-theme";
      const initialReference = readInitialReference();
      const refreshIntervalMs = __REFRESH_INTERVAL_MS__;
      const rowsPerPage = __ROWS_PER_PAGE__;
      const heroShell = document.querySelector("[data-hero-shell]");
      const heroWindow = document.querySelector("[data-hero-window]");
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
      const countTargets = Array.from(document.querySelectorAll("[data-endpoint-count]"));
      const methodPreference = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"];
      const bodyMethods = new Set(["POST", "PUT", "PATCH"]);
      const filterState = {
        query: "",
        method: "all",
        category: "all",
        page: 1,
      };
      let currentReference = initialReference;
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
          themeToggle.textContent = darkActive ? "Light mode" : "Dark mode";
          themeToggle.setAttribute("aria-pressed", String(darkActive));
          themeToggle.setAttribute("aria-label", darkActive ? "Switch to light mode" : "Switch to dark mode");
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

      function endpointStatusTone(statusCode) {
        const parsedStatus = Number(statusCode);
        if (!Number.isFinite(parsedStatus)) {
          return "status-neutral";
        }
        if (parsedStatus >= 400) {
          return "status-error";
        }
        if (parsedStatus >= 200) {
          return "status-success";
        }
        return "status-neutral";
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
        const statusCode = String(endpoint.success_status_code || 200);
        const statusTone = endpointStatusTone(statusCode);
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
              <span class="tag is-light is-rounded endpoint-status ${statusTone}">${escapeHtml(statusCode)}</span>
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
          referenceTableBody.innerHTML = '<tr><td colspan="6"><div class="empty-state">No public endpoints are enabled yet.</div></td></tr>';
          return;
        }

        if (!filteredEndpoints.length) {
          referenceTableBody.innerHTML = '<tr><td colspan="6"><div class="empty-state">No routes match the current filters. Clear a filter and try again.</div></td></tr>';
          return;
        }

        referenceTableBody.innerHTML = visibleEndpoints.map((endpoint, index) => renderEndpointRow(endpoint, index)).join("");
      }

      function syncHeroFrames() {
        if (!heroShell || !heroWindow) {
          return;
        }

        const rect = heroShell.getBoundingClientRect();
        const scrollDistance = Math.max(heroShell.offsetHeight - window.innerHeight, 1);
        const revealDistance = Math.max(scrollDistance * 0.84, 1);
        const rawProgress = Math.min(Math.max(-rect.top / revealDistance, 0), 1);
        const blendProgress = smoothstep(0.42, 0.92, rawProgress);
        renderHeroProgress(blendProgress);
      }

      function smoothstep(start, end, value) {
        if (start === end) {
          return value >= end ? 1 : 0;
        }

        const normalized = Math.min(Math.max((value - start) / (end - start), 0), 1);
        return normalized * normalized * (3 - 2 * normalized);
      }

      function renderHeroProgress(progress) {
        const topOpacity = 1 - progress;
        const bottomOpacity = progress;
        heroWindow.style.setProperty("--hero-top-opacity", String(topOpacity));
        heroWindow.style.setProperty("--hero-bottom-opacity", String(bottomOpacity));
      }

      let heroTicking = false;
      function requestHeroSync() {
        if (heroTicking) {
          return;
        }

        heroTicking = true;
        window.requestAnimationFrame(() => {
          syncHeroFrames();
          heroTicking = false;
        });
      }

      function handleWindowScroll() {
        requestHeroSync();
      }

      async function refreshReference() {
        try {
          const response = await fetch("/api/reference.json", {
            headers: { Accept: "application/json" },
            cache: "no-store",
          });

          if (!response.ok) {
            return;
          }

          renderReference(await response.json());
        } catch (error) {
          console.warn("Unable to refresh reference feed", error);
        }
      }

      if (themeToggle) {
        applyTheme(document.documentElement.dataset.theme || "light");
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

      renderReference(initialReference);
      syncHeroFrames();
      window.addEventListener("scroll", handleWindowScroll, { passive: true });
      window.addEventListener("resize", () => {
        requestHeroSync();
      });
      window.setInterval(refreshReference, refreshIntervalMs);
    </script>
  </body>
</html>
"""


def _find_landing_asset(stem: str) -> str | None:
    for extension in SUPPORTED_HERO_EXTENSIONS:
        candidate = LANDING_STATIC_DIR / f"{stem}{extension}"
        if candidate.exists():
            return f"/static/landing/{candidate.name}"
    return None


def _render_hero_panel(
    top_source: str | None,
    bottom_source: str | None,
    alt_text: str,
    label: str,
    *,
    legacy_split: bool = False,
) -> str:
    if top_source and bottom_source:
        escaped_top_source = html.escape(top_source)
        escaped_bottom_source = html.escape(bottom_source)
        escaped_alt = html.escape(alt_text)
        bottom_image_class = "hero-panel-media hero-panel-image"
        if legacy_split:
            bottom_image_class += " hero-panel-image--legacy-bottom"
        return (
            f'<figure class="hero-panel hero-panel-top">'
            f'<div class="hero-panel-frame">'
            f'<img class="hero-panel-media hero-panel-image" src="{escaped_top_source}" alt="{escaped_alt}" />'
            f"</div>"
            f"</figure>"
            f'<figure class="hero-panel hero-panel-bottom" aria-hidden="true">'
            f'<div class="hero-panel-frame">'
            f'<img class="{bottom_image_class}" src="{escaped_bottom_source}" alt="" />'
            f"</div>"
            f"</figure>"
        )

    return """
      <figure class="hero-panel hero-panel-top">
        <div class="hero-placeholder">
          <div class="hero-placeholder-card">
            <img src="/static/mockingbird-icon.svg" alt="Mockingbird logo" />
            <div class="hero-placeholder-label">Mockingbird</div>
            <div class="eyebrow">""" + html.escape(label) + """</div>
          </div>
        </div>
      </figure>
      <figure class="hero-panel hero-panel-bottom" aria-hidden="true">
        <div class="hero-placeholder">
          <div class="hero-placeholder-card">
            <img src="/static/mockingbird-icon.svg" alt="Mockingbird logo" />
            <div class="hero-placeholder-label">Mockingbird</div>
            <div class="eyebrow">""" + html.escape(label) + """</div>
          </div>
        </div>
      </figure>
    """


def _build_hero_media() -> str:
    split_top_asset = _find_landing_asset("hero-top")
    split_bottom_asset = _find_landing_asset("hero-bottom")
    legacy_tall_asset = _find_landing_asset("hero")

    if split_top_asset and split_bottom_asset:
        top_asset = split_top_asset
        bottom_asset = split_bottom_asset
        legacy_split = False
    else:
        top_asset = legacy_tall_asset
        bottom_asset = legacy_tall_asset
        legacy_split = bool(legacy_tall_asset)

    return _render_hero_panel(
        top_asset,
        bottom_asset,
        "Mockingbird hero artwork",
        "Public API surface",
        legacy_split=legacy_split,
    )


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
        return '<tr><td colspan="6"><div class="empty-state">No public endpoints are enabled yet.</div></td></tr>'

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
        status_code = str(endpoint.get("success_status_code", 200))
        status_tone = _status_tone(status_code)
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
                <span class="tag is-light is-rounded endpoint-status {status_tone}">{status_code}</span>
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
                status_code=html.escape(status_code),
                status_tone=html.escape(status_tone),
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
    try:
        parsed_status = int(status_code)
    except (TypeError, ValueError):
        return "status-neutral"

    if parsed_status >= 400:
        return "status-error"
    if parsed_status >= 200:
        return "status-success"
    return "status-neutral"


def _build_reference(session: Session) -> dict:
    endpoints = list_endpoints(session, limit=1000)
    payload = build_public_reference(endpoints)
    response = PublicReferenceResponse(**payload).model_dump()
    response["endpoints"] = _sort_reference_endpoints(response)
    return response


def _json_for_script_tag(value: object) -> str:
    return (
        json.dumps(value, default=str)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _render_landing_page(reference_payload: dict) -> str:
    total_pages = _page_count(reference_payload)
    return (
        LANDING_TEMPLATE.replace("__HERO_MEDIA__", _build_hero_media())
        .replace("__INITIAL_REFERENCE_JSON__", _json_for_script_tag(reference_payload))
        .replace("__INITIAL_METHOD_FILTERS__", _render_method_filters(reference_payload))
        .replace("__INITIAL_CATEGORY_OPTIONS__", _render_category_options(reference_payload))
        .replace("__INITIAL_ROWS__", _render_reference_rows(reference_payload))
        .replace("__INITIAL_PAGE_STATUS__", _page_status(reference_payload))
        .replace("__INITIAL_PREV_DISABLED__", "disabled aria-disabled=\"true\"")
        .replace("__INITIAL_NEXT_DISABLED__", "disabled aria-disabled=\"true\"" if total_pages <= 1 else "")
        .replace("__REFRESH_INTERVAL_MS__", str(REFRESH_INTERVAL_MS))
        .replace("__ROWS_PER_PAGE__", str(ROWS_PER_PAGE))
        .replace("__REFRESH_SECONDS__", str(REFRESH_INTERVAL_MS // 1000))
        .replace("__ENDPOINT_COUNT__", str(reference_payload.get("endpoint_count", 0)))
    )


@router.get("/", include_in_schema=False)
@router.get("/api", include_in_schema=False)
def landing_page(session: Session = Depends(get_session)) -> HTMLResponse:
    reference_payload = _build_reference(session)
    return HTMLResponse(content=_render_landing_page(reference_payload), headers={"Cache-Control": "no-store"})


@router.get("/assets/mockingbird-mark.svg", include_in_schema=False)
def mockingbird_mark() -> Response:
    if not BRAND_ASSET_PATH.exists():
        raise HTTPException(status_code=404, detail="Brand asset not found")

    return Response(content=BRAND_ASSET_PATH.read_text(encoding="utf-8"), media_type="image/svg+xml")


@router.get("/reference.json", include_in_schema=False)
@router.get("/api/reference.json", include_in_schema=False)
def reference_feed(session: Session = Depends(get_session)) -> PublicReferenceResponse:
    return PublicReferenceResponse(**_build_reference(session))
