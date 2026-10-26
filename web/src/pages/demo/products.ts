import type { Order } from "../../api";

/** Product photography for the demo shop, matched on the order's first line item. */
const PRODUCT_IMAGES: [RegExp, string][] = [
  [/yirgacheffe|beans|coffee 12oz/i, "/shop/beans.webp"],
  [/sampler/i, "/shop/sampler.webp"],
  [/grinder/i, "/shop/grinder.webp"],
  [/filter/i, "/shop/filters.webp"],
  [/mug/i, "/shop/mug.webp"],
  [/kettle/i, "/shop/kettle.webp"],
];

export function productImage(order: Order): string | undefined {
  const text = `${order.items?.join(" ") ?? ""} ${order.label ?? ""}`;
  return PRODUCT_IMAGES.find(([pattern]) => pattern.test(text))?.[1];
}

/** "2 x Ethiopia Yirgacheffe 12oz @ 17.00" -> "Ethiopia Yirgacheffe 12oz" */
export function productName(order: Order): string {
  const first = order.items?.[0];
  if (!first) return order.label || order.order_id;
  return first.replace(/^\d+\s*x\s*/i, "").replace(/\s*@\s*[\d.]+$/, "");
}
