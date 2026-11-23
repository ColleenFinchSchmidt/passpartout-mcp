import { PrismaClient } from "../src/generated/prisma/client";

const prisma = new PrismaClient();

async function main() {
  const hotel = await prisma.hotel.upsert({
    where: { id: "bristol-stresa" },
    update: {},
    create: {
      id: "bristol-stresa",
      name: "Grand Hotel Bristol",
      town: "Stresa",
      region: "Piedmont, Italy",
      lat: 45.8833,
      lon: 8.5333,
      totalRooms: 85,
      publicRateEur: 280,
      lowestPriceEur: 195,
      maxDiscountPct: 30,
    },
  });

  const today = new Date();
  const fri = new Date(today);
  fri.setDate(today.getDate() + ((5 - today.getDay() + 7) % 7 || 7));
  const sat = new Date(fri);
  sat.setDate(fri.getDate() + 1);
  const sun = new Date(fri);
  sun.setDate(fri.getDate() + 2);
  const mon = new Date(fri);
  mon.setDate(fri.getDate() + 3);

  const wed = new Date(today);
  wed.setDate(today.getDate() + ((3 - today.getDay() + 7) % 7 || 7));
  const thu = new Date(wed);
  thu.setDate(wed.getDate() + 1);
  const wedEnd = new Date(wed);
  wedEnd.setDate(wed.getDate() + 2);

  const offers = [
    {
      id: "offer-rain-weekend",
      hotelId: hotel.id,
      status: "pending",
      roomType: "Lake View Suite",
      checkIn: fri,
      checkOut: sun,
      nights: 2,
      roomsAvailable: 3,
      publicPriceEur: 320,
      privatePriceEur: 229,
      discountPct: 28,
      triggerType: "weather",
      triggerLabel: "Rain forecast in Milan",
      triggerDetail:
        "Heavy rain expected in Milan this weekend — lake-side escape appeal peaks.",
      targetGuests: "Milan weekend travellers",
    },
    {
      id: "offer-event-stresa",
      hotelId: hotel.id,
      status: "pending",
      roomType: "Superior Double",
      checkIn: fri,
      checkOut: mon,
      nights: 3,
      roomsAvailable: 5,
      publicPriceEur: 280,
      privatePriceEur: 210,
      discountPct: 25,
      triggerType: "event",
      triggerLabel: "Stresa Music Festival",
      triggerDetail:
        "Annual music festival draws visitors — fill remaining rooms at a private rate.",
      targetGuests: "Culture & music lovers",
    },
    {
      id: "offer-midweek-empty",
      hotelId: hotel.id,
      status: "pending",
      roomType: "Classic Room",
      checkIn: wed,
      checkOut: wedEnd,
      nights: 2,
      roomsAvailable: 12,
      publicPriceEur: 240,
      privatePriceEur: 169,
      discountPct: 30,
      triggerType: "occupancy",
      triggerLabel: "Low midweek occupancy",
      triggerDetail:
        "Only 42% occupancy forecast mid-week — a private offer can fill empty rooms.",
      targetGuests: "Flexible remote workers",
    },
  ];

  for (const offer of offers) {
    await prisma.offer.upsert({
      where: { id: offer.id },
      update: {},
      create: offer,
    });
  }

  console.log(`Seeded hotel "${hotel.name}" with ${offers.length} offers`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
