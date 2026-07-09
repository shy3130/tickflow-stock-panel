export type FXMacroDataQuery = Record<string, string | number | boolean | undefined | null>;

export class FXMacroDataClient {
  constructor(
    private readonly apiKey?: string,
    private readonly baseUrl = "https://api.fxmacrodata.com/v1",
  ) {}

  dataCatalogue(currency: string) {
    return this.get(`/data_catalogue/${normalize(currency)}`);
  }

  announcements(currency: string, indicator: string) {
    return this.get(`/announcements/${normalize(currency)}/${indicator}`);
  }

  calendar(currency: string) {
    return this.get(`/calendar/${normalize(currency)}`);
  }

  predictions(currency: string, indicator: string) {
    return this.get(`/predictions/${normalize(currency)}/${indicator}`);
  }

  forex(base: string, quote: string) {
    return this.get(`/forex/${normalize(base)}/${normalize(quote)}`);
  }

  cot(currency: string) {
    return this.get(`/cot/${normalize(currency)}`);
  }

  commoditiesLatest() {
    return this.get("/commodities/latest");
  }

  commodity(indicator: string) {
    return this.get(`/commodities/${indicator}`);
  }

  curves(currency: string) {
    return this.get(`/curves/${normalize(currency)}`);
  }

  curveProxies(currency: string) {
    return this.get(`/curve_proxies/${normalize(currency)}`);
  }

  forwardCurves(currency: string) {
    return this.get(`/forward_curves/${normalize(currency)}`);
  }

  marketSessions() {
    return this.get("/market_sessions");
  }

  riskSentiment() {
    return this.get("/risk_sentiment");
  }

  news(currency: string) {
    return this.get(`/news/${normalize(currency)}`);
  }

  pressReleases(currency: string) {
    return this.get(`/press-releases/${normalize(currency)}`);
  }

  centralBankers(currency: string) {
    return this.get(`/central_bankers/${normalize(currency)}`);
  }

  async get(path: string, query: FXMacroDataQuery = {}) {
    const url = this.url(path, query);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`FXMacroData request failed: ${response.status}`);
    }
    return response.json();
  }

  url(path: string, query: FXMacroDataQuery = {}) {
    const params = new URLSearchParams();
    if (this.apiKey) params.set("api_key", this.apiKey);
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) params.set(key, String(value));
    }
    const suffix = params.toString();
    return `${this.baseUrl.replace(/\/$/, "")}${path}${suffix ? `?${suffix}` : ""}`;
  }
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}
