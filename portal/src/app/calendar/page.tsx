"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";
import {
  ChevronLeft,
  ChevronRight,
  Calendar,
  Star,
  Send,
  GraduationCap,
  Loader2,
  Check,
} from "lucide-react";

/* ---------- types ---------- */

type DayEvent = { name: string; place: string };
type DayOffer = { offer_id: string; rooms_allocated: number; rooms_booked: number; status: string };
type CalDay = {
  date: string;
  weekday: string;
  free_rooms: number;
  total_rooms: number;
  blocked: boolean;
  events: DayEvent[];
  offers: DayOffer[];
  markers: string[];
};

type Rules = {
  public_rate_eur: number;
  lowest_price_eur: number;
  max_discount_pct: number;
  max_rooms_per_offer: number;
  blackout_dates: string[];
  booking_window_days: number[];
  offer_lifetime_hours: number;
  contact_cooldown_days: number;
  min_score_to_fire: number;
  auto_send: boolean;
  auto_waves: boolean;
};

/* ---------- helpers ---------- */

const MONTH_NAMES_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const MONTH_NAMES_IT = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
const DOW_EN = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const DOW_IT = ["Lun","Mar","Mer","Gio","Ven","Sab","Dom"];

function occupancyColor(free: number, total: number, blocked: boolean): { bg: string; text: string; label: string } {
  if (blocked) return { bg: "bg-gray-100", text: "text-gray-400", label: "Blocked" };
  const ratio = free / Math.max(total, 1);
  if (ratio <= 0.1) return { bg: "bg-red-50", text: "text-red-700", label: "High" };
  if (ratio <= 0.3) return { bg: "bg-amber-50", text: "text-amber-700", label: "Medium" };
  if (ratio <= 0.6) return { bg: "bg-emerald-50", text: "text-emerald-700", label: "Low" };
  return { bg: "bg-blue-50", text: "text-blue-700", label: "Very low" };
}

/* ---------- CalendarGrid ---------- */

function CalendarGrid({
  days,
  year,
  month,
  locale,
}: {
  days: CalDay[];
  year: number;
  month: number;
  locale: "en" | "it";
}) {
  const labels = t(locale).calendar;
  const dowLabels = locale === "it" ? DOW_IT : DOW_EN;

  const firstDate = new Date(year, month - 1, 1);
  let startDow = firstDate.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const dayMap = new Map(days.map((d) => [d.date, d]));
  const daysInMonth = new Date(year, month, 0).getDate();

  const cells: (CalDay | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push(dayMap.get(iso) ?? null);
  }

  return (
    <div>
      <div className="grid grid-cols-7 gap-px mb-1">
        {dowLabels.map((d) => (
          <div key={d} className="text-center text-[10px] font-medium text-[var(--color-text-muted)] py-1">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px bg-[var(--color-border)] rounded-lg overflow-hidden">
        {cells.map((day, i) => {
          if (!day) {
            return <div key={`empty-${i}`} className="bg-[var(--color-bg)] min-h-[80px]" />;
          }
          const occ = occupancyColor(day.free_rooms, day.total_rooms, day.blocked);
          const dayNum = parseInt(day.date.split("-")[2]);

          return (
            <div
              key={day.date}
              className={`${occ.bg} min-h-[80px] p-1.5 relative transition-colors hover:ring-2 hover:ring-[var(--color-accent)] hover:z-10`}
            >
              <div className="flex items-start justify-between">
                <span className={`text-xs font-medium ${occ.text}`}>{dayNum}</span>
                {day.blocked && (
                  <span className="text-[9px] text-gray-400 font-medium">{labels.blocked}</span>
                )}
              </div>

              {!day.blocked && (
                <div className="mt-0.5">
                  <span className={`text-[11px] font-semibold tabular-nums ${occ.text}`}>
                    {day.free_rooms}
                  </span>
                  <span className="text-[9px] text-[var(--color-text-muted)]">
                    /{day.total_rooms}
                  </span>
                </div>
              )}

              <div className="flex flex-wrap gap-0.5 mt-1">
                {day.markers.includes("offer_sent") && (
                  <span className="w-3.5 h-3.5 rounded-full bg-[var(--color-accent)] flex items-center justify-center" title={labels.offers}>
                    <Send className="w-2 h-2 text-white" />
                  </span>
                )}
                {day.events.length > 0 && (
                  <span className="w-3.5 h-3.5 rounded-full bg-purple-500 flex items-center justify-center" title={day.events.map((e) => e.name).join(", ")}>
                    <Star className="w-2 h-2 text-white" />
                  </span>
                )}
                {day.markers.includes("school_holiday") && (
                  <span className="w-3.5 h-3.5 rounded-full bg-amber-500 flex items-center justify-center" title={labels.schoolHoliday}>
                    <GraduationCap className="w-2 h-2 text-white" />
                  </span>
                )}
                {day.markers.includes("ponte") && (
                  <span className="text-[8px] font-bold text-amber-600 leading-none" title={labels.ponte}>P</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-4 mt-3 text-[10px] text-[var(--color-text-muted)]">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-red-200" /> {labels.high} occ.</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-amber-200" /> {labels.medium}</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-emerald-200" /> {labels.low}</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-blue-200" /> {labels.veryLow}</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-gray-200" /> {labels.blocked}</span>
        <span className="flex items-center gap-1 ml-2">
          <span className="w-3 h-3 rounded-full bg-[var(--color-accent)] flex items-center justify-center"><Send className="w-1.5 h-1.5 text-white" /></span> {labels.offers}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-purple-500 flex items-center justify-center"><Star className="w-1.5 h-1.5 text-white" /></span> {labels.events}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-amber-500 flex items-center justify-center"><GraduationCap className="w-1.5 h-1.5 text-white" /></span> {labels.schoolHoliday}
        </span>
      </div>
    </div>
  );
}

/* ---------- RulesPanel ---------- */

function RulesPanel({ locale }: { locale: "en" | "it" }) {
  const labels = t(locale).calendar;
  const [rules, setRules] = useState<Rules | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/rules")
      .then((r) => r.json())
      .then((data) => {
        if (!data.error) setRules(data);
        else setError(data.error);
      })
      .catch(() => setError("Failed to load rules"));
  }, []);

  const updateField = <K extends keyof Rules>(key: K, value: Rules[K]) => {
    if (!rules) return;
    setRules({ ...rules, [key]: value });
    setSaved(false);
  };

  const handleSave = async () => {
    if (!rules) return;
    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/rules", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          public_rate_eur: rules.public_rate_eur,
          lowest_price_eur: rules.lowest_price_eur,
          max_discount_pct: rules.max_discount_pct,
          max_rooms_per_offer: rules.max_rooms_per_offer,
          blackout_dates: rules.blackout_dates,
          booking_window_days: rules.booking_window_days,
          contact_cooldown_days: rules.contact_cooldown_days,
          auto_send: rules.auto_send,
          auto_waves: rules.auto_waves,
        }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } else {
        const data = await res.json();
        setError(data.error || "Save failed");
      }
    } catch {
      setError("Save failed");
    }
    setSaving(false);
  };

  if (!rules) {
    return (
      <Card>
        <CardContent className="p-5">
          {error ? (
            <p className="text-xs text-red-600">{error}</p>
          ) : (
            <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading rules...
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <h2 className="text-sm font-semibold text-[var(--color-text)] font-[family-name:var(--font-space-grotesk)]">
          {labels.rules}
        </h2>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.publicRate}</label>
            <div className="flex items-center gap-1">
              <span className="text-xs">€</span>
              <Input
                type="number"
                value={rules.public_rate_eur}
                onChange={(e) => updateField("public_rate_eur", Number(e.target.value))}
                className="h-8 text-xs w-24"
              />
              <span className="text-xs text-[var(--color-text-muted)]">{labels.perNight}</span>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.lowestPrice}</label>
            <div className="flex items-center gap-1">
              <span className="text-xs">€</span>
              <Input
                type="number"
                value={rules.lowest_price_eur}
                onChange={(e) => updateField("lowest_price_eur", Number(e.target.value))}
                className="h-8 text-xs w-24"
              />
              <span className="text-xs text-[var(--color-text-muted)]">{labels.perNight}</span>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.maxDiscount}</label>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={rules.max_discount_pct}
                onChange={(e) => updateField("max_discount_pct", Number(e.target.value))}
                className="h-8 text-xs w-20"
              />
              <span className="text-xs text-[var(--color-text-muted)]">%</span>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.maxRooms}</label>
            <Input
              type="number"
              value={rules.max_rooms_per_offer}
              onChange={(e) => updateField("max_rooms_per_offer", Number(e.target.value))}
              className="h-8 text-xs w-20"
            />
          </div>
        </div>

        <div className="border-t border-[var(--color-border)] pt-3 space-y-3">
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.bookingWindow}</label>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={rules.booking_window_days[0]}
                onChange={(e) => updateField("booking_window_days", [Number(e.target.value), rules.booking_window_days[1]])}
                className="h-8 text-xs w-16"
              />
              <span className="text-xs text-[var(--color-text-muted)]">–</span>
              <Input
                type="number"
                value={rules.booking_window_days[1]}
                onChange={(e) => updateField("booking_window_days", [rules.booking_window_days[0], Number(e.target.value)])}
                className="h-8 text-xs w-16"
              />
              <span className="text-xs text-[var(--color-text-muted)]">{labels.days}</span>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.offerLifetime}</label>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={rules.offer_lifetime_hours}
                onChange={(e) => updateField("offer_lifetime_hours", Number(e.target.value))}
                className="h-8 text-xs w-20"
              />
              <span className="text-xs text-[var(--color-text-muted)]">{labels.hours}</span>
            </div>
          </div>
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.contactCooldown}</label>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={rules.contact_cooldown_days}
                onChange={(e) => updateField("contact_cooldown_days", Number(e.target.value))}
                className="h-8 text-xs w-20"
              />
              <span className="text-xs text-[var(--color-text-muted)]">{labels.days}</span>
            </div>
          </div>
        </div>

        <div className="border-t border-[var(--color-border)] pt-3 space-y-3">
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">{labels.blackoutDates}</label>
            <div className="flex flex-wrap gap-1.5">
              {rules.blackout_dates.map((d) => (
                <Badge key={d} variant="outline" className="text-[10px] gap-1">
                  {d}
                  <button
                    onClick={() => updateField("blackout_dates", rules.blackout_dates.filter((x) => x !== d))}
                    className="text-red-400 hover:text-red-600"
                  >
                    ×
                  </button>
                </Badge>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-xs text-[var(--color-text-muted)]">{labels.autoSend}</label>
            <button
              onClick={() => updateField("auto_send", !rules.auto_send)}
              className={`w-10 h-5 rounded-full transition-colors ${rules.auto_send ? "bg-[var(--color-accent)]" : "bg-gray-300"} relative`}
            >
              <span className={`block w-4 h-4 rounded-full bg-white shadow absolute top-0.5 transition-transform ${rules.auto_send ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
          <div className="flex items-center justify-between">
            <label className="text-xs text-[var(--color-text-muted)]">{labels.autoWaves}</label>
            <button
              onClick={() => updateField("auto_waves", !rules.auto_waves)}
              className={`w-10 h-5 rounded-full transition-colors ${rules.auto_waves ? "bg-[var(--color-accent)]" : "bg-gray-300"} relative`}
            >
              <span className={`block w-4 h-4 rounded-full bg-white shadow absolute top-0.5 transition-transform ${rules.auto_waves ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <Button size="sm" onClick={handleSave} disabled={saving || saved}>
          {saving ? (
            <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
          ) : saved ? (
            <Check className="w-3.5 h-3.5 mr-1 text-emerald-500" />
          ) : null}
          {saved ? labels.saved : labels.save}
        </Button>
      </CardContent>
    </Card>
  );
}

/* ---------- CalendarPage ---------- */

export default function CalendarPage() {
  const { locale } = useLocale();
  const labels = t(locale).calendar;
  const monthNames = locale === "it" ? MONTH_NAMES_IT : MONTH_NAMES_EN;

  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(11);
  const [days, setDays] = useState<CalDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const now = new Date();
    setYear(now.getFullYear());
    setMonth(now.getMonth() + 1);
    setReady(true);
  }, []);

  const fetchCalendar = useCallback(async (y: number, m: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/calendar?year=${y}&month=${m}`);
      if (res.ok) {
        const data = await res.json();
        setDays(data.days ?? []);
      }
    } catch { /* best effort */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (ready) fetchCalendar(year, month);
  }, [year, month, ready, fetchCalendar]);

  const prevMonth = () => {
    if (month === 1) { setYear(year - 1); setMonth(12); }
    else setMonth(month - 1);
  };
  const nextMonth = () => {
    if (month === 12) { setYear(year + 1); setMonth(1); }
    else setMonth(month + 1);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
        {labels.title}
      </h1>

      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-4">
            <Button variant="ghost" size="sm" onClick={prevMonth}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <h2 className="text-sm font-semibold font-[family-name:var(--font-space-grotesk)]">
              {monthNames[month - 1]} {year}
            </h2>
            <Button variant="ghost" size="sm" onClick={nextMonth}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-muted)]" />
            </div>
          ) : (
            <CalendarGrid days={days} year={year} month={month} locale={locale} />
          )}
        </CardContent>
      </Card>

      <RulesPanel locale={locale} />

      <p className="text-[10px] text-[var(--color-text-muted)] text-center">
        {locale === "it" ? "Dati demo simulati — le camere libere si basano su un modello di occupazione" : "Simulated demo data — free rooms are based on an occupancy model"}
      </p>
    </div>
  );
}
