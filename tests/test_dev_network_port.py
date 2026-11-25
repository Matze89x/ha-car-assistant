"""The development switch that lets the page checks draw the pages that need a mapped host port (tools/pagecheck.py)."""

from carassistant import ha


def test_the_dev_network_port_works_only_in_dev_mode(monkeypatch):
    monkeypatch.setenv("CARASSISTANT_DEV_NETWORK_PORT", "8321")
    monkeypatch.setenv("CARASSISTANT_DEV", "1")
    assert ha.network_port() == (True, 8321)
    monkeypatch.delenv("CARASSISTANT_DEV")
    ha._cache.clear()
    assert ha.network_port() == (False, None)  # in production only the Supervisor decides
