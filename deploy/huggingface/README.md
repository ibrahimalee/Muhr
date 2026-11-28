---
title: Muhr
emoji: 🔏
colorFrom: gray
colorTo: green
sdk: gradio
python_version: "3.11"
app_file: app.py
pinned: false
---

# Muhr backend

The marketplace registry and three demo sellers (summarizer, classifier, Urdu translation),
running in demo mode: invoices are synthetic and no money moves.

- Health: `/health`
- Sellers: `/api/sellers`
- Live feed: `/api/feed`

The dashboard lives on its own host and calls this API. Source and setup guide:
https://github.com/ibrahimalee/muhr
