"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";
import {
  CloudRain,
  Wind,
  Sun,
  Snowflake,
  Calendar,
  TrendingDown,
  ChevronRight,
  Check,
  X,
  Pencil,
  Users,
  ToggleLeft,
  ToggleRight,
  Gift,
  Send,
  Bell,
  Eye,
  MousePointer,
  BedDouble,
  Loader2,
} from "lucide-react";

type Extra = {
  id: string;
  name: string;
  value_to_guest: number;
  cost_to_hotel: number;
  unit: string;
  limit: string;
  stay_value?: number;
  stay_cost?: number;
};

type SegmentPackage = {
  public_rate_per_night: number;
  public_total: number;
  private_rate_per_night: number;
  private_total: number;
  discount_pct: number;
  you_save: number;
  extras?: Extra[];
  extras_value_total?: number;
  extras_cost_total?: number;
  total_giveaway?: number;
  nights?: number;
  guests?: number;
  starting_mix: string;
};

type TargetSegment = {
  segment: string;
  label: string;
  score: number;
  segment_weight: number;
  hotel_fit: number;
  channels: string[];
  starting_mix: string;
  package?: SegmentPackage;
};

type Suggestion = {
  hotel: string;
  hotel_id: string;
  guest_city?: string;
  guest_cities?: string[];
  check_in: string;
  nights: number;
  rooms_to_offer: number;
  rooms_free: number;
  score: number;
  price: {
    public_rate_per_night: number;
    public_total: number;
    private_rate_per_night: number;
    private_total: number;
    discount_pct: number;
    you_save: number;
  };
  reasons: string[];
  also_on?: string[];
  event_sources?: { name: string; place: string; source_url: string }[];
  target_segments?: TargetSegment[];
  source_scores: Record<string, number>;
};

type WaveMetrics = {
  sent: number;
  opened: number;
  clicked: number;
  booked: number;
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
  metrics: WaveMetrics;
};

type InventoryData = {
  offer_id: string;
  hotel_id: string;
  check_in: string;
  nights: number;
  rooms_allocated: number;
  rooms_booked: number;
  rooms_held: number;
  rooms_left: number;
  status: string;
  auto_waves: boolean;
  booking_rate: number;
  waves: WaveData[];
  created_at: string | null;
  expires_at: string;
  notify_waitlist: number;
};

type RowKey = string;
type RowState = {
  enabled: boolean;
  price: number;
  extras: Set<string>;
};

const GUESTS = 2;

function stayMultiplier(unit: string, nights: number): number {
  switch (unit) {
    case "per_night_per_person": return nights * GUESTS;
    case "per_stay_per_person": return GUESTS;
    case "per_night_per_room": return nights;
    default: return 1;
  }
}

function unitLabel(unit: string): string {
  switch (unit) {
    case "per_night_per_person": return "/night/person";
    case "per_stay_per_person": return "/stay/person";
    case "per_night_per_room": return "/night";
    default: return "/stay";
  }
}

function guestCities(s: Suggestion): string[] {
  if (s.guest_cities?.length) return s.guest_cities;
  if (s.guest_city) return [s.guest_city];
  return [];
}

function classifyReasons(reasons: string[]): {
  icon: React.ReactNode;
  variant: "weather" | "event" | "occupancy";
  label: string;
} {
  const text = reasons.join(" ").toLowerCase();
  if (text.includes("spa escape"))
    return { icon: <CloudRain className="w-3.5 h-3.5" />, variant: "event", label: "Spa escape" };
  if (text.includes("rain") || text.includes("grey"))
    return { icon: <CloudRain className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("snow"))
    return { icon: <Snowflake className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("sunny"))
    return { icon: <Sun className="w-3.5 h-3.5" />, variant: "event", label: reasons[0] };
  if (text.includes("smog") || text.includes("air"))
    return { icon: <Wind className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("ponte") || text.includes("holiday") || text.includes("event"))
    return { icon: <Calendar className="w-3.5 h-3.5" />, variant: "event", label: reasons[0] };
  if (text.includes("empty") || text.includes("occupancy") || text.includes("room"))
    return { icon: <TrendingDown className="w-3.5 h-3.5" />, variant: "occupancy", label: reasons[0] };
  return { icon: <CloudRain className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] ?? "Moment detected" };
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function checkOutDate(checkIn: string, nights: number) {
  const d = new Date(checkIn);
  d.setDate(d.getDate() + nights);
  return formatDate(d.toISOString());
}

function rowKey(city: string, seg: string): RowKey {
  return `${city}|${seg}`;
}

function statusColor(status: string): string {
  switch (status) {
    case "active": return "text-emerald-600";
    case "sold_out": return "text-red-600";
    case "expired": return "text-amber-600";
    default: return "text-[var(--color-text-muted)]";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "active": return "Active";
    case "sold_out": return "Sold out";
    case "expired": return "Expired";
    case "closed": return "Closed";
    default: return status;
  }
}

function InventoryPanel({
  inv,
  onSendWave,
  sendingWave,
}: {
  inv: InventoryData;
  onSendWave: () => void;
  sendingWave: boolean;
}) {
  const hasPending = inv.waves.some(w => w.status === "pending");

  return (
    <div className="space-y-3">
      {/* Allocation bar */}
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium text-[var(--color-text)]">
          {inv.rooms_allocated} allocated
        </span>
        <span className="text-[var(--color-text-muted)]">·</span>
        <span className="text-emerald-600 font-medium">{inv.rooms_booked} booked</span>
        <span className="text-[var(--color-text-muted)]">·</span>
        <span className="text-amber-600">{inv.rooms_held} held</span>
        <span className="text-[var(--color-text-muted)]">·</span>
        <span className={inv.rooms_left === 0 ? "text-red-600 font-medium" : "text-[var(--color-text)]"}>
          {inv.rooms_left} left
        </span>
        <Badge variant="default" className={`ml-auto ${statusColor(inv.status)}`}>
          {statusLabel(inv.status)}
        </Badge>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-[var(--color-bg-hover)] rounded-full overflow-hidden flex">
        <div
          className="bg-emerald-500 transition-all"
          style={{ width: `${(inv.rooms_booked / inv.rooms_allocated) * 100}%` }}
        />
        <div
          className="bg-amber-400 transition-all"
          style={{ width: `${(inv.rooms_held / inv.rooms_allocated) * 100}%` }}
        />
      </div>

      {/* Waves table */}
      <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]">
              <th className="text-left p-2 font-medium">Wave</th>
              <th className="text-left p-2 font-medium">Target</th>
              <th className="text-right p-2 font-medium">
                <span className="inline-flex items-center gap-1"><Send className="w-3 h-3" />Sent</span>
              </th>
              <th className="text-right p-2 font-medium">
                <span className="inline-flex items-center gap-1"><Eye className="w-3 h-3" />Opened</span>
              </th>
              <th className="text-right p-2 font-medium">
                <span className="inline-flex items-center gap-1"><MousePointer className="w-3 h-3" />Clicked</span>
              </th>
              <th className="text-right p-2 font-medium">
                <span className="inline-flex items-center gap-1"><BedDouble className="w-3 h-3" />Booked</span>
              </th>
              <th className="text-right p-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {inv.waves.map(w => (
              <tr key={w.wave_number} className={w.status === "pending" ? "opacity-50" : ""}>
                <td className="p-2 font-medium">{w.wave_number}</td>
                <td className="p-2">
                  {w.city} × {w.segment_label}
                  {w.extra_added && (
                    <span className="ml-1 text-emerald-600">+{w.extra_added}</span>
                  )}
                </td>
                <td className="p-2 text-right tabular-nums">{w.metrics.sent}</td>
                <td className="p-2 text-right tabular-nums">
                  {w.metrics.opened}
                  {w.metrics.sent > 0 && (
                    <span className="text-[var(--color-text-muted)] ml-1">
                      ({Math.round((w.metrics.opened / w.metrics.sent) * 100)}%)
                    </span>
                  )}
                </td>
                <td className="p-2 text-right tabular-nums">
                  {w.metrics.clicked}
                  {w.metrics.opened > 0 && (
                    <span className="text-[var(--color-text-muted)] ml-1">
                      ({Math.round((w.metrics.clicked / w.metrics.opened) * 100)}%)
                    </span>
                  )}
                </td>
                <td className="p-2 text-right tabular-nums font-medium text-emerald-600">
                  {w.metrics.booked}
                </td>
                <td className="p-2 text-right">
                  <Badge variant={w.status === "sent" ? "default" : "outline"} className="text-[10px]">
                    {w.status === "sent" ? "Sent" : "Pending"}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Send next wave button */}
      {hasPending && inv.status === "active" && (
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onSendWave}
            disabled={sendingWave}
          >
            {sendingWave ? (
              <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5 mr-1" />
            )}
            Send next wave
          </Button>
          <span className="text-xs text-[var(--color-text-muted)]">
            {inv.rooms_left} rooms left · booking rate {Math.round(inv.booking_rate * 100)}%
          </span>
        </div>
      )}

      {/* Sold out + waitlist */}
      {inv.status === "sold_out" && (
        <div className="flex items-center gap-2 text-sm">
          <Bell className="w-4 h-4 text-amber-500" />
          <span className="text-[var(--color-text-muted)]">
            Sold out · {inv.notify_waitlist} on waitlist
          </span>
        </div>
      )}

      <p className="text-[10px] text-[var(--color-text-muted)]">
        Expires {new Date(inv.expires_at).toLocaleString("en-GB", {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        })}
      </p>
    </div>
  );
}

function OfferCard({ s }: { s: Suggestion }) {
  const { locale } = useLocale();
  const labels = t(locale).offers;
  const cities = guestCities(s);
  const segments = s.target_segments ?? [];
  const publicRate = s.price.public_rate_per_night;
  const nights = s.nights;
  const maxGiveawayTotal = publicRate * (25 / 100) * nights;

  const initialRows: Record<RowKey, RowState> = {};
  for (const city of cities) {
    for (const seg of segments) {
      const pkg = seg.package;
      const extrasSet = new Set(
        (pkg?.extras ?? []).map((e: Extra) => e.id),
      );
      initialRows[rowKey(city, seg.segment)] = {
        enabled: true,
        price: pkg?.private_rate_per_night ?? s.price.private_rate_per_night,
        extras: extrasSet,
      };
    }
  }

  const [rows, setRows] = useState<Record<RowKey, RowState>>(initialRows);
  const [editingRow, setEditingRow] = useState<RowKey | null>(null);
  const [cardState, setCardState] = useState<"idle" | "done">("idle");
  const [doneAction, setDoneAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [inventory, setInventory] = useState<InventoryData | null>(null);
  const [sendingWave, setSendingWave] = useState(false);

  const toggleRow = (key: RowKey) => {
    setRows(prev => ({
      ...prev,
      [key]: { ...prev[key], enabled: !prev[key].enabled },
    }));
  };

  const updateRowPrice = (key: RowKey, price: number) => {
    setRows(prev => ({
      ...prev,
      [key]: { ...prev[key], price },
    }));
    setActionError("");
  };

  const toggleExtra = (key: RowKey, extraId: string) => {
    setRows(prev => {
      const r = prev[key];
      const next = new Set(r.extras);
      if (next.has(extraId)) next.delete(extraId);
      else next.add(extraId);
      return { ...prev, [key]: { ...r, extras: next } };
    });
  };

  function getExtrasForSegment(seg: TargetSegment): Extra[] {
    return seg.package?.extras ?? [];
  }

  function computeStayTotals(key: RowKey, seg: TargetSegment) {
    const r = rows[key];
    const extras = getExtrasForSegment(seg);
    const discountTotal = (publicRate - r.price) * nights;
    const roomTotal = r.price * nights;
    let extrasCostTotal = 0;
    let extrasValueTotal = 0;
    for (const ex of extras) {
      if (r.extras.has(ex.id)) {
        const mult = stayMultiplier(ex.unit ?? "per_stay_per_room", nights);
        extrasCostTotal += ex.cost_to_hotel * mult;
        extrasValueTotal += ex.value_to_guest * mult;
      }
    }
    const totalGiveaway = discountTotal + extrasCostTotal;
    return {
      roomTotal,
      discountTotal,
      extrasCostTotal,
      extrasValueTotal,
      totalGiveaway,
      overMax: totalGiveaway > maxGiveawayTotal,
    };
  }

  async function handleSend() {
    const activeRows = Object.entries(rows).filter(([, r]) => r.enabled);
    if (activeRows.length === 0) return;

    for (const [key, r] of activeRows) {
      const [city, segKey] = key.split("|");
      const seg = segments.find(s => s.segment === segKey);
      const extras = getExtrasForSegment(seg!).filter(e => r.extras.has(e.id));
      const totals = computeStayTotals(key, seg!);
      const body = {
        action: "approved",
        hotelId: s.hotel_id,
        guestCity: city,
        checkIn: s.check_in,
        nights: s.nights,
        roomsToOffer: s.rooms_to_offer,
        publicPriceEur: publicRate,
        privatePriceEur: r.price,
        discountPct: ((publicRate - r.price) / publicRate) * 100,
        reasons: s.reasons,
        targetSegment: segKey,
        segmentScore: seg?.score ?? null,
        packageType: seg?.starting_mix ?? null,
        inclusions: extras.map(e => e.id),
        extrasValue: totals.extrasValueTotal,
        extrasCost: totals.extrasCostTotal,
      };
      const res = await fetch("/api/offers/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json();
        setActionError(data.error);
        return;
      }
    }
    // Create inventory record with wave plan
    const enabledRows = Object.entries(rows).filter(([, r]) => r.enabled);
    const citySegments = enabledRows.map(([key]) => {
      const [city, segKey] = key.split("|");
      const seg = segments.find(s => s.segment === segKey);
      return {
        city,
        segment: segKey,
        segment_label: seg?.label ?? segKey,
        contact_limit: 500,
      };
    });

    try {
      const invRes = await fetch("/api/inventory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hotel_id: s.hotel_id,
          check_in: s.check_in,
          nights: s.nights,
          rooms_allocated: s.rooms_to_offer,
          city_segments: citySegments,
          auto_waves: false,
          booking_rate: 0.03,
        }),
      });
      if (invRes.ok) {
        const invData = await invRes.json();
        setInventory(invData);
      }
    } catch {
      // inventory creation is best-effort for demo
    }

    setDoneAction("approved");
    setCardState("done");
  }

  async function handleSkip() {
    const body = {
      action: "skipped",
      hotelId: s.hotel_id,
      guestCity: cities.join(", "),
      checkIn: s.check_in,
      nights: s.nights,
      roomsToOffer: s.rooms_to_offer,
      publicPriceEur: publicRate,
      privatePriceEur: s.price.private_rate_per_night,
      discountPct: s.price.discount_pct,
      reasons: s.reasons,
      targetSegment: null,
      segmentScore: null,
      packageType: null,
      inclusions: [],
    };
    const res = await fetch("/api/offers/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json();
      setActionError(data.error);
      return;
    }
    setDoneAction("skipped");
    setCardState("done");
  }

  async function handleSendWave() {
    if (!inventory) return;
    setSendingWave(true);
    try {
      const res = await fetch("/api/inventory/wave", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ offer_id: inventory.offer_id }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.offer) setInventory(data.offer);
      }
    } catch {
      // best-effort
    }
    setSendingWave(false);
  }

  const { icon, variant, label } = classifyReasons(s.reasons);
  const activeCount = Object.values(rows).filter(r => r.enabled).length;

  if (cardState === "done") {
    if (doneAction === "approved" && inventory) {
      return (
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center gap-3">
              <Check className="w-5 h-5 text-green-600" />
              <span className="text-sm font-medium text-[var(--color-text)]">
                {cities.join(", ")} · {formatDate(s.check_in)} – {checkOutDate(s.check_in, s.nights)}
              </span>
              <span className="text-xs text-[var(--color-text-muted)] ml-auto">
                {s.nights}n · Wave 1 sent
              </span>
            </div>
            <InventoryPanel
              inv={inventory}
              onSendWave={handleSendWave}
              sendingWave={sendingWave}
            />
          </CardContent>
        </Card>
      );
    }

    return (
      <Card className="opacity-60">
        <CardContent className="p-5 flex items-center gap-3">
          {doneAction === "approved" ? (
            <Check className="w-5 h-5 text-green-600" />
          ) : (
            <X className="w-5 h-5 text-gray-400" />
          )}
          <span className="text-sm font-medium">
            {doneAction === "approved"
              ? `Sent ${activeCount} row${activeCount !== 1 ? "s" : ""}`
              : "Skipped"}
          </span>
          <span className="text-sm text-[var(--color-text-muted)] ml-auto">
            {cities.join(", ")} · {formatDate(s.check_in)}
          </span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={variant}>
                <span className="flex items-center gap-1">{icon}{label}</span>
              </Badge>
              <span className="text-xs text-[var(--color-text-muted)]">
                Score {Math.round(s.score * 100)}%
              </span>
            </div>
            <div>
              <p className="text-sm text-[var(--color-text-muted)]">
                {formatDate(s.check_in)} – {checkOutDate(s.check_in, s.nights)}
                <span className="mx-1.5">·</span>
                {s.nights} {labels.nights}
                <span className="mx-1.5">·</span>
                {s.rooms_to_offer} {labels.rooms}
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-[var(--color-text-muted)]">
              <span className="line-through">€{publicRate * nights}</span> public ({nights}n)
            </div>
          </div>
        </div>

        {/* Reasons */}
        <div className="space-y-1">
          <p className="text-xs font-medium text-[var(--color-text-muted)]">{labels.whyNow}</p>
          <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
            {s.reasons.map((r, i) => <li key={i}>· {r}</li>)}
          </ul>
          {s.also_on && s.also_on.length > 0 && (
            <p className="text-xs text-[var(--color-text-muted)] italic mt-1">
              Also on: {s.also_on.map((a, i) => {
                const src = s.event_sources?.find(e => a.startsWith(e.name));
                const isUrl = src && (src.source_url.startsWith("http://") || src.source_url.startsWith("https://"));
                return <span key={i}>{i > 0 ? ", " : ""}{isUrl ? <a href={src.source_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-[var(--color-text)]">{a}</a> : a}</span>;
              })}
            </p>
          )}
          {s.event_sources && s.event_sources.length > 0 && (
            <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
              Sources: {[...new Set(s.event_sources.map(e => e.source_url))].map((url, i) => {
                const isUrl = url.startsWith("http://") || url.startsWith("https://");
                return <span key={i}>{i > 0 ? ", " : ""}{isUrl ? <a href={url} target="_blank" rel="noopener noreferrer" className="underline hover:text-[var(--color-text)]">{new URL(url).hostname}</a> : <span>{url}</span>}</span>;
              })}
            </p>
          )}
        </div>

        {/* City × Segment rows */}
        {segments.length > 0 && (
          <div className="border border-[var(--color-border)] rounded-lg divide-y divide-[var(--color-border)]">
            {cities.map(city =>
              segments.map(seg => {
                const key = rowKey(city, seg.segment);
                const r = rows[key];
                if (!r) return null;
                const extras = getExtrasForSegment(seg);
                const stay = computeStayTotals(key, seg);
                const isEditing = editingRow === key;
                const activeExtras = extras.filter(e => r.extras.has(e.id));

                return (
                  <div key={key} className={`p-3 ${!r.enabled ? "opacity-40" : ""}`}>
                    {/* Row header: toggle + city × segment + stay price */}
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => toggleRow(key)}
                        className="shrink-0 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
                      >
                        {r.enabled ? (
                          <ToggleRight className="w-6 h-6 text-emerald-600" />
                        ) : (
                          <ToggleLeft className="w-6 h-6" />
                        )}
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-[var(--color-text)]">{city}</span>
                          <span className="text-xs text-[var(--color-text-muted)]">×</span>
                          <Badge variant="segment" className="text-xs">
                            <Users className="w-3 h-3 mr-1" />{seg.label}
                          </Badge>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="text-lg font-semibold text-[var(--color-text)]">
                          €{stay.roomTotal}
                        </span>
                        <span className="text-xs text-[var(--color-text-muted)]"> stay</span>
                        <Badge variant="default" className="ml-2 text-xs">
                          -{Math.round(((publicRate - r.price) / publicRate) * 100)}%
                        </Badge>
                      </div>
                    </div>

                    {/* Extras summary (non-edit mode) */}
                    {!isEditing && r.enabled && activeExtras.length > 0 && (
                      <div className="ml-9 mt-1.5 flex items-start gap-1.5">
                        <Gift className="w-3.5 h-3.5 text-[var(--color-text-muted)] mt-0.5 shrink-0" />
                        <div className="text-xs text-[var(--color-text-muted)]">
                          <span>{activeExtras.map(e => e.name).join(", ")}</span>
                          <span className="ml-1.5 text-emerald-700 font-medium">
                            worth €{stay.extrasValueTotal} for {nights}n/{GUESTS} guests
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Edit button */}
                    {!isEditing && r.enabled && (
                      <div className="ml-9 mt-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => setEditingRow(key)}
                        >
                          <Pencil className="w-3 h-3 mr-1" /> Edit
                        </Button>
                      </div>
                    )}

                    {/* Edit panel */}
                    {isEditing && r.enabled && (
                      <div className="ml-9 mt-3 space-y-3 p-3 bg-[var(--color-bg-hover)] rounded-lg">
                        {/* Price */}
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium w-12">Price</span>
                          <span className="text-xs">€</span>
                          <Input
                            type="number"
                            value={r.price}
                            onChange={e => updateRowPrice(key, Number(e.target.value))}
                            className="w-20 h-7 text-xs"
                          />
                          <span className="text-xs text-[var(--color-text-muted)]">/night × {nights} = €{r.price * nights}</span>
                        </div>

                        {/* Extras checkboxes */}
                        {extras.length > 0 && (
                          <div>
                            <p className="text-xs font-medium mb-1.5">Extras ({GUESTS} guests, {nights} nights)</p>
                            <div className="space-y-1.5">
                              {extras.map(ex => {
                                const mult = stayMultiplier(ex.unit ?? "per_stay_per_room", nights);
                                return (
                                  <label
                                    key={ex.id}
                                    className="flex items-center gap-2 text-xs cursor-pointer"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={r.extras.has(ex.id)}
                                      onChange={() => toggleExtra(key, ex.id)}
                                      className="rounded border-gray-300"
                                    />
                                    <span className="text-[var(--color-text)]">{ex.name}</span>
                                    <span className="text-[var(--color-text-muted)]">
                                      €{ex.value_to_guest}{unitLabel(ex.unit)}
                                      {" "}= €{ex.value_to_guest * mult} value
                                      {ex.cost_to_hotel > 0 && `, €${ex.cost_to_hotel * mult} cost`}
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Live totals — per stay */}
                        <div className="border-t border-[var(--color-border)] pt-2 space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="text-[var(--color-text-muted)]">Guest sees ({nights}n, {GUESTS} guests)</span>
                            <span className="text-[var(--color-text)]">
                              €{stay.roomTotal} room
                              {stay.extrasValueTotal > 0 && (
                                <span className="text-emerald-700">
                                  {" "}+ €{stay.extrasValueTotal} extras = worth €{stay.roomTotal + stay.extrasValueTotal}
                                </span>
                              )}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-[var(--color-text-muted)]">Hotel gives away</span>
                            <span className={stay.overMax ? "text-red-600 font-medium" : "text-[var(--color-text)]"}>
                              €{stay.discountTotal} discount
                              {stay.extrasCostTotal > 0 && ` + €${stay.extrasCostTotal} extras`}
                              {" "}= €{stay.totalGiveaway}
                              {stay.overMax && " (over max!)"}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs text-[var(--color-text-muted)]">
                            <span>Max give-away</span>
                            <span>€{maxGiveawayTotal} for stay (25%)</span>
                          </div>
                        </div>

                        <div className="flex gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => setEditingRow(null)}
                          >
                            Done
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* No segments fallback */}
        {segments.length === 0 && (
          <div className="text-sm text-[var(--color-text)]">
            €{s.price.private_total} ({s.nights}n, -{Math.round(s.price.discount_pct)}%)
          </div>
        )}

        {/* Actions */}
        {actionError && (
          <p className="text-xs text-red-600">{actionError}</p>
        )}
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-[var(--color-text-muted)]">
            {activeCount} of {cities.length * segments.length} rows selected
          </span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleSkip}>
              {labels.skip}
            </Button>
            <Button
              size="sm"
              onClick={handleSend}
              disabled={activeCount === 0}
            >
              Send {activeCount} row{activeCount !== 1 ? "s" : ""}
              <ChevronRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function OffersList({
  suggestions,
  engineError,
}: {
  suggestions: Array<Record<string, unknown>>;
  engineError: string;
}) {
  const { locale } = useLocale();
  const labels = t(locale).offers;

  if (engineError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
          {labels.title}
        </h1>
        <Card>
          <CardContent className="py-12 text-center text-red-600">
            Engine error: {engineError}
          </CardContent>
        </Card>
      </div>
    );
  }

  const typed = suggestions as unknown as Suggestion[];

  if (typed.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
          {labels.title}
        </h1>
        <Card>
          <CardContent className="py-12 text-center text-[var(--color-text-muted)]">
            {labels.empty}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
          {labels.title}
        </h1>
        <span className="text-sm text-[var(--color-text-muted)]">
          {typed.length} {typed.length === 1 ? "offer" : "offers"}
        </span>
      </div>

      <div className="space-y-3">
        {typed.map((s, i) => (
          <OfferCard key={`${(s.guest_cities ?? [s.guest_city]).join("-")}-${s.check_in}-${i}`} s={s} />
        ))}
      </div>
    </div>
  );
}
