"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";
import {
  Send,
  BedDouble,
  DollarSign,
  TrendingUp,
  BarChart3,
  Lightbulb,
  Loader2,
  Eye,
  MousePointer,
  Users,
  MapPin,
  Gift,
} from "lucide-react";

/* ---------- types ---------- */

type Tiles = {
  offers_sent: number;
  offers_skipped: number;
  sim_bookings: number;
  sim_revenue: number;
  commission: number;
  holdback_bookings: number;
  holdback_revenue: number;
  uplift_pct: number | null;
};

type WaveData = {
  wave_number: number;
  city: string;
  segment: string;
  segment_label: string;
  recipients: number;
  status: string;
  sent_at: string | null;
  extra_added: string | null;
  metrics: { sent: number; opened: number; clicked: number; booked: number };
};

type InventoryOffer = {
  offer_id: string;
  hotel_id: string;
  check_in: string;
  nights: number;
  rooms_allocated: number;
  rooms_booked: number;
  rooms_held: number;
  rooms_left: number;
  status: string;
  waves: WaveData[];
};

type BacktestMonth = { [month: string]: number };
type BacktestType = { [type: string]: number };
type BacktestRow = {
  date: string;
  stay_type: string;
  city: string;
  flagged: boolean;
  score: number;
  moment_types: string[];
};
type BacktestData = {
  per_month: BacktestMonth;
  per_type: BacktestType;
  flagged_total: number;
  flagged: BacktestRow[];
};

type ResultsData = {
  tiles: Tiles;
  inventory: InventoryOffer[];
  by_segment: Record<string, { sent: number; booked: number }>;
  by_city: Record<string, { sent: number; booked: number }>;
  by_package: Record<string, { count: number }>;
  total_actions: number;
};

/* ---------- helpers ---------- */

function formatLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatDate(iso: string) {
  return parseDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/* ---------- StatTile ---------- */

function StatTile({
  icon,
  label,
  value,
  sub,
  color = "text-[var(--color-text)]",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4 flex items-start gap-3">
        <div className="p-2 rounded-lg bg-[var(--color-bg)]">{icon}</div>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
          <p className={`text-lg font-semibold tabular-nums ${color}`}>{value}</p>
          {sub && <p className="text-[10px] text-[var(--color-text-muted)]">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- BacktestChart ---------- */

function BacktestChart({ data, locale }: { data: BacktestData; locale: "en" | "it" }) {
  const labels = t(locale).results;
  const months = Object.entries(data.per_month).sort(([a], [b]) => a.localeCompare(b));
  if (months.length === 0) return null;

  const maxCount = Math.max(...months.map(([, c]) => c), 1);

  const monthLabel = (ym: string) => {
    const [, m] = ym.split("-");
    const names = locale === "it"
      ? ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]
      : ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return names[parseInt(m) - 1] || m;
  };

  const typeColors: Record<string, string> = {
    rain_escape: "bg-blue-400",
    snow: "bg-sky-300",
    sunny_rebound: "bg-amber-400",
    ponte: "bg-purple-400",
    school_holiday: "bg-orange-400",
    public_holiday: "bg-red-400",
    seasonal: "bg-emerald-400",
    low_occupancy: "bg-gray-400",
    hotel_rain_penalty: "bg-rose-300",
    poor_air_quality: "bg-violet-400",
  };

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold font-[family-name:var(--font-space-grotesk)]">
            {labels.backtest}
          </h2>
          <span className="text-xs text-[var(--color-text-muted)]">
            {data.flagged_total} {labels.flagged}
          </span>
        </div>

        <div className="flex items-end gap-1" style={{ height: 160 }}>
          {months.map(([ym, count]) => (
            <div key={ym} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-[9px] tabular-nums text-[var(--color-text-muted)]">{count}</span>
              <div
                className="w-full bg-[var(--color-accent)] rounded-t transition-all"
                style={{ height: `${(count / maxCount) * 120}px`, minHeight: count > 0 ? 4 : 0 }}
              />
              <span className="text-[9px] text-[var(--color-text-muted)]">{monthLabel(ym)}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 pt-2 border-t border-[var(--color-border)]">
          {Object.entries(data.per_type).map(([type, count]) => (
            <div key={type} className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
              <span className={`w-2 h-2 rounded ${typeColors[type] || "bg-gray-300"}`} />
              {formatLabel(type)} ({count})
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- Learnings ---------- */

function Learnings({ data, locale }: { data: ResultsData; locale: "en" | "it" }) {
  const labels = t(locale).results;
  const totalBookings = Object.values(data.by_segment).reduce((s, v) => s + v.booked, 0);
  const hasEnoughData = totalBookings >= 20;

  const insights: string[] = [];
  if (hasEnoughData) {
    const segsWithRate = Object.entries(data.by_segment)
      .filter(([, v]) => v.sent > 0 && v.booked >= 5)
      .map(([seg, v]) => [seg, v.booked / v.sent, v] as const)
      .sort((a, b) => b[1] - a[1]);
    const topSeg = segsWithRate[0];
    if (topSeg) {
      const rate = Math.round(topSeg[1] * 100);
      insights.push(
        locale === "it"
          ? `${formatLabel(topSeg[0])} ha il miglior tasso di prenotazione (${rate}%)`
          : `${formatLabel(topSeg[0])} has the best booking rate (${rate}%)`,
      );
    }
    const citiesWithRate = Object.entries(data.by_city)
      .filter(([, v]) => v.sent > 0 && v.booked >= 5)
      .map(([city, v]) => [city, v.booked / v.sent, v] as const)
      .sort((a, b) => b[1] - a[1]);
    const topCity = citiesWithRate[0];
    if (topCity) {
      const rate = Math.round(topCity[1] * 100);
      insights.push(
        locale === "it"
          ? `${topCity[0]} ha il miglior tasso di conversione (${rate}%)`
          : `${topCity[0]} has the best conversion rate (${rate}%)`,
      );
    }
    const topPkg = Object.entries(data.by_package).sort((a, b) => b[1].count - a[1].count)[0];
    if (topPkg) {
      insights.push(
        locale === "it"
          ? `"${topPkg[0]}" è l'extra più incluso`
          : `"${topPkg[0]}" is the most included extra`,
      );
    }
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          <h2 className="text-sm font-semibold font-[family-name:var(--font-space-grotesk)]">
            {labels.learnings}
          </h2>
        </div>

        {!hasEnoughData ? (
          <p className="text-xs text-[var(--color-text-muted)]">
            {locale === "it"
              ? `Dati insufficienti (${totalBookings} prenotazioni — servono almeno 20)`
              : `Not enough data yet (${totalBookings} bookings — need at least 20)`}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {insights.map((ins, i) => (
              <li key={i} className="text-xs text-[var(--color-text)] flex items-start gap-1.5">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0">•</span>
                {ins}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------- ResultsPage ---------- */

export default function ResultsPage() {
  const { locale } = useLocale();
  const labels = t(locale).results;

  const [data, setData] = useState<ResultsData | null>(null);
  const [backtest, setBacktest] = useState<BacktestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [btLoading, setBtLoading] = useState(true);

  useEffect(() => {
    fetch("/api/results")
      .then((r) => r.json())
      .then((d) => { if (!d.error) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));

    fetch("/api/backtest")
      .then((r) => r.json())
      .then((d) => { if (!d.error) setBacktest(d); })
      .catch(() => {})
      .finally(() => setBtLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">{labels.title}</h1>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">{labels.title}</h1>
        <Card><CardContent className="p-5"><p className="text-xs text-[var(--color-text-muted)]">{labels.noData}</p></CardContent></Card>
      </div>
    );
  }

  const tiles = data.tiles;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">{labels.title}</h1>
        <Badge variant="amber" className="text-[10px]">{labels.demoLabel}</Badge>
      </div>

      {/* Top tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          icon={<Send className="w-4 h-4 text-[var(--color-accent)]" />}
          label={labels.offersSent}
          value={String(tiles.offers_sent)}
          sub={`${tiles.offers_skipped} ${labels.skipped.toLowerCase()}`}
        />
        <StatTile
          icon={<BedDouble className="w-4 h-4 text-emerald-600" />}
          label={labels.bookings}
          value={String(tiles.sim_bookings)}
          color="text-emerald-600"
        />
        <StatTile
          icon={<DollarSign className="w-4 h-4 text-[var(--color-text)]" />}
          label={labels.revenue}
          value={`€${tiles.sim_revenue.toLocaleString()}`}
          sub={`${labels.commission}: €${tiles.commission.toLocaleString()}`}
        />
        <StatTile
          icon={<TrendingUp className="w-4 h-4 text-blue-600" />}
          label={labels.uplift}
          value={tiles.uplift_pct !== null ? `+${tiles.uplift_pct}%` : "—"}
          sub={tiles.uplift_pct !== null
            ? `${labels.holdback}: ${tiles.holdback_bookings} ${locale === "it" ? "pren." : "book."}`
            : (locale === "it" ? "Dati insufficienti" : "Not enough data")}
          color={tiles.uplift_pct !== null && tiles.uplift_pct > 0 ? "text-emerald-600" : "text-[var(--color-text)]"}
        />
      </div>

      {/* Per offer & wave */}
      {data.inventory.length > 0 && (
        <Card>
          <CardContent className="p-5 space-y-4">
            <h2 className="text-sm font-semibold font-[family-name:var(--font-space-grotesk)]">
              {labels.perOffer}
            </h2>
            <p className="text-[10px] text-[var(--color-text-muted)]">
              {locale === "it"
                ? "Ogni offerta ha onde successive inviate a segmenti diversi"
                : "Each offer sends waves to different city × segment groups"}
            </p>

            {data.inventory.map((inv) => (
              <div key={inv.offer_id} className="border border-[var(--color-border)] rounded-lg p-3 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">
                    {formatDate(inv.check_in)} · {inv.nights}n
                  </span>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-emerald-600 font-medium">{inv.rooms_booked} {labels.booked.toLowerCase()}</span>
                    <span className="text-[var(--color-text-muted)]">{inv.rooms_left} {labels.roomsLeft.toLowerCase()}</span>
                    <Badge variant={inv.status === "active" ? "default" : "outline"} className="text-[10px]">
                      {formatLabel(inv.status)}
                    </Badge>
                  </div>
                </div>

                <div className="h-1.5 bg-[var(--color-bg)] rounded-full overflow-hidden flex">
                  <div className="bg-emerald-500" style={{ width: `${(inv.rooms_booked / Math.max(inv.rooms_allocated, 1)) * 100}%` }} />
                  <div className="bg-amber-400" style={{ width: `${(inv.rooms_held / Math.max(inv.rooms_allocated, 1)) * 100}%` }} />
                </div>

                {inv.waves.length > 0 && (
                  <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-[var(--color-bg)] text-[var(--color-text-muted)]">
                          <th className="text-left p-2 font-medium">Wave</th>
                          <th className="text-left p-2 font-medium">Target</th>
                          <th className="text-right p-2 font-medium"><span className="inline-flex items-center gap-1"><Send className="w-3 h-3" />{labels.sent}</span></th>
                          <th className="text-right p-2 font-medium"><span className="inline-flex items-center gap-1"><Eye className="w-3 h-3" />{labels.opened}</span></th>
                          <th className="text-right p-2 font-medium"><span className="inline-flex items-center gap-1"><MousePointer className="w-3 h-3" />{labels.clicked}</span></th>
                          <th className="text-right p-2 font-medium"><span className="inline-flex items-center gap-1"><BedDouble className="w-3 h-3" />{labels.booked}</span></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--color-border)]">
                        {inv.waves.map((w) => (
                          <tr key={w.wave_number}>
                            <td className="p-2 font-medium">{w.wave_number}</td>
                            <td className="p-2">{w.city} × {w.segment_label}</td>
                            <td className="p-2 text-right tabular-nums">{w.metrics.sent}</td>
                            <td className="p-2 text-right tabular-nums">
                              {w.metrics.opened}
                              {w.metrics.sent > 0 && (
                                <span className="text-[var(--color-text-muted)] ml-1">({Math.round((w.metrics.opened / w.metrics.sent) * 100)}%)</span>
                              )}
                            </td>
                            <td className="p-2 text-right tabular-nums">
                              {w.metrics.clicked}
                              {w.metrics.opened > 0 && (
                                <span className="text-[var(--color-text-muted)] ml-1">({Math.round((w.metrics.clicked / w.metrics.opened) * 100)}%)</span>
                              )}
                            </td>
                            <td className="p-2 text-right tabular-nums font-medium text-emerald-600">{w.metrics.booked}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* By segment */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-[var(--color-text-muted)]" />
              <h3 className="text-sm font-semibold">{labels.bySegment}</h3>
            </div>
            {Object.keys(data.by_segment).length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">{labels.noData}</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(data.by_segment)
                  .sort((a, b) => b[1].booked - a[1].booked)
                  .map(([seg, info]) => (
                    <div key={seg} className="flex items-center justify-between text-xs">
                      <Badge variant="segment" className="text-[10px]">{formatLabel(seg)}</Badge>
                      <span className="tabular-nums">
                        <span className="font-medium text-emerald-600">{info.booked}</span>
                        <span className="text-[var(--color-text-muted)]"> / {info.sent} {labels.sent.toLowerCase()}</span>
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* By city */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-[var(--color-text-muted)]" />
              <h3 className="text-sm font-semibold">{labels.byCity}</h3>
            </div>
            {Object.keys(data.by_city).length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">{labels.noData}</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(data.by_city)
                  .sort((a, b) => b[1].booked - a[1].booked)
                  .map(([city, info]) => (
                    <div key={city} className="flex items-center justify-between text-xs">
                      <span className="font-medium text-[var(--color-text)]">{city}</span>
                      <span className="tabular-nums">
                        <span className="font-medium text-emerald-600">{info.booked}</span>
                        <span className="text-[var(--color-text-muted)]"> / {info.sent} {labels.sent.toLowerCase()}</span>
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* By package / extras */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Gift className="w-4 h-4 text-[var(--color-text-muted)]" />
              <h3 className="text-sm font-semibold">{labels.byPackage}</h3>
            </div>
            {Object.keys(data.by_package).length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">{labels.noData}</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(data.by_package)
                  .sort((a, b) => b[1].count - a[1].count)
                  .map(([pkg, info]) => (
                    <div key={pkg} className="flex items-center justify-between text-xs">
                      <span className="text-[var(--color-text)]">{formatLabel(pkg)}</span>
                      <span className="tabular-nums">{info.count}×</span>
                    </div>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Backtest */}
      {btLoading ? (
        <Card>
          <CardContent className="p-5 flex items-center justify-center py-8">
            <Loader2 className="w-4 h-4 animate-spin text-[var(--color-text-muted)]" />
            <span className="ml-2 text-xs text-[var(--color-text-muted)]">Loading back-test…</span>
          </CardContent>
        </Card>
      ) : backtest ? (
        <BacktestChart data={backtest} locale={locale} />
      ) : null}

      {/* Learnings */}
      <Learnings data={data} locale={locale} />

      <p className="text-[10px] text-[var(--color-text-muted)] text-center">
        {labels.demoLabel} — {locale === "it" ? "prenotazioni, aperture e clic sono simulati" : "bookings, opens and clicks are simulated"}
      </p>
    </div>
  );
}
