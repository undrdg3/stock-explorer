"""Generate stocks.csv for the dashboard.

Run this OFFLINE (locally) whenever you want to refresh the data:

    python fetch_data.py

It downloads daily closing prices from Yahoo Finance, normalizes each ticker
to 1.00 on the first trading day, and writes stocks.csv. The Streamlit app then
reads that CSV — so the deployed app has NO runtime dependency on yfinance or
any network API. yfinance is only needed to run THIS script, not the app.
"""

import os
import ssl
import sys
import tempfile
from datetime import date

import certifi


def _bootstrap_ca_bundle():
    """Make TLS verification work behind a corporate SSL-inspecting proxy.

    On such networks the proxy presents its own root CA, which isn't in
    certifi's bundle but IS in the Windows trust store. We build a combined
    PEM (certifi + Windows ROOT/CA stores) and point libcurl/requests at it,
    so certificates are still verified (not disabled) — just against the
    machine's real trust anchors. No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        pems = [open(certifi.where(), "r", encoding="utf-8").read()]
        for store in ("ROOT", "CA"):
            for der, enc, _ in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    pems.append(ssl.DER_cert_to_PEM_cert(der))
        path = os.path.join(tempfile.gettempdir(), "stocks_ca_bundle.pem")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(pems))
        # Must be set before yfinance/curl_cffi makes any request.
        os.environ.setdefault("CURL_CA_BUNDLE", path)
        os.environ.setdefault("SSL_CERT_FILE", path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", path)
    except Exception as exc:  # best-effort; fall back to default verification
        print(f"CA bundle bootstrap skipped: {exc}")


_bootstrap_ca_bundle()

import pandas as pd  # noqa: E402  (imported after CA bootstrap on purpose)
import yfinance as yf  # noqa: E402

TICKERS = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NFLX"]
START = "2018-01-01"
END = date.today().isoformat()  # yfinance treats `end` as exclusive
OUTPUT = "stocks.csv"


def main():
    # auto_adjust=True → "Close" is split/dividend-adjusted, the correct basis
    # for measuring performance over time.
    raw = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False)

    # Multi-ticker download returns MultiIndex columns (Price, Ticker).
    close = raw["Close"][TICKERS].copy()

    # Align on common trading days so every column starts on the same date.
    close = close.dropna()
    if close.empty:
        raise SystemExit("No data returned — check connectivity or ticker symbols.")

    # Normalize each stock to 1.00 on the first trading day (px.data.stocks() format).
    normalized = close / close.iloc[0]

    # Shape: "date" column (YYYY-MM-DD string) + one column per ticker.
    out = normalized.reset_index().rename(columns={"Date": "date", "index": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out[["date"] + TICKERS]

    out.to_csv(OUTPUT, index=False)
    print(f"Wrote {OUTPUT}: {len(out)} rows, {out['date'].iloc[0]} to {out['date'].iloc[-1]}")
    print(out.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
