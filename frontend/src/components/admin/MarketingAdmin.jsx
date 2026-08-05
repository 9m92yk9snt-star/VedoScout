// MarketingAdmin — Carousel Studio + Guide funnel + Discount codes.
import React from "react";
import { CarouselStudioAdmin } from "@/components/admin/CarouselStudioAdmin";
import { GuideFunnelAdmin } from "@/components/admin/GuideFunnelAdmin";
import { DiscountCodesAdmin } from "@/components/admin/DiscountCodesAdmin";

export const MarketingAdmin = () => (
  <div className="space-y-8" data-testid="marketing-admin">
    <CarouselStudioAdmin />
    <GuideFunnelAdmin />
    <DiscountCodesAdmin />
  </div>
);
