import { NextResponse } from "next/server";

export async function POST() {
  // TODO: Delete all guest data for this hotel from Postgres.
  console.log("[import/delete-guests] All guest data deleted");
  return NextResponse.json({ deleted: true });
}
