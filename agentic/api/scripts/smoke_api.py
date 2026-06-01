#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Smoke checks for the running API service.

Usage:
    python scripts/smoke_api.py
    python scripts/smoke_api.py http://localhost:8088/api
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx


def assert_ok(response: httpx.Response) -> dict:
    response.raise_for_status()
    data = response.json()
    assert data.get("code") in (0, 200), data
    return data.get("data") or {}


def main() -> int:
    base_url = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8088/api").rstrip("/")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        status = client.get("/status")
        status.raise_for_status()
        assert status.json().get("status") == "ok", status.text

        sessions = assert_ok(client.get("/sessions"))
        assert isinstance(sessions.get("sessions"), list), sessions

        created = assert_ok(client.post("/sessions"))
        session_id = created["session_id"]

        detail = assert_ok(client.get(f"/sessions/{session_id}"))
        assert detail["session_id"] == session_id, detail

        stopped = assert_ok(client.post(f"/sessions/{session_id}/stop"))
        assert isinstance(stopped, dict), stopped

        mcp_servers = assert_ok(client.get("/app-config/mcp-servers"))
        assert isinstance(mcp_servers.get("mcp_servers"), list), mcp_servers

        a2a_servers = assert_ok(client.get("/app-config/a2a-servers"))
        assert isinstance(a2a_servers.get("a2a_servers"), list), a2a_servers

        llm_config = assert_ok(client.get("/app-config/llm"))
        assert "api_key" not in llm_config, llm_config

        sample = b"smoke file check\n"
        files = {"file": ("smoke.txt", sample, "text/plain")}
        upload = assert_ok(client.post("/files", files=files))
        file_id = upload["id"]
        assert upload["filename"] == "smoke.txt", upload
        assert upload["content_type"] == "text/plain", upload

        info = assert_ok(client.get(f"/files/{file_id}"))
        assert info["id"] == file_id, info

        download = client.get(f"/files/{file_id}/download")
        download.raise_for_status()
        assert download.content == sample, download.content

    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
