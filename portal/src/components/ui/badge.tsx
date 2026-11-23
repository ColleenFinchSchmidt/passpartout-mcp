import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-[var(--radius-badge)] px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-[var(--color-accent-light)] text-[var(--color-accent)]",
        amber: "bg-[var(--color-amber-light)] text-[var(--color-amber)]",
        outline: "border border-[var(--color-border)] text-[var(--color-text-muted)]",
        weather: "bg-blue-50 text-blue-700",
        event: "bg-purple-50 text-purple-700",
        occupancy: "bg-orange-50 text-orange-700",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
