import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export const instant = false;

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

type HotelData = {
  id: string;
  name: string;
  town: string;
  amenities?: string[];
  segments_wanted?: string[];
  segments_excluded?: string[];
  experiences?: string[];
  rooms: number;
  public_rate_eur: number;
  lowest_price_eur: number;
  max_discount_pct: number;
};

type SegmentInfo = {
  label: string;
  when: string;
  appeals: string;
  channels: string[];
};

type SettingsData = {
  segments?: Record<string, SegmentInfo>;
};

async function fetchHotelAndSettings(): Promise<{
  hotel: HotelData | null;
  settings: SettingsData | null;
}> {
  try {
    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const [hRes, sRes] = await Promise.all([
      fetch(`${ENGINE_URL}/api/hotel/suggest?hotel_id=bristol-stresa`, {
        cache: "no-store",
        headers,
      }),
      fetch(`${ENGINE_URL}/api/hotel/settings`, {
        cache: "no-store",
        headers,
      }).catch(() => null),
    ]);

    let hotel: HotelData | null = null;
    if (hRes.ok) {
      const data = await hRes.json();
      hotel = data._hotel_profile ?? null;
    }

    let settings: SettingsData | null = null;
    if (sRes && sRes.ok) {
      settings = await sRes.json();
    }

    return { hotel, settings };
  } catch {
    return { hotel: null, settings: null };
  }
}

function formatLabel(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default async function SetupPage() {
  const { hotel, settings } = await fetchHotelAndSettings();
  const allSegments = settings?.segments ?? {};

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
        Hotel set-up
      </h1>

      {!hotel ? (
        <Card>
          <CardContent className="py-8">
            <p className="text-sm text-[var(--color-text-muted)]">
              Hotel profile will appear here once the engine is connected.
              The setup page reads amenities, segments, and experiences from
              the hotel configuration.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-5 space-y-4">
              <h2 className="text-sm font-semibold text-[var(--color-text)]">
                Amenities
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                What your hotel offers. These determine how well you fit each
                guest segment.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(hotel.amenities ?? []).map((a) => (
                  <Badge key={a} variant="outline">
                    {formatLabel(a)}
                  </Badge>
                ))}
                {(!hotel.amenities || hotel.amenities.length === 0) && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    No amenities configured
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 space-y-4">
              <h2 className="text-sm font-semibold text-[var(--color-text)]">
                Target segments
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                Which guest segments you want to reach. The engine will
                prioritise these when scoring moments.
              </p>

              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-[var(--color-text-muted)] mb-1.5">
                    Wanted
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(hotel.segments_wanted ?? []).map((s) => (
                      <Badge key={s} variant="segment">
                        {allSegments[s]?.label ?? formatLabel(s)}
                      </Badge>
                    ))}
                    {(!hotel.segments_wanted ||
                      hotel.segments_wanted.length === 0) && (
                      <span className="text-xs text-[var(--color-text-muted)]">
                        All segments
                      </span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs font-medium text-[var(--color-text-muted)] mb-1.5">
                    Excluded
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(hotel.segments_excluded ?? []).length > 0 ? (
                      (hotel.segments_excluded ?? []).map((s) => (
                        <Badge key={s} variant="outline" className="text-red-600 border-red-200">
                          {allSegments[s]?.label ?? formatLabel(s)}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-xs text-[var(--color-text-muted)]">
                        None excluded
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {Object.keys(allSegments).length > 0 && (
                <div className="pt-2 border-t border-[var(--color-border)]">
                  <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">
                    All available segments
                  </p>
                  <div className="space-y-2">
                    {Object.entries(allSegments).map(([key, info]) => (
                      <div key={key} className="text-xs">
                        <span className="font-medium text-[var(--color-text)]">
                          {info.label}
                        </span>
                        <span className="text-[var(--color-text-muted)]">
                          {" "}— {info.appeals}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 space-y-4">
              <h2 className="text-sm font-semibold text-[var(--color-text)]">
                Experiences
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                What you can include in packages. The engine matches these to
                each segment&apos;s preferences.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(hotel.experiences ?? []).map((e) => (
                  <Badge key={e} variant="default">
                    {formatLabel(e)}
                  </Badge>
                ))}
                {(!hotel.experiences || hotel.experiences.length === 0) && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    No experiences configured
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 space-y-4">
              <h2 className="text-sm font-semibold text-[var(--color-text)]">
                Pricing guardrails
              </h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Public rate
                  </p>
                  <p className="font-medium text-[var(--color-text)]">
                    &euro;{hotel.public_rate_eur}/night
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Floor price
                  </p>
                  <p className="font-medium text-[var(--color-text)]">
                    &euro;{hotel.lowest_price_eur}/night
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Max discount
                  </p>
                  <p className="font-medium text-[var(--color-text)]">
                    {hotel.max_discount_pct}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Total rooms
                  </p>
                  <p className="font-medium text-[var(--color-text)]">
                    {hotel.rooms}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
