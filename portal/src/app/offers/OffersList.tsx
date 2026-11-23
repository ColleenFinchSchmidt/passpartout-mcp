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
} from "lucide-react";

type Suggestion = {
  hotel: string;
  hotel_id: string;
  guest_city: string;
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
  source_scores: Record<string, number>;
};

function classifyReasons(reasons: string[]): {
  icon: React.ReactNode;
  variant: "weather" | "event" | "occupancy";
  label: string;
} {
  const text = reasons.join(" ").toLowerCase();
  if (text.includes("rain") || text.includes("grey"))
    return { icon: <CloudRain className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("snow"))
    return { icon: <Snowflake className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("sunny"))
    return { icon: <Sun className="w-3.5 h-3.5" />, variant: "event", label: reasons[0] };
  if (text.includes("smog") || text.includes("air"))
    return { icon: <Wind className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] };
  if (text.includes("holiday") || text.includes("event") || text.includes("festival"))
    return { icon: <Calendar className="w-3.5 h-3.5" />, variant: "event", label: reasons[0] };
  if (text.includes("empty") || text.includes("occupancy") || text.includes("room"))
    return { icon: <TrendingDown className="w-3.5 h-3.5" />, variant: "occupancy", label: reasons[0] };
  return { icon: <CloudRain className="w-3.5 h-3.5" />, variant: "weather", label: reasons[0] ?? "Moment detected" };
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

function checkOutDate(checkIn: string, nights: number) {
  const d = new Date(checkIn);
  d.setDate(d.getDate() + nights);
  return formatDate(d.toISOString());
}

type ActionState = "idle" | "editing" | "done";

function OfferCard({ s }: { s: Suggestion }) {
  const { locale } = useLocale();
  const labels = t(locale).offers;
  const [state, setState] = useState<ActionState>("idle");
  const [result, setResult] = useState<string | null>(null);
  const [editPrice, setEditPrice] = useState(s.price.private_rate_per_night);
  const [editError, setEditError] = useState("");

  const { icon, variant, label } = classifyReasons(s.reasons);

  async function handleAction(action: string, editedFields?: Record<string, number>) {
    const body = {
      action,
      hotelId: s.hotel_id,
      guestCity: s.guest_city,
      checkIn: s.check_in,
      nights: s.nights,
      roomsToOffer: s.rooms_to_offer,
      publicPriceEur: s.price.public_rate_per_night,
      privatePriceEur: s.price.private_rate_per_night,
      discountPct: s.price.discount_pct,
      reasons: s.reasons,
      editedFields,
    };
    const res = await fetch("/api/offers/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      setEditError(data.error);
      return false;
    }
    setResult(action);
    setState("done");
    return true;
  }

  if (state === "done") {
    const icons: Record<string, React.ReactNode> = {
      approved: <Check className="w-5 h-5 text-green-600" />,
      skipped: <X className="w-5 h-5 text-gray-400" />,
      edited: <Pencil className="w-5 h-5 text-blue-600" />,
    };
    const msgs: Record<string, string> = {
      approved: "Approved",
      skipped: "Skipped",
      edited: `Edited to €${editPrice}/night`,
    };
    return (
      <Card className="opacity-60">
        <CardContent className="p-5 flex items-center gap-3">
          {icons[result!]}
          <span className="text-sm font-medium">{msgs[result!]}</span>
          <span className="text-sm text-[var(--color-text-muted)] ml-auto">
            {s.guest_city} · {formatDate(s.check_in)}
          </span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0 space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={variant}>
                <span className="flex items-center gap-1">
                  {icon}
                  {label}
                </span>
              </Badge>
              <span className="text-xs text-[var(--color-text-muted)]">
                Score {Math.round(s.score * 100)}%
              </span>
            </div>

            <div>
              <h3 className="font-medium text-[var(--color-text)]">
                {s.guest_city} getaway
              </h3>
              <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
                {formatDate(s.check_in)} – {checkOutDate(s.check_in, s.nights)}
                <span className="mx-1.5">·</span>
                {s.nights} {labels.nights}
                <span className="mx-1.5">·</span>
                {s.rooms_to_offer} {labels.rooms}
              </p>
            </div>

            <div className="space-y-1">
              <p className="text-xs font-medium text-[var(--color-text-muted)]">
                {labels.whyNow}
              </p>
              <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
                {s.reasons.map((r, i) => (
                  <li key={i}>· {r}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="text-right shrink-0 space-y-3">
            <div>
              <div className="text-sm text-[var(--color-text-muted)]">
                <span className="line-through">
                  €{s.price.public_rate_per_night}
                </span>
                <span className="ml-1">{labels.publicPrice}</span>
              </div>
              <div className="flex items-baseline justify-end gap-1.5 mt-0.5">
                <span className="text-xl font-semibold text-[var(--color-text)]">
                  €{s.price.private_rate_per_night}
                </span>
                <span className="text-sm text-[var(--color-text-muted)]">
                  {labels.perNight}
                </span>
              </div>
              <Badge variant="default" className="mt-1">
                -{Math.round(s.price.discount_pct)}%
              </Badge>
            </div>

            {state === "editing" ? (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs">€</span>
                  <Input
                    type="number"
                    value={editPrice}
                    onChange={(e) => {
                      setEditPrice(Number(e.target.value));
                      setEditError("");
                    }}
                    className="w-20 h-8 text-sm"
                  />
                  <span className="text-xs text-[var(--color-text-muted)]">
                    /night
                  </span>
                </div>
                {editError && (
                  <p className="text-xs text-red-600">{editError}</p>
                )}
                <div className="flex gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setState("idle");
                      setEditError("");
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      handleAction("edited", {
                        privatePriceEur: editPrice,
                        discountPct:
                          ((s.price.public_rate_per_night - editPrice) /
                            s.price.public_rate_per_night) *
                          100,
                      })
                    }
                  >
                    Save
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleAction("skipped")}
                >
                  {labels.skip}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setState("editing")}
                >
                  {labels.edit}
                </Button>
                <Button size="sm" onClick={() => handleAction("approved")}>
                  {labels.approve}
                  <ChevronRight className="w-3.5 h-3.5 ml-1" />
                </Button>
              </div>
            )}
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
          <OfferCard key={`${s.guest_city}-${s.check_in}-${i}`} s={s} />
        ))}
      </div>
    </div>
  );
}
