import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";

export const instant = false;

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";
const HOTEL_ID = "bristol-stresa";

type Period = {
  has_offer?: boolean;
  suggestion?: { check_in: string };
};

type Wave = { status: string };
type InventoryOffer = {
  status: string;
  waves: Wave[];
};

async function shouldOpenOffers(): Promise<boolean> {
  try {
    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;
    const signal = AbortSignal.timeout(8000);

    const [timelineRes, inventoryRes] = await Promise.all([
      fetch(
        `${ENGINE_URL}/api/hotel/offers-timeline?hotel_id=${HOTEL_ID}`,
        { cache: "no-store", headers, signal },
      ),
      fetch(
        `${ENGINE_URL}/api/hotel/inventory?hotel_id=${HOTEL_ID}`,
        { cache: "no-store", headers, signal },
      ),
    ]);

    if (!timelineRes.ok) return false;
    const timelineData = await timelineRes.json();
    const periods: Period[] = timelineData.periods ?? [];

    const offeredCheckIns = new Set(
      periods
        .filter((p) => p.has_offer && p.suggestion?.check_in)
        .map((p) => p.suggestion!.check_in),
    );

    if (offeredCheckIns.size > 0) {
      const actions = await prisma.offerAction.findMany({
        where: { hotelId: HOTEL_ID, checkIn: { in: [...offeredCheckIns] } },
        select: { checkIn: true },
      });
      const actedOn = new Set(actions.map((a) => a.checkIn));
      const unsent = [...offeredCheckIns].some((ci) => !actedOn.has(ci));
      if (unsent) return true;
    }

    if (inventoryRes.ok) {
      const invData = await inventoryRes.json();
      const offers: InventoryOffer[] = invData.offers ?? [];
      const hasPendingWave = offers.some(
        (o) =>
          o.status === "active" &&
          o.waves.some((w) => w.status === "pending"),
      );
      if (hasPendingWave) return true;
    }

    return false;
  } catch {
    return false;
  }
}

export default async function Home() {
  const goToOffers = await shouldOpenOffers();
  redirect(goToOffers ? "/offers" : "/results");
}
