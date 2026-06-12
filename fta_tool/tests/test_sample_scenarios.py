from app.services import sample_scenarios as ss


def test_get_sample_scenarios_loads_default_file():
    ss.get_sample_scenarios(force_reload=True)
    scenarios = ss.get_sample_scenarios()
    assert len(scenarios) >= 6
    for s in scenarios:
        for key in ("id", "category", "title", "top_event",
                     "system_context", "incident_context", "demo_points"):
            assert s.get(key), f"{s.get('id')} missing {key}"


def test_get_sample_scenario_by_id():
    ss.get_sample_scenarios(force_reload=True)
    s = ss.get_sample_scenario("internet_web_access_failure")
    assert s is not None
    assert "Web" in s["title"] or "Web" in s["top_event"]


def test_get_sample_scenario_unknown_returns_none():
    assert ss.get_sample_scenario("does_not_exist") is None


def test_missing_file_returns_empty_list(monkeypatch, tmp_path):
    monkeypatch.setenv("FTA_SAMPLE_SCENARIOS_FILE", str(tmp_path / "nonexistent.yaml"))
    assert ss.get_sample_scenarios(force_reload=True) == []
    monkeypatch.delenv("FTA_SAMPLE_SCENARIOS_FILE", raising=False)
    ss.get_sample_scenarios(force_reload=True)


def test_invalid_entry_skipped(monkeypatch, tmp_path):
    p = tmp_path / "sample_scenarios.yaml"
    p.write_text(
        "scenarios:\n"
        "  - id: ok\n"
        "    category: cat\n"
        "    title: title\n"
        "    top_event: event\n"
        "    system_context: sys\n"
        "    incident_context: inc\n"
        "    demo_points: demo\n"
        "  - id: missing_fields\n"
        "    category: cat\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FTA_SAMPLE_SCENARIOS_FILE", str(p))
    scenarios = ss.get_sample_scenarios(force_reload=True)
    assert len(scenarios) == 1
    assert scenarios[0]["id"] == "ok"
    monkeypatch.delenv("FTA_SAMPLE_SCENARIOS_FILE", raising=False)
    ss.get_sample_scenarios(force_reload=True)
