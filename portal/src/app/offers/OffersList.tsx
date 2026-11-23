"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";
import {
  CloudRain,
  Calendar,
  TrendingDown,
  ChevronRight,
} from "lucide-react";

type Offer = {
  id: string;
  hotelName: string;
  status: string;
  roomType: string;
  checkIn: string;
  checkOut: string;
  nights: number;
  roomsAvailable: number;
  publicPriceEur: number;
  privatePriceEur: number;
  discountPct: number;
  triggerType: string;
  triggerLabel: string;
  triggerDetail: string | null;
  targetGuests: string | null;
};

const triggerIcon: Record<string, React.ReactNode> = {
  weather: <CloudRain className="w-3.5 h-3.5" />,
  event: <Calendar className="w-3.5 h-3.5" />,
  occupancy: <TrendingDown className="w-3.5 h-3.5" />,
};

const triggerVariant: Record<
  string,
  "weather" | "event" | "occupancy"
> = {
  weather: "weather",
  event: "event",
  occupancy: "occupancy",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

export default function OffersList({ offers }: { offers: Offer[] }) {
  const { locale } = useLocale();
  const labels = t(locale).offers;

  if (offers.length === 0) {
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
          {offers.length} {offers.length === 1 ? "offer" : "offers"}
        </span>
      </div>

      <div className="space-y-3">
        {offers.map((offer) => (
          <Card key={offer.id} className="hover:shadow-md transition-shadow">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                {/* Left: trigger + room info */}
                <div className="flex-1 min-w-0 space-y-3">
                  {/* Trigger badge + label */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={triggerVariant[offer.triggerType] ?? "default"}>
                      <span className="flex items-center gap-1">
                        {triggerIcon[offer.triggerType]}
                        {offer.triggerLabel}
                      </span>
                    </Badge>
                    {offer.triggerDetail && (
                      <span className="text-xs text-[var(--color-text-muted)]">
                        {offer.triggerDetail}
                      </span>
                    )}
                  </div>

                  {/* Room type + dates */}
                  <div>
                    <h3 className="font-medium text-[var(--color-text)]">
                      {offer.roomType}
                    </h3>
                    <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
                      {formatDate(offer.checkIn)} – {formatDate(offer.checkOut)}
                      <span className="mx-1.5">·</span>
                      {offer.nights} {labels.nights}
                      <span className="mx-1.5">·</span>
                      {offer.roomsAvailable} {labels.rooms}
                    </p>
                  </div>

                  {/* Target guests */}
                  {offer.targetGuests && (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {labels.target}: {offer.targetGuests}
                    </p>
                  )}
                </div>

                {/* Right: pricing + actions */}
                <div className="text-right shrink-0 space-y-3">
                  {/* Prices */}
                  <div>
                    <div className="text-sm text-[var(--color-text-muted)]">
                      <span className="line-through">
                        €{offer.publicPriceEur}
                      </span>
                      <span className="ml-1">{labels.publicPrice}</span>
                    </div>
                    <div className="flex items-baseline justify-end gap-1.5 mt-0.5">
                      <span className="text-xl font-semibold text-[var(--color-text)]">
                        €{offer.privatePriceEur}
                      </span>
                      <span className="text-sm text-[var(--color-text-muted)]">
                        {labels.perNight}
                      </span>
                    </div>
                    <Badge variant="default" className="mt-1">
                      -{offer.discountPct}%
                    </Badge>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 justify-end">
                    <Button variant="ghost" size="sm">
                      {labels.skip}
                    </Button>
                    <Button variant="outline" size="sm">
                      {labels.edit}
                    </Button>
                    <Button size="sm">
                      {labels.approve}
                      <ChevronRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
