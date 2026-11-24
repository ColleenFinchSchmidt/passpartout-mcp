import { PrismaClient } from "../src/generated/prisma/client";

const prisma = new PrismaClient();

async function main() {
  const existing = await prisma.hotel.findUnique({
    where: { id: "bristol-stresa" },
  });

  if (existing) {
    console.log(`Hotel "${existing.name}" already exists — skipping seed.`);
    return;
  }

  const hotel = await prisma.hotel.create({
    data: {
      id: "bristol-stresa",
      name: "Grand Hotel Bristol",
      town: "Stresa",
      region: "Verbano-Cusio-Ossola, Piedmont, Italy",
      lat: 45.8833,
      lon: 8.5333,
      totalRooms: 85,
      publicRateEur: 280,
      lowestPriceEur: 210,
      maxDiscountPct: 25,
      blackoutDates: [
        "2026-12-24",
        "2026-12-25",
        "2026-12-26",
        "2026-12-31",
        "2027-01-01",
      ],
    },
  });

  console.log(`Seeded hotel "${hotel.name}" with rules (no offers — engine provides those).`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
